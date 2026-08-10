"""The optimistic-concurrency counter, under two real sessions.

``BaseEntity`` declares ``version`` as the mapper's ``version_id_col``, so every
ORM update adds ``WHERE version = :loaded`` and a write aimed at a row someone
else has already changed matches nothing. ``database_error_handler`` turns the
resulting ``StaleDataError`` into a 409.

The claim spans the ORM, the database and the error handler, and none of it had
a test. Two sessions against a real server is the only way to make the race
happen rather than assert that it would.
"""

import asyncio
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions.handlers import database_error_handler
from app.firms.models import Firm


@pytest.fixture
def two_sessions(engine: Engine, temp_schema: str) -> Iterator[tuple[Session, Session]]:
    """Two independent sessions onto one disposable schema."""
    bind = engine.execution_options(schema_translate_map={None: temp_schema})
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    first, second = factory(), factory()
    try:
        yield first, second
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()


def _firm(session: Session, code: str) -> Firm:
    """Commit one firm and return it."""
    row = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def test_the_second_writer_of_a_row_is_refused(
    two_sessions: tuple[Session, Session],
) -> None:
    """Both sessions read the same version; only the first write may land."""
    first, second = two_sessions
    created = _firm(first, "RACE1")

    mine = first.get(Firm, created.id)
    theirs = second.get(Firm, created.id)
    assert mine is not None and theirs is not None
    assert mine.version == theirs.version, "both loaded the same version"

    mine.name = "Renamed by the first writer"
    first.commit()

    theirs.name = "Renamed by the second writer"
    with pytest.raises(StaleDataError):
        second.commit()

    second.rollback()
    assert first.get(Firm, created.id).name == "Renamed by the first writer"


def test_the_counter_moves_on_every_write(
    two_sessions: tuple[Session, Session],
) -> None:
    """A stale write is detected because the counter advanced, so check it does."""
    first, _ = two_sessions
    created = _firm(first, "RACE2")
    started_at = created.version

    created.name = "First edit"
    first.commit()
    created.name = "Second edit"
    first.commit()

    first.expire_all()
    assert first.get(Firm, created.id).version == started_at + 2


def test_a_reload_lets_the_second_writer_succeed(
    two_sessions: tuple[Session, Session],
) -> None:
    """The 409 tells a client to reload, so reloading has to be a way through."""
    first, second = two_sessions
    created = _firm(first, "RACE3")

    mine = first.get(Firm, created.id)
    theirs = second.get(Firm, created.id)
    assert mine is not None and theirs is not None

    mine.name = "First writer"
    first.commit()

    second.rollback()
    reloaded = second.get(Firm, created.id)
    assert reloaded is not None
    second.refresh(reloaded)
    reloaded.name = "Second writer, after reloading"
    second.commit()

    first.expire_all()
    assert first.get(Firm, created.id).name == "Second writer, after reloading"


def test_a_stale_write_surfaces_as_409() -> None:
    """The handler is what turns the race into an answer a client can act on."""
    response = asyncio.run(
        database_error_handler(
            None,  # type: ignore[arg-type]
            StaleDataError("UPDATE on table 'firms' expected to update 1 row"),
        )
    )
    assert response.status_code == 409
    assert b"changed since you loaded it" in response.body


def test_the_handler_refuses_anything_that_is_not_a_database_error() -> None:
    """It is registered for SQLAlchemyError; anything else is a programming fault."""
    with pytest.raises(TypeError):
        asyncio.run(
            database_error_handler(None, ValueError("not a database error"))  # type: ignore[arg-type]
        )


def test_every_entity_carries_the_counter(temp_schema: str, engine: Engine) -> None:
    """The guarantee is only as wide as the column.

    ``version`` comes from ``BaseEntity``, so a table without it is a table that
    silently opted out of concurrency control. ``uom_conversion_rules`` is why
    this is worth checking: it declared its own business column named
    ``version`` and took the counter's place until 20260809_0055.

    ``audit_logs`` is the one deliberate exception. It extends ``UUIDMixin,
    Base`` rather than ``BaseEntity`` because an append-only log has nothing to
    reconcile: it is never updated, and a trigger enforces that. The deployed
    tables do carry a ``version`` column from an older migration, but the ORM
    does not map it and nothing reads it.
    """
    with engine.connect() as connection:
        missing = (
            connection.exec_driver_sql(
                """
            select t.table_name
            from information_schema.tables t
            where t.table_schema = %(schema)s
              and t.table_type = 'BASE TABLE'
              and t.table_name not in ('alembic_version', 'audit_logs')
              and not exists (
                select 1 from information_schema.columns c
                where c.table_schema = t.table_schema
                  and c.table_name = t.table_name
                  and c.column_name = 'version'
              )
            """,
                {"schema": temp_schema},
            )
            .scalars()
            .all()
        )
    assert missing == [], f"tables without an optimistic-concurrency counter: {missing}"
