from __future__ import annotations

import asyncio
import base64
import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor, Future

from flask import request
from flask_sock import Sock
from openai import OpenAI
from simple_websocket import ConnectionClosed

from claude_agent_sdk import (
    query as claude_query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)

from config import (
    OPENAI_API_KEY,
    MODEL,
    VOICE,
    AUDIO_FORMAT,
    TTS_MODEL,
    CLAUDE_CLI_PATH,
    CLAUDE_CWD,
)
from models.message import Message
from services.session_service import SessionService

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Sentinel raised when the WebSocket has closed so callers can react without
# letting a raw ConnectionClosed bubble into anyio's internals.
# ---------------------------------------------------------------------------

class _WsClosed(Exception):
    """The WebSocket connection was closed while we were streaming."""


def _send(ws, payload: dict) -> None:
    """Send a JSON payload; converts ConnectionClosed → _WsClosed."""
    try:
        ws.send(json.dumps(payload))
    except ConnectionClosed:
        raise _WsClosed()


# ---------------------------------------------------------------------------
# TTS helpers
# ---------------------------------------------------------------------------

_TTS_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tts")


def _tts_fetch(text: str, openai_client: OpenAI) -> bytes:
    """Fetch the full PCM audio for a sentence and return it as raw bytes."""
    response = openai_client.audio.speech.create(
        model=TTS_MODEL, voice=VOICE, input=text, response_format="pcm"
    )
    return response.read()


def _process_text_block(ws, text: str, openai_client: OpenAI) -> None:
    """Convert a text block to speech.

    All per-sentence TTS requests are dispatched concurrently via a shared
    thread-pool. Audio is then streamed to the client in sentence order so
    playback remains coherent, while later sentences are already being fetched
    in the background — reducing total latency from Σ(latencies) to
    roughly max(latencies).

    Raises _WsClosed if the connection drops mid-stream.
    """
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return

    # Dispatch all TTS requests in parallel before waiting on any result.
    futures: list[Future[bytes]] = [
        _TTS_EXECUTOR.submit(_tts_fetch, sentence, openai_client)
        for sentence in sentences
    ]

    # Stream audio in order — each future.result() blocks only until *that*
    # sentence is ready, by which time later sentences are already in-flight.
    for sentence, future in zip(sentences, futures):
        _send(ws, {"type": "audio_delta", "transcript": sentence + " "})
        audio_data = future.result()
        for i in range(0, len(audio_data), 4096):
            _send(
                ws,
                {
                    "type": "audio_delta",
                    "data": base64.b64encode(audio_data[i : i + 4096]).decode(),
                },
            )


# ---------------------------------------------------------------------------
# Claude async query
# ---------------------------------------------------------------------------

async def _run_claude_query(
    user_text: str,
    session_id: str | None,
    ws,
    openai_client: OpenAI,
) -> tuple[str | None, list[dict]]:
    """Run the Claude agent query, streaming results to *ws*.

    Never lets _WsClosed propagate out of a _send call into anyio internals.
    Instead it sets a flag and continues draining the generator so anyio can
    clean up its cancel scopes normally.
    """
    options = ClaudeAgentOptions(
        cli_path=CLAUDE_CLI_PATH,
        permission_mode="acceptEdits",
        cwd=CLAUDE_CWD,
    )
    if session_id:
        options.resume = session_id

    new_session_id = None
    turn_messages: list[dict] = []
    ws_closed = False  # once True we collect messages but stop sending

    async for message in claude_query(prompt=user_text, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    if not ws_closed:
                        try:
                            _process_text_block(ws, block.text, openai_client)
                        except _WsClosed:
                            ws_closed = True
                            logger.info("WebSocket closed during TTS streaming")
                    turn_messages.append({"role": "assistant", "text": block.text})

                elif isinstance(block, ToolUseBlock):
                    if not ws_closed:
                        try:
                            _send(
                                ws,
                                {
                                    "type": "tool_use",
                                    "tool": block.name,
                                    "input": block.input,
                                },
                            )
                        except _WsClosed:
                            ws_closed = True
                    turn_messages.append(
                        {
                            "role": "tool_use",
                            "text": json.dumps(block.input),
                            "tool_name": block.name,
                            "tool_input": json.dumps(block.input),
                        }
                    )

                elif isinstance(block, ToolResultBlock):
                    content = block.content
                    if isinstance(content, list):
                        content = "\n".join(
                            (
                                item.get("text", str(item))
                                if isinstance(item, dict)
                                else str(item)
                            )
                            for item in content
                        )
                    if not ws_closed:
                        try:
                            _send(
                                ws,
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.tool_use_id,
                                    "content": str(content) if content else "",
                                    "is_error": bool(block.is_error),
                                },
                            )
                        except _WsClosed:
                            ws_closed = True
                    turn_messages.append(
                        {
                            "role": "tool_result",
                            "text": str(content) if content else "",
                            "is_error": bool(block.is_error),
                        }
                    )

        elif isinstance(message, ResultMessage):
            new_session_id = message.session_id

    return new_session_id, turn_messages


# ---------------------------------------------------------------------------
# Thread executor for Claude queries
#
# Running asyncio.run() inside a gevent greenlet causes anyio's cancel scopes
# to be entered in one asyncio task and exited in another (because gevent
# monkey-patches asyncio).  The fix is to run the coroutine in a real OS
# thread that has its own fresh, unpatched event loop.
# ---------------------------------------------------------------------------

_CLAUDE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="claude")


def _run_claude_in_thread(
    user_text: str,
    session_id: str | None,
    ws,
    openai_client: OpenAI,
) -> tuple[str | None, list[dict]]:
    """Execute _run_claude_query in a dedicated OS thread with its own event loop.

    This avoids the gevent monkey-patching conflict that causes:
        RuntimeError: Attempted to exit cancel scope in a different task than
        it was entered in
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _run_claude_query(user_text, session_id, ws, openai_client)
        )
    finally:
        # Cancel any leftover tasks so the loop can close cleanly.
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# OpenAI handler
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

                _send(ws, payload)
    except _WsClosed:
        # Connection dropped mid-stream; return whatever we collected so it
        # can still be persisted to the database.
        logger.info("WebSocket closed during OpenAI streaming")
        return full_transcript

    try:
        _send(ws, {"type": "done"})
    except _WsClosed:
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

def register_ws_routes(sock: Sock, session_service: SessionService) -> None:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    @sock.route("/ws")
    def websocket_handler(ws):
        session_id = request.args.get("session_id")
        if not session_id:
            _send(ws, {"type": "error", "message": "session_id is required"})
            return

        session = session_service.get_session(session_id)
        if not session:
            _send(ws, {"type": "error", "message": "Session not found"})
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

        logger.info(
            "WebSocket connected for session %s (mode=%s)", session_id, session.mode
        )

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break

                msg = json.loads(raw)
                if msg.get("type") != "message":
                    continue

                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue

                turn_messages: list[Message] = []

                try:
                    turn_messages.append(
                        Message(
                            session_id=session_id,
                            role="user",
                            text=user_text,
                            sequence=current_sequence,
                        )
                    )
                    current_sequence += 1

                    if session.mode == "claude_code":
                        future = _CLAUDE_EXECUTOR.submit(
                            _run_claude_in_thread,
                            user_text,
                            claude_session_id,
                            ws,
                            openai_client,
                        )
                        new_claude_sid, claude_turn_msgs = future.result()

                        if new_claude_sid:
                            claude_session_id = new_claude_sid
                            session_service.update_claude_session_id(
                                session_id, claude_session_id
                            )

                        for tm in claude_turn_msgs:
                            turn_messages.append(
                                Message(
                                    session_id=session_id,
                                    role=tm["role"],
                                    text=tm["text"],
                                    tool_name=tm.get("tool_name"),
                                    tool_input=tm.get("tool_input"),
                                    is_error=tm.get("is_error", False),
                                    sequence=current_sequence,
                                )
                            )
                            current_sequence += 1

                        try:
                            _send(ws, {"type": "done"})
                        except _WsClosed:
                            pass

                    else:
                        full_transcript = _handle_openai(
                            ws, user_text, conversation_history, openai_client
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

                except _WsClosed:
                    # Client disconnected mid-turn; fall through to finally so
                    # whatever was collected is still saved.
                    logger.info(
                        "WebSocket closed mid-turn for session %s", session_id
                    )

                except Exception as e:
                    logger.exception("Streaming error (%s)", session.mode)
                    try:
                        _send(ws, {"type": "error", "message": str(e)})
                    except (_WsClosed, ConnectionClosed):
                        pass

                finally:
                    # Always persist whatever messages were collected this turn,
                    # even if the connection dropped or an error occurred.
                    if turn_messages:
                        try:
                            session_service.save_messages(turn_messages)
                        except Exception:
                            logger.exception(
                                "Failed to persist messages for session %s",
                                session_id,
                            )

        except Exception:
            logger.info("WebSocket disconnected for session %s", session_id)
