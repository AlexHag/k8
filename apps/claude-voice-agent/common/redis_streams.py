from __future__ import annotations

import logging

import redis

logger = logging.getLogger(__name__)


class RedisStreamClient:
    """Thin wrapper around Redis Streams and common key operations."""

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    @property
    def connection(self) -> redis.Redis:
        return self._redis

    # ------------------------------------------------------------------
    # Stream operations
    # ------------------------------------------------------------------

    def ensure_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            self._redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("Created consumer group %s on stream %s", group, stream)
        except redis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass
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
        """Read new entries from a single stream via the consumer group."""
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

    def read_multi(
        self,
        streams: dict[str, str],
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 2000,
    ) -> list[tuple[str, str, dict[str, str]]]:
        """Read new entries from multiple streams via the consumer group.

        Returns a list of ``(stream_name, entry_id, fields)`` tuples.
        """
        if not streams:
            return []
        results = self._redis.xreadgroup(
            group, consumer, streams, count=count, block=block_ms
        )
        if not results:
            return []
        entries: list[tuple[str, str, dict[str, str]]] = []
        for stream_name, messages in results:
            for entry_id, fields in messages:
                entries.append((stream_name, entry_id, fields))
        return entries

    def ack(self, stream: str, group: str, entry_id: str) -> None:
        """Acknowledge a processed entry."""
        self._redis.xack(stream, group, entry_id)

    def delete_stream(self, stream: str) -> None:
        """Delete an entire stream key."""
        self._redis.delete(stream)

    # ------------------------------------------------------------------
    # Key/value operations
    # ------------------------------------------------------------------

    def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> None:
        self._redis.set(key, value, ex=ttl_seconds)

    def refresh_ttl(self, key: str, ttl_seconds: int) -> bool:
        return bool(self._redis.expire(key, ttl_seconds))

    def get(self, key: str) -> str | None:
        return self._redis.get(key)

    def exists(self, key: str) -> bool:
        return bool(self._redis.exists(key))

    def delete_key(self, *keys: str) -> int:
        if not keys:
            return 0
        return self._redis.delete(*keys)

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------

    def sadd(self, key: str, *members: str) -> int:
        return self._redis.sadd(key, *members)

    def srem(self, key: str, *members: str) -> int:
        return self._redis.srem(key, *members)

    def smembers(self, key: str) -> set[str]:
        return self._redis.smembers(key)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._redis.close()
