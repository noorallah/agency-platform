"""The printed bill names every delivery note and order it bills (backlog 58.7).

A tax invoice made of several dispatches has to say which, or the buyer
cannot match it to the goods received: Tally prints "Delivery Note No." and
"Buyer's Order No." in the head. Until 2026-10-01 the PDF named only the
invoice's own reference.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_invoice.services.invoice_pdf import PartyBlock
from app.sales_invoice.services.invoice_print_service import (
    SEVERAL,
    SalesInvoicePrintService,
)
from tests.unit.test_invoice_print import _text_of
from tests.unit.test_sales_invoice_module import (
    _Billing,
    _dispatched_note,
    _session_factory,
)

pytestmark = pytest.mark.typed_document_numbers


@pytest.fixture(autouse=True)
def _no_platform_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the seller without opening the platform store.

    `firm_party` reads `firms` through `platform_reader`, a real connection;
    the unit suite has none, and the seller is not what these tests are about.
    """
    monkeypatch.setattr(
        SalesInvoicePrintService,
        "_seller",
        lambda self, firm_scope: PartyBlock(name="Seller", address_lines=[]),
    )


def _second_note(setup: _Billing, quantity: Decimal, on: date) -> DeliveryNote:
    """Ship more of the already-approved order on another note."""
    notes = DeliveryNoteService(setup.session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=setup.order.id,
            delivery_date=on,
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=setup.order_line.id,
                    line_number=1,
                    current_delivery_quantity=quantity,
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    notes.approve_note(note.id, firm_scope=setup.firm.id, actor_id=uuid4())
    notes.dispatch_note(note.id, firm_scope=setup.firm.id, actor_id=uuid4())
    return note


def _bill(setup: _Billing, notes: list[DeliveryNote]) -> SalesInvoice:
    """Bill every line of the given notes on one invoice."""
    lines = []
    for number, note in enumerate(notes, start=1):
        dn_line = setup.session.scalar(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
        assert dn_line is not None
        lines.append(
            SalesInvoiceLineWrite(
                source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                source_document_id=note.id,
                source_document_line_id=dn_line.id,
                line_number=number,
                current_invoice_quantity=dn_line.current_delivery_quantity,
                unit_price=Decimal("100"),
            )
        )
    return SalesInvoiceService(setup.session).create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            invoice_date=date(2026, 8, 9),
            lines=lines,
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _printed(setup: _Billing, invoice: SalesInvoice) -> str:
    pdf, _ = SalesInvoicePrintService(setup.session).render(
        invoice.id, firm_scope=setup.firm.id
    )
    # A long number wraps in its cell, so the runs are joined back up; the
    # PDF escapes its parentheses.
    text = _text_of(pdf).replace(" | ", "")
    return text.replace(r"\(", "(").replace(r"\)", ")")


def test_a_bill_of_two_notes_names_both_and_their_order() -> None:
    setup = _Billing(_session_factory()())
    setup.order.customer_reference = "PO-77"
    first = _dispatched_note(setup, quantity=Decimal("2"))
    second = _second_note(setup, Decimal("2"), date(2026, 8, 6))

    text = _printed(setup, _bill(setup, [first, second]))

    for note in (first, second):
        assert note.delivery_note_number in text
    assert "Delivery note" in text
    assert f"{setup.order.order_number} dt." in text
    assert "Buyer's order no.PO-77" in text
    # More than one note: every line says which one it came from.
    assert f"(note {first.delivery_note_number})" in text
    assert f"(note {second.delivery_note_number})" in text


def test_a_bill_of_one_note_prints_its_one_note_and_order() -> None:
    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup, quantity=Decimal("4"))

    text = _printed(setup, _bill(setup, [note]))

    assert f"{note.delivery_note_number} dt. 04 Aug" in text
    assert setup.order.order_number in text
    # One note: the head says it, and the line need not repeat it.
    assert f"(note {note.delivery_note_number})" not in text


def test_many_notes_say_several_in_the_head_and_name_each_on_its_line() -> None:
    setup = _Billing(_session_factory()())
    notes = [_dispatched_note(setup, quantity=Decimal("1"))]
    notes += [
        _second_note(setup, Decimal("1"), date(2026, 8, 5 + index))
        for index in range(3)
    ]

    text = _printed(setup, _bill(setup, notes))

    assert SEVERAL in text
    for note in notes:
        assert f"(note {note.delivery_note_number})" in text


def test_the_offers_claimed_on_the_order_and_the_saving_are_printed() -> None:
    """Backlog 60 item 12: "Diwali offer, you saved 50" on the bill."""
    from app.promotions.models import Promotion, PromotionRedemption

    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup, quantity=Decimal("4"))
    promotion = Promotion(
        firm_id=setup.firm.id,
        code="DIWALI20",
        name="Diwali 20%",
        priority=100,
        status="ACTIVE",
        allow_stacking=True,
        version_group_id=uuid4(),
        version_number=1,
    )
    setup.session.add(promotion)
    setup.session.flush()
    setup.session.add(
        PromotionRedemption(
            firm_id=setup.firm.id,
            promotion_id=promotion.id,
            customer_id=setup.customer.id,
            document_type="SALES_ORDER",
            document_id=setup.order.id,
            document_number=setup.order.order_number,
            redeemed_on=date(2026, 8, 3),
            benefit_amount=Decimal("50"),
            status="CLAIMED",
        )
    )
    invoice = _bill(setup, [note])
    invoice.line_discount_total = Decimal("50")
    setup.session.commit()

    text = _printed(setup, invoice)

    assert "OffersDIWALI20" in text
    assert "You saved50.00" in text


def test_a_bill_with_no_offer_and_no_discount_says_neither() -> None:
    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup, quantity=Decimal("4"))
    text = _printed(setup, _bill(setup, [note]))
    assert "Offers" not in text
    assert "You saved" not in text
