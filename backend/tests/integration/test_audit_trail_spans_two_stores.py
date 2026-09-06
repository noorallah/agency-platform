"""A firm's audit trail includes the platform rows that belong to that firm.

A firm's history is written to its own store, except for the part that is not.
`users`, `roles` and `user_firms` live only in the platform schema, so
administering a firm's people runs on the platform session and `record_audit`
writes there. Those rows carry the firm on `firm_id` -- they were simply in a
store the firm cannot read, so a firm administrator could not see their own
hiring, role edits or promotions in their own Audit Logs.

`AuditLogReader.list_events_with` merges the two on the **read**. Moving the
write was the alternative and was rejected: a DATABASE-mode firm is a separate
database, possibly on a separate server, so the audit row would be a second
transaction -- the promotion could commit and its record fail, or the reverse.
Today they commit together, and that is worth more than the row's location.

This is exactly the class of change the unit suite cannot see. It builds one
SQLite schema holding every table, so "the firm's store" and "the platform
store" are the same table there and the merge collapses to a single read. Two
real schemas are the only way to check that rows combine, that the order holds
across both, and that one firm never sees another's.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.common.audit.models import AuditLog
from app.common.audit.schemas import AuditLogFilters
from app.common.audit.services.reader import AuditLogReader
from app.core.config.settings import Settings
from app.core.utils.dates import utc_now

_SETTINGS = Settings()
_URL = _SETTINGS.database_url or (
    f"postgresql+psycopg://{_SETTINGS.database_username}:"
    f"{_SETTINGS.database_password.get_secret_value()}"
    f"@{_SETTINGS.database_host}:{_SETTINGS.database_port}/"
    f"{_SETTINGS.database_name}"
)


@contextmanager
def _stores(schemas: tuple[str, str]) -> Iterator[tuple[Session, Session]]:
    """Open a session on each schema, and **close both**.

    Two things here, both learned the hard way.

    **Closing is not tidiness.** A session left open sits `idle in
    transaction` holding a lock on `audit_logs`, and the fixture's
    `DROP SCHEMA ... CASCADE` then blocks on it for ever -- the test hangs at
    teardown rather than failing, which reads as a slow database and is not
    one. It wedged three runs before `pg_stat_activity` showed
    `Lock/relation` sitting behind the drop.

    **And the schema is chosen with `schema_translate_map`, not
    `SET search_path`.** The latter is *session* state on a pooled
    connection: it survives the return to the pool, so the next test to
    borrow that connection silently runs against this schema. Doing it that
    way passed these tests and broke
    `test_firm_scope_resolves_membership_on_the_platform_session` further
    down the run -- a failure in a file this one does not touch, which is the
    worst shape a test-only bug can take.
    """
    own = create_engine(_URL)
    sessions = tuple(
        sessionmaker(
            bind=own.execution_options(schema_translate_map={None: schema}),
            expire_on_commit=False,
        )()
        for schema in schemas
    )
    try:
        yield sessions[0], sessions[1]
    finally:
        for session in sessions:
            session.rollback()
            session.close()
        own.dispose()


def _event(
    session: Session, action: str, firm_id: UUID | None, minutes_ago: int
) -> None:
    """Write one audit row directly, at a known instant."""
    session.add(
        AuditLog(
            action=action,
            entity_type="user",
            entity_id=uuid4(),
            actor_id=uuid4(),
            firm_id=firm_id,
            created_at=utc_now() - timedelta(minutes=minutes_ago),
        )
    )
    session.commit()


def _page(
    firm_store: Session,
    platform_store: Session,
    *,
    firm_scope: UUID,
    filters: AuditLogFilters | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditLog], int]:
    """Read one page of the merged trail."""
    return AuditLogReader(firm_store).list_events_with(
        AuditLogReader(platform_store),
        firm_scope=firm_scope,
        filters=filters or AuditLogFilters(),
        page=page,
        page_size=page_size,
    )


def test_a_firms_trail_includes_its_platform_rows(
    audit_store_pair: tuple[str, str],
) -> None:
    """The whole point: staffing decisions show up in the firm's own trail.

    `user_template.applied` is written on the platform session -- that is where
    `user_roles` lives -- so before this it was invisible to the firm whose
    person had just been promoted.
    """
    firm_id, other_firm = uuid4(), uuid4()
    with _stores(audit_store_pair) as (firm_store, platform_store):
        # What the firm itself did, in its own store.
        _event(firm_store, "customer.created", firm_id, minutes_ago=30)
        _event(firm_store, "sales_invoice.approved", firm_id, minutes_ago=10)
        # What was done *to* the firm's people, on the platform session.
        _event(platform_store, "user_template.applied", firm_id, minutes_ago=20)
        # Another firm's promotion, and a platform act belonging to nobody.
        _event(platform_store, "user_template.applied", other_firm, minutes_ago=15)
        _event(platform_store, "firm.created", None, minutes_ago=5)

        rows, total = _page(firm_store, platform_store, firm_scope=firm_id)

        assert total == 3
        # Newest first across both stores, not one store after the other.
        assert [row.action for row in rows] == [
            "sales_invoice.approved",
            "user_template.applied",
            "customer.created",
        ]
        # One firm never sees another's, and the platform's own unscoped rows
        # are nobody's firm history.
        assert all(row.firm_id == firm_id for row in rows)


def test_the_merge_pages_across_both_stores(
    audit_store_pair: tuple[str, str],
) -> None:
    """Page two is the second page of the *combined* order, not of one store.

    A union that paged each store separately would repeat and drop rows at
    every boundary. `page * page_size` is taken from each and the slice comes
    out of the merged order, which is why deep paging costs more here.
    """
    firm_id = uuid4()
    with _stores(audit_store_pair) as (firm_store, platform_store):
        # Interleaved on purpose: the stores alternate by age, so a per-store
        # pager would visibly get the order wrong.
        for minute in range(6):
            store = firm_store if minute % 2 == 0 else platform_store
            _event(store, f"event.{minute}", firm_id, minutes_ago=minute)

        first, total = _page(
            firm_store, platform_store, firm_scope=firm_id, page=1, page_size=2
        )
        second, _ = _page(
            firm_store, platform_store, firm_scope=firm_id, page=2, page_size=2
        )

        assert total == 6
        # Newest first: 0 minutes ago is the newest.
        assert [row.action for row in first] == ["event.0", "event.1"]
        assert [row.action for row in second] == ["event.2", "event.3"]
        assert not {row.id for row in first} & {row.id for row in second}


def test_a_filter_reaches_both_stores(
    audit_store_pair: tuple[str, str],
) -> None:
    """Filtering one store and not the other would answer a half-truth."""
    firm_id = uuid4()
    with _stores(audit_store_pair) as (firm_store, platform_store):
        _event(firm_store, "user_template.applied", firm_id, minutes_ago=30)
        _event(firm_store, "customer.created", firm_id, minutes_ago=20)
        _event(platform_store, "user_template.applied", firm_id, minutes_ago=10)

        rows, total = _page(
            firm_store,
            platform_store,
            firm_scope=firm_id,
            filters=AuditLogFilters(action="user_template.applied"),
        )

        assert total == 2
        assert {row.action for row in rows} == {"user_template.applied"}


def test_one_store_read_twice_is_refused(
    audit_store_pair: tuple[str, str],
) -> None:
    """Merging a store with itself would double every row and the total.

    It is reachable rather than hypothetical: the unit suite builds one schema
    holding every table, so both dependencies resolve to the same session
    there, and a doubled trail would look like history nobody wrote.
    """
    firm_id = uuid4()
    with _stores(audit_store_pair) as (store, _unused):
        _event(store, "customer.created", firm_id, minutes_ago=10)
        _event(store, "user_template.applied", firm_id, minutes_ago=5)

        reader = AuditLogReader(store)
        rows, total = reader.list_events_with(
            reader,
            firm_scope=firm_id,
            filters=AuditLogFilters(),
            page=1,
            page_size=20,
        )

        assert total == 2
        assert len(rows) == 2
