"""Transaction boundary abstractions for application services."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from types import TracebackType

from sqlalchemy.orm import Session

from app.core.database.session import SessionManager


class UnitOfWork(ABC):
    """Define the transaction boundary used by future application services."""

    session: Session

    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        """Open the unit of work."""

    @abstractmethod
    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the unit of work, rolling back unfinished work."""

    @abstractmethod
    def commit(self) -> None:
        """Persist the current transaction."""

    @abstractmethod
    def rollback(self) -> None:
        """Discard the current transaction."""


class SQLAlchemyUnitOfWork(UnitOfWork):
    """Manage one SQLAlchemy session and its transaction lifecycle."""

    def __init__(self, session_manager: SessionManager) -> None:
        """Store the manager used to create a transaction-scoped session."""
        self._session_manager = session_manager
        self._session_context: AbstractContextManager[Session] | None = None

    def __enter__(self) -> "SQLAlchemyUnitOfWork":
        """Open a session for use by services and repositories."""
        session_context = self._session_manager.session()
        self._session_context = session_context
        self.session = session_context.__enter__()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Rollback uncommitted work after errors, then close the session."""
        if exception_type is not None:
            self.rollback()
        session_context = self._session_context
        if session_context is not None:
            session_context.__exit__(exception_type, exception, traceback)

    def commit(self) -> None:
        """Commit the active transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the active transaction."""
        self.session.rollback()
