"""Per-operation SQLAlchemy session lifecycle management."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker


class SessionManager:
    """Create and close sessions without retaining global session instances."""

    def __init__(
        self, session_factory: sessionmaker[Session], schema: str | None = None
    ) -> None:
        """Initialize the factory and optional future schema translation context."""
        self._session_factory = session_factory
        self._schema = schema

    @contextmanager
    def session(self) -> Generator[Session]:
        """Yield one session and ensure failed work is rolled back and closed."""
        bind = self._session_factory.kw["bind"]
        if self._schema is not None:
            bind = bind.execution_options(schema_translate_map={None: self._schema})
        database_session = self._session_factory(bind=bind)
        try:
            yield database_session
        except Exception:
            database_session.rollback()
            raise
        finally:
            database_session.close()
