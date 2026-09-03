"""What optimistic concurrency protects, and what it does not.

Three modules were found guarding a write with a read that nothing held --
`loyalty.redeem`, `commission.accrue` and `credit_note`'s per-line cap (review
rows 39-41). Auditing the rest turned up the rule that separates them from the
sites that are already safe:

    Optimistic concurrency protects a decision made about a **row**. It
    protects nothing about a decision made about a **set** of rows.

`BaseEntity` sets `version_id_col`, so every ORM *update* carries
`WHERE version = :read` and a stale write raises `StaleDataError`. That covers
`inventory`, whose dispatch is a read-modify-write of one inventory row --
which is why the most alarming-looking guard in the codebase turns out to be
the safe one, and why the fix for the others is not "add a version".

It covers nothing where the guard sums or counts *other* rows and then
INSERTs. A customer's loyalty balance is a sum over entries and a credit
note's cap is a sum over other notes' lines; neither updates a row, so no
version can conflict, and two transactions that both read before either
commits both pass. Those need a lock on the thing being consumed -- the
customer, and the invoice line.
"""

# ruff: noqa: D103

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.pool import NullPool

from app.branches.models import Branch, Warehouse
from app.credit_note.services import CreditNoteService
from app.customers.models import Customer
from app.firms.models import Firm
from app.inventory.models.inventory import InventoryRecord
from app.loyalty.services import LoyaltyService
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine


@pytest.fixture
def sessions(engine: Engine, temp_schema: str) -> Iterator[Callable[[], Session]]:
    """Hand out ORM sessions on this file's own pool, bound to the schema.

    A pool of its own because these tests hold two connections at once and
    hand them back; a sibling that sets `search_path` on a pooled connection
    and expects it back fails once the pool has been shuffled. `NullPool`
    keeps nothing, so nothing of ours reaches anybody else's test.
    """
    own = create_engine(engine.url, poolclass=NullPool).execution_options(
        schema_translate_map={None: temp_schema}
    )
    made: list[Session] = []

    def factory() -> Session:
        session = sessionmaker(bind=own, expire_on_commit=False)()
        made.append(session)
        return session

    try:
        yield factory
    finally:
        for session in made:
            session.close()


def _shelf(session: Session) -> UUID:
    """Put 100 of something on a shelf, all of it available.

    The parents are real rows: `inventories` carries foreign keys to the firm,
    the branch, the warehouse and the product, and `create_all` builds all four
    in the disposable schema.
    """
    firm = Firm(
        name="Probe Firm",
        code=f"P{uuid4().hex[:6].upper()}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    branch = Branch(
        firm_id=firm.id,
        code="BR-1",
        name="Branch One",
        display_name="Branch One",
    )
    session.add(branch)
    session.flush()
    warehouse = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="WH-1",
        name="Warehouse One",
        display_name="Warehouse One",
    )
    product = Product(
        firm_id=firm.id,
        code="P-1",
        name="Product One",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add_all([warehouse, product])
    session.flush()
    row = InventoryRecord(
        firm_id=firm.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        storage_locator="A-1",
        current_quantity=Decimal("100"),
        reserved_quantity=Decimal("0"),
        available_quantity=Decimal("100"),
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row.id


def test_two_dispatches_of_one_shelf_cannot_both_win(
    sessions: Callable[[], Session],
) -> None:
    """A decision about a row is protected, and this is why.

    `_stage_movement` reads an inventory row's quantities, works the new ones
    out in Python and assigns them -- a read-modify-write with no lock, the
    same shape that made the other three unsafe. It is safe here because it
    *updates* a row: `BaseEntity` sets `version_id_col`, so the second
    transaction's UPDATE carries the version it read, matches nothing, and
    raises instead of overwriting.

    Pinned because it is the boundary of the rule. If the version column were
    ever taken off these rows, stock would begin overselling silently, and
    this is the test that would say so.
    """
    with sessions() as setup:
        shelf_id = _shelf(setup)

    one, two = sessions(), sessions()
    try:
        first = one.get(InventoryRecord, shelf_id)
        second = two.get(InventoryRecord, shelf_id)
        assert first is not None and second is not None
        # Both read the same 100 available, as two dispatch requests would.
        assert first.available_quantity == Decimal("100")
        assert second.available_quantity == Decimal("100")

        first.current_quantity = Decimal("40")
        first.available_quantity = Decimal("40")
        one.commit()

        second.current_quantity = Decimal("40")
        second.available_quantity = Decimal("40")
        with pytest.raises(StaleDataError):
            two.commit()
        two.rollback()
    finally:
        one.close()
        two.close()

    with sessions() as check:
        row = check.get(InventoryRecord, shelf_id)
        assert row is not None
        assert row.available_quantity == Decimal(
            "40"
        ), "one dispatch of 60 took effect, not two"


def test_a_row_nobody_else_touched_saves_normally(
    sessions: Callable[[], Session],
) -> None:
    """The guard must not refuse an ordinary write.

    Worth stating: a version check that refused everything would pass the test
    above for the wrong reason.
    """
    with sessions() as setup:
        shelf_id = _shelf(setup)

    with sessions() as session:
        row = session.get(InventoryRecord, shelf_id)
        assert row is not None
        row.available_quantity = Decimal("70")
        session.commit()

        assert row.available_quantity == Decimal("70")


def _customer(session: Session) -> tuple[UUID, UUID]:
    """Build a firm with one customer, which is what a balance belongs to."""
    firm = Firm(
        name="Probe Firm",
        code=f"P{uuid4().hex[:6].upper()}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    customer = Customer(
        firm_id=firm.id,
        code="C-1",
        customer_type="BUSINESS",
        name="Kumar Stores",
        display_name="Kumar Stores",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(customer)
    session.commit()
    return firm.id, customer.id


def test_a_second_redemption_waits_for_the_first(
    sessions: Callable[[], Session],
) -> None:
    """The hold serialises two redemptions of one customer's points.

    A balance is a sum over entries, so `BaseEntity.version` protects nothing
    here -- a redemption inserts, and there is no row whose version can
    conflict. `_hold_customer` takes the customer before the balance is read,
    and this is the proof it is really taken: the second transaction cannot
    get the row while the first holds it.
    """
    with sessions() as setup:
        firm_id, customer_id = _customer(setup)

    one, two = sessions(), sessions()
    try:
        LoyaltyService(one)._hold_customer(customer_id, firm_scope=firm_id)

        # Fail fast rather than hang the suite: without the hold this returns
        # immediately, and with it the row is unavailable.
        two.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(OperationalError):
            LoyaltyService(two)._hold_customer(customer_id, firm_scope=firm_id)
        two.rollback()
    finally:
        one.rollback()
        one.close()
        two.close()


def test_the_hold_is_per_customer_not_per_firm(
    sessions: Callable[[], Session],
) -> None:
    """Two tills serving different people must not queue behind each other."""
    with sessions() as setup:
        firm_id, first = _customer(setup)
        second_customer = Customer(
            firm_id=firm_id,
            code="C-2",
            customer_type="BUSINESS",
            name="Other Stores",
            display_name="Other Stores",
            currency_code="INR",
            status="ACTIVE",
        )
        setup.add(second_customer)
        setup.commit()
        second = second_customer.id

    one, two = sessions(), sessions()
    try:
        LoyaltyService(one)._hold_customer(first, firm_scope=firm_id)
        two.execute(text("SET LOCAL lock_timeout = '250ms'"))
        # No exception: a different customer is a different row.
        LoyaltyService(two)._hold_customer(second, firm_scope=firm_id)
        two.rollback()
    finally:
        one.rollback()
        one.close()
        two.close()


def test_a_second_credit_note_waits_for_the_line(
    sessions: Callable[[], Session],
) -> None:
    """The hold serialises two credit notes against one invoice line.

    The cap is a sum over other notes' lines, so nothing about it is
    protected by a version either -- and unlike the commission payout this
    one cannot be closed with a unique index, because a cap that is a sum is
    not a key. `_hold_line` takes the invoice line instead.
    """
    with sessions() as setup:
        firm_id, customer_id = _customer(setup)
        branch = Branch(firm_id=firm_id, code="BR-1", name="B", display_name="B")
        product = Product(
            firm_id=firm_id,
            code="P-1",
            name="Product One",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        setup.add_all([branch, product])
        setup.flush()
        invoice = SalesInvoice(
            firm_id=firm_id,
            customer_id=customer_id,
            branch_id=branch.id,
            invoice_number="SI-1",
            invoice_date=date(2026, 4, 20),
            status="APPROVED",
            grand_total=Decimal("1180"),
        )
        setup.add(invoice)
        setup.flush()
        line = SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=firm_id,
            line_number=1,
            source_document_type="SALES_ORDER",
            source_document_id=uuid4(),
            source_document_number="SO-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=product.id,
            delivered_quantity=Decimal("10"),
            gross_amount=Decimal("1000"),
            tax_amount=Decimal("180"),
            net_amount=Decimal("1180"),
        )
        setup.add(line)
        setup.commit()
        line_id = line.id

    one, two = sessions(), sessions()
    try:
        CreditNoteService(one)._hold_line(line_id)

        two.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(OperationalError):
            CreditNoteService(two)._hold_line(line_id)
        two.rollback()
    finally:
        one.rollback()
        one.close()
        two.close()
