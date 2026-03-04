from __future__ import annotations

from abc import ABC, abstractmethod

from models.session import Session
from models.message import Message


class SessionRepositoryBase(ABC):
    @abstractmethod
    def create(self, session: Session) -> Session: ...

    @abstractmethod
    def get_by_id(self, session_id: str) -> Session | None: ...

    @abstractmethod
    def list_all(self) -> list[Session]: ...

    @abstractmethod
    def update(self, session: Session) -> Session: ...

    @abstractmethod
    def delete(self, session_id: str) -> bool: ...


class MessageRepositoryBase(ABC):
    @abstractmethod
    def create(self, message: Message) -> Message: ...

    @abstractmethod
    def create_many(self, messages: list[Message]) -> list[Message]: ...

    @abstractmethod
    def get_by_session_id(self, session_id: str) -> list[Message]: ...

    @abstractmethod
    def delete_by_session_id(self, session_id: str) -> int: ...

    @abstractmethod
    def get_max_sequence(self, session_id: str) -> int: ...
