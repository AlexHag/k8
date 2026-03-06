from __future__ import annotations

import json
import logging
import threading
import time

from openai import OpenAI

from common.constants import RESPONSE_CONSUMER_GROUP, session_response_stream
from common.events import (
    deserialize_response_event,
    TextEvent,
    ToolUseEvent,
    ToolResultEvent,
    SessionUpdateEvent,
    DoneEvent,
    ErrorEvent,
)
from common.redis_streams import RedisStreamClient
from models.message import Message
from services.session_service import SessionService
from services.tts import WsClosed, ws_send, process_text_block

logger = logging.getLogger(__name__)

CONSUMER_NAME = "backend-1"


class ConnectionRegistry:
    """Thread-safe registry mapping session_id -> active WebSocket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, object] = {}

    def register(self, session_id: str, ws) -> None:
        with self._lock:
            self._connections[session_id] = ws

    def unregister(self, session_id: str) -> None:
        with self._lock:
            self._connections.pop(session_id, None)

    def get(self, session_id: str):
        with self._lock:
            return self._connections.get(session_id)


class BackendRedisConsumer:
    """Consumes agent response events from per-session Redis streams,
    persists to DB, and forwards to connected WebSocket clients with TTS."""

    def __init__(
        self,
        redis_client: RedisStreamClient,
        session_service: SessionService,
        openai_client: OpenAI,
        registry: ConnectionRegistry,
    ) -> None:
        self._redis = redis_client
        self._session_service = session_service
        self._openai = openai_client
        self._registry = registry
        self._running = False
        self._sequence_counters: dict[str, int] = {}

        self._sessions_lock = threading.Lock()
        self._active_sessions: set[str] = set()

    # ------------------------------------------------------------------
    # Dynamic session tracking
    # ------------------------------------------------------------------

    def add_session(self, session_id: str) -> None:
        """Start consuming the response stream for *session_id*."""
        stream = session_response_stream(session_id)
        self._redis.ensure_group(stream, RESPONSE_CONSUMER_GROUP)
        with self._sessions_lock:
            self._active_sessions.add(session_id)
        logger.info("Consumer now tracking session %s", session_id)

    def remove_session(self, session_id: str) -> None:
        """Stop consuming the response stream for *session_id*."""
        with self._sessions_lock:
            self._active_sessions.discard(session_id)
        logger.info("Consumer stopped tracking session %s", session_id)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _next_sequence(self, session_id: str) -> int:
        if session_id not in self._sequence_counters:
            self._sequence_counters[session_id] = (
                self._session_service.get_next_sequence(session_id)
            )
        seq = self._sequence_counters[session_id]
        self._sequence_counters[session_id] = seq + 1
        return seq

    def run(self) -> None:
        """Blocking consumer loop -- meant to run in a background thread."""
        self._running = True
        logger.info("Backend Redis consumer started (multi-stream mode)")

        while self._running:
            with self._sessions_lock:
                session_ids = set(self._active_sessions)

            if not session_ids:
                time.sleep(0.5)
                continue

            streams = {
                session_response_stream(sid): ">"
                for sid in session_ids
            }

            try:
                entries = self._redis.read_multi(
                    streams,
                    RESPONSE_CONSUMER_GROUP,
                    CONSUMER_NAME,
                    count=10,
                    block_ms=2000,
                )
            except Exception:
                logger.exception("Error reading from Redis response streams")
                time.sleep(1)
                continue

            for stream_name, entry_id, fields in entries:
                logger.info(
                    "[EVENT_IN] stream=%s entry_id=%s raw_fields=%s",
                    stream_name, entry_id, fields,
                )
                try:
                    event = deserialize_response_event(fields)
                    self._handle_event(event)
                except Exception:
                    logger.exception(
                        "Error handling response event %s from %s",
                        entry_id, stream_name,
                    )
                finally:
                    self._redis.ack(
                        stream_name, RESPONSE_CONSUMER_GROUP, entry_id
                    )

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Event handling (unchanged from single-stream version)
    # ------------------------------------------------------------------

    def _handle_event(self, event) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

        if isinstance(event, TextEvent):
            logger.info(
                "[EVENT_IN] session=%s type=text text=%r",
                session_id, event.text[:200],
            )
            self._persist_message(
                session_id=session_id, role="assistant", text=event.text,
            )
            if ws:
                session = self._session_service.get_session(session_id)
                voice_enabled = session.voice_mode if session else False
                try:
                    if voice_enabled:
                        process_text_block(ws, event.text, self._openai)
                    else:
                        ws_send(ws, {"type": "text_delta", "text": event.text})
                except WsClosed:
                    self._registry.unregister(session_id)

        elif isinstance(event, ToolUseEvent):
            self._persist_message(
                session_id=session_id, role="tool_use", text=event.tool_input,
                tool_name=event.tool_name, tool_input=event.tool_input,
            )
            if ws:
                try:
                    ws_send(ws, {
                        "type": "tool_use",
                        "tool": event.tool_name,
                        "input": json.loads(event.tool_input),
                    })
                except WsClosed:
                    self._registry.unregister(session_id)

        elif isinstance(event, ToolResultEvent):
            self._persist_message(
                session_id=session_id, role="tool_result", text=event.content,
                is_error=event.is_error,
            )
            if ws:
                try:
                    ws_send(ws, {
                        "type": "tool_result",
                        "tool_use_id": event.tool_use_id,
                        "content": event.content,
                        "is_error": event.is_error,
                    })
                except WsClosed:
                    self._registry.unregister(session_id)

        elif isinstance(event, SessionUpdateEvent):
            self._session_service.update_claude_session_id(
                session_id, event.claude_session_id,
            )

        elif isinstance(event, DoneEvent):
            logger.info("[EVENT_IN] session=%s type=done", session_id)
            self._session_service.update_status(session_id, "idle")
            self._sequence_counters.pop(session_id, None)
            if ws:
                try:
                    ws_send(ws, {"type": "done"})
                except WsClosed:
                    self._registry.unregister(session_id)

        elif isinstance(event, ErrorEvent):
            logger.info(
                "[EVENT_IN] session=%s type=error message=%r",
                session_id, event.message,
            )
            self._session_service.update_status(session_id, "error")
            self._sequence_counters.pop(session_id, None)
            if ws:
                try:
                    ws_send(ws, {"type": "error", "message": event.message})
                except WsClosed:
                    self._registry.unregister(session_id)

    def _persist_message(
        self,
        session_id: str,
        role: str,
        text: str,
        tool_name: str | None = None,
        tool_input: str | None = None,
        is_error: bool = False,
    ) -> None:
        msg = Message(
            session_id=session_id,
            role=role,
            text=text,
            tool_name=tool_name,
            tool_input=tool_input,
            is_error=is_error,
            sequence=self._next_sequence(session_id),
        )
        try:
            self._session_service.save_message(msg)
        except Exception:
            logger.exception("Failed to persist message for session %s", session_id)
