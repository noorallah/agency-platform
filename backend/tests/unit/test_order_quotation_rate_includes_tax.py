"""A sales order and a quotation typed at shelf prices (backlog 64 row 4).

The counter bill's switch, on the two documents before it. A rate (and a
discount amount) typed on an order or a quotation whose "Rate includes GST" is
on is read back to its pre-tax rate before the line is written; the figures
typed are kept beside it, so an editor can show them again and send them back.
Absent on a new document is off, because a converted quotation, a counter bill
and an import all hand over rates that are already before tax.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.quotation.models import SalesQuotation, SalesQuotationLine
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services.quotation_print_service import QuotationPrintService
from app.quotation.services.quotation_service import QuotationService
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_invoice_print import _text_of
from tests.unit.test_sales_chain_synthesis import _Firm
from tests.unit.test_sales_invoice_rate_includes_tax import (
    OTHER_STATE_BUYER,
    _gst_firm,
)


def _order_create(
    setup: _Firm,
    *,
    rate: Decimal,
    inclusive: bool | None = True,
    discount_amount: Decimal | None = None,
    discount_percent: Decimal | None = None,
    quantity: Decimal = Decimal("2"),
) -> SalesOrderCreate:
    """Return an order of one typed line."""
    return SalesOrderCreate(
        customer_id=setup.customer.id,
        branch_id=setup.branch.id,
        warehouse_id=setup.warehouse.id,
        order_date=date(2026, 8, 4),
        rate_includes_tax=inclusive,
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=setup.product.id,
                quantity=quantity,
                unit_price=rate,
                discount_amount=discount_amount,
                # Typed as none, so no standing arrangement muddies the sums.
                discount_percent=(
                    discount_percent
                    if discount_percent is not None or discount_amount is not None
                    else Decimal("0")
                ),
            )
        ],
    )


def _order_line(setup: _Firm, order: SalesOrder) -> SalesOrderLine:
    """Return the order's only line."""
    line = setup.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    return line


def _quotation_create(
    setup: _Firm,
    *,
    rate: Decimal,
    inclusive: bool | None = True,
    discount_amount: Decimal | None = None,
) -> QuotationCreate:
    """Return a quotation of one typed line."""
    return QuotationCreate(
        customer_id=setup.customer.id,
        branch_id=setup.branch.id,
        warehouse_id=setup.warehouse.id,
        quotation_date=date(2026, 8, 4),
        valid_until=date(2099, 12, 31),
        rate_includes_tax=inclusive,
        lines=[
            QuotationLineWrite(
                line_number=1,
                product_id=setup.product.id,
                quantity=Decimal("2"),
                unit_price=rate,
                discount_amount=discount_amount,
                discount_percent=None if discount_amount is not None else Decimal("0"),
            )
        ],
    )


def _quotation_line(setup: _Firm, quotation: SalesQuotation) -> SalesQuotationLine:
    """Return the quotation's only line."""
    line = setup.session.scalar(
        select(SalesQuotationLine).where(
            SalesQuotationLine.sales_quotation_id == quotation.id
        )
    )
    assert line is not None
    return line


def test_an_order_typed_at_shelf_prices_totals_the_shelf_price() -> None:
    """2 x 118 incl. 18% is 200 taxable and 36 tax."""
    setup = _gst_firm(sales_order_stage=True)
    order = SalesOrderService(setup.session).create_order(
        _order_create(setup, rate=Decimal("118")),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    line = _order_line(setup, order)

    assert order.rate_includes_tax is True
    assert line.unit_price == Decimal("100.0000")
    assert line.entered_rate == Decimal("118.0000")
    assert line.entered_discount_amount is None
    assert order.subtotal == Decimal("200.0000")
    assert order.tax_total == Decimal("36.0000")
    assert order.grand_total == Decimal("236.0000")
    response = SalesOrderService(setup.session).order_response(order)
    assert response.rate_includes_tax is True
    assert response.lines[0].entered_rate == Decimal("118.0000")


def test_an_order_to_another_state_divides_by_igst() -> None:
    """The rate divided by is the one charged, across the border too."""
    setup = _gst_firm(buyer_gstin=OTHER_STATE_BUYER, sales_order_stage=True)
    order = SalesOrderService(setup.session).create_order(
        _order_create(setup, rate=Decimal("118")),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    assert _order_line(setup, order).unit_price == Decimal("100.0000")
    assert order.grand_total == Decimal("236.0000")


def test_an_order_keeps_the_typed_discount_amount_beside_its_pre_tax_twin() -> None:
    """2 x 118 less 23.60 is 212.40: 20 off before tax, 23.60 as typed."""
    setup = _gst_firm(sales_order_stage=True)
    order = SalesOrderService(setup.session).create_order(
        _order_create(setup, rate=Decimal("118"), discount_amount=Decimal("23.60")),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    line = _order_line(setup, order)

    assert line.discount_amount == Decimal("20.0000")
    assert line.entered_discount_amount == Decimal("23.6000")
    assert order.subtotal == Decimal("180.0000")
    assert order.grand_total == Decimal("212.4000")


def test_an_order_that_says_nothing_is_before_tax_whatever_the_firm_default() -> None:
    """The firm default is the counter bill's and the editors'; absent is off."""
    setup = _gst_firm(sales_order_stage=True, default_inclusive=True)
    order = SalesOrderService(setup.session).create_order(
        _order_create(setup, rate=Decimal("118"), inclusive=None),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    line = _order_line(setup, order)

    assert order.rate_includes_tax is False
    assert line.unit_price == Decimal("118.0000")
    assert line.entered_rate is None
    assert order.tax_total == Decimal("42.4800")


def test_an_order_edit_reads_the_rates_sent_back_as_typed() -> None:
    """Absent keeps the order's switch; the rates sent are read the same way.

    Switching it off on an edit takes the rates as before tax, and the typed
    figures go with it.
    """
    setup = _gst_firm(sales_order_stage=True)
    service = SalesOrderService(setup.session)
    actor = uuid4()
    order = service.create_order(
        _order_create(setup, rate=Decimal("118")),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    line_id = _order_line(setup, order).id

    edited = service.update_order(
        order.id,
        _order_create(
            setup, rate=Decimal("118"), quantity=Decimal("1"), inclusive=None
        ),
        firm_scope=setup.firm.id,
        actor_id=actor,
    )
    line = _order_line(setup, edited)
    assert edited.rate_includes_tax is True
    assert line.id == line_id, "the line is reconciled, not re-inserted"
    assert line.entered_rate == Decimal("118.0000")
    assert edited.grand_total == Decimal("118.0000")

    off = service.update_order(
        order.id,
        _order_create(
            setup, rate=Decimal("100"), quantity=Decimal("1"), inclusive=False
        ),
        firm_scope=setup.firm.id,
        actor_id=actor,
    )
    line = _order_line(setup, off)
    assert off.rate_includes_tax is False
    assert line.unit_price == Decimal("100.0000")
    assert line.entered_rate is None
    assert off.grand_total == Decimal("118.0000")


def test_a_counter_bill_does_not_read_its_rates_twice() -> None:
    """The bill reads the typed rate once; the order it raises is before tax."""
    setup = _gst_firm(default_inclusive=True)
    invoice = SalesInvoiceService(setup.session).create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    product_id=setup.product.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("2"),
                    unit_price=Decimal("118"),
                    discount_percent=Decimal("0"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    order = setup.session.scalar(
        select(SalesOrder).where(SalesOrder.firm_id == setup.firm.id)
    )
    assert order is not None

    assert invoice.grand_total == Decimal("236.0000")
    assert order.rate_includes_tax is False
    assert order.grand_total == Decimal("236.0000")
    assert _order_line(setup, order).unit_price == Decimal("100.0000")


def test_a_quotation_typed_at_shelf_prices_quotes_the_shelf_price() -> None:
    """The quotation reads its typed rates exactly as the order does."""
    setup = _gst_firm()
    quotation = QuotationService(setup.session).create_quotation(
        _quotation_create(setup, rate=Decimal("118")),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    line = _quotation_line(setup, quotation)

    assert quotation.rate_includes_tax is True
    assert line.unit_price == Decimal("100.0000")
    assert line.entered_rate == Decimal("118.0000")
    assert quotation.grand_total == Decimal("236.0000")
    response = QuotationService(setup.session).quotation_response(quotation)
    assert response.rate_includes_tax is True
    assert response.lines[0].entered_rate == Decimal("118.0000")


def test_a_quotation_that_says_nothing_is_before_tax() -> None:
    """An import, or a client that never offers the switch, quotes as before."""
    setup = _gst_firm(default_inclusive=True)
    quotation = QuotationService(setup.session).create_quotation(
        _quotation_create(setup, rate=Decimal("118"), inclusive=None),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    assert quotation.rate_includes_tax is False
    assert _quotation_line(setup, quotation).entered_rate is None
    assert quotation.tax_total == Decimal("42.4800")


def test_a_shelf_price_quotation_becomes_a_shelf_price_order() -> None:
    """Converting hands the order the rates as typed, discount amount too.

    The order reads them back on its own date, so it bills what was quoted,
    and an editor opening it shows the figures the customer was given.
    """
    setup = _gst_firm(sales_order_stage=True)
    service = QuotationService(setup.session)
    actor = uuid4()
    quotation = service.create_quotation(
        _quotation_create(setup, rate=Decimal("118"), discount_amount=Decimal("23.60")),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    service.accept_quotation(quotation.id, firm_scope=setup.firm.id, actor_id=actor)
    _, order = service.convert_quotation(
        quotation.id,
        firm_scope=setup.firm.id,
        actor_id=actor,
        order_date=date(2026, 8, 5),
    )
    line = _order_line(setup, order)

    assert order.rate_includes_tax is True
    assert line.unit_price == Decimal("100.0000")
    assert line.entered_rate == Decimal("118.0000")
    assert line.discount_amount == Decimal("20.0000")
    assert line.entered_discount_amount == Decimal("23.6000")
    assert order.grand_total == quotation.grand_total == Decimal("212.4000")


def test_a_quotation_before_tax_converts_as_it_always_did() -> None:
    """No switch on the quote, none on the order, the rate carried as it is."""
    setup = _gst_firm(sales_order_stage=True)
    service = QuotationService(setup.session)
    actor = uuid4()
    quotation = service.create_quotation(
        _quotation_create(setup, rate=Decimal("100"), inclusive=False),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    service.accept_quotation(quotation.id, firm_scope=setup.firm.id, actor_id=actor)
    _, order = service.convert_quotation(
        quotation.id,
        firm_scope=setup.firm.id,
        actor_id=actor,
        order_date=date(2026, 8, 5),
    )

    assert order.rate_includes_tax is False
    assert _order_line(setup, order).unit_price == Decimal("100.0000")
    assert order.grand_total == Decimal("236.0000")


def test_a_shelf_price_quotation_prints_both_rates() -> None:
    """The customer reads the price they were quoted beside the taxable one."""
    setup = _gst_firm()
    quotation = QuotationService(setup.session).create_quotation(
        _quotation_create(setup, rate=Decimal("118")),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    pdf, _ = QuotationPrintService(setup.session).render(
        quotation.id, firm_scope=setup.firm.id
    )

    printed = _text_of(pdf)
    assert "incl." in printed
    assert "118.00 | 100.00" in printed
