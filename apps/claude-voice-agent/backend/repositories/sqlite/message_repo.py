from __future__ import annotations

from datetime import datetime

from models.message import Message
from repositories.base import MessageRepositoryBase
from repositories.sqlite.connection import SQLiteConnectionManager


class SQLiteMessageRepository(MessageRepositoryBase):
    def __init__(self, db: SQLiteConnectionManager):
        self._db = db

    def _row_to_message(self, row) -> Message:
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            text=row["text"],
            tool_name=row["tool_name"],
            tool_input=row["tool_input"],
            is_error=bool(row["is_error"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            sequence=row["sequence"],
        )

    def create(self, message: Message) -> Message:
        conn = self._db.get_connection()
        conn.execute(
            """
            INSERT INTO messages
                (id, session_id, role, text, tool_name, tool_input, is_error, created_at, sequence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.session_id,
                message.role,
                message.text,
                message.tool_name,
                message.tool_input,
                int(message.is_error),
                message.created_at.isoformat(),
                message.sequence,
            ),
        )
        conn.commit()
        return message

    def create_many(self, messages: list[Message]) -> list[Message]:
        if not messages:
            return []
        conn = self._db.get_connection()
        conn.executemany(
            """
            INSERT INTO messages
                (id, session_id, role, text, tool_name, tool_input, is_error, created_at, sequence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    m.id,
                    m.session_id,
                    m.role,
                    m.text,
                    m.tool_name,
                    m.tool_input,
                    int(m.is_error),
                    m.created_at.isoformat(),
                    m.sequence,
                )
                for m in messages
            ],
        )
        conn.commit()
        return messages

    def get_by_session_id(self, session_id: str) -> list[Message]:
        conn = self._db.get_connection()
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def delete_by_session_id(self, session_id: str) -> int:
        conn = self._db.get_connection()
        cursor = conn.execute(
            "DELETE FROM messages WHERE session_id = ?", (session_id,)
        )
        conn.commit()
        return cursor.rowcount

    def get_max_sequence(self, session_id: str) -> int:
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT COALESCE(MAX(sequence), -1) AS max_seq FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["max_seq"]
