from __future__ import annotations

import json
import logging

from flask import request
from flask_sock import Sock
from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    MODEL,
    VOICE,
    AUDIO_FORMAT,
)
from common.constants import PROMPT_STREAM
from common.events import PromptEvent, serialize_event
from common.redis_streams import RedisStreamClient
from models.message import Message
from services.session_service import SessionService
from services.redis_consumer import ConnectionRegistry
from services.tts import WsClosed, ws_send

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OpenAI handler (unchanged -- stays in-process)
# ---------------------------------------------------------------------------

def _handle_openai(
    ws,
    user_text: str,
    conversation_history: list[dict],
    openai_client: OpenAI,
) -> str:
    conversation_history.append({"role": "user", "content": user_text})

    response = openai_client.chat.completions.create(
        model=MODEL,
        modalities=["text", "audio"],
        audio={"voice": VOICE, "format": AUDIO_FORMAT},
        messages=conversation_history,
        stream=True,
    )

    audio_id = None
    full_transcript = ""

    try:
        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if hasattr(delta, "audio") and delta.audio:
                audio_data = delta.audio
                payload: dict = {"type": "audio_delta"}

                transcript_piece = audio_data.get("transcript")
                if transcript_piece:
                    payload["transcript"] = transcript_piece
                    full_transcript += transcript_piece

                data_piece = audio_data.get("data")
                if data_piece:
                    payload["data"] = data_piece

                audio_resp_id = audio_data.get("id")
                if audio_resp_id:
                    audio_id = audio_resp_id

                ws_send(ws, payload)
    except WsClosed:
        logger.info("WebSocket closed during OpenAI streaming")
        return full_transcript

    try:
        ws_send(ws, {"type": "done"})
    except WsClosed:
        pass

    if audio_id:
        conversation_history.append({"role": "assistant", "audio": {"id": audio_id}})
    else:
        conversation_history.append(
            {"role": "assistant", "content": full_transcript}
        )

    return full_transcript


# ---------------------------------------------------------------------------
# WebSocket route
# ---------------------------------------------------------------------------

def register_ws_routes(
    sock: Sock,
    session_service: SessionService,
    redis_client: RedisStreamClient,
    registry: ConnectionRegistry,
) -> None:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    @sock.route("/ws")
    def websocket_handler(ws):
        session_id = request.args.get("session_id")
        if not session_id:
            ws_send(ws, {"type": "error", "message": "session_id is required"})
            return

        session = session_service.get_session(session_id)
        if not session:
            ws_send(ws, {"type": "error", "message": "Session not found"})
            return

        existing_messages = session_service.get_messages(session_id)

        conversation_history: list[dict] = []
        if session.mode == "openai":
            for msg in existing_messages:
                if msg.role in ("user", "assistant"):
                    conversation_history.append(
                        {"role": msg.role, "content": msg.text}
                    )

        claude_session_id = session.claude_session_id
        current_sequence = session_service.get_next_sequence(session_id)

        if session.mode == "claude_code":
            registry.register(session_id, ws)

        logger.info(
            "WebSocket connected for session %s (mode=%s)", session_id, session.mode
        )

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    logger.info(
                        "[WS_IN] session=%s received None (client disconnected)",
                        session_id,
                    )
                    break

                msg = json.loads(raw)
                logger.info(
                    "[WS_IN] session=%s type=%s payload=%r",
                    session_id,
                    msg.get("type"),
                    {k: (v[:200] if isinstance(v, str) else v) for k, v in msg.items()},
                )

                if msg.get("type") != "message":
                    logger.info(
                        "[WS_IN] session=%s ignoring non-message type=%s",
                        session_id,
                        msg.get("type"),
                    )
                    continue

                user_text = msg.get("text", "").strip()
                if not user_text:
                    logger.info(
                        "[WS_IN] session=%s ignoring empty message text",
                        session_id,
                    )
                    continue

                try:
                    if session.mode == "claude_code":
                        user_msg = Message(
                            session_id=session_id,
                            role="user",
                            text=user_text,
                            sequence=current_sequence,
                        )
                        current_sequence += 1
                        session_service.save_message(user_msg)

                        prompt_event = PromptEvent(
                            type="prompt",
                            session_id=session_id,
                            text=user_text,
                            claude_session_id=claude_session_id,
                        )
                        redis_client.publish(
                            PROMPT_STREAM, serialize_event(prompt_event)
                        )
                        logger.info(
                            "[WS_OUT] session=%s published prompt to Redis — text=%r claude_sid=%s",
                            session_id,
                            user_text[:200],
                            claude_session_id,
                        )
                        session_service.update_status(session_id, "running")

                    else:
                        turn_messages: list[Message] = []

                        turn_messages.append(
                            Message(
                                session_id=session_id,
                                role="user",
                                text=user_text,
                                sequence=current_sequence,
                            )
                        )
                        current_sequence += 1

                        logger.info(
                            "[WS_OUT] session=%s sending to OpenAI — text=%r",
                            session_id,
                            user_text[:200],
                        )
                        full_transcript = _handle_openai(
                            ws, user_text, conversation_history, openai_client
                        )
                        logger.info(
                            "[WS_OUT] session=%s OpenAI response complete — transcript=%r",
                            session_id,
                            full_transcript[:200] if full_transcript else "",
                        )

                        turn_messages.append(
                            Message(
                                session_id=session_id,
                                role="assistant",
                                text=full_transcript,
                                sequence=current_sequence,
                            )
                        )
                        current_sequence += 1

                        session_service.save_messages(turn_messages)

                except WsClosed:
                    logger.info(
                        "WebSocket closed mid-turn for session %s", session_id
                    )
                    break

                except Exception as e:
                    logger.exception("Streaming error (%s)", session.mode)
                    try:
                        ws_send(ws, {"type": "error", "message": str(e)})
                    except WsClosed:
                        break

        except Exception:
            logger.info("WebSocket disconnected for session %s", session_id)

        finally:
            if session.mode == "claude_code":
                registry.unregister(session_id)
