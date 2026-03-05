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

    try:
        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        event = TextEvent(
                            type="text",
                            session_id=session_id,
                            text=block.text,
                        )
                        redis_client.publish(RESPONSE_STREAM, serialize_event(event))

                    elif isinstance(block, ToolUseBlock):
                        event = ToolUseEvent(
                            type="tool_use",
                            session_id=session_id,
                            tool_name=block.name,
                            tool_input=json.dumps(block.input),
                        )
                        redis_client.publish(RESPONSE_STREAM, serialize_event(event))

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
                        event = ToolResultEvent(
                            type="tool_result",
                            session_id=session_id,
                            content=str(content) if content else "",
                            is_error=bool(block.is_error),
                            tool_use_id=block.tool_use_id,
                        )
                        redis_client.publish(RESPONSE_STREAM, serialize_event(event))

            elif isinstance(message, ResultMessage):
                if message.session_id:
                    event = SessionUpdateEvent(
                        type="session_update",
                        session_id=session_id,
                        claude_session_id=message.session_id,
                    )
                    redis_client.publish(RESPONSE_STREAM, serialize_event(event))

        done = DoneEvent(type="done", session_id=session_id)
        redis_client.publish(RESPONSE_STREAM, serialize_event(done))

    except asyncio.CancelledError:
        logger.info("Claude session %s was cancelled", session_id)
        done = DoneEvent(type="done", session_id=session_id)
        redis_client.publish(RESPONSE_STREAM, serialize_event(done))
        raise

    except Exception as exc:
        logger.exception("Claude session %s failed", session_id)
        err = ErrorEvent(
            type="error",
            session_id=session_id,
            message=str(exc),
        )
        redis_client.publish(RESPONSE_STREAM, serialize_event(err))
