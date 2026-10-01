"""What the stock is worth as on a day, beside the books (D-GOLIVE-3).

There was no stock valuation anywhere: nothing to check an opening stock
against, no closing stock for the accounts, nothing for the bank's monthly
stock statement. These pin Tally's *Stock Summary* shape -- quantity, rate,
value, a grand total -- and the two rows it adds: the Inventory account's
balance on the same day, and the difference.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.firms.models import Firm
from app.inventory.services.stock_valuation import StockValuationService
from tests.unit.test_opening_stock_import_file import _ON, _csv, _factory, _firm, _run

pytestmark = pytest.mark.typed_document_numbers


def _stocked() -> tuple[Session, Firm]:
    session = _factory()()
    firm = _firm(session)
    report = _run(
        session,
        firm.id,
        _csv(
            "ProductCode,Warehouse,Quantity,UnitCost",
            "RICE,MAIN,10,50",
            "RICE,EAST,5,50",
            "OIL,MAIN,3,100",
        ),
        apply=True,
    )
    assert report.imported, [issue.describe() for issue in report.issues]
    return session, firm


def test_each_item_is_valued_at_its_average_cost_with_a_grand_total() -> None:
    session, firm = _stocked()

    rows = StockValuationService(session).valuation(firm.id, on=_ON)

    items = {row.product_code: row for row in rows if row.row_type == "ITEM"}
    assert items["RICE"].quantity == Decimal("15")
    assert items["RICE"].rate == Decimal("50")
    assert items["RICE"].value == Decimal("750.00")
    assert items["OIL"].value == Decimal("300.00")
    totals = {row.row_type: row.value for row in rows if row.row_type != "ITEM"}
    assert totals["TOTAL"] == Decimal("1050.00")


def test_the_books_are_stated_beside_the_stock_and_agree() -> None:
    session, firm = _stocked()

    rows = StockValuationService(session).valuation(firm.id, on=_ON)

    totals = {row.row_type: row.value for row in rows if row.row_type != "ITEM"}
    # Opening stock posts Dr Inventory at the cost it came in at, so the
    # account and the stock agree to the paisa.
    assert totals["BOOKS"] == Decimal("1050.00")
    assert totals["DIFFERENCE"] == Decimal("0.00")
    assert [row.row_type for row in rows][-3:] == ["TOTAL", "BOOKS", "DIFFERENCE"]


def test_a_day_before_the_stock_arrived_values_nothing() -> None:
    session, firm = _stocked()

    rows = StockValuationService(session).valuation(firm.id, on=_ON - timedelta(days=1))

    assert [row.row_type for row in rows if row.row_type == "ITEM"] == []
    totals = {row.row_type: row.value for row in rows if row.row_type != "ITEM"}
    assert totals["TOTAL"] == Decimal("0.00")
    assert totals["BOOKS"] == Decimal("0.00")


def test_one_warehouse_is_valued_at_the_firms_rate_without_the_books() -> None:
    session, firm = _stocked()
    east = session.scalar(
        select(Warehouse).where(Warehouse.firm_id == firm.id, Warehouse.code == "EAST")
    )
    assert east is not None

    rows = StockValuationService(session).valuation(
        firm.id, on=_ON, warehouse_id=east.id
    )

    [item] = [row for row in rows if row.row_type == "ITEM"]
    assert (item.product_code, item.quantity, item.value) == (
        "RICE",
        Decimal("5"),
        Decimal("250.00"),
    )
    # The books cannot be split by warehouse, so there is nothing to compare.
    assert [row.row_type for row in rows if row.row_type != "ITEM"] == ["TOTAL"]


def test_the_route_answers_as_on_the_to_date_and_never_the_future() -> None:
    from app.inventory.api.router import stock_valuation

    session, firm = _stocked()
    scope = type("Scope", (), {"firm_id": firm.id})()
    response = stock_valuation(
        scope=scope,  # type: ignore[arg-type]
        to_date=date(2099, 1, 1),
        from_date=None,
        warehouse_id=None,
        include_zero=False,
        page=1,
        page_size=100,
        db=session,
    )
    assert response.data[-3].product_name == "Grand total"
    assert response.data[-3].value == Decimal("1050.00")


def test_quarantined_goods_are_still_owned_and_still_valued() -> None:
    """Found on WHOLE01: two units on hold read as gone, 191.35 short."""
    from app.inventory.models import InventoryRecord
    from app.inventory.schemas import StockQuarantineCreate
    from app.inventory.services import InventoryService
    from app.products.models import Product

    session, firm = _stocked()
    rice = session.scalar(
        select(Product).where(Product.firm_id == firm.id, Product.code == "RICE")
    )
    assert rice is not None
    record = session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == firm.id, InventoryRecord.product_id == rice.id
        )
    )
    assert record is not None
    InventoryService(session).quarantine_stock(
        StockQuarantineCreate(
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            product_id=rice.id,
            action="HOLD",  # type: ignore[arg-type]
            quantity=Decimal("2"),
            transaction_date=_ON,
        ),
        firm_scope=firm.id,
        actor_id=firm.id,
    )
    session.commit()

    rows = StockValuationService(session).valuation(firm.id, on=_ON)

    items = {row.product_code: row for row in rows if row.row_type == "ITEM"}
    assert items["RICE"].quantity == Decimal("15")
    totals = {row.row_type: row.value for row in rows if row.row_type != "ITEM"}
    assert totals["DIFFERENCE"] == Decimal("0.00")


# -- The stock statement for the bank (backlog 70 row 6) ----------------------


def _identity_holds(rows: list[object]) -> None:
    """Check opening + in - out = closing, in quantity and value, every row."""
    for row in rows:
        assert (
            row.opening_quantity + row.inward_quantity - row.outward_quantity  # type: ignore[attr-defined]
            == row.closing_quantity  # type: ignore[attr-defined]
        ), row
        assert (
            row.opening_value + row.inward_value - row.outward_value  # type: ignore[attr-defined]
            == row.closing_value  # type: ignore[attr-defined]
        ), row


def test_the_month_the_stock_arrived_shows_it_coming_in() -> None:
    """Nothing before; all of it in; closing is the valuation as on the day."""
    from app.inventory.services.stock_valuation import StockStatementService

    session, firm = _stocked()
    rows = StockStatementService(session).statement(
        firm.id, from_date=_ON - timedelta(days=5), to_date=_ON
    )

    items = [row for row in rows if row.row_type == "ITEM"]
    assert items and all(row.opening_quantity == 0 for row in items)
    assert all(row.outward_quantity == 0 for row in items)
    total = rows[-1]
    assert total.row_type == "TOTAL"
    valued = StockValuationService(session).valuation(firm.id, on=_ON)
    grand = next(row for row in valued if row.row_type == "TOTAL")
    assert total.closing_value == grand.value
    _identity_holds(rows)


def test_a_write_off_is_an_issue_and_the_next_month_opens_where_it_closed() -> None:
    """Goods out at the moving average; next period's opening is this closing."""
    from app.inventory.models import InventoryRecord
    from app.inventory.schemas import StockWriteOffCreate
    from app.inventory.services import InventoryService
    from app.inventory.services.stock_valuation import StockStatementService
    from app.products.models import Product

    session, firm = _stocked()
    rice = session.scalar(
        select(Product).where(Product.firm_id == firm.id, Product.code == "RICE")
    )
    assert rice is not None
    record = session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == firm.id, InventoryRecord.product_id == rice.id
        )
    )
    assert record is not None
    later = _ON + timedelta(days=10)
    InventoryService(session).write_off_stock(
        StockWriteOffCreate(
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            product_id=rice.id,
            reason="DAMAGE",  # type: ignore[arg-type]
            quantity=Decimal("3"),
            transaction_date=later,
        ),
        firm_scope=firm.id,
        actor_id=firm.id,
    )
    session.commit()
    service = StockStatementService(session)

    first = service.statement(firm.id, from_date=_ON - timedelta(days=5), to_date=_ON)
    second = service.statement(
        firm.id, from_date=_ON + timedelta(days=1), to_date=later
    )

    rice_first = next(row for row in first if row.product_code == "RICE")
    rice_second = next(row for row in second if row.product_code == "RICE")
    assert rice_second.opening_quantity == rice_first.closing_quantity
    assert rice_second.opening_value == rice_first.closing_value
    assert rice_second.outward_quantity == Decimal("3")
    assert rice_second.outward_value > 0
    _identity_holds(second)


def test_a_period_that_ends_before_it_starts_is_refused() -> None:
    """Named rather than answered with an empty statement."""
    from app.core.exceptions import ValidationError
    from app.inventory.api.router import stock_statement

    session, firm = _stocked()
    scope = type("Scope", (), {"firm_id": firm.id})()
    with pytest.raises(ValidationError, match="ends before it starts"):
        stock_statement(
            scope=scope,  # type: ignore[arg-type]
            from_date=_ON,
            to_date=_ON - timedelta(days=1),
            warehouse_id=None,
            page=1,
            page_size=100,
            db=session,
        )
