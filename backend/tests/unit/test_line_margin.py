"""Cost and margin on the order and bill line, screen only (L3 step 4).

`docs/design/LOT_MARGINS_DESIGN.md`, section 3.7. A line says what its goods
cost and what it earns over that, and the document totals both, only to a
holder of ``PRODUCT_VIEW_COST_PRICE``; nothing that prints reads either.
"""

import ast
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.sales_invoice.schemas import SalesInvoiceResponse
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.services.line_margin import margin_of
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_lot_selling import _ByLot

_FIELDS = {
    "cost_amount",
    "cost_is_estimate",
    "margin_amount",
    "margin_percent",
    "cost_total",
    "margin_total",
}
_APP = Path(__file__).resolve().parents[2] / "app"


def _taxable(line: object) -> Decimal:
    """Return a line response's taxable value."""
    return Decimal(getattr(line, "net_amount")) - Decimal(  # noqa: B009
        getattr(line, "tax_amount")  # noqa: B009
    )


def _assert_margins(response: SalesInvoiceResponse) -> None:
    """Every line's margin is its taxable less its cost; the totals add up."""
    for line in response.lines:
        assert line.cost_amount is not None
        assert line.margin_amount == _taxable(line) - line.cost_amount
        assert line.margin_percent == (
            line.margin_amount * 100 / line.cost_amount
        ).quantize(Decimal("0.01"))
    assert response.cost_total == sum(
        (line.cost_amount or Decimal("0") for line in response.lines), Decimal("0")
    )
    assert response.margin_total == sum(
        (line.margin_amount or Decimal("0") for line in response.lines),
        Decimal("0"),
    )


def test_a_dispatched_bill_shows_its_recorded_cost_and_margin() -> None:
    """EARLY's four cost 160 and LATE's 144, recorded, not estimated."""
    shop = _ByLot()
    invoice_id = shop.approved(shop.two_lines())
    row = shop.bills.get_invoice(invoice_id, firm_scope=shop.firm.id)

    shown = shop.bills.invoice_response(row, show_cost=True)

    assert [line.cost_amount for line in shown.lines] == [
        Decimal("160.0000"),
        Decimal("144.0000"),
    ]
    assert not any(line.cost_is_estimate for line in shown.lines)
    _assert_margins(shown)
    assert shown.cost_total == Decimal("304.0000")


def test_nobody_without_the_cost_permission_sees_cost_or_margin() -> None:
    """The same bill read without ``show_cost`` carries none of it."""
    shop = _ByLot()
    invoice_id = shop.approved(shop.two_lines())
    row = shop.bills.get_invoice(invoice_id, firm_scope=shop.firm.id)

    hidden = shop.bills.invoice_response(row)

    for line in hidden.lines:
        assert line.cost_amount is None
        assert line.margin_amount is None
        assert line.margin_percent is None
        assert line.cost_is_estimate is False
    assert hidden.cost_total is None
    assert hidden.margin_total is None


def test_a_draft_bill_estimates_from_the_lots_chosen() -> None:
    """Before dispatch the lots picked price it: EARLY at 40, LATE at 36."""
    shop = _ByLot()
    draft = shop.bills.create_invoice(
        shop.two_lines(), firm_id=shop.firm.id, actor_id=shop.actor
    )
    row = shop.bills.get_invoice(draft.id, firm_scope=shop.firm.id)

    shown = shop.bills.invoice_response(row, show_cost=True)

    assert [line.cost_amount for line in shown.lines] == [
        Decimal("160.0000"),
        Decimal("144.0000"),
    ]
    assert all(line.cost_is_estimate for line in shown.lines)
    _assert_margins(shown)


def test_a_draft_bill_on_average_estimates_at_the_average() -> None:
    """On Average every unit is worth 44, whichever batch was picked."""
    shop = _ByLot(by_lot=False)
    draft = shop.bills.create_invoice(
        shop.two_lines(), firm_id=shop.firm.id, actor_id=shop.actor
    )
    row = shop.bills.get_invoice(draft.id, firm_scope=shop.firm.id)

    shown = shop.bills.invoice_response(row, show_cost=True)

    assert [line.cost_amount for line in shown.lines] == [
        Decimal("176.0000"),
        Decimal("176.0000"),
    ]
    _assert_margins(shown)


def _raised_order(shop: _ByLot, invoice_id: UUID) -> SalesOrder:
    """Return the order a counter bill raised for itself."""
    order = shop.session.scalar(
        select(SalesOrder).where(SalesOrder.raised_by_sales_invoice_id == invoice_id)
    )
    assert order is not None
    return order


def test_an_order_line_is_costed_at_its_pinned_lot() -> None:
    """A line pinned to LATE costs four of LATE's 36; the order totals it."""
    shop = _ByLot()
    draft = shop.bills.create_invoice(
        shop.bill(None), firm_id=shop.firm.id, actor_id=shop.actor
    )
    order = _raised_order(shop, draft.id)
    [line] = shop.session.scalars(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    ).all()
    line.pinned_batch_id = shop.batches["LATE"].id
    shop.session.flush()
    orders = SalesOrderService(shop.session)

    shown = orders.order_response(order, show_cost=True)
    [listed] = orders.order_responses([order], show_cost=True)
    hidden = orders.order_response(order)

    [costed] = shown.lines
    assert costed.cost_amount == Decimal("144.0000")
    assert costed.cost_is_estimate is True
    assert costed.margin_amount == _taxable(costed) - costed.cost_amount
    assert shown.cost_total == costed.cost_amount
    assert shown.margin_total == costed.margin_amount
    assert listed.lines[0].margin_amount == costed.margin_amount
    assert hidden.lines[0].cost_amount is None
    assert hidden.lines[0].margin_amount is None
    assert hidden.cost_total is None


def test_a_cost_of_nothing_has_a_margin_but_no_percentage() -> None:
    """Free goods earn their whole value; an unknown cost earns nothing said."""
    free = margin_of(Decimal("100"), Decimal("0"), estimate=False)
    unknown = margin_of(Decimal("100"), None, estimate=True)

    assert free.margin_amount == Decimal("100.0000")
    assert free.margin_percent is None
    assert unknown.cost_amount is None
    assert unknown.margin_amount is None
    assert unknown.cost_is_estimate is False


def _print_files() -> list[Path]:
    """Return every module that prints or renders a document for paper."""
    return sorted(
        path
        for path in _APP.rglob("*.py")
        if "print" in path.name or "pdf" in path.name
    )


def test_no_print_path_reads_cost_or_margin() -> None:
    """Design 3.7: never printed. No print or PDF module names the fields.

    Read by AST, so a word in a comment does not count and an attribute, a
    name or a string key does.
    """
    files = _print_files()
    assert any(path.name == "invoice_pdf.py" for path in files)
    assert any(path.name == "order_print_service.py" for path in files)
    assert any(path.name == "challan_print_service.py" for path in files)
    found: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            named = (
                node.attr
                if isinstance(node, ast.Attribute)
                else (
                    node.id
                    if isinstance(node, ast.Name)
                    else (
                        node.value
                        if isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        else None
                    )
                )
            )
            if named in _FIELDS:
                found.append(f"{path.relative_to(_APP)}:{node.lineno} {named}")
    assert found == []
