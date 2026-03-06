from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod

from .constants import (
    RESPONSE_CONSUMER_GROUP,
    pod_notify_key,
    session_response_stream,
)
from .events import NotifyEvent, serialize_event
from .redis_streams import RedisStreamClient
from .registry import PodRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PodDeadError(Exception):
    """The pod that owned the session is no longer alive."""


class NoPodAvailableError(Exception):
    """No agent pods are registered / alive."""


# ---------------------------------------------------------------------------
# Pluggable pod-selection strategy
# ---------------------------------------------------------------------------

class PodSelectionStrategy(ABC):
    @abstractmethod
    def select(self, alive_pods: list[str]) -> str:
        ...


class RandomStrategy(PodSelectionStrategy):
    def select(self, alive_pods: list[str]) -> str:
        return random.choice(alive_pods)


# ---------------------------------------------------------------------------
# Session router
# ---------------------------------------------------------------------------

class SessionRouter:
    """Looks up or assigns an agent pod for a given session."""

    def __init__(
        self,
        registry: PodRegistry,
        redis_client: RedisStreamClient,
        strategy: PodSelectionStrategy | None = None,
    ) -> None:
        self._registry = registry
        self._redis = redis_client
        self._strategy = strategy or RandomStrategy()

    def route_session(self, session_id: str) -> str:
        """Return the ``pod_id`` that owns *session_id*.

        * If the session already has a live owner, return it.
        * If the owner pod is dead, clean up and raise ``PodDeadError``.
        * If there is no owner yet, pick one, set up streams, and notify.
        """
        owner = self._registry.get_session_owner(session_id)

        if owner is not None:
            if self._registry.is_pod_alive(owner):
                return owner
            self._registry.cleanup_dead_pod(owner)
            raise PodDeadError(
                f"Pod {owner} that owned session {session_id} is dead"
            )

        alive_pods = self._registry.get_alive_pods()
        if not alive_pods:
            raise NoPodAvailableError("No agent pods available")

        pod_id = self._strategy.select(alive_pods)

        self._registry.assign_session(session_id, pod_id)

        resp_stream = session_response_stream(session_id)
        self._redis.ensure_group(resp_stream, RESPONSE_CONSUMER_GROUP)

        notify = NotifyEvent(session_id=session_id, action="start")
        self._redis.publish(pod_notify_key(pod_id), serialize_event(notify))
        logger.info(
            "Routed session %s -> pod %s (new assignment)", session_id, pod_id
        )
        return pod_id
