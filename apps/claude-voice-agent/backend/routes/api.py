from __future__ import annotations

import logging
import threading

from flask import Flask, request, jsonify
from openai import OpenAI

from config import MODEL, VOICE, AUDIO_FORMAT
from common.constants import PROMPT_STREAM
from common.events import PromptEvent, serialize_event
from common.redis_streams import RedisStreamClient
from models.message import Message
from services.session_service import SessionService
from services.redis_consumer import ConnectionRegistry
from services.tts import WsClosed, ws_send

logger = logging.getLogger(__name__)


def _handle_openai_background(
    session_id: str,
    session_service: SessionService,
    openai_client: OpenAI,
    registry: ConnectionRegistry,
) -> None:
    """Run OpenAI streaming in a background thread, pushing audio to the WS."""
    try:
        session = session_service.get_session(session_id)
        voice_enabled = session.voice_mode if session else False

        existing_messages = session_service.get_messages(session_id)
        conversation_history: list[dict] = []
        for msg in existing_messages:
            if msg.role in ("user", "assistant"):
                conversation_history.append(
                    {"role": msg.role, "content": msg.text}
                )

        create_kwargs: dict = dict(
            model=MODEL,
            messages=conversation_history,
            stream=True,
        )
        if voice_enabled:
            create_kwargs["modalities"] = ["text", "audio"]
            create_kwargs["audio"] = {"voice": VOICE, "format": AUDIO_FORMAT}
        else:
            create_kwargs["modalities"] = ["text"]

        response = openai_client.chat.completions.create(**create_kwargs)

        full_transcript = ""
        ws = registry.get(session_id)

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if voice_enabled and hasattr(delta, "audio") and delta.audio:
                audio_data = delta.audio
                payload: dict = {"type": "audio_delta"}

                transcript_piece = audio_data.get("transcript")
                if transcript_piece:
                    payload["transcript"] = transcript_piece
                    full_transcript += transcript_piece

                data_piece = audio_data.get("data")
                if data_piece:
                    payload["data"] = data_piece

                if ws:
                    try:
                        ws_send(ws, payload)
                    except WsClosed:
                        logger.info("WS closed during OpenAI streaming for session %s", session_id)
                        ws = None

            elif not voice_enabled and hasattr(delta, "content") and delta.content:
                full_transcript += delta.content
                if ws:
                    try:
                        ws_send(ws, {"type": "text_delta", "text": delta.content})
                    except WsClosed:
                        logger.info("WS closed during OpenAI streaming for session %s", session_id)
                        ws = None

        seq = session_service.get_next_sequence(session_id)
        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            text=full_transcript,
            sequence=seq,
        )
        session_service.save_message(assistant_msg)

        if ws:
            try:
                ws_send(ws, {"type": "done"})
            except WsClosed:
                pass

    except Exception:
        logger.exception("OpenAI background error for session %s", session_id)
        ws = registry.get(session_id)
        if ws:
            try:
                ws_send(ws, {"type": "error", "message": "OpenAI streaming failed"})
            except WsClosed:
                pass
        session_service.update_status(session_id, "error")
        return

    session_service.update_status(session_id, "idle")


def register_api_routes(
    app: Flask,
    session_service: SessionService,
    redis_client: RedisStreamClient,
    registry: ConnectionRegistry,
    openai_client: OpenAI,
) -> None:
    @app.route("/health")
    def health():
        return {"status": "ok", "num_connections": len(registry._connections), "connections": list(registry._connections.keys())}

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        data = request.get_json()

        if not data or "title" not in data or "mode" not in data:
            return jsonify({"error": "title and mode are required"}), 400

        if data["mode"] not in ("openai", "claude_code"):
            return jsonify({"error": "mode must be 'openai' or 'claude_code'"}), 400

        session = session_service.create_session(data["title"], data["mode"])
        return jsonify(session.to_dict()), 201

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        sessions = session_service.list_sessions()
        return jsonify([s.to_dict() for s in sessions])

    @app.route("/api/sessions/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        result = session_service.get_session_with_messages(session_id)

        if result is None:
            return jsonify({"error": "Not found"}), 404

        return jsonify(result)

    @app.route("/api/sessions/<session_id>", methods=["PATCH"])
    def update_session(session_id: str):
        data = request.get_json()

        if not data or ("title" not in data and "voice_mode" not in data):
            return jsonify({"error": "title or voice_mode is required"}), 400

        session = session_service.get_session(session_id)
        if session is None:
            return jsonify({"error": "Not found"}), 404

        if "title" in data:
            session = session_service.update_session_title(session_id, data["title"])

        if "voice_mode" in data:
            session = session_service.update_voice_mode(session_id, bool(data["voice_mode"]))

        return jsonify(session.to_dict())

    @app.route("/api/sessions/<session_id>", methods=["DELETE"])
    def delete_session(session_id: str):
        success = session_service.delete_session(session_id)

        if not success:
            return jsonify({"error": "Not found"}), 404

        return "", 204

    @app.route("/api/sessions/<session_id>/messages", methods=["POST"])
    def send_message(session_id: str):
        session = session_service.get_session(session_id)
        if not session:
            return jsonify({"error": "Not found"}), 404

        if session.status == "running":
            return jsonify({"error": "Session is already processing a prompt"}), 409

        data = request.get_json()
        text = (data or {}).get("text", "").strip()
        if not text:
            return jsonify({"error": "text is required"}), 400

        seq = session_service.get_next_sequence(session_id)
        user_msg = Message(
            session_id=session_id, role="user", text=text, sequence=seq
        )
        session_service.save_message(user_msg)
        session_service.update_status(session_id, "running")

        if session.mode == "claude_code":
            prompt_event = PromptEvent(
                type="prompt",
                session_id=session_id,
                text=text,
                claude_session_id=session.claude_session_id,
            )
            redis_client.publish(PROMPT_STREAM, serialize_event(prompt_event))
            logger.info(
                "[REST] session=%s published prompt to Redis — text=%r",
                session_id,
                text[:200],
            )
        else:
            threading.Thread(
                target=_handle_openai_background,
                args=(session_id, session_service, openai_client, registry),
                daemon=True,
            ).start()
            logger.info(
                "[REST] session=%s started OpenAI background thread — text=%r",
                session_id,
                text[:200],
            )

        return jsonify({
            "message_id": user_msg.id,
            "session": {**session.to_dict(), "status": "running"},
        }), 200
