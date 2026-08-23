"""A by-salesman report must not reach for `users` on the firm's session.

`users` exists only in the platform schema. `SalesOrderService.by_salesman`
and `DeliveryNoteService.by_salesman_report` both ran ``select(User)`` on the
request session, so on PostgreSQL the report raised ``UndefinedTable`` and
answered 503.

It sat latent because the branch only runs once a document *carries* a
salesman, and no seeded document does. Driving it proved the point: both
reports answered 200 against a real dedicated-database firm until one order and
one note were tagged, and then both answered "The database is temporarily
unavailable."

Fifth occurrence of the trap, after territory search, global search and two
others recorded in CLAUDE.md. The **sixth** was the write path of the same
field, found the next day and covered at the bottom of this file: validating
a `salesman_id` on create ran ``select(User)`` on the request session too, so
raising a sales order or a delivery note that named anybody answered 503 on
every firm outside the platform store. It stayed hidden for the same reason --
nothing sent a `salesman_id` until the desktop grew a picker for one.

This is the suite that can see it. The unit tests build one SQLite schema
holding every table, so `users` is always reachable there and the report passes
for the wrong reason.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.branches.models import Branch, Warehouse
from app.core.exceptions import ValidationError
from app.core.tenancy.lifecycle import _PLATFORM_TABLES
from app.customers.models import Customer
from app.delivery_note.services import DeliveryNoteService
from app.sales_order.services import SalesOrderService


@pytest.fixture
def pruned_schema(engine: Engine, temp_schema: str) -> Iterator[str]:
    """Build a firm schema shaped the way provisioning leaves one.

    `temp_schema` comes from `Base.metadata.create_all`, which gives it every
    table including `users` -- and that is exactly the difference that hides
    this defect. `prune_platform_objects` drops those from a real firm store,
    so the test drops them too.
    """
    with engine.begin() as connection:
        for table in _PLATFORM_TABLES:
            connection.execute(
                text(f'DROP TABLE IF EXISTS "{temp_schema}"."{table}" CASCADE')
            )
    yield temp_schema


@pytest.fixture
def tenant_session(engine: Engine, pruned_schema: str) -> Iterator[Session]:
    """Yield a session shaped like a request carrying `X-Firm-ID`."""
    bind = engine.execution_options(schema_translate_map={None: pruned_schema})
    session = sessionmaker(bind=bind, expire_on_commit=False)()
    session.execute(text(f'SET search_path TO "{pruned_schema}"'))
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_naming_a_salesman_does_not_reach_for_users_on_this_session(
    tenant_session: Session,
) -> None:
    """The exact line that broke, on both services.

    `users` is genuinely absent, asserted first -- otherwise a passing test
    could mean the pruning silently did nothing. Both services used to run
    ``select(User)`` here on the tenant session; both now read the platform
    store, and neither raises.
    """
    with pytest.raises(ProgrammingError):
        tenant_session.execute(text("select id from users limit 1"))
    tenant_session.rollback()

    unknown = uuid4()

    # Not a document-level test on purpose: a sales order carries real foreign
    # keys to customers, branches and warehouses, and building that graph to
    # reach one name lookup would test the fixture more than the fix.
    assert SalesOrderService(tenant_session)._salesman_names({unknown}) == {}
    assert DeliveryNoteService(tenant_session)._salesman_names({unknown}) == {}


def test_the_delivery_note_report_runs_against_a_pruned_store(
    tenant_session: Session,
) -> None:
    """The report itself, end to end on a store shaped like a real one."""
    with pytest.raises(ProgrammingError):
        tenant_session.execute(text("select id from users limit 1"))
    tenant_session.rollback()

    rows = DeliveryNoteService(tenant_session).by_salesman_report(firm_scope=uuid4())

    # No notes in this schema, so no rows. What matters is that asking did not
    # raise: the query shape is what used to fail the moment a note carried a
    # salesman.
    assert rows == []


def test_validating_a_salesman_on_create_does_not_reach_for_users_either(
    tenant_session: Session,
) -> None:
    """The write path of the same field, which broke the same way.

    `SalesOrderService` and `DeliveryNoteService` each validated a caller's
    `salesman_id` with ``select(User)`` on the request session. Reading a name
    for a report and checking a name on a create are different lines in
    different methods, and fixing the first did not fix the second: raising
    either document with a salesman named answered 503 on this shape of store.

    The customer, branch and warehouse are real rows because the validator
    checks them first and would otherwise refuse before reaching the line
    under test -- the one thing the report-side test above could skip.

    Both services now ask `FirmMetadataReader`, which reads the platform
    store, and ask the better question while they are there: the old check
    accepted any user that existed anywhere, so one firm could tag another
    firm's people on its own documents. A stranger is refused with a
    `ValidationError` rather than a database failure, which is the difference
    between a message somebody can act on and a 503.
    """
    with pytest.raises(ProgrammingError):
        tenant_session.execute(text("select id from users limit 1"))
    tenant_session.rollback()

    firm = uuid4()
    branch = Branch(
        firm_id=firm,
        code="HO",
        name="Head Office",
        display_name="Head Office",
        currency_code="INR",
        working_hours={},
        status="ACTIVE",
    )
    tenant_session.add(branch)
    tenant_session.flush()
    warehouse = Warehouse(
        firm_id=firm,
        branch_id=branch.id,
        code="MAIN",
        name="Main",
        display_name="Main",
        status="ACTIVE",
    )
    customer = Customer(
        firm_id=firm,
        code="C1",
        customer_type="RETAIL",
        name="Customer One",
        display_name="Customer One",
        currency_code="INR",
        status="ACTIVE",
    )
    tenant_session.add_all([warehouse, customer])
    tenant_session.flush()

    stranger = uuid4()
    for service in (
        SalesOrderService(tenant_session),
        DeliveryNoteService(tenant_session),
    ):
        with pytest.raises(ValidationError) as refusal:
            service._validate_scope_references(
                firm_id=firm,
                customer_id=customer.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                salesman_id=stranger,
                territory_id=None,
                route_id=None,
            )
        assert "active member" in str(refusal.value), type(service).__name__
