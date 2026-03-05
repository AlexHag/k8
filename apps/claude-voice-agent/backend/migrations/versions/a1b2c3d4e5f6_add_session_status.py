"""add session status

Revision ID: a1b2c3d4e5f6
Revises: ff8628ce7f8a
Create Date: 2026-03-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ff8628ce7f8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("status", sa.Text, nullable=False, server_default="idle"),
    )


def downgrade() -> None:
    op.drop_column("sessions", "status")
