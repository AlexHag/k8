from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Message:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = ""
    text: str = ""
    tool_name: str | None = None
    tool_input: str | None = None
    is_error: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "text": self.text,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "is_error": self.is_error,
            "created_at": self.created_at.isoformat(),
            "sequence": self.sequence,
        }
