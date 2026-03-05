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
from common.constants import RESPONSE_STREAM
from config import CLAUDE_CLI_PATH, CLAUDE_CWD

logger = logging.getLogger(__name__)


async def run_claude_session(
    session_id: str,
    prompt: str,
    claude_session_id: str | None,
    redis_client: RedisStreamClient,
) -> None:
    """Run a Claude Code query and publish each event to Redis."""
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
        # Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent
        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                logger.info(
                    "[CLAUDE_RESPONSE] session=%s AssistantMessage blocks=%d",
                    session_id,
                    len(message.content),
                )
                for block in message.content:
                    if isinstance(block, TextBlock):
                        logger.info(
                            "[CLAUDE_RESPONSE] session=%s TextBlock text=%r",
                            session_id,
                            block.text[:200],
                        )
                        event = TextEvent(
                            type="text",
                            session_id=session_id,
                            text=block.text,
                        )
                        redis_client.publish(RESPONSE_STREAM, serialize_event(event))
                        logger.info(
                            "[EVENT_OUT] session=%s type=text text=%r",
                            session_id,
                            block.text[:200],
                        )

                    elif isinstance(block, ToolUseBlock):
                        tool_input_str = json.dumps(block.input)
                        logger.info(
                            "[CLAUDE_RESPONSE] session=%s ToolUseBlock tool=%s input=%r",
                            session_id,
                            block.name,
                            tool_input_str[:300],
                        )
                        event = ToolUseEvent(
                            type="tool_use",
                            session_id=session_id,
                            tool_name=block.name,
                            tool_input=tool_input_str,
                        )
                        redis_client.publish(RESPONSE_STREAM, serialize_event(event))
                        logger.info(
                            "[EVENT_OUT] session=%s type=tool_use tool=%s",
                            session_id,
                            block.name,
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
                        content_str = str(content) if content else ""
                        logger.info(
                            "[CLAUDE_RESPONSE] session=%s ToolResultBlock tool_use_id=%s is_error=%s content=%r",
                            session_id,
                            block.tool_use_id,
                            block.is_error,
                            content_str[:300],
                        )
                        event = ToolResultEvent(
                            type="tool_result",
                            session_id=session_id,
                            content=content_str,
                            is_error=bool(block.is_error),
                            tool_use_id=block.tool_use_id,
                        )
                        redis_client.publish(RESPONSE_STREAM, serialize_event(event))
                        logger.info(
                            "[EVENT_OUT] session=%s type=tool_result tool_use_id=%s is_error=%s",
                            session_id,
                            block.tool_use_id,
                            block.is_error,
                        )

            elif isinstance(message, ResultMessage):
                logger.info(
                    "[CLAUDE_RESPONSE] session=%s ResultMessage claude_sid=%s",
                    session_id,
                    message.session_id,
                )
                if message.session_id:
                    event = SessionUpdateEvent(
                        type="session_update",
                        session_id=session_id,
                        claude_session_id=message.session_id,
                    )
                    redis_client.publish(RESPONSE_STREAM, serialize_event(event))
                    logger.info(
                        "[EVENT_OUT] session=%s type=session_update claude_sid=%s",
                        session_id,
                        message.session_id,
                    )

            else:
                try:
                    message_details = vars(message)
                except TypeError:
                    message_details = repr(message)
                logger.warning(
                    "[CLAUDE_RESPONSE] session=%s unknown_message_type=%s details=%s",
                    session_id,
                    type(message).__name__,
                    message_details,
                )

        done = DoneEvent(type="done", session_id=session_id)
        redis_client.publish(RESPONSE_STREAM, serialize_event(done))
        logger.info("[EVENT_OUT] session=%s type=done", session_id)

    except asyncio.CancelledError:
        logger.info("Claude session %s was cancelled", session_id)
        done = DoneEvent(type="done", session_id=session_id)
        redis_client.publish(RESPONSE_STREAM, serialize_event(done))
        logger.info("[EVENT_OUT] session=%s type=done (cancelled)", session_id)
        raise

    except Exception as exc:
        logger.exception("Claude session %s failed", session_id)
        err = ErrorEvent(
            type="error",
            session_id=session_id,
            message=str(exc),
        )
        redis_client.publish(RESPONSE_STREAM, serialize_event(err))
        logger.info("[EVENT_OUT] session=%s type=error message=%r", session_id, str(exc))
