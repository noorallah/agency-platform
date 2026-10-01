"""A counter types the shelf price, and the bill still states it before tax.

Backlog 64 row 4. A rate typed on a bill whose "Rate includes GST" switch is on
is read back to its pre-tax rate before the line is written, so the journal,
returns, GSTR-1/3B and every document downstream keep reading ``unit_price``
as they always have; the figure typed is kept beside it in ``entered_rate``
for the print and the editor. A line continuing an order or a note keeps the
price it inherited, and a bill with the switch off is priced exactly as before.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.money import quantize_ledger
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoicePdfRenderer,
    TemplateSettings,
)
from app.sales_order.models import SalesOrderLine, SalesWorkflowSettings
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesWorkflowSettingsWrite,
)
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from app.tax.services.gst_template import apply_india_gst_template
from app.tax.services.inclusive_rate import derive_pre_tax
from tests.unit.test_invoice_print import _document, _text_of
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

#: A Tamil Nadu seller, and a buyer in the same state or in Karnataka.
SELLER_GSTIN = "33AABCU9603R1ZM"
LOCAL_BUYER = "33AAACR5055K1Z5"
OTHER_STATE_BUYER = "29AAACR5055K1Z5"


def _gst_firm(
    *,
    buyer_gstin: str = LOCAL_BUYER,
    sales_order_stage: bool = False,
    default_inclusive: bool = False,
) -> _Firm:
    """Build a counter firm on the GST template selling an 18% good."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.firm.gst_number = SELLER_GSTIN
    setup.customer.gst_number = buyer_gstin
    session.commit()
    apply_india_gst_template(session, firm_id=setup.firm.id, actor_id=uuid4())
    setup.product.tax_profile_group_code = "GST_18_LOCAL"
    session.add(
        SalesWorkflowSettings(
            firm_id=setup.firm.id,
            quotation_stage=False,
            sales_order_stage=sales_order_stage,
            delivery_note_stage=False,
            rate_includes_tax=default_inclusive,
        )
    )
    session.commit()
    return setup


def _bill(
    setup: _Firm,
    *,
    rate: Decimal,
    quantity: Decimal = Decimal("2"),
    inclusive: bool | None = True,
    discount_amount: Decimal | None = None,
    discount_percent: Decimal | None = None,
) -> SalesInvoice:
    """Raise a counter bill for one typed line and return it."""
    return SalesInvoiceService(setup.session).create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            invoice_date=date(2026, 8, 4),
            rate_includes_tax=inclusive,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=setup.product.id,
                    line_number=1,
                    current_invoice_quantity=quantity,
                    unit_price=rate,
                    # Typed as none, so no standing arrangement muddies the sums.
                    discount_amount=discount_amount,
                    discount_percent=(
                        discount_percent
                        if discount_percent is not None or discount_amount is not None
                        else Decimal("0")
                    ),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _line(session: Session, invoice: SalesInvoice) -> SalesInvoiceLine:
    """Return the bill's only line."""
    line = session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    )
    assert line is not None
    return line


def _components(setup: _Firm, invoice: SalesInvoice) -> dict[str, Decimal]:
    """Return the tax the bill charged, by component."""
    response = SalesInvoiceService(setup.session).invoice_response(invoice)
    return {
        tax.component_code: tax.amount for line in response.lines for tax in line.taxes
    }


def test_a_typed_inclusive_rate_bills_exactly_the_shelf_price() -> None:
    """2 x 118 incl. 18% is 200 taxable and 36 tax, CGST and SGST in halves."""
    setup = _gst_firm()
    invoice = _bill(setup, rate=Decimal("118"))
    line = _line(setup.session, invoice)

    assert invoice.rate_includes_tax is True
    assert line.unit_price == Decimal("100.0000")
    assert line.entered_rate == Decimal("118.0000")
    assert invoice.subtotal == Decimal("200.0000")
    assert invoice.tax_total == Decimal("36.0000")
    assert invoice.grand_total == Decimal("236.0000")
    assert _components(setup, invoice) == {
        "CGST": Decimal("18.0000"),
        "SGST": Decimal("18.0000"),
    }


def test_a_sale_to_another_state_divides_by_igst() -> None:
    """The rate divided by is the one charged: IGST across the border."""
    setup = _gst_firm(buyer_gstin=OTHER_STATE_BUYER)
    invoice = _bill(setup, rate=Decimal("118"))

    assert _line(setup.session, invoice).unit_price == Decimal("100.0000")
    assert invoice.grand_total == Decimal("236.0000")
    assert _components(setup, invoice) == {"IGST": Decimal("36.0000")}


def test_an_awkward_price_still_adds_back_to_the_paisa() -> None:
    """100 incl. 18% does not divide evenly; taxable plus tax is still 100.

    Kept at the documents' four places: 84.7458 + 15.2542. Rounding the
    taxable value to the paisa first would bill 84.75 + 15.26 = 100.01.
    """
    setup = _gst_firm()
    invoice = _bill(setup, rate=Decimal("100"), quantity=Decimal("1"))

    assert _line(setup.session, invoice).unit_price == Decimal("84.7458")
    assert invoice.subtotal + invoice.tax_total == Decimal("100.0000")
    assert quantize_ledger(invoice.subtotal) + quantize_ledger(
        invoice.tax_total
    ) == Decimal("100.00")


def test_a_discount_amount_on_an_inclusive_line_is_gross_too() -> None:
    """2 x 118 less 23.60 off is 212.40 paid: 180 taxable, 32.40 tax."""
    setup = _gst_firm()
    invoice = _bill(setup, rate=Decimal("118"), discount_amount=Decimal("23.60"))
    line = _line(setup.session, invoice)

    assert line.unit_price == Decimal("100.0000")
    assert line.discount_amount == Decimal("20.0000")
    assert invoice.subtotal == Decimal("180.0000")
    assert invoice.tax_total == Decimal("32.4000")
    assert invoice.grand_total == Decimal("212.4000")


def test_a_discount_percentage_applies_unchanged() -> None:
    """Ten percent off a shelf price is ten percent off its taxable value."""
    setup = _gst_firm()
    invoice = _bill(setup, rate=Decimal("118"), discount_percent=Decimal("10"))
    line = _line(setup.session, invoice)

    assert line.discount_percent == Decimal("10.0000")
    assert invoice.subtotal == Decimal("180.0000")
    assert invoice.grand_total == Decimal("212.4000")


def test_the_firms_default_decides_a_bill_that_says_nothing() -> None:
    """Absent takes the firm's setting; an explicit answer beats it."""
    setup = _gst_firm(default_inclusive=True)

    defaulted = _bill(setup, rate=Decimal("118"), inclusive=None)
    assert defaulted.rate_includes_tax is True
    assert defaulted.grand_total == Decimal("236.0000")

    refused = _bill(setup, rate=Decimal("118"), inclusive=False)
    assert refused.rate_includes_tax is False
    assert _line(setup.session, refused).entered_rate is None
    assert refused.grand_total == Decimal("278.4800")


def test_the_switch_off_prices_a_bill_exactly_as_before() -> None:
    """A firm that never chose anything: 118 is the rate before tax."""
    setup = _gst_firm()
    invoice = _bill(setup, rate=Decimal("118"), inclusive=None)
    line = _line(setup.session, invoice)

    assert invoice.rate_includes_tax is False
    assert line.unit_price == Decimal("118.0000")
    assert line.entered_rate is None
    assert invoice.subtotal == Decimal("236.0000")
    assert invoice.tax_total == Decimal("42.4800")


def test_a_line_continuing_an_order_keeps_its_inherited_price() -> None:
    """The switch reads only rates typed on this bill, never an order's."""
    setup = _gst_firm(sales_order_stage=True)
    actor = uuid4()
    orders = SalesOrderService(setup.session)
    order = orders.stage_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("2"),
                    unit_price=Decimal("100"),
                    discount_percent=Decimal("0"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    orders.stage_approval(order.id, firm_scope=setup.firm.id, actor_id=actor)
    setup.session.commit()
    order_line = setup.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None

    invoice = SalesInvoiceService(setup.session).create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            invoice_date=date(2026, 8, 4),
            rate_includes_tax=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("2"),
                    # The editor sends the order's own price back.
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    line = _line(setup.session, invoice)

    assert line.unit_price == Decimal("100.0000")
    assert line.entered_rate is None
    assert invoice.tax_total == Decimal("36.0000")


def test_an_edit_keeps_the_rate_as_typed() -> None:
    """Re-saving the draft from its own lines keeps the figure typed."""
    setup = _gst_firm()
    service = SalesInvoiceService(setup.session)
    draft = _bill(setup, rate=Decimal("118"))
    [line] = service.invoice_response(draft).lines

    service.update_invoice(
        draft.id,
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            invoice_date=draft.invoice_date,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=line.source_document_type,
                    source_document_id=line.source_document_id,
                    source_document_line_id=line.source_document_line_id,
                    line_number=1,
                    current_invoice_quantity=Decimal("1"),
                    unit_price=line.unit_price,
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    stored = setup.session.get(SalesInvoice, draft.id)
    assert stored is not None
    assert stored.rate_includes_tax is True
    [kept] = service.invoice_response(stored).lines
    assert kept.entered_rate == Decimal("118.0000")
    assert kept.unit_price == Decimal("100.0000")
    assert stored.grand_total == Decimal("118.0000")


def test_a_slabbed_rate_is_asked_again_at_the_taxable_value() -> None:
    """Gross decides 18%, the taxable value 12%: the second answer is taken."""
    asked: list[Decimal] = []

    def rate_at(value: Decimal) -> Decimal:
        """Charge 18% above 1,000 and 12% at or below it."""
        asked.append(value)
        return Decimal("0.18") if value > Decimal("1000") else Decimal("0.12")

    derived = derive_pre_tax(
        quantity=Decimal("1"),
        entered_rate=Decimal("1100"),
        discount_percent=None,
        discount_amount=None,
        rate_at=rate_at,
    )

    assert len(asked) == 2, "asked at the gross value, then once more, then stop"
    assert derived.tax_rate == Decimal("0.12")
    assert derived.unit_price == Decimal("982.1429")


def test_the_firm_default_is_left_alone_by_a_write_that_omits_it() -> None:
    """A settings write from an editor that never showed the switch keeps it."""
    setup = _gst_firm()
    service = SalesWorkflowService(setup.session)
    actor = uuid4()
    stages = {
        "quotation_stage": False,
        "sales_order_stage": False,
        "delivery_note_stage": False,
    }

    switched = service.update_settings(
        SalesWorkflowSettingsWrite(**stages, rate_includes_tax=True),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    assert switched.rate_includes_tax is True
    kept = service.update_settings(
        SalesWorkflowSettingsWrite(**stages),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    assert kept.rate_includes_tax is True
    assert service.settings_response(setup.firm.id).rate_includes_tax is True


def _inclusive_document() -> InvoiceDocument:
    """Return the print test's bill, its rate typed as 295 incl. 18%."""
    document = _document()
    [line] = document.lines
    return replace(document, lines=(replace(line, entered_rate=Decimal("295.00")),))


def test_the_print_states_both_rates() -> None:
    """The A4 bill and the counter roll show the rate typed and the taxable one."""
    a4 = _text_of(InvoicePdfRenderer().render(_inclusive_document()))
    # The heading wraps in its cell, as the tax headings do.
    assert "Rate | incl. | GST | Rate" in a4
    assert "295.00 | 250.00" in a4

    roll = _text_of(
        InvoicePdfRenderer(TemplateSettings(page_size="THERMAL80")).render(
            _inclusive_document()
        )
    )
    assert "295.00" in roll
    assert "taxable rate 250.00" in roll


def test_a_bill_typed_before_tax_prints_one_rate() -> None:
    """No line typed inclusive, no extra column."""
    printed = _text_of(InvoicePdfRenderer().render(_document()))
    assert "incl." not in printed
