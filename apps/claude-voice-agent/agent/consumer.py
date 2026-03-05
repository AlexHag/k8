from __future__ import annotations

import asyncio
import logging

from common.constants import PROMPT_STREAM, AGENT_CONSUMER_GROUP
from common.events import deserialize_prompt_event, PromptEvent, CancelEvent
from common.redis_streams import RedisStreamClient
from claude_runner import run_claude_session
from config import CONSUMER_NAME

logger = logging.getLogger(__name__)


class AgentConsumer:
    """Consumes prompt/cancel events from Redis and manages Claude tasks."""

    def __init__(self, redis_client: RedisStreamClient) -> None:
        self._redis = redis_client
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self) -> None:
        self._redis.ensure_group(PROMPT_STREAM, AGENT_CONSUMER_GROUP)
        self._running = True
        logger.info("Agent consumer started (consumer=%s)", CONSUMER_NAME)

        while self._running:
            try:
                entries = await asyncio.to_thread(
                    self._redis.read,
                    PROMPT_STREAM,
                    AGENT_CONSUMER_GROUP,
                    CONSUMER_NAME,
                    count=5,
                    block_ms=2000,
                )
            except Exception:
                logger.exception("Error reading from Redis stream")
                await asyncio.sleep(1)
                continue

            for entry_id, fields in entries:
                try:
                    event = deserialize_prompt_event(fields)
                    await self._handle_event(event)
                except Exception:
                    logger.exception("Error handling event %s", entry_id)
                finally:
                    self._redis.ack(PROMPT_STREAM, AGENT_CONSUMER_GROUP, entry_id)

            self._cleanup_finished_tasks()

    def stop(self) -> None:
        self._running = False
        for session_id, task in self._tasks.items():
            if not task.done():
                task.cancel()
                logger.info("Cancelled task for session %s", session_id)

    async def _handle_event(self, event: PromptEvent | CancelEvent) -> None:
        if isinstance(event, PromptEvent):
            logger.info(
                "Received prompt for session %s (claude_sid=%s)",
                event.session_id,
                event.claude_session_id,
            )
            task = asyncio.create_task(
                run_claude_session(
                    session_id=event.session_id,
                    prompt=event.text,
                    claude_session_id=event.claude_session_id,
                    redis_client=self._redis,
                ),
                name=f"claude-{event.session_id}",
            )
            self._tasks[event.session_id] = task

        elif isinstance(event, CancelEvent):
            logger.info("Received cancel for session %s", event.session_id)
            task = self._tasks.get(event.session_id)
            if task and not task.done():
                task.cancel()

    def _cleanup_finished_tasks(self) -> None:
        finished = [
            sid for sid, task in self._tasks.items() if task.done()
        ]
        for sid in finished:
            task = self._tasks.pop(sid)
            exc = task.exception() if not task.cancelled() else None
            if exc:
                logger.error("Task for session %s raised: %s", sid, exc)
