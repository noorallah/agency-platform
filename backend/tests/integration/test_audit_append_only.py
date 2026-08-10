"""The audit trail's append-only guarantee, which only a database can make.

``TR_audit_logs_append_only`` is the reason CLAUDE.md can call the audit trail
immutable: a BEFORE UPDATE OR DELETE trigger that raises unconditionally. It had
no test at all, in a system whose per-firm audit trails are a compliance
artefact.

These tests deliberately do **not** use the ``temp_schema`` fixture. That
fixture builds its schema with ``Base.metadata.create_all``, which emits tables
and indexes and no triggers, so an append-only test written against it would
pass while proving nothing. The guarantee lives in a migration, so the test has
to look at a migrated schema.

Nothing is left behind: every test runs inside a transaction that is always
rolled back, so the rows it writes never commit.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import InternalError, ProgrammingError

# Every schema that carries firm-owned or platform-owned audit rows. 20260809_0043
# exists because the original migration created the trigger without a schema
# qualifier, so it landed in one schema only.
_MIGRATED_SCHEMAS = ("platform", "firm_shared")


@pytest.fixture(params=_MIGRATED_SCHEMAS)
def migrated_schema(
    request: pytest.FixtureRequest, engine: Engine
) -> Iterator[tuple[Connection, str]]:
    """Yield a rolled-back connection pinned to a real, migrated schema."""
    schema = request.param
    with engine.connect() as connection:
        exists = connection.execute(
            text(
                "select 1 from information_schema.tables "
                "where table_schema = :s and table_name = 'audit_logs'"
            ),
            {"s": schema},
        ).scalar()
        if not exists:
            pytest.skip(f"{schema}.audit_logs is not deployed here")
        # The lookup above autobegins the transaction, so it is rolled back at
        # the end rather than opened explicitly here.
        connection.execute(text(f'SET search_path TO "{schema}"'))
        try:
            yield connection, schema
        finally:
            connection.rollback()


def _insert_audit_row(connection: Connection, schema: str) -> str:
    """Write one audit row and return its id."""
    row_id = str(uuid4())
    connection.execute(
        text(
            f"INSERT INTO {schema}.audit_logs "  # noqa: S608 - schema is a literal
            "(id, action, entity_type, entity_id, created_at, updated_at, "
            " is_deleted, version) "
            "VALUES (:id, 'test.appended', 'test_entity', :entity, now(), now(), "
            " false, 0)"
        ),
        {"id": row_id, "entity": str(uuid4())},
    )
    return row_id


def test_the_trigger_is_installed_in_every_audited_schema(
    migrated_schema: tuple[Connection, str],
) -> None:
    """Each store enforces its own trail; one schema's trigger cannot cover another."""
    connection, schema = migrated_schema
    installed = (
        connection.execute(
            text(
                "select t.tgname from pg_trigger t "
                "join pg_class c on c.oid = t.tgrelid "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = :s and c.relname = 'audit_logs' "
                "and not t.tgisinternal"
            ),
            {"s": schema},
        )
        .scalars()
        .all()
    )
    assert "TR_audit_logs_append_only" in installed


def test_an_audit_row_cannot_be_updated(
    migrated_schema: tuple[Connection, str],
) -> None:
    """Rewriting history is refused by the database, not merely by convention."""
    connection, schema = migrated_schema
    row_id = _insert_audit_row(connection, schema)

    with pytest.raises((InternalError, ProgrammingError)) as caught:
        connection.execute(
            text(
                f"UPDATE {schema}.audit_logs SET action = 'test.rewritten' "  # noqa: S608
                "WHERE id = :id"
            ),
            {"id": row_id},
        )
    assert "append-only" in str(caught.value)


def test_an_audit_row_cannot_be_deleted(
    migrated_schema: tuple[Connection, str],
) -> None:
    """Nor can it be removed, which is the other half of an immutable trail."""
    connection, schema = migrated_schema
    row_id = _insert_audit_row(connection, schema)

    with pytest.raises((InternalError, ProgrammingError)) as caught:
        connection.execute(
            text(f"DELETE FROM {schema}.audit_logs WHERE id = :id"),  # noqa: S608
            {"id": row_id},
        )
    assert "append-only" in str(caught.value)


def test_a_soft_delete_is_refused_like_a_hard_one(
    migrated_schema: tuple[Connection, str],
) -> None:
    """`is_deleted` is on the table because every entity has it.

    Setting it is still an UPDATE, so the trigger refuses it: an audit row
    cannot be hidden any more than it can be removed.
    """
    connection, schema = migrated_schema
    row_id = _insert_audit_row(connection, schema)

    with pytest.raises((InternalError, ProgrammingError)):
        connection.execute(
            text(
                f"UPDATE {schema}.audit_logs SET is_deleted = true "  # noqa: S608
                "WHERE id = :id"
            ),
            {"id": row_id},
        )


def test_the_trail_still_accepts_new_rows(
    migrated_schema: tuple[Connection, str],
) -> None:
    """Append-only means append works.

    Without this the refusal tests could pass for the wrong reason: an UPDATE
    that matches no row does not fire a FOR EACH ROW trigger, so a broken
    INSERT would look like enforcement.
    """
    connection, schema = migrated_schema
    row_id = _insert_audit_row(connection, schema)

    stored = connection.execute(
        text(f"SELECT action FROM {schema}.audit_logs WHERE id = :id"),  # noqa: S608
        {"id": row_id},
    ).scalar()
    assert stored == "test.appended"
