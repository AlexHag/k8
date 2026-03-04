from __future__ import annotations

import os
import sqlite3
import threading


class SQLiteConnectionManager:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    @property
    def db_path(self) -> str:
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self._db_path)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        return self._local.connection

    def init_db(self) -> None:
        conn = self.get_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                mode TEXT NOT NULL,
                claude_session_id TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                tool_name TEXT,
                tool_input TEXT,
                is_error BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sequence INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_session_sequence
                ON messages(session_id, sequence);
            """
        )
        conn.commit()
