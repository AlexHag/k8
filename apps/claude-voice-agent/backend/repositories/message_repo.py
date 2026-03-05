from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import scoped_session

from models.message import Message
from repositories.base import MessageRepositoryBase


class MessageRepository(MessageRepositoryBase):
    def __init__(self, db_session: scoped_session):
        self._db = db_session

    def create(self, message: Message) -> Message:
        self._db.add(message)
        self._db.commit()
        return message

    def create_many(self, messages: list[Message]) -> list[Message]:
        if not messages:
            return []
        self._db.add_all(messages)
        self._db.commit()
        return messages

    def get_by_session_id(self, session_id: str) -> list[Message]:
        return (
            self._db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.sequence.asc())
            .all()
        )

    def delete_by_session_id(self, session_id: str) -> int:
        count = (
            self._db.query(Message)
            .filter(Message.session_id == session_id)
            .delete()
        )
        self._db.commit()
        return count

    def get_max_sequence(self, session_id: str) -> int:
        result = (
            self._db.query(func.coalesce(func.max(Message.sequence), -1))
            .filter(Message.session_id == session_id)
            .scalar()
        )
        return result
