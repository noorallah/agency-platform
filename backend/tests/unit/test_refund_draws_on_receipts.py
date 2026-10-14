"""A refund comes off the receipts that brought the money in (D-FIN-30).

A refund took money off the customer's advance and named no receipt, so the
receipt kept reading it as unapplied: a receipt of 500.00 on account with
200.00 handed back read 500.00, and the period close and the order's advance
list read it too. The customer's account was right; the receipt was not. A
refund now records which receipts gave how much, oldest first, the receipts
come down by it, and reversing the refund puts back exactly that.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.settlements.models import RefundReceiptDraw, Settlement
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import ReceiptService, RefundService
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers


def _receive(books: _Books, amount: str, on: date = WHEN) -> Settlement:
    """Record one receipt on account, set against nothing."""
    row = ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=on,
            amount=Decimal(amount),
            method=SettlementMethodEnum.CASH,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _refund(books: _Books, amount: str) -> Settlement:
    """Hand money back to the customer."""
    row = RefundService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _unapplied(books: _Books, receipt: Settlement) -> Decimal:
    """Read a receipt's unapplied money fresh from the database."""
    books.session.refresh(receipt)
    return receipt.unallocated_amount


def test_a_refund_comes_off_the_receipt_that_brought_the_money_in() -> None:
    """The defect as reproduced: 500.00 on account, 200.00 handed back."""
    books = _Books(_session_factory()())
    receipt = _receive(books, "500.00")

    refund = _refund(books, "200.00")

    assert _unapplied(books, receipt) == Decimal("300.00")
    draws = books.session.scalars(
        select(RefundReceiptDraw).where(RefundReceiptDraw.refund_id == refund.id)
    ).all()
    assert [(row.receipt_id, row.amount) for row in draws] == [
        (receipt.id, Decimal("200.00"))
    ]
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("300.00")


def test_the_oldest_receipt_gives_first() -> None:
    """A refund larger than one receipt's money takes the next one too."""
    books = _Books(_session_factory()())
    newer = _receive(books, "300.00", on=WHEN)
    older = _receive(books, "100.00", on=date(2026, 4, 10))

    _refund(books, "250.00")

    assert _unapplied(books, older) == Decimal("0.00")
    assert _unapplied(books, newer) == Decimal("150.00")


def test_reversing_the_refund_gives_each_receipt_back_what_it_gave() -> None:
    """A reversal puts back exactly what each receipt gave, and no more."""
    books = _Books(_session_factory()())
    newer = _receive(books, "300.00", on=WHEN)
    older = _receive(books, "100.00", on=date(2026, 4, 10))
    refund = _refund(books, "250.00")

    RefundService(books.session).reverse(
        refund.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Wrong"
    )
    books.session.commit()

    assert _unapplied(books, older) == Decimal("100.00")
    assert _unapplied(books, newer) == Decimal("300.00")
    statuses = books.session.scalars(
        select(RefundReceiptDraw.status).where(RefundReceiptDraw.refund_id == refund.id)
    ).all()
    assert set(statuses) == {"REVERSED"}


def test_money_handed_back_cannot_be_set_against_a_bill() -> None:
    """The receipt now refuses what it no longer has, by its own figure."""
    books = _Books(_session_factory()())
    invoice = books.sales_invoice("SI-1", "400.00")
    receipt = _receive(books, "500.00")
    _refund(books, "200.00")

    # Refused by the receipt's own figure, which before this read 500.00
    # and let the account be the only thing standing in the way.
    with pytest.raises(ValidationError, match="300.00 left unapplied"):
        ReceiptService(books.session).allocate(
            receipt.id,
            invoice_id=invoice.id,
            amount=Decimal("400.00"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_refund_paid_from_a_returns_credit_takes_nothing_off_a_receipt() -> None:
    """Credits pay first: only what they do not cover comes off a receipt.

    With no return or credit note on the account the whole refund is the
    receipts' money; this pins that a refund of less than nothing drawn from
    credits draws exactly its amount, never more.
    """
    books = _Books(_session_factory()())
    receipt = _receive(books, "500.00")
    _refund(books, "500.00")

    assert _unapplied(books, receipt) == Decimal("0.00")
    with pytest.raises(ValidationError):
        _refund(books, "1.00")
