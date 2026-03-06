from __future__ import annotations

import asyncio
import logging

from common.constants import (
    NOTIFY_CONSUMER_GROUP,
    PROMPT_CONSUMER_GROUP,
    pod_notify_key,
    session_prompt_stream,
    session_response_stream,
)
from common.events import (
    deserialize_notify_event,
    deserialize_prompt_event,
    serialize_event,
    ErrorEvent,
    PromptEvent,
    CancelEvent,
)
from common.redis_streams import RedisStreamClient
from common.registry import PodRegistry
from claude_runner import run_claude_session
from config import POD_ID, HEARTBEAT_TTL, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)


class AgentConsumer:
    """Listens for session assignments on the pod notify stream and spawns
    a per-session worker task for each owned session."""

    def __init__(
        self,
        redis_client: RedisStreamClient,
        registry: PodRegistry,
    ) -> None:
        self._redis = redis_client
        self._registry = registry
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._registry.register_pod(POD_ID, HEARTBEAT_TTL)

        notify_stream = pod_notify_key(POD_ID)
        self._redis.ensure_group(notify_stream, NOTIFY_CONSUMER_GROUP)

        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="heartbeat"
        )
        self._notify_task = asyncio.create_task(
            self._notification_loop(), name="notify-loop"
        )

        logger.info(
            "Agent consumer started (pod=%s, heartbeat=%ds/%ds)",
            POD_ID, HEARTBEAT_INTERVAL, HEARTBEAT_TTL,
        )

        await asyncio.gather(self._heartbeat_task, self._notify_task)

    async def stop(self) -> None:
        self._running = False

        self._heartbeat_task.cancel()
        self._notify_task.cancel()

        for session_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                logger.info("Cancelled session worker for %s", session_id)

            try:
                err = ErrorEvent(
                    type="error",
                    session_id=session_id,
                    message="Agent pod shutting down",
                )
                self._redis.publish(
                    session_response_stream(session_id),
                    serialize_event(err),
                )
            except Exception:
                logger.exception(
                    "Failed to publish shutdown error for session %s", session_id
                )

            try:
                self._registry.release_session(session_id, POD_ID)
            except Exception:
                logger.exception(
                    "Failed to release session %s on shutdown", session_id
                )

        self._tasks.clear()
        self._registry.deregister_pod(POD_ID)
        logger.info("Agent consumer stopped (pod=%s)", POD_ID)

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(
                    self._registry.refresh_heartbeat, POD_ID, HEARTBEAT_TTL
                )
            except Exception:
                logger.exception("Heartbeat refresh failed")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    # ------------------------------------------------------------------
    # Notification listener
    # ------------------------------------------------------------------

    async def _notification_loop(self) -> None:
        notify_stream = pod_notify_key(POD_ID)

        while self._running:
            try:
                entries = await asyncio.to_thread(
                    self._redis.read,
                    notify_stream,
                    NOTIFY_CONSUMER_GROUP,
                    POD_ID,
                    count=10,
                    block_ms=2000,
                )
            except Exception:
                logger.exception("Error reading notify stream")
                await asyncio.sleep(1)
                continue

            for entry_id, fields in entries:
                try:
                    event = deserialize_notify_event(fields)
                    logger.info(
                        "[NOTIFY] action=%s session=%s",
                        event.action, event.session_id,
                    )
                    if event.action == "start":
                        self._start_session_worker(event.session_id)
                    elif event.action == "stop":
                        self._stop_session_worker(event.session_id)
                except Exception:
                    logger.exception("Error handling notify event %s", entry_id)
                finally:
                    self._redis.ack(notify_stream, NOTIFY_CONSUMER_GROUP, entry_id)

            self._cleanup_finished_tasks()

    # ------------------------------------------------------------------
    # Per-session workers
    # ------------------------------------------------------------------

    def _start_session_worker(self, session_id: str) -> None:
        if session_id in self._tasks and not self._tasks[session_id].done():
            logger.warning("Worker already running for session %s", session_id)
            return

        prompt_stream = session_prompt_stream(session_id)
        self._redis.ensure_group(prompt_stream, PROMPT_CONSUMER_GROUP)

        task = asyncio.create_task(
            self._session_worker(session_id),
            name=f"session-{session_id}",
        )
        self._tasks[session_id] = task
        logger.info("Started session worker for %s", session_id)

    def _stop_session_worker(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            logger.info("Stopped session worker for %s", session_id)

    async def _session_worker(self, session_id: str) -> None:
        """Poll the per-session prompt stream and run Claude for each prompt."""
        prompt_stream = session_prompt_stream(session_id)
        claude_task: asyncio.Task | None = None

        try:
            while self._running:
                try:
                    entries = await asyncio.to_thread(
                        self._redis.read,
                        prompt_stream,
                        PROMPT_CONSUMER_GROUP,
                        POD_ID,
                        count=5,
                        block_ms=2000,
                    )
                except Exception:
                    logger.exception(
                        "Error reading prompt stream for session %s", session_id
                    )
                    await asyncio.sleep(1)
                    continue

                for entry_id, fields in entries:
                    try:
                        event = deserialize_prompt_event(fields)
                        if isinstance(event, PromptEvent):
                            logger.info(
                                "[SESSION %s] prompt received, starting Claude",
                                session_id,
                            )
                            claude_task = asyncio.create_task(
                                run_claude_session(
                                    session_id=event.session_id,
                                    prompt=event.text,
                                    claude_session_id=event.claude_session_id,
                                    redis_client=self._redis,
                                ),
                                name=f"claude-{session_id}",
                            )
                            await claude_task
                            claude_task = None

                        elif isinstance(event, CancelEvent):
                            logger.info(
                                "[SESSION %s] cancel received", session_id
                            )
                            if claude_task and not claude_task.done():
                                claude_task.cancel()
                                try:
                                    await claude_task
                                except asyncio.CancelledError:
                                    pass
                                claude_task = None
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception(
                            "Error handling prompt event %s for session %s",
                            entry_id, session_id,
                        )
                    finally:
                        self._redis.ack(
                            prompt_stream, PROMPT_CONSUMER_GROUP, entry_id
                        )

        except asyncio.CancelledError:
            if claude_task and not claude_task.done():
                claude_task.cancel()
                try:
                    await claude_task
                except asyncio.CancelledError:
                    pass
            logger.info("Session worker cancelled for %s", session_id)

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def _cleanup_finished_tasks(self) -> None:
        finished = [
            sid for sid, task in self._tasks.items() if task.done()
        ]
        for sid in finished:
            task = self._tasks.pop(sid)
            exc = task.exception() if not task.cancelled() else None
            if exc:
                logger.error("Session worker %s raised: %s", sid, exc)
