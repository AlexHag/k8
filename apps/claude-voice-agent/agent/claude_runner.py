from __future__ import annotations

import asyncio
import json
import logging

from claude_agent_sdk import (
    query as claude_query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)

from common.events import (
    TextEvent,
    ToolUseEvent,
    ToolResultEvent,
    SessionUpdateEvent,
    DoneEvent,
    ErrorEvent,
    serialize_event,
)
from common.redis_streams import RedisStreamClient
from common.constants import session_response_stream
from config import CLAUDE_CLI_PATH, CLAUDE_CWD

logger = logging.getLogger(__name__)


class _ClaudeSessionRunner:
    """Encapsulates the per-session state and message-dispatch logic."""

    def __init__(
        self,
        session_id: str,
        redis_client: RedisStreamClient,
        response_stream: str,
    ) -> None:
        self._session_id = session_id
        self._redis = redis_client
        self._stream = response_stream

    def _publish(self, event: TextEvent | ToolUseEvent | ToolResultEvent | SessionUpdateEvent | DoneEvent | ErrorEvent) -> None:
        self._redis.publish(self._stream, serialize_event(event))

    # -- block handlers -------------------------------------------------------

    def _handle_text_block(self, block: TextBlock) -> None:
        logger.info(
            "[CLAUDE_RESPONSE] session=%s TextBlock text=%r",
            self._session_id,
            block.text[:200],
        )
        event = TextEvent(
            type="text",
            session_id=self._session_id,
            text=block.text,
        )
        self._publish(event)
        logger.info(
            "[EVENT_OUT] session=%s type=text text=%r",
            self._session_id,
            block.text[:200],
        )

    def _handle_tool_use_block(self, block: ToolUseBlock) -> None:
        tool_input_str = json.dumps(block.input)
        logger.info(
            "[CLAUDE_RESPONSE] session=%s ToolUseBlock tool=%s input=%r",
            self._session_id,
            block.name,
            tool_input_str[:300],
        )
        event = ToolUseEvent(
            type="tool_use",
            session_id=self._session_id,
            tool_name=block.name,
            tool_input=tool_input_str,
        )
        self._publish(event)
        logger.info(
            "[EVENT_OUT] session=%s type=tool_use tool=%s",
            self._session_id,
            block.name,
        )

    def _handle_tool_result_block(self, block: ToolResultBlock) -> None:
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
        content_str = str(content) if content else ""
        logger.info(
            "[CLAUDE_RESPONSE] session=%s ToolResultBlock tool_use_id=%s is_error=%s content=%r",
            self._session_id,
            block.tool_use_id,
            block.is_error,
            content_str[:300],
        )
        event = ToolResultEvent(
            type="tool_result",
            session_id=self._session_id,
            content=content_str,
            is_error=bool(block.is_error),
            tool_use_id=block.tool_use_id,
        )
        self._publish(event)
        logger.info(
            "[EVENT_OUT] session=%s type=tool_result tool_use_id=%s is_error=%s",
            self._session_id,
            block.tool_use_id,
            block.is_error,
        )

    # -- message handlers ------------------------------------------------------

    def _handle_assistant_message(self, message: AssistantMessage) -> None:
        logger.info(
            "[CLAUDE_RESPONSE] session=%s AssistantMessage blocks=%d",
            self._session_id,
            len(message.content),
        )
        for block in message.content:
            if isinstance(block, TextBlock):
                self._handle_text_block(block)
            elif isinstance(block, ToolUseBlock):
                self._handle_tool_use_block(block)
            elif isinstance(block, ToolResultBlock):
                self._handle_tool_result_block(block)

    def _handle_result_message(self, message: ResultMessage) -> None:
        logger.info(
            "[CLAUDE_RESPONSE] session=%s ResultMessage claude_sid=%s",
            self._session_id,
            message.session_id,
        )
        if message.session_id:
            event = SessionUpdateEvent(
                type="session_update",
                session_id=self._session_id,
                claude_session_id=message.session_id,
            )
            self._publish(event)
            logger.info(
                "[EVENT_OUT] session=%s type=session_update claude_sid=%s",
                self._session_id,
                message.session_id,
            )

    # -- top-level dispatch ----------------------------------------------------

    def dispatch(self, message: object) -> None:
        if isinstance(message, AssistantMessage):
            self._handle_assistant_message(message)
        elif isinstance(message, ResultMessage):
            self._handle_result_message(message)
        else:
            try:
                message_details = vars(message)
            except TypeError:
                message_details = repr(message)
            logger.warning(
                "[CLAUDE_RESPONSE] session=%s unknown_message_type=%s details=%s",
                self._session_id,
                type(message).__name__,
                message_details,
            )


async def run_claude_session(
    session_id: str,
    prompt: str,
    claude_session_id: str | None,
    redis_client: RedisStreamClient,
) -> None:
    """Run a Claude Code query and publish each event to Redis."""
    response_stream = session_response_stream(session_id)
    runner = _ClaudeSessionRunner(session_id, redis_client, response_stream)

    options = ClaudeAgentOptions(
        cli_path=CLAUDE_CLI_PATH,
        permission_mode="acceptEdits",
        cwd=CLAUDE_CWD,
    )
    if claude_session_id:
        options.resume = claude_session_id

    logger.info(
        "[CLAUDE_QUERY] session=%s claude_sid=%s prompt=%r",
        session_id,
        claude_session_id,
        prompt,
    )

    try:
        async for message in claude_query(prompt=prompt, options=options):
            runner.dispatch(message)

        done = DoneEvent(type="done", session_id=session_id)
        runner._publish(done)
        logger.info("[EVENT_OUT] session=%s type=done", session_id)

    except asyncio.CancelledError:
        logger.info("Claude session %s was cancelled", session_id)
        done = DoneEvent(type="done", session_id=session_id)
        runner._publish(done)
        logger.info("[EVENT_OUT] session=%s type=done (cancelled)", session_id)
        raise

    except Exception as exc:
        logger.exception("Claude session %s failed", session_id)
        err = ErrorEvent(
            type="error",
            session_id=session_id,
            message=str(exc),
        )
        runner._publish(err)
        logger.info("[EVENT_OUT] session=%s type=error message=%r", session_id, str(exc))
