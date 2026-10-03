"""What a bill still owes, now that covered bills are skipped in SQL (PLT-4).

A bill its allocations alone already cover is left out before Python sees
it -- points, returns and write-offs only take more off. A customer debit
note is the one thing that adds to a bill, so a bill paid in full and then
raised by a note must still be read, and still owe the note.
"""

# ruff: noqa: D103

from decimal import Decimal

from app.settlements.services.settlement_service import ReceiptService
from tests.unit.test_credit_note import _Books, _session_factory
from tests.unit.test_customer_debit_note import _approved, _pay


def _owing(books: _Books) -> dict[str, Decimal]:
    return {
        record.invoice_number: record.outstanding_amount
        for record in ReceiptService(books.session).outstanding_invoices(
            firm_id=books.firm.id, party_id=None
        )
    }


def test_a_bill_paid_in_full_owes_nothing() -> None:
    books = _Books(_session_factory()())
    books.approved("100")  # 118 off: the receipt below over-covers the bill
    _pay(books, "1180.00")

    assert _owing(books) == {}


def test_a_bill_paid_in_full_then_debited_still_owes_the_note() -> None:
    books = _Books(_session_factory()())
    _approved(books)  # 100 more, and 18 of tax
    _pay(books, "1180.00")

    assert _owing(books) == {books.invoice.invoice_number: Decimal("118.00")}


def test_a_bill_part_paid_owes_the_rest() -> None:
    books = _Books(_session_factory()())
    books.approved("100")  # 118 off
    _pay(books, "1000.00")

    assert _owing(books) == {books.invoice.invoice_number: Decimal("62.00")}
