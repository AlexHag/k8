from __future__ import annotations

from dataclasses import dataclass
from typing import Union


# ---------------------------------------------------------------------------
# Prompt events (backend -> agent)
# ---------------------------------------------------------------------------

@dataclass
class PromptEvent:
    type: str  # "prompt"
    session_id: str
    text: str
    claude_session_id: str | None = None


@dataclass
class CancelEvent:
    type: str  # "cancel"
    session_id: str


PromptEventTypes = Union[PromptEvent, CancelEvent]


# ---------------------------------------------------------------------------
# Response events (agent -> backend)
# ---------------------------------------------------------------------------

@dataclass
class TextEvent:
    type: str  # "text"
    session_id: str
    text: str


@dataclass
class ToolUseEvent:
    type: str  # "tool_use"
    session_id: str
    tool_name: str
    tool_input: str


@dataclass
class ToolResultEvent:
    type: str  # "tool_result"
    session_id: str
    content: str
    is_error: bool
    tool_use_id: str


@dataclass
class SessionUpdateEvent:
    type: str  # "session_update"
    session_id: str
    claude_session_id: str


@dataclass
class DoneEvent:
    type: str  # "done"
    session_id: str


@dataclass
class ErrorEvent:
    type: str  # "error"
    session_id: str
    message: str


ResponseEventTypes = Union[
    TextEvent, ToolUseEvent, ToolResultEvent,
    SessionUpdateEvent, DoneEvent, ErrorEvent,
]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def serialize_event(event: PromptEventTypes | ResponseEventTypes) -> dict[str, str]:
    """Serialize a dataclass event into a flat dict of strings for Redis XADD."""
    data: dict[str, str] = {}
    for key, value in event.__dict__.items():
        if value is None:
            continue
        if isinstance(value, bool):
            data[key] = "1" if value else "0"
        else:
            data[key] = str(value)
    return data


def deserialize_prompt_event(raw: dict[str, str]) -> PromptEventTypes:
    """Deserialize a Redis stream entry into a prompt event."""
    event_type = raw["type"]
    if event_type == "prompt":
        return PromptEvent(
            type=event_type,
            session_id=raw["session_id"],
            text=raw["text"],
            claude_session_id=raw.get("claude_session_id"),
        )
    if event_type == "cancel":
        return CancelEvent(type=event_type, session_id=raw["session_id"])
    raise ValueError(f"Unknown prompt event type: {event_type}")


def deserialize_response_event(raw: dict[str, str]) -> ResponseEventTypes:
    """Deserialize a Redis stream entry into a response event."""
    event_type = raw["type"]
    if event_type == "text":
        return TextEvent(
            type=event_type,
            session_id=raw["session_id"],
            text=raw["text"],
        )
    if event_type == "tool_use":
        return ToolUseEvent(
            type=event_type,
            session_id=raw["session_id"],
            tool_name=raw["tool_name"],
            tool_input=raw["tool_input"],
        )
    if event_type == "tool_result":
        return ToolResultEvent(
            type=event_type,
            session_id=raw["session_id"],
            content=raw["content"],
            is_error=raw.get("is_error", "0") == "1",
            tool_use_id=raw.get("tool_use_id", ""),
        )
    if event_type == "session_update":
        return SessionUpdateEvent(
            type=event_type,
            session_id=raw["session_id"],
            claude_session_id=raw["claude_session_id"],
        )
    if event_type == "done":
        return DoneEvent(type=event_type, session_id=raw["session_id"])
    if event_type == "error":
        return ErrorEvent(
            type=event_type,
            session_id=raw["session_id"],
            message=raw.get("message", ""),
        )
    raise ValueError(f"Unknown response event type: {event_type}")
