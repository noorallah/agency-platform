"""Margin by lot (L2 step 10).

`docs/design/LOT_COST_DESIGN.md`, section 5: "A margin-by-lot report is new".
One bill line drawing two lots at two costs is two rows, each at its own
cost; a return takes its quantity, value and cost back from the lot it
refilled; a caller who may not see cost gets the rows with cost and margin
omitted rather than zeroed. A firm on Average sees its batches at the
average they left with, and is told so.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.sales_invoice.api.router import sales_margin_by_lot
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.services.lot_margin import (
    AVERAGE_NOTE,
    BY_LOT_NOTE,
    LotMarginRecord,
    LotMarginService,
)
from tests.unit.test_lot_returns import _returned, _sold
from tests.unit.test_lot_selling import _ByLot
from tests.unit.test_sales_analysis_rest import _scope

# The return fixture shares the lot tests' numbering; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

AUGUST = {"from_date": date(2026, 8, 1), "to_date": date(2026, 8, 31)}


def _taxable(line: SalesInvoiceLine) -> Decimal:
    """Return a bill line's taxable value, net of every discount."""
    return Decimal(line.net_amount) - Decimal(line.tax_amount)


def _rows(shop: _ByLot, *, show_cost: bool = True) -> dict[str, LotMarginRecord]:
    """Run the report for August, keyed by printed batch number."""
    return {
        str(row.batch_number): row
        for row in LotMarginService(shop.session).report(
            shop.firm.id, show_cost=show_cost, **AUGUST
        )
    }


def test_one_line_from_two_lots_is_two_rows_at_their_own_costs() -> None:
    """Four from EARLY at 40 and four from LATE at 36 on one line of eight."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})
    half = (_taxable(line) / 2).quantize(Decimal("0.01"))
    rows = _rows(shop)
    assert set(rows) == {"EARLY", "LATE"}
    early, late = rows["EARLY"], rows["LATE"]
    assert early.quantity == late.quantity == Decimal("4")
    assert early.sales_value == late.sales_value == half
    assert early.cost == Decimal("160.00")
    assert late.cost == Decimal("144.00")
    assert early.margin == half - Decimal("160")
    assert late.margin == half - Decimal("144")
    assert early.margin_percent == ((half - Decimal("160")) * 100 / half).quantize(
        Decimal("0.01")
    )
    assert early.lot_reference == shop.batches["EARLY"].lot_reference


def test_a_return_takes_its_lot_back() -> None:
    """Six come back: LATE takes its four back at 36, EARLY two at 40."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})
    _returned(shop, line, "6")
    half = (_taxable(line) / 2).quantize(Decimal("0.01"))
    rows = _rows(shop)
    early, late = rows["EARLY"], rows["LATE"]
    assert early.quantity == Decimal("2")
    assert early.cost == Decimal("80.00")
    assert early.sales_value == (half / 2).quantize(Decimal("0.01"))
    assert late.quantity == Decimal("0")
    assert late.cost == Decimal("0.00")
    assert late.sales_value == Decimal("0.00")


def test_without_the_cost_permission_cost_and_margin_are_omitted() -> None:
    """The rows stand; cost, margin and percent are None, not zero."""
    shop = _ByLot()
    _sold(shop, {"EARLY": "4", "LATE": "4"})
    hidden = sales_margin_by_lot(
        scope=_scope(shop.firm.id), db=shop.session, page=1, page_size=100, **AUGUST
    )
    assert len(hidden.data) == 2
    assert all(
        row.cost is None and row.margin is None and row.margin_percent is None
        for row in hidden.data
    )
    assert all(row.sales_value > 0 for row in hidden.data)
    assert hidden.message == BY_LOT_NOTE
    shown = sales_margin_by_lot(
        scope=_scope(shop.firm.id, "PRODUCT_VIEW_COST_PRICE"),
        db=shop.session,
        page=1,
        page_size=100,
        **AUGUST,
    )
    assert sorted(row.cost for row in shown.data if row.cost is not None) == [
        Decimal("144.00"),
        Decimal("160.00"),
    ]


def test_a_firm_on_average_sees_its_batches_and_is_told_how() -> None:
    """Every unit is worth 44 on Average, so both batches cost 176."""
    shop = _ByLot(by_lot=False)
    _sold(shop, {"EARLY": "4", "LATE": "4"})
    rows = _rows(shop)
    assert set(rows) == {"EARLY", "LATE"}
    assert {row.cost for row in rows.values()} == {Decimal("176.00")}
    assert LotMarginService(shop.session).note(shop.firm.id) == AVERAGE_NOTE


def test_a_bill_outside_the_dates_is_not_counted() -> None:
    """The report reads the bill's own date."""
    shop = _ByLot()
    _sold(shop, {"EARLY": "4"})
    assert (
        LotMarginService(shop.session).report(
            shop.firm.id,
            from_date=date(2026, 9, 1),
            to_date=date(2026, 9, 30),
            show_cost=True,
        )
        == []
    )
