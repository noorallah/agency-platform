"""Per-operation SQLAlchemy session lifecycle management."""

import re
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

_SAFE_SCHEMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


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
        if self._schema is not None and bind.dialect.name == "postgresql":
            bind = bind.execution_options(schema_translate_map={None: self._schema})
        database_session = self._session_factory(bind=bind)
        try:
            self._apply_schema_search_path(database_session)
            yield database_session
        except Exception:
            database_session.rollback()
            raise
        finally:
            database_session.close()

    def _apply_schema_search_path(self, database_session: Session) -> None:
        if self._schema is None:
            return
        if not _SAFE_SCHEMA.fullmatch(self._schema):
            raise ValueError(f"Invalid schema name {self._schema!r}.")
        dialect = database_session.bind.dialect.name if database_session.bind else ""
        if dialect != "postgresql":
            return
        database_session.execute(text(f'SET search_path TO "{self._schema}"'))
