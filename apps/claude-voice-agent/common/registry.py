from __future__ import annotations

import logging

from .constants import (
    PODS_ALIVE_SET,
    pod_alive_key,
    pod_sessions_key,
    pod_notify_key,
    session_pod_key,
    session_prompt_stream,
    session_response_stream,
)
from .redis_streams import RedisStreamClient

logger = logging.getLogger(__name__)


class PodRegistry:
    """Manages pod liveness, session ownership, and cleanup in Redis."""

    def __init__(self, redis_client: RedisStreamClient) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Pod lifecycle
    # ------------------------------------------------------------------

    def register_pod(self, pod_id: str, ttl: int) -> None:
        self._redis.sadd(PODS_ALIVE_SET, pod_id)
        self._redis.set_with_ttl(pod_alive_key(pod_id), "1", ttl)
        logger.info("Pod %s registered (TTL=%ds)", pod_id, ttl)

    def refresh_heartbeat(self, pod_id: str, ttl: int) -> None:
        self._redis.set_with_ttl(pod_alive_key(pod_id), "1", ttl)

    def deregister_pod(self, pod_id: str) -> None:
        self._redis.srem(PODS_ALIVE_SET, pod_id)
        self._redis.delete_key(
            pod_alive_key(pod_id),
            pod_sessions_key(pod_id),
            pod_notify_key(pod_id),
        )
        logger.info("Pod %s deregistered", pod_id)

    def is_pod_alive(self, pod_id: str) -> bool:
        return self._redis.exists(pod_alive_key(pod_id))

    def get_alive_pods(self) -> list[str]:
        """Return pod_ids from the enumeration SET, filtering out stale entries."""
        candidates = self._redis.smembers(PODS_ALIVE_SET)
        alive: list[str] = []
        for pod_id in candidates:
            if self._redis.exists(pod_alive_key(pod_id)):
                alive.append(pod_id)
        return alive

    # ------------------------------------------------------------------
    # Session ownership
    # ------------------------------------------------------------------

    def assign_session(self, session_id: str, pod_id: str) -> None:
        self._redis.connection.set(session_pod_key(session_id), pod_id)
        self._redis.sadd(pod_sessions_key(pod_id), session_id)
        logger.info("Session %s assigned to pod %s", session_id, pod_id)

    def get_session_owner(self, session_id: str) -> str | None:
        return self._redis.get(session_pod_key(session_id))

    def release_session(self, session_id: str, pod_id: str) -> None:
        self._redis.delete_key(session_pod_key(session_id))
        self._redis.srem(pod_sessions_key(pod_id), session_id)
        logger.info("Session %s released from pod %s", session_id, pod_id)

    def get_pod_sessions(self, pod_id: str) -> set[str]:
        return self._redis.smembers(pod_sessions_key(pod_id))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_dead_pod(self, pod_id: str) -> set[str]:
        """Remove a dead pod from the alive set, release all its sessions,
        and delete the associated streams.  Returns the set of cleaned-up
        session ids.
        """
        sessions = self.get_pod_sessions(pod_id)
        for session_id in sessions:
            self._redis.delete_key(session_pod_key(session_id))
            self._redis.delete_stream(session_prompt_stream(session_id))
            self._redis.delete_stream(session_response_stream(session_id))

        self._redis.srem(PODS_ALIVE_SET, pod_id)
        self._redis.delete_key(
            pod_alive_key(pod_id),
            pod_sessions_key(pod_id),
            pod_notify_key(pod_id),
        )
        logger.info("Cleaned up dead pod %s (%d sessions)", pod_id, len(sessions))
        return sessions

    def cleanup_session_streams(self, session_id: str) -> None:
        """Delete the prompt and response streams for a single session."""
        self._redis.delete_stream(session_prompt_stream(session_id))
        self._redis.delete_stream(session_response_stream(session_id))
