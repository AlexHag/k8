from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import registry as sa_registry

from models.session import Session
from models.message import Message

mapper_registry = sa_registry()
metadata = mapper_registry.metadata

sessions_table = sa.Table(
    "sessions",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("mode", sa.Text, nullable=False),
    sa.Column("claude_session_id", sa.Text, nullable=True),
    sa.Column(
        "created_at",
        sa.DateTime,
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime,
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
)

messages_table = sa.Table(
    "messages",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column(
        "session_id",
        sa.Text,
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("tool_name", sa.Text, nullable=True),
    sa.Column("tool_input", sa.Text, nullable=True),
    sa.Column("is_error", sa.Boolean, nullable=False, server_default=sa.False_()),
    sa.Column(
        "created_at",
        sa.DateTime,
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column("sequence", sa.Integer, nullable=False),
    sa.Index("idx_messages_session_id", "session_id"),
    sa.Index("idx_messages_session_sequence", "session_id", "sequence"),
)


def start_mappers() -> None:
    """Register imperative mappings. Safe to call multiple times."""
    if _is_mapped():
        return
    mapper_registry.map_imperatively(Session, sessions_table)
    mapper_registry.map_imperatively(Message, messages_table)


def _is_mapped() -> bool:
    try:
        sa.inspect(Session)
        return True
    except sa.exc.NoInspectionAvailable:
        return False
