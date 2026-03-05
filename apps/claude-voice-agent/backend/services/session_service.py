from __future__ import annotations

from datetime import datetime, timezone

from models.session import Session
from models.message import Message
from repositories.base import SessionRepositoryBase, MessageRepositoryBase


class SessionService:
    def __init__(
        self,
        session_repo: SessionRepositoryBase,
        message_repo: MessageRepositoryBase,
    ):
        self._session_repo = session_repo
        self._message_repo = message_repo

    def create_session(self, title: str, mode: str) -> Session:
        session = Session(title=title, mode=mode)
        return self._session_repo.create(session)

    def get_session(self, session_id: str) -> Session | None:
        return self._session_repo.get_by_id(session_id)

    def list_sessions(self) -> list[Session]:
        return self._session_repo.list_all()

    def get_session_with_messages(self, session_id: str) -> dict | None:
        session = self._session_repo.get_by_id(session_id)
        if session is None:
            return None
        messages = self._message_repo.get_by_session_id(session_id)
        return {
            **session.to_dict(),
            "messages": [m.to_dict() for m in messages],
        }

    def update_session_title(self, session_id: str, title: str) -> Session | None:
        session = self._session_repo.get_by_id(session_id)
        if session is None:
            return None
        session.title = title
        session.updated_at = datetime.now(timezone.utc)
        return self._session_repo.update(session)

    def update_claude_session_id(
        self, session_id: str, claude_sid: str
    ) -> Session | None:
        session = self._session_repo.get_by_id(session_id)
        if session is None:
            return None
        session.claude_session_id = claude_sid
        return self._session_repo.update(session)

    def update_status(self, session_id: str, status: str) -> Session | None:
        session = self._session_repo.get_by_id(session_id)
        if session is None:
            return None
        session.status = status
        session.updated_at = datetime.now(timezone.utc)
        return self._session_repo.update(session)

    def delete_session(self, session_id: str) -> bool:
        self._message_repo.delete_by_session_id(session_id)
        return self._session_repo.delete(session_id)

    def get_messages(self, session_id: str) -> list[Message]:
        return self._message_repo.get_by_session_id(session_id)

    def save_message(self, message: Message) -> Message:
        return self._message_repo.create(message)

    def save_messages(self, messages: list[Message]) -> list[Message]:
        return self._message_repo.create_many(messages)

    def get_next_sequence(self, session_id: str) -> int:
        return self._message_repo.get_max_sequence(session_id) + 1
