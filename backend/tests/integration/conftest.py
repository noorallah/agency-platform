"""Fixtures for tests that need a real PostgreSQL server.

The unit suite builds a SQLite database where every table lives in one schema.
That is why it could not see the defect this suite exists to catch: firm-owned
routers resolved ``firms``/``user_firms`` on a tenant session whose search_path
is the firm schema, and those tables exist only in the platform schema. Anything
involving multiple schemas, PostgreSQL-only constraints, database triggers or
real concurrency is invisible to SQLite.

Every test here is skipped when no server is reachable, so the suite stays
runnable on a laptop with no database.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

# Importing the model modules registers every table on Base.metadata.
import tests.conftest  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base


def _engine_or_skip() -> Engine:
    """Return an engine for the configured server, or skip the test."""
    try:
        settings = Settings()
    except Exception as error:  # pragma: no cover - configuration problem
        pytest.skip(f"settings unavailable: {error}")
    if settings.database_dialect != "postgresql":
        pytest.skip("integration tests require PostgreSQL")
    from app.core.database.engine import DatabaseManager

    engine = DatabaseManager.from_settings(settings).engine
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except Exception as error:
        pytest.skip(f"PostgreSQL not reachable: {type(error).__name__}")
    return engine


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Provide a connection to the configured PostgreSQL server."""
    return _engine_or_skip()


@pytest.fixture
def temp_schema(engine: Engine) -> Iterator[str]:
    """Create a disposable schema holding the full ORM schema, then drop it.

    Tests never write to platform, firm_shared or any real firm schema; each one
    gets its own namespace so a failure cannot leave debris behind or disturb
    development data.
    """
    name = f"it_{uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
    try:
        Base.metadata.create_all(
            engine.execution_options(schema_translate_map={None: name})
        )
        yield name
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))


@pytest.fixture
def temp_session(engine: Engine, temp_schema: str) -> Iterator[Session]:
    """Yield a session bound to the disposable schema, as a tenant request is."""
    bind = engine.execution_options(schema_translate_map={None: temp_schema})
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    session = factory()
    session.execute(text(f'SET search_path TO "{temp_schema}"'))
    try:
        yield session
    finally:
        session.rollback()
        session.close()
