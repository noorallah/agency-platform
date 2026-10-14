"""A sales line naming no unit is in the product's selling unit (D-PRC-53).

A purchase line naming none is in the product's buying unit; a sales line
naming none was read in the stock unit, whatever the product is sold in, so
2 of a product sold by the box of 12 were 2 pieces at the price of a piece.
A line naming either unit, and a saved line sent again, are left as they were.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.quotation.models import SalesQuotation, SalesQuotationLine
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate
from tests.unit.test_lines_in_another_unit import DAY, _Shop

D = Decimal


def _sold_by_the_box(*, counter: bool = False) -> _Shop:
    """Return a shop whose product is kept in pieces and sold by the box."""
    shop = _Shop(counter=counter)
    shop.setup.product.sales_uom_id = shop.box
    shop.session.commit()
    return shop


def _quote(shop: _Shop, **line: object) -> SalesQuotation:
    """Save a draft quotation of 2 of the product, with what the line names."""
    return QuotationService(shop.session).create_quotation(
        QuotationCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "branch_id": shop.setup.branch.id,
                "warehouse_id": shop.setup.warehouse.id,
                "quotation_date": DAY,
                "valid_until": date(2027, 12, 31),
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": shop.setup.product.id,
                        "quantity": "2",
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )


def _order_body(shop: _Shop, **line: object) -> SalesOrderCreate:
    """Return an order of 2 of the product, with what the line names."""
    return SalesOrderCreate.model_validate(
        {
            "customer_id": shop.setup.customer.id,
            "branch_id": shop.setup.branch.id,
            "warehouse_id": shop.setup.warehouse.id,
            "order_date": DAY,
            "lines": [
                {"line_number": 1, "product_id": shop.setup.product.id, "quantity": "2"}
                | line
            ],
        }
    )


def test_an_order_line_naming_no_unit_is_in_the_selling_unit() -> None:
    """2 naming nothing is 2 BOX: 2,400.00 for 24 pieces, not 200.00 for 2."""
    shop = _sold_by_the_box()

    line = shop.line(shop.order())

    assert line.sales_uom_id == shop.box
    assert (line.unit_price, line.gross_amount) == (D("1200.0000"), D("2400.0000"))
    assert (line.conversion_factor, line.base_quantity) == (D("12"), D("24.0000"))


def test_a_line_naming_the_stock_unit_stays_in_pieces() -> None:
    """A screen showing pieces names them, either way, and is read as pieces."""
    shop = _sold_by_the_box()

    for named in ({"sales_uom_id": shop.piece}, {"inventory_uom_id": shop.piece}):
        line = shop.line(shop.order(**named))
        assert (line.unit_price, line.gross_amount) == (D("100.0000"), D("200.0000"))
        assert line.base_quantity == D("2.0000")


def test_a_product_sold_in_its_stock_unit_is_unchanged() -> None:
    """Selling unit and stock unit the same: the line stores no unit, as before."""
    shop = _Shop()
    shop.setup.product.sales_uom_id = shop.piece
    shop.session.commit()

    line = shop.line(shop.order())

    assert line.sales_uom_id is None
    assert (line.unit_price, line.base_quantity) == (D("100.0000"), D("2.0000"))


def test_a_draft_saved_in_pieces_keeps_them_when_sent_again() -> None:
    """A line saved in no unit, sent back as read, is not re-read in boxes."""
    shop = _Shop()
    order = shop.order()
    shop.setup.product.sales_uom_id = shop.box
    shop.session.commit()

    shop.orders.update_order(
        order.id,
        _order_body(shop, quantity="3"),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )

    line = shop.line(order)
    assert line.sales_uom_id is None
    assert (line.quantity, line.base_quantity) == (D("3.0000"), D("3.0000"))


def test_a_quotation_line_naming_no_unit_is_in_the_selling_unit() -> None:
    """The same on a quotation: 2 naming nothing is quoted 2,400.00."""
    shop = _sold_by_the_box()

    quote = _quote(shop)

    line = shop.session.scalars(select(SalesQuotationLine)).one()
    assert line.sales_uom_id == shop.box
    assert quote.subtotal == D("2400.0000")


def test_a_quotation_in_pieces_before_the_rule_is_ordered_in_pieces() -> None:
    """A quoted line saved in no unit is ordered in the stock unit, not boxes."""
    shop = _Shop()
    service = QuotationService(shop.session)
    quote = _quote(shop)
    shop.setup.product.sales_uom_id = shop.box
    shop.session.commit()
    service.send_quotation(quote.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    service.accept_quotation(quote.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    _, order = service.convert_quotation(
        quote.id, firm_scope=shop.firm_id, actor_id=shop.actor
    )

    line = shop.line(order)
    assert line.sales_uom_id == shop.piece
    assert (line.gross_amount, line.base_quantity) == (D("200.0000"), D("2.0000"))


def test_a_counter_bill_line_naming_no_unit_is_in_the_selling_unit() -> None:
    """Stages off: 2 typed straight onto a bill naming nothing is 2 BOX."""
    shop = _sold_by_the_box(counter=True)

    bill = SalesInvoiceService(shop.session).create_invoice(
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "invoice_date": DAY,
                "lines": [
                    {
                        "product_id": shop.setup.product.id,
                        "line_number": 1,
                        "current_invoice_quantity": "2",
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    shop.session.expire_all()
    billed = shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).one()
    assert (billed.unit_price, billed.gross_amount) == (D("1200.0000"), D("2400.0000"))
    hidden = shop.session.scalars(select(SalesOrderLine)).one()
    assert (hidden.sales_uom_id, hidden.base_quantity) == (shop.box, D("24.0000"))
    assert shop.reserved() == D("24.0000")
