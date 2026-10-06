"""Free goods can come back on a sales return, credited nothing.

D-PRC-8, driven 2026-10-06: a bill of 12 + 1 free. A return of the 12 went
through; a second return of 1 for the same line was refused -- "Return
quantity exceeds what was dispatched on the source document (12.0000 sent,
12.0000 already returned)." -- so the thirteenth unit had nowhere to go but a
stock adjustment. The buying side has taken free goods back since D-BUY-56,
and this is its twin: what the note shipped can come back, charged and free;
the free units are credited nothing and return to stock at their cost; and a
free unit that came back is a unit the offer and the principal's claim no
longer count as given.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.customers.models import Customer, CustomerReceivableTransaction
from app.delivery_note.models import DeliveryNoteLine
from app.inventory.models import InventoryRecord
from app.principal_claims.services import PrincipalClaimService
from app.promotions.models import Promotion
from app.promotions.services.promotion_service import budget_rooms
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.models import SalesReturn, SalesReturnLine
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services import SalesReturnService
from tests.unit.test_principal_claim_free_goods import _Agency

D = Decimal


def _bill_line(agency: _Agency, bill: SalesInvoice) -> SalesInvoiceLine:
    """Return the bill's one line."""
    return agency.session.scalars(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == bill.id,
            SalesInvoiceLine.is_deleted.is_(False),
        )
    ).one()


def _note_line(agency: _Agency, bill: SalesInvoice) -> DeliveryNoteLine:
    """Return the note line whose goods the bill's line charged for."""
    line = agency.session.get(
        DeliveryNoteLine, _bill_line(agency, bill).source_document_line_id
    )
    assert line is not None
    return line


def _describe(
    agency: _Agency,
    bill: SalesInvoice,
    quantity: str,
    *,
    free: str | None = None,
    off_the_note: bool = False,
) -> SalesReturnCreate:
    """Describe a return of the bill's line, off the bill or off its note."""
    if off_the_note:
        note_line = _note_line(agency, bill)
        source = (
            SalesReturnSourceType.DELIVERY_NOTE,
            note_line.delivery_note_id,
            note_line.id,
        )
    else:
        source = (
            SalesReturnSourceType.SALES_INVOICE,
            bill.id,
            _bill_line(agency, bill).id,
        )
    return SalesReturnCreate(
        warehouse_id=agency.setup.warehouse.id,
        return_date=date(2026, 8, 20),
        lines=[
            SalesReturnLineWrite(
                source_document_type=source[0],
                source_document_id=source[1],
                source_document_line_id=source[2],
                line_number=1,
                current_return_quantity=D(quantity),
                free_quantity=None if free is None else D(free),
            )
        ],
    )


def _returned(
    agency: _Agency,
    bill: SalesInvoice,
    quantity: str,
    *,
    free: str | None = None,
    off_the_note: bool = False,
) -> SalesReturn:
    """Raise, approve and complete a return of the bill's line."""
    service = SalesReturnService(agency.session)
    row = service.create_return(
        _describe(agency, bill, quantity, free=free, off_the_note=off_the_note),
        firm_id=agency.firm_id,
        actor_id=agency.actor,
    )
    service.approve_return(row.id, firm_scope=agency.firm_id, actor_id=agency.actor)
    return service.complete_return(
        row.id, firm_scope=agency.firm_id, actor_id=agency.actor
    )


def _line(agency: _Agency, row: SalesReturn) -> SalesReturnLine:
    """Return a return's one line, freshly read."""
    agency.session.expire_all()
    return agency.session.scalars(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == row.id)
    ).one()


def _on_hand(agency: _Agency, product_id: UUID | None = None) -> Decimal:
    """Sum what the firm holds of a product, sellable."""
    agency.session.expire_all()
    rows = agency.session.scalars(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == agency.firm_id,
            InventoryRecord.product_id == (product_id or agency.setup.product.id),
        )
    ).all()
    return sum((D(str(row.current_quantity)) for row in rows), D("0"))


def _outstanding(agency: _Agency) -> Decimal:
    """Return what the customer owes."""
    agency.session.expire_all()
    customer = agency.session.get(Customer, agency.setup.customer.id)
    assert customer is not None
    return D(str(customer.current_outstanding))


def _credit_rows(agency: _Agency) -> int:
    """Count the credits written to the customer's account by returns."""
    return len(
        agency.session.scalars(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.reference_type == "SALES_RETURN"
            )
        ).all()
    )


def test_the_free_unit_comes_back_after_everything_charged_has() -> None:
    """The case as driven: the charged four, then the free one, same line."""
    agency = _Agency()
    held = _on_hand(agency)
    bill = agency.bill(free="1")
    assert _on_hand(agency) == held - 5
    _returned(agency, bill, "4")
    owed, credits = _outstanding(agency), _credit_rows(agency)
    assert _on_hand(agency) == held - 1

    second = _returned(agency, bill, "1")

    line = _line(agency, second)
    assert (line.current_return_quantity, line.free_quantity) == (D("0"), D("1"))
    assert (line.gross_amount, line.tax_amount, line.net_amount) == (
        D("0"),
        D("0"),
        D("0"),
    )
    assert _on_hand(agency) == held, "the thirteenth unit is back on the shelf"
    assert _outstanding(agency) == owed, "a free unit credits nothing"
    assert _credit_rows(agency) == credits
    assert second.journal_entry_id is None, "no credit note was posted"


def test_left_blank_the_charged_units_are_taken_first() -> None:
    """Five back of four charged and one free: four are credited, one is not."""
    agency = _Agency()
    held = _on_hand(agency)
    bill = agency.bill(free="1")

    row = _returned(agency, bill, "5")

    line = _line(agency, row)
    assert (line.current_return_quantity, line.free_quantity) == (D("4"), D("1"))
    assert line.gross_amount == D("400.0000")
    assert line.restock_quantity == D("5.0000")
    assert row.total_current_return_quantity == D("5.0000")
    assert _on_hand(agency) == held
    assert _outstanding(agency) == D("0")


def test_a_number_says_the_unit_coming_back_is_the_free_one() -> None:
    """One back, stated free, while all four charged are still out."""
    agency = _Agency()
    bill = agency.bill(free="1")
    owed = _outstanding(agency)

    row = _returned(agency, bill, "1", free="1")

    line = _line(agency, row)
    assert (line.current_return_quantity, line.free_quantity) == (D("0"), D("1"))
    assert _outstanding(agency) == owed
    (view,) = SalesReturnService(agency.session).return_responses([row])
    assert (view.lines[0].current_return_quantity, view.lines[0].free_quantity) == (
        D("1.0000"),
        D("1.0000"),
    ), "the line reads as it was typed: one back, one of it free"
    # The four charged are still there to come back, and are credited.
    rest = _returned(agency, bill, "4")
    assert _line(agency, rest).current_return_quantity == D("4.0000")
    assert _outstanding(agency) == D("0")


def test_more_than_was_sent_is_refused_and_says_what_is_left() -> None:
    """Six of four and one free."""
    agency = _Agency()
    bill = agency.bill(free="1")

    with pytest.raises(ValidationError) as refused:
        SalesReturnService(agency.session).create_return(
            _describe(agency, bill, "6"),
            firm_id=agency.firm_id,
            actor_id=agency.actor,
        )
    agency.session.rollback()

    assert refused.value.message == (
        "Return quantity exceeds what was dispatched on the source document "
        "(4.0000 sent and 1.0000 free, 0.0000 and 0.0000 already returned; "
        "line 1 can still bring back 4.0000 charged and 1.0000 free)."
    )


@pytest.mark.parametrize(
    ("quantity", "free", "message"),
    [
        (
            "1",
            "2",
            "Line 1: the free quantity is part of the return quantity and "
            "cannot exceed it.",
        ),
        (
            "2",
            "2",
            "Return quantity exceeds what was dispatched on the source "
            "document (4.0000 sent and 1.0000 free, 0.0000 and 0.0000 "
            "already returned; line 1 can still bring back 4.0000 charged "
            "and 1.0000 free).",
        ),
    ],
)
def test_no_more_free_goods_come_back_than_were_given(
    quantity: str, free: str, message: str
) -> None:
    """The free figure is part of the quantity, and capped at what was free."""
    agency = _Agency()
    bill = agency.bill(free="1")

    with pytest.raises(ValidationError) as refused:
        SalesReturnService(agency.session).create_return(
            _describe(agency, bill, quantity, free=free),
            firm_id=agency.firm_id,
            actor_id=agency.actor,
        )
    agency.session.rollback()

    assert refused.value.message == message


def test_a_bill_with_no_free_goods_keeps_the_refusal_it_had() -> None:
    """Nothing was free, so nothing about free goods is said."""
    agency = _Agency()
    bill = agency.bill(free="0")

    with pytest.raises(ValidationError) as refused:
        SalesReturnService(agency.session).create_return(
            _describe(agency, bill, "5"),
            firm_id=agency.firm_id,
            actor_id=agency.actor,
        )
    agency.session.rollback()

    assert refused.value.message == (
        "Return quantity exceeds what was dispatched on the source document "
        "(4.0000 sent, 0.0000 already returned)."
    )


@pytest.mark.parametrize("first_off_the_note", [True, False])
def test_the_same_free_unit_does_not_come_back_by_both_documents(
    first_off_the_note: bool,
) -> None:
    """The twin of D-BUY-61: the note line and the bill line are one unit."""
    agency = _Agency()
    bill = agency.bill(free="1")
    _returned(agency, bill, "1", free="1", off_the_note=first_off_the_note)
    number = agency.session.scalars(
        select(SalesReturnLine.source_document_number).where(
            SalesReturnLine.source_document_type == "DELIVERY_NOTE"
        )
    ).first()

    with pytest.raises(ValidationError) as refused:
        SalesReturnService(agency.session).create_return(
            _describe(agency, bill, "1", free="1", off_the_note=not first_off_the_note),
            firm_id=agency.firm_id,
            actor_id=agency.actor,
        )
    agency.session.rollback()

    assert "Free quantity exceeds what left free on" in refused.value.message
    assert refused.value.message.endswith(
        "(1.0000 sent free, 1.0000 already returned against it or the bill " "for it)."
    )
    assert number is None or number in refused.value.message


def test_the_reports_count_free_goods_as_quantity_with_no_value() -> None:
    """By product: five came back, one of them free, and 400 was credited."""
    agency = _Agency()
    bill = agency.bill(free="1")
    _returned(agency, bill, "5")
    service = SalesReturnService(agency.session)

    (by_product,) = service.by_product_report(firm_scope=agency.firm_id)
    (by_customer,) = service.by_customer_report(firm_scope=agency.firm_id)
    (register,) = service.register_report(firm_scope=agency.firm_id)
    summary = service.summary(firm_scope=agency.firm_id)

    assert (
        by_product.return_quantity,
        by_product.free_quantity,
        by_product.restock_quantity,
        by_product.return_amount,
    ) == (D("5.0000"), D("1.0000"), D("5.0000"), D("400.0000"))
    assert by_customer.return_amount == D("400.0000")
    assert register.credited_amount == D("400.0000")
    assert summary.total_restock_quantity == D("5.0000")


def test_cancelling_the_return_takes_the_free_goods_out_again() -> None:
    """Five came back; cancelled, five leave -- the free one with them."""
    agency = _Agency()
    held = _on_hand(agency)
    bill = agency.bill(free="1")
    row = _returned(agency, bill, "5")
    assert _on_hand(agency) == held

    SalesReturnService(agency.session).cancel_return(
        row.id, firm_scope=agency.firm_id, actor_id=agency.actor, reason="Mistake."
    )

    assert _on_hand(agency) == held - 5
    # And the free unit can come back again: a cancelled return holds nothing.
    again = _returned(agency, bill, "1", free="1")
    assert _line(agency, again).free_quantity == D("1.0000")


def _free_claimed(agency: _Agency, offer: Promotion) -> Decimal:
    """Return the free units the offer's budget counts as given."""
    agency.session.expire_all()
    return budget_rooms(agency.session, [offer], firm_id=agency.firm_id)[
        offer.id
    ].free_claimed


def test_a_free_unit_an_offer_gave_and_took_back_is_not_counted_as_given() -> None:
    """Buy 2 get 1 on four gives two; one comes back; the offer gave one."""
    agency = _Agency()
    typed = agency.bill(free="1")
    offer = agency.offer()
    bill = agency.bill(free=None)
    assert _bill_line(agency, bill).free_quantity == D("2.0000")
    assert _free_claimed(agency, offer) == D("2.0000")

    _returned(agency, bill, "1", free="1")

    assert _free_claimed(agency, offer) == D("1.0000")
    # A free unit somebody typed is nobody's offer, and moves no budget.
    _returned(agency, typed, "1", free="1")
    assert _free_claimed(agency, offer) == D("1.0000")
    # A charged unit coming back is not a free one.
    _returned(agency, bill, "1", off_the_note=True)
    assert _free_claimed(agency, offer) == D("1.0000")


def test_a_return_not_yet_completed_has_brought_nothing_back() -> None:
    """A draft holds its claim on the line and gives the offer nothing back."""
    agency = _Agency()
    offer = agency.offer()
    bill = agency.bill(free=None)

    SalesReturnService(agency.session).create_return(
        _describe(agency, bill, "1", free="1"),
        firm_id=agency.firm_id,
        actor_id=agency.actor,
    )

    assert _free_claimed(agency, offer) == D("2.0000")


def test_the_claim_preview_nets_free_goods_that_came_back() -> None:
    """The principal is not asked to pay for a unit the customer sent back."""
    agency = _Agency()
    typed = agency.bill(free="1")
    agency.offer()
    schemed = agency.bill(free=None)
    claims = PrincipalClaimService(agency.session)
    before = claims.preview(agency.write(), firm_id=agency.firm_id)
    assert (before.scheme_amount, before.free_goods_amount) == (
        D("60.00"),
        D("60.00"),
    )

    _returned(agency, typed, "1", free="1")
    _returned(agency, schemed, "1", free="1", off_the_note=True)

    after = claims.preview(agency.write(), firm_id=agency.firm_id)
    assert (after.scheme_amount, after.free_goods_amount) == (D("30.00"), D("0"))
    assert [(line.kind, line.quantity, line.amount) for line in after.lines] == [
        ("SCHEME", D("1.0000"), D("30.00"))
    ]


def test_a_claim_already_raised_is_not_rewritten() -> None:
    """Raised at 60.00; the free unit comes back afterwards; it still reads 60."""
    agency = _Agency()
    bill = agency.bill(free="1")
    claims = PrincipalClaimService(agency.session)
    claim = claims.raise_claim(
        agency.write(), firm_id=agency.firm_id, actor_id=agency.actor
    )
    agency.session.commit()

    _returned(agency, bill, "1", free="1")

    agency.session.expire_all()
    (view,) = claims.responses([claims.get(claim.id, firm_id=agency.firm_id)])
    assert (view.free_goods_amount, view.total_amount) == (D("60.00"), D("60.00"))
