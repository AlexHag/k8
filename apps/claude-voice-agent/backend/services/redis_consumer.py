from __future__ import annotations

import json
import logging
import socket
import time

from openai import OpenAI

from common.constants import RESPONSE_CONSUMER_GROUP, RESPONSE_STREAM
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
from services.ws_connection_registry import WsConnectionRegistry

logger = logging.getLogger(__name__)

CONSUMER_NAME = socket.gethostname() # TODO: Use hostname env var

class BackendRedisConsumer:
    """Consumes agent response events from Redis stream,
    persists to DB, and forwards to connected WebSocket clients with TTS."""

    def __init__(
        self,
        redis_client: RedisStreamClient,
        session_service: SessionService,
        openai_client: OpenAI,
        registry: WsConnectionRegistry,
    ) -> None:
        self._redis = redis_client
        self._session_service = session_service
        self._openai = openai_client
        self._registry = registry
        self._running = False
        self._sequence_counters: dict[str, int] = {}

        self._redis.ensure_group(RESPONSE_STREAM, RESPONSE_CONSUMER_GROUP)

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
        logger.info("Backend Redis consumer started")

        while self._running:
            try:
                entries = self._redis.read(
                    RESPONSE_STREAM,
                    RESPONSE_CONSUMER_GROUP,
                    CONSUMER_NAME,
                    count=10,
                    block_ms=2000,
                )
            except Exception:
                logger.exception("Error reading from Redis response stream")
                time.sleep(1)
                continue

            for entry_id, fields in entries:
                logger.info(
                    "[EVENT_IN] stream=%s entry_id=%s raw_fields=%s",
                    RESPONSE_STREAM, entry_id, fields,
                )
                try:
                    event = deserialize_response_event(fields)
                    self._handle_event(event)
                except Exception:
                    logger.exception(
                        "Error handling response event %s",
                        entry_id,
                    )
                finally:
                    self._redis.ack(
                        RESPONSE_STREAM, RESPONSE_CONSUMER_GROUP, entry_id
                    )

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_event(self, event) -> None:
        if isinstance(event, TextEvent):
            self._process_text_event(event)

        elif isinstance(event, ToolUseEvent):
            self._process_tool_use_event(event)

        elif isinstance(event, ToolResultEvent):
            self._process_tool_result_event(event)

        elif isinstance(event, SessionUpdateEvent):
            self._process_session_update_event(event)

        elif isinstance(event, DoneEvent):
            self._process_done_event(event)

        elif isinstance(event, ErrorEvent):
            self._process_error_event(event)
    
    def _process_text_event(self, event: TextEvent) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

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
    
    def _process_tool_use_event(self, event: ToolUseEvent) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

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
    
    def _process_tool_result_event(self, event: ToolResultEvent) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

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
    
    def _process_session_update_event(self, event: SessionUpdateEvent) -> None:
        session_id = event.session_id

        self._session_service.update_claude_session_id(
            session_id, event.claude_session_id,
        )

    def _process_done_event(self, event: DoneEvent) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

        logger.info("[EVENT_IN] session=%s type=done", session_id)
        self._session_service.update_status(session_id, "idle")
        self._sequence_counters.pop(session_id, None)
        if ws:
            try:
                ws_send(ws, {"type": "done"})
            except WsClosed:
                self._registry.unregister(session_id)
    
    def _process_error_event(self, event: ErrorEvent) -> None:
        session_id = event.session_id
        ws = self._registry.get(session_id)

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
