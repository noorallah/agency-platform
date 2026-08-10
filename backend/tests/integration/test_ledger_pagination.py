"""Paging the stock ledger must show every row exactly once.

``list_ledger`` sorted on one column and nothing else. ``created_at`` is not
unique -- a dispatch writes its DISPATCH and UNRESERVE rows in a single flush,
so they carry the same timestamp to the microsecond -- and ``OFFSET``/``LIMIT``
over a tie has no defined answer. PostgreSQL is free to hand the same row to two
pages and never show another.

It did. Walking the seeded ledger 20 rows at a time returned 197 rows for 197
records, of which only 196 were distinct: one row appeared on two pages and one
was invisible from the client entirely, at every page size that split a tie.

This lives in the integration suite because it cannot be reproduced in the unit
suite. SQLite's row order for a tie happens to be stable, so the same walk on
SQLite passes whether or not the tiebreaker is there -- the same reason the
conversion-rule NULL ordering in ``test_uom_conversion_resolution`` went
unnoticed. Only the deployment target can fail this test.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.firms.models import Firm
from app.inventory.models.inventory import (
    InventoryRecord,
    InventoryTransaction,
    StockLedgerEntry,
)
from app.inventory.schemas.inventory import StockLedgerListFilters
from app.inventory.services.inventory_service import InventoryService
from app.products.models import Product

_ACTOR = uuid4()

# Every quantity column the ledger requires, none of which this test is about.
_QUANTITIES = {
    "quantity": Decimal("1"),
    "previous_current_quantity": Decimal("0"),
    "new_current_quantity": Decimal("1"),
    "previous_reserved_quantity": Decimal("0"),
    "new_reserved_quantity": Decimal("0"),
    "previous_available_quantity": Decimal("0"),
    "new_available_quantity": Decimal("1"),
    "previous_blocked_quantity": Decimal("0"),
    "new_blocked_quantity": Decimal("0"),
    "previous_damaged_quantity": Decimal("0"),
    "new_damaged_quantity": Decimal("0"),
    "previous_quarantine_quantity": Decimal("0"),
    "new_quarantine_quantity": Decimal("0"),
    "previous_in_transit_quantity": Decimal("0"),
    "new_in_transit_quantity": Decimal("0"),
}


def _seed(session: Session, *, rows: int) -> tuple[UUID, list[UUID]]:
    """Create a firm holding ``rows`` ledger entries that all share a timestamp.

    The shared ``created_at`` is the whole point: it reproduces what a single
    flush does in production, where several ledger rows are written together.
    """
    firm = Firm(
        name="Ledger Firm",
        code="LEDG01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()

    branch = Branch(
        firm_id=firm.id,
        code="LEDG-HO",
        name="Head Office",
        display_name="Head Office",
    )
    session.add(branch)
    session.flush()

    warehouse = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="LEDG-WH",
        name="Main Warehouse",
        display_name="Main Warehouse",
    )
    product = Product(
        firm_id=firm.id,
        code="SKU-LEDG-1",
        name="Ledger Item",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=_ACTOR,
        updated_by=_ACTOR,
    )
    session.add_all([warehouse, product])
    session.flush()

    inventory = InventoryRecord(
        firm_id=firm.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        storage_locator="A-1",
        product_id=product.id,
        created_by=_ACTOR,
        updated_by=_ACTOR,
    )
    session.add(inventory)
    session.flush()

    common = {
        "inventory_id": inventory.id,
        "firm_id": firm.id,
        "branch_id": branch.id,
        "warehouse_id": warehouse.id,
        "product_id": product.id,
        "transaction_type": "GOODS_RECEIPT",
        "reference_type": "GRN",
        "transaction_date": date(2026, 6, 1),
        "created_by": _ACTOR,
        "updated_by": _ACTOR,
    }
    stamp = datetime(2026, 6, 1, 9, 30, 0, tzinfo=UTC)
    entries: list[StockLedgerEntry] = []
    for index in range(rows):
        transaction = InventoryTransaction(
            reference_number=f"GRN-{index:04d}", **common, **_QUANTITIES
        )
        session.add(transaction)
        session.flush()
        entries.append(
            StockLedgerEntry(
                transaction_id=transaction.id,
                reference_number=f"GRN-{index:04d}",
                # Identical for every row, exactly as one flush produces.
                created_at=stamp,
                **common,
                **_QUANTITIES,
            )
        )
    session.add_all(entries)
    session.flush()
    return firm.id, [entry.id for entry in entries]


def _walk(session: Session, firm_id: UUID, *, page_size: int) -> list[UUID]:
    """Page through the ledger the way the desktop pager does."""
    service = InventoryService(session)
    collected: list[UUID] = []
    page = 1
    while True:
        rows, total = service.list_ledger(
            firm_scope=firm_id,
            filters=StockLedgerListFilters(),
            page=page,
            page_size=page_size,
            search=None,
            sort_by="created_at",
            descending=True,
        )
        collected.extend(row.id for row in rows)
        if page * page_size >= total:
            return collected
        page += 1


@pytest.mark.parametrize("page_size", [3, 5, 20])
def test_every_ledger_row_is_shown_exactly_once(
    temp_session: Session, page_size: int
) -> None:
    """No row may be repeated on two pages or skipped between them."""
    firm_id, expected = _seed(temp_session, rows=37)

    seen = _walk(temp_session, firm_id, page_size=page_size)

    assert len(seen) == len(set(seen)), "a row was returned on more than one page"
    assert set(seen) == set(expected), "a row was never shown on any page"


def test_the_same_walk_twice_returns_the_same_order(temp_session: Session) -> None:
    """An unstable sort also reshuffles under the user between refreshes."""
    firm_id, _ = _seed(temp_session, rows=37)

    first = _walk(temp_session, firm_id, page_size=5)
    second = _walk(temp_session, firm_id, page_size=5)

    assert first == second
