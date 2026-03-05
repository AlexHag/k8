"""create sessions and messages tables

Revision ID: ff8628ce7f8a
Revises: 
Create Date: 2026-03-04 19:17:43.632776

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ff8628ce7f8a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
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

    op.create_table(
        "messages",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("session_id", sa.Text, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
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
    )

    op.create_index("idx_messages_session_id", "messages", ["session_id"])
    op.create_index("idx_messages_session_sequence", "messages", ["session_id", "sequence"])


def downgrade() -> None:
    op.drop_index("idx_messages_session_sequence", table_name="messages")
    op.drop_index("idx_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("sessions")
