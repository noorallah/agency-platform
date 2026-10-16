"""Stock valuation and ageing by lot, with the lots behind them (L2 step 10).

`docs/design/LOT_COST_DESIGN.md`, section 5. For a firm costing by lot an
item is worth the sum of its lots, on any day; units billed before their lot
are a line of their own, so the grand total still compares with the
Inventory account; a drill-down lists the lots; ageing reads each lot's
received date and is exact. A firm on Average reports as before.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.schemas.inventory import StockWriteOffCreate
from app.inventory.services import InventoryService
from app.inventory.services.lot_shortfalls import LotShortfallService
from app.inventory.services.stock_ageing import StockAgeingService
from app.inventory.services.stock_valuation import (
    OWED_LABEL,
    StockValuationRow,
    StockValuationService,
)
from tests.unit.test_goods_receipt import _Fixture
from tests.unit.test_lot_receiving import _shop
from tests.unit.test_lot_shortfalls import _Short

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal


def _receive(fixture: _Fixture, quantity: str, price: str, on: date) -> GoodsReceipt:
    """Receive part of the order at ``price`` on ``on``: a lot of its own."""
    values = fixture.receipt_payload(quantity).model_dump()
    values["receipt_date"] = on
    values["lines"][0]["unit_price"] = price
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        type(fixture.receipt_payload()).model_validate(values),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.expire_all()
    return receipt


def _traded(code: str, *, by_lot: bool) -> _Fixture:
    """Four in at 100 on 5 August, six at 120 on 20 August, five out on 25th.

    By lot the five leave the first lot that holds them all -- the second --
    so the first lot keeps four at 100 and the second one at 120: 520. On
    Average the ten cost 112 each and the five left are worth 560.
    """
    fixture = _shop(code, by_lot=by_lot, track_batch=False)
    fixture.product.mrp = D("150")
    fixture.session.commit()
    _receive(fixture, "4", "100", date(2026, 8, 5))
    _receive(fixture, "6", "120", date(2026, 8, 20))
    InventoryService(fixture.session).write_off_stock(
        StockWriteOffCreate(
            branch_id=fixture.branch.id,
            warehouse_id=fixture.warehouse.id,
            product_id=fixture.product.id,
            reason="DAMAGE",
            quantity=D("5"),
            transaction_date=date(2026, 8, 25),
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    fixture.session.expire_all()
    return fixture


def _closing(rows: list[StockValuationRow]) -> dict[str, D]:
    """Return the closing rows' values by kind."""
    return {row.row_type: row.value for row in rows if row.row_type != "ITEM"}


def _item(rows: list[StockValuationRow], code: str = "") -> StockValuationRow:
    """Return the one item line, or the line of the item coded ``code``."""
    [item] = [
        row
        for row in rows
        if row.row_type == "ITEM" and (not code or row.product_code == code)
    ]
    return item


def test_an_item_is_worth_the_sum_of_its_lots_and_agrees_with_the_books() -> None:
    """Four at 100 and one at 120: 520, the lots' sum and the Inventory account."""
    fixture = _traded("LOTR1", by_lot=True)
    service = StockValuationService(fixture.session)

    rows = service.valuation(fixture.firm.id, on=date(2026, 9, 10))

    item = _item(rows)
    assert (item.quantity, item.value) == (D("5"), D("520.00"))
    assert item.rate == D("104")
    # Each unit at the product's MRP, as before.
    assert item.mrp_value == D("750.00")
    totals = _closing(rows)
    assert totals["TOTAL"] == D("520.00")
    assert totals["BOOKS"] == D("520.00")
    assert totals["DIFFERENCE"] == D("0.00")
    assert "OWED" not in totals
    lots = service.lots(fixture.firm.id, on=date(2026, 9, 10))
    assert sum((lot.value for lot in lots), D("0")) == totals["TOTAL"]


def test_a_past_day_is_the_lots_as_they_stood_that_day() -> None:
    """On 10 August only the first lot; on 22 August both, whole."""
    fixture = _traded("LOTR2", by_lot=True)
    service = StockValuationService(fixture.session)

    early = service.valuation(fixture.firm.id, on=date(2026, 8, 10))
    middle = service.valuation(fixture.firm.id, on=date(2026, 8, 22))

    assert (_item(early).quantity, _item(early).value) == (D("4"), D("400.00"))
    assert _closing(early)["DIFFERENCE"] == D("0.00")
    assert (_item(middle).quantity, _item(middle).value) == (D("10"), D("1120.00"))
    assert _closing(middle)["BOOKS"] == D("1120.00")
    assert [
        (lot.quantity, lot.value)
        for lot in service.lots(fixture.firm.id, on=date(2026, 8, 22))
    ] == [(D("4"), D("400.00")), (D("6"), D("720.00"))]


def test_the_drill_down_lists_each_lot_with_its_cost_and_mrp() -> None:
    """One row per lot, oldest received first; no printed batch, none shown."""
    fixture = _traded("LOTR3", by_lot=True)

    first, second = StockValuationService(fixture.session).lots(
        fixture.firm.id, on=date(2026, 9, 10), product_id=fixture.product.id
    )

    assert first.received_on == date(2026, 8, 5)
    assert first.lot_reference.startswith("LOT")
    assert first.batch_number == ""
    assert (first.quantity, first.rate, first.value) == (D("4"), D("100"), D("400.00"))
    assert (first.mrp, first.mrp_value) == (D("150"), D("600.00"))
    assert second.received_on == date(2026, 8, 20)
    assert (second.quantity, second.rate, second.value) == (
        D("1"),
        D("120"),
        D("120.00"),
    )


def _scope(fixture: _Fixture, *, cost: bool) -> object:
    """Return a scope whose principal holds the cost permission, or not."""
    granted: Callable[[str], bool] = lambda code: cost  # noqa: E731
    principal = type("Principal", (), {"has_permission": staticmethod(granted)})()
    return type("Scope", (), {"firm_id": fixture.firm.id, "principal": principal})()


def test_the_route_leaves_the_cost_out_without_the_permission() -> None:
    """Quantity and MRP to anyone; cost rate and value only with the right."""
    from app.inventory.api.router import stock_valuation_lots

    fixture = _traded("LOTR4", by_lot=True)

    def answer(cost: bool) -> list[Any]:
        return stock_valuation_lots(
            scope=_scope(fixture, cost=cost),  # type: ignore[arg-type]
            to_date=date(2026, 9, 10),
            from_date=None,
            warehouse_id=None,
            product_id=None,
            page=1,
            page_size=100,
            db=fixture.session,
        ).data

    shown = answer(True)
    hidden = answer(False)

    assert [row.value for row in shown] == [D("400.00"), D("120.00")]
    assert [(row.rate, row.value) for row in hidden] == [(None, None)] * 2
    assert [row.quantity for row in hidden] == [D("4"), D("1")]
    assert hidden[0].mrp_value == D("600.00")


@pytest.mark.parametrize("by_lot", [True, False])
def test_the_valuation_leaves_the_cost_out_without_the_permission(
    by_lot: bool,
) -> None:
    """D-STK-76: a Viewer read 20 at 41.50 = 830.00 off the stock valuation.

    Quantity and MRP to anyone; the rate, the value and the closing rows
    built from cost -- total, books, difference -- only with the right.
    """
    from app.inventory.api.router import stock_valuation

    fixture = _traded(f"LOTR7{int(by_lot)}", by_lot=by_lot)

    def answer(cost: bool) -> list[Any]:
        return stock_valuation(
            scope=_scope(fixture, cost=cost),  # type: ignore[arg-type]
            to_date=date(2026, 9, 10),
            from_date=None,
            warehouse_id=None,
            include_zero=False,
            page=1,
            page_size=100,
            db=fixture.session,
        ).data

    shown = answer(True)
    hidden = answer(False)

    worth = D("520.00") if by_lot else D("560.00")
    assert [row.value for row in shown] == [worth, worth, worth, D("0.00")]
    assert shown[0].rate is not None
    assert [row.row_type for row in hidden] == [
        "ITEM",
        "TOTAL",
        "BOOKS",
        "DIFFERENCE",
    ]
    assert [(row.rate, row.value) for row in hidden] == [(None, None)] * 4
    assert hidden[0].quantity == D("5")
    assert hidden[0].mrp_value == D("750.00")


@pytest.mark.parametrize("by_lot", [True, False])
def test_the_ageing_leaves_the_cost_out_without_the_permission(by_lot: bool) -> None:
    """D-STK-76: the ageing's rate and value go only to a holder of the right."""
    from app.inventory.api.router import stock_ageing

    fixture = _traded(f"LOTR8{int(by_lot)}", by_lot=by_lot)

    def answer(cost: bool) -> list[Any]:
        return stock_ageing(
            scope=_scope(fixture, cost=cost),  # type: ignore[arg-type]
            to_date=date(2026, 9, 10),
            from_date=None,
            page=1,
            page_size=100,
            db=fixture.session,
        ).data

    [shown] = answer(True)
    [hidden] = answer(False)

    assert shown.value == (D("520.00") if by_lot else D("560.00"))
    assert shown.rate == (D("104") if by_lot else D("112"))
    assert (hidden.rate, hidden.value) == (None, None)
    assert hidden.quantity == D("5")
    assert hidden.days_0_30 + hidden.days_31_60 == D("5")


def test_ageing_reads_each_lots_received_date() -> None:
    """Four of 5 August are 36 days old, one of 20 August 21: FIFO would say 5."""
    fixture = _traded("LOTR5", by_lot=True)

    [row] = StockAgeingService(fixture.session).ageing(
        fixture.firm.id, on=date(2026, 9, 10)
    )

    assert row.quantity == D("5")
    assert (row.days_0_30, row.days_31_60) == (D("1"), D("4"))
    assert row.days_61_90 == row.days_91_180 == row.days_over_180 == D("0")
    assert (row.value, row.rate) == (D("520.00"), D("104"))


def test_an_average_firm_values_and_ages_as_before() -> None:
    """Five left at the average of 112: 560, FIFO ageing, no lots listed."""
    fixture = _traded("LOTR6", by_lot=False)
    on = date(2026, 9, 10)

    rows = StockValuationService(fixture.session).valuation(fixture.firm.id, on=on)
    [aged] = StockAgeingService(fixture.session).ageing(fixture.firm.id, on=on)

    item = _item(rows)
    assert (item.quantity, item.rate, item.value) == (D("5"), D("112"), D("560.00"))
    assert [row.row_type for row in rows] == ["ITEM", "TOTAL", "BOOKS", "DIFFERENCE"]
    assert (aged.days_0_30, aged.days_31_60) == (D("5"), D("0"))
    assert aged.value == D("560.00")
    assert StockValuationService(fixture.session).lots(fixture.firm.id, on=on) == []


def _gap(rows: list[StockValuationRow]) -> D:
    """Return the grand total less the books, or the total with no books."""
    totals = _closing(rows)
    return totals["TOTAL"] - totals.get("BOOKS", D("0"))


def test_units_owed_to_lots_are_a_line_of_their_own() -> None:
    """Two billed past the lot at 40: owed -2 at -80, the gap to the books kept."""
    shop = _Short()
    service = StockValuationService(shop.session)
    before = service.valuation(shop.firm.id, on=date(2026, 8, 3))

    shop.sold_short()
    after = service.valuation(shop.firm.id, on=date(2026, 8, 4))

    [owed] = [row for row in after if row.row_type == "OWED"]
    assert owed.product_name == OWED_LABEL
    assert (owed.quantity, owed.value) == (D("-2"), D("-80.00"))
    # The lot is empty, so the item has no line; the total is the lots
    # less the units owed, which is what the sale took off the books. (The
    # firm's other item holds stock that names no lot, valued at nothing.)
    assert [row.product_code for row in after if row.row_type == "ITEM"] == ["SKU-001"]
    assert _closing(after)["TOTAL"] == D("-80.00")
    assert _gap(after) == _gap(before)
    assert [row.row_type for row in after][-4:] == [
        "OWED",
        "TOTAL",
        "BOOKS",
        "DIFFERENCE",
    ]
    # The stock statement folds them back into the item, as the movements do.
    folded = service.valuation(shop.firm.id, on=date(2026, 8, 4), owed_apart=False)
    assert (_item(folded, "SKU-LOT").quantity, _item(folded, "SKU-LOT").value) == (
        D("-2"),
        D("-80.00"),
    )


def test_the_owed_line_clears_on_the_day_the_lot_covers_it() -> None:
    """Covered on 6 August: owed on the 4th, gone on the 6th, lots add up."""
    shop = _Short()
    shop.sold_short()
    lot = shop.lot_in("10", "46", "GRN-2")
    LotShortfallService(shop.session).settle_from_lot(
        firm_id=shop.firm.id,
        product_id=shop.item.id,
        lot_id=lot.id,
        lot_place=(shop.branch.id, shop.warehouse.id, None),
        available=D("10"),
        on=date(2026, 8, 6),
        document_id=uuid4(),
        document_line_id=uuid4(),
        document_number="GRN-2",
        actor_id=shop.actor,
    )
    shop.session.commit()
    service = StockValuationService(shop.session)

    waiting = service.valuation(shop.firm.id, on=date(2026, 8, 4))
    covered = service.valuation(shop.firm.id, on=date(2026, 8, 6))

    assert (_item(waiting, "SKU-LOT").quantity, _item(waiting, "SKU-LOT").value) == (
        D("10"),
        D("460.00"),
    )
    assert _closing(waiting)["OWED"] == D("-80.00")
    assert _closing(waiting)["TOTAL"] == D("380.00")
    assert "OWED" not in _closing(covered)
    assert (_item(covered, "SKU-LOT").quantity, _item(covered, "SKU-LOT").value) == (
        D("8"),
        D("368.00"),
    )
    assert shop.item_value() == D("368")
    lots = service.lots(shop.firm.id, on=date(2026, 8, 4), product_id=shop.item.id)
    assert sum((row.value for row in lots), D("0")) == D("460.00")


def test_a_switched_firm_values_its_carried_lots_and_its_past_on_average() -> None:
    """Carried forward on 3 August: 8,110.00 in lots; the 2nd stays on Average."""
    from tests.unit.test_lot_switch_over import SWITCH_DAY, _Trader

    firm = _Trader()
    service = StockValuationService(firm.session)
    before = service.valuation(firm.firm.id, on=date(2026, 8, 2))
    firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)

    after = service.valuation(firm.firm.id, on=SWITCH_DAY)
    lots = service.lots(firm.firm.id, on=SWITCH_DAY)
    second = service.lots(
        firm.firm.id,
        on=SWITCH_DAY,
        warehouse_id=firm.second.id,
        product_id=firm.product.id,
    )

    assert _closing(after)["TOTAL"] == D("8110.00")
    assert sum((row.value for row in lots), D("0")) == D("8110.00")
    assert len(lots) == 4
    # The plain item's one lot spans both warehouses: the second's 30 of
    # 130 units carry their share of its value.
    [here] = second
    assert (here.quantity, here.value) == (D("30"), D("1869.23"))
    assert service.valuation(firm.firm.id, on=date(2026, 8, 2)) == before
    assert service.lots(firm.firm.id, on=date(2026, 8, 2)) == []
