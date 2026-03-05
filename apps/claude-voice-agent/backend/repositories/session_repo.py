from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import scoped_session

from models.session import Session
from repositories.base import SessionRepositoryBase


class SessionRepository(SessionRepositoryBase):
    def __init__(self, db_session: scoped_session):
        self._db = db_session

    def create(self, session: Session) -> Session:
        self._db.add(session)
        self._db.commit()
        return session

    def get_by_id(self, session_id: str) -> Session | None:
        return self._db.get(Session, session_id)

    def list_all(self) -> list[Session]:
        return (
            self._db.query(Session)
            .order_by(Session.updated_at.desc())
            .all()
        )

    def update(self, session: Session) -> Session:
        session.updated_at = datetime.now(timezone.utc)
        self._db.merge(session)
        self._db.commit()
        return session

    def delete(self, session_id: str) -> bool:
        session = self._db.get(Session, session_id)
        if session is None:
            return False
        self._db.delete(session)
        self._db.commit()
        return True
