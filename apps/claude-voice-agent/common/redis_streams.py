from __future__ import annotations

import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)


class RedisStreamClient:
    """Thin wrapper around Redis Streams (XADD / XREADGROUP / XACK)."""

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    @property
    def connection(self) -> redis.Redis:
        return self._redis

    def ensure_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            self._redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("Created consumer group %s on stream %s", group, stream)
        except redis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass  # group already exists
            else:
                raise

    def publish(self, stream: str, data: dict[str, str]) -> str:
        """Append an entry to the stream. Returns the entry ID."""
        entry_id: str = self._redis.xadd(stream, data)
        return entry_id

    def read(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 2000,
    ) -> list[tuple[str, dict[str, str]]]:
        """Read new entries from the stream via the consumer group.

        Returns a list of ``(entry_id, fields)`` tuples.
        """
        results = self._redis.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block_ms
        )
        if not results:
            return []
        entries: list[tuple[str, dict[str, str]]] = []
        for _stream_name, messages in results:
            for entry_id, fields in messages:
                entries.append((entry_id, fields))
        return entries

    def ack(self, stream: str, group: str, entry_id: str) -> None:
        """Acknowledge a processed entry."""
        self._redis.xack(stream, group, entry_id)

    def close(self) -> None:
        self._redis.close()
