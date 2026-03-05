from __future__ import annotations

import json
import logging
import threading

from openai import OpenAI

from common.constants import RESPONSE_STREAM, BACKEND_CONSUMER_GROUP
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
    """Consumes agent response events from Redis, persists to DB, and
    forwards to connected WebSocket clients with TTS."""

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

    def _next_sequence(self, session_id: str) -> int:
        if session_id not in self._sequence_counters:
            self._sequence_counters[session_id] = (
                self._session_service.get_next_sequence(session_id)
            )
        seq = self._sequence_counters[session_id]
        self._sequence_counters[session_id] = seq + 1
        return seq

    def run(self) -> None:
        """Blocking consumer loop -- meant to run in a background thread/greenlet."""
        self._redis.ensure_group(RESPONSE_STREAM, BACKEND_CONSUMER_GROUP)
        self._running = True
        logger.info("Backend Redis consumer started")

        while self._running:
            try:
                entries = self._redis.read(
                    RESPONSE_STREAM,
                    BACKEND_CONSUMER_GROUP,
                    CONSUMER_NAME,
                    count=10,
                    block_ms=2000,
                )
            except Exception:
                logger.exception("Error reading from Redis response stream")
                import time
                time.sleep(1)
                continue

            for entry_id, fields in entries:
                logger.info(
                    "[EVENT_IN] entry_id=%s raw_fields=%s",
                    entry_id,
                    fields,
                )
                try:
                    event = deserialize_response_event(fields)
                    self._handle_event(event)
                except Exception:
                    logger.exception("Error handling response event %s", entry_id)
                finally:
                    self._redis.ack(
                        RESPONSE_STREAM, BACKEND_CONSUMER_GROUP, entry_id
                    )

    def stop(self) -> None:
        self._running = False

    def _handle_event(self, event) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

        if isinstance(event, TextEvent):
            logger.info(
                "[EVENT_IN] session=%s type=text text=%r",
                session_id,
                event.text[:200],
            )
            self._persist_message(
                session_id=session_id,
                role="assistant",
                text=event.text,
            )
            if ws:
                session = self._session_service.get_session(session_id)
                voice_enabled = session.voice_mode if session else False
                try:
                    if voice_enabled:
                        logger.info(
                            "[WS_FWD] session=%s type=text (TTS) text=%r",
                            session_id,
                            event.text[:200],
                        )
                        process_text_block(ws, event.text, self._openai)
                    else:
                        logger.info(
                            "[WS_FWD] session=%s type=text_delta text=%r",
                            session_id,
                            event.text[:200],
                        )
                        ws_send(ws, {"type": "text_delta", "text": event.text})
                except WsClosed:
                    logger.info("WS closed during text forward for session %s", session_id)
                    self._registry.unregister(session_id)
            else:
                logger.info(
                    "[WS_FWD] session=%s type=text — no active WS connection",
                    session_id,
                )

        elif isinstance(event, ToolUseEvent):
            logger.info(
                "[EVENT_IN] session=%s type=tool_use tool=%s input=%r",
                session_id,
                event.tool_name,
                event.tool_input[:300],
            )
            self._persist_message(
                session_id=session_id,
                role="tool_use",
                text=event.tool_input,
                tool_name=event.tool_name,
                tool_input=event.tool_input,
            )
            if ws:
                try:
                    logger.info(
                        "[WS_FWD] session=%s type=tool_use tool=%s",
                        session_id,
                        event.tool_name,
                    )
                    ws_send(ws, {
                        "type": "tool_use",
                        "tool": event.tool_name,
                        "input": json.loads(event.tool_input),
                    })
                except WsClosed:
                    self._registry.unregister(session_id)
            else:
                logger.info(
                    "[WS_FWD] session=%s type=tool_use — no active WS connection",
                    session_id,
                )

        elif isinstance(event, ToolResultEvent):
            logger.info(
                "[EVENT_IN] session=%s type=tool_result tool_use_id=%s is_error=%s content=%r",
                session_id,
                event.tool_use_id,
                event.is_error,
                event.content[:300],
            )
            self._persist_message(
                session_id=session_id,
                role="tool_result",
                text=event.content,
                is_error=event.is_error,
            )
            if ws:
                try:
                    logger.info(
                        "[WS_FWD] session=%s type=tool_result tool_use_id=%s is_error=%s",
                        session_id,
                        event.tool_use_id,
                        event.is_error,
                    )
                    ws_send(ws, {
                        "type": "tool_result",
                        "tool_use_id": event.tool_use_id,
                        "content": event.content,
                        "is_error": event.is_error,
                    })
                except WsClosed:
                    self._registry.unregister(session_id)
            else:
                logger.info(
                    "[WS_FWD] session=%s type=tool_result — no active WS connection",
                    session_id,
                )

        elif isinstance(event, SessionUpdateEvent):
            logger.info(
                "[EVENT_IN] session=%s type=session_update claude_sid=%s",
                session_id,
                event.claude_session_id,
            )
            self._session_service.update_claude_session_id(
                session_id, event.claude_session_id
            )

        elif isinstance(event, DoneEvent):
            logger.info("[EVENT_IN] session=%s type=done", session_id)
            self._session_service.update_status(session_id, "idle")
            self._sequence_counters.pop(session_id, None)
            if ws:
                try:
                    logger.info("[WS_FWD] session=%s type=done", session_id)
                    ws_send(ws, {"type": "done"})
                except WsClosed:
                    self._registry.unregister(session_id)
            else:
                logger.info(
                    "[WS_FWD] session=%s type=done — no active WS connection",
                    session_id,
                )

        elif isinstance(event, ErrorEvent):
            logger.info(
                "[EVENT_IN] session=%s type=error message=%r",
                session_id,
                event.message,
            )
            self._session_service.update_status(session_id, "error")
            self._sequence_counters.pop(session_id, None)
            if ws:
                try:
                    logger.info(
                        "[WS_FWD] session=%s type=error message=%r",
                        session_id,
                        event.message,
                    )
                    ws_send(ws, {"type": "error", "message": event.message})
                except WsClosed:
                    self._registry.unregister(session_id)
            else:
                logger.info(
                    "[WS_FWD] session=%s type=error — no active WS connection",
                    session_id,
                )

        else:
            logger.warning(
                "[EVENT_IN] session=%s unknown event type=%s",
                session_id,
                type(event).__name__,
            )

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
