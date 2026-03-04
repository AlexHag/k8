from __future__ import annotations

from datetime import datetime, timezone

from models.session import Session
from repositories.base import SessionRepositoryBase
from repositories.sqlite.connection import SQLiteConnectionManager


class SQLiteSessionRepository(SessionRepositoryBase):
    def __init__(self, db: SQLiteConnectionManager):
        self._db = db

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row["id"],
            title=row["title"],
            mode=row["mode"],
            claude_session_id=row["claude_session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create(self, session: Session) -> Session:
        conn = self._db.get_connection()
        conn.execute(
            """
            INSERT INTO sessions (id, title, mode, claude_session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.title,
                session.mode,
                session.claude_session_id,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        conn.commit()
        return session

    def get_by_id(self, session_id: str) -> Session | None:
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_all(self) -> list[Session]:
        conn = self._db.get_connection()
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update(self, session: Session) -> Session:
        session.updated_at = datetime.now(timezone.utc)
        conn = self._db.get_connection()
        conn.execute(
            """
            UPDATE sessions
            SET title = ?, mode = ?, claude_session_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                session.title,
                session.mode,
                session.claude_session_id,
                session.updated_at.isoformat(),
                session.id,
            ),
        )
        conn.commit()
        return session

    def delete(self, session_id: str) -> bool:
        conn = self._db.get_connection()
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
