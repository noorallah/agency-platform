"""Payables by supplier and month, checked against the books (§85, PG-2).

The report's total must be the payables account's balance: a part payment, a
return after billing, a debit note, a return off a goods receipt and an
advance each move both, and D-BUY-32 was the report missing the credits the
ledger had. The as-of date leaves later documents out, the due-date basis
moves a bill to the month it falls due, the Paid view is the payments, and
the statement count does not grow with the bills.
"""

# ruff: noqa: D103

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.services.document_posting import DocumentPostingService
from app.purchase_invoice.api.router import payables_report
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.services.payables_report import (
    PayablesReport,
    PayablesReportService,
)
from tests.unit.test_debit_note_supplier_credit import _note
from tests.unit.test_settlements import _Books, _session_factory
from tests.unit.test_supplier_credit import _return
from tests.unit.test_supplier_statement import _bill, _pay, _payables

AS_OF = date(2026, 5, 31)


def _books() -> _Books:
    return _Books(_session_factory()())


def _post_return(books: _Books, row: object, total: str, on: date) -> None:
    """Post a completed return's journal: Dr payable, Cr stock."""
    row.return_date = on  # type: ignore[attr-defined]
    DocumentPostingService(books.session).post_purchase_return(
        firm_id=books.firm.id,
        return_id=row.id,  # type: ignore[attr-defined]
        return_number=row.return_number,  # type: ignore[attr-defined]
        return_date=on,
        stock_value=Decimal(total),
        tax_amount=Decimal("0"),
        total_amount=Decimal(total),
        actor_id=books.actor_id,
    )
    books.session.commit()


def _post_note(books: _Books, note: object) -> None:
    DocumentPostingService(books.session).post_debit_note_document(
        firm_id=books.firm.id,
        debit_note_id=note.id,  # type: ignore[attr-defined]
        debit_note_number=note.debit_note_number,  # type: ignore[attr-defined]
        note_date=note.debit_note_date,  # type: ignore[attr-defined]
        taxable_amount=note.taxable_amount,  # type: ignore[attr-defined]
        tax_amount=note.tax_amount,  # type: ignore[attr-defined]
        actor_id=books.actor_id,
    )
    books.session.commit()


def _trade(books: _Books) -> tuple[PurchaseInvoice, PurchaseInvoice]:
    """Two bills, a part payment, two returns, a debit note and an advance.

    PI-1 1,000 (April) less 600 paid and a 50 debit note owes 350; PI-2 500
    (May) less a 100 return off its lines owes 400; an 80 return off a goods
    receipt and a 200 advance are 280 of credit. 470 in all, as in payables.
    """
    first = _bill(books, "PI-1", "1000.00", when=date(2026, 4, 5))
    second = _bill(books, "PI-2", "500.00", when=date(2026, 5, 10))
    _pay(books, "600.00", when=date(2026, 4, 20), bill=first)
    off_bill = _return(
        books, "PR-1", total="100.00", source_type="PURCHASE_INVOICE", bill=second
    )
    _post_return(books, off_bill, "100.00", date(2026, 5, 15))
    off_receipt = _return(books, "PR-2", total="80.00")
    _post_return(books, off_receipt, "80.00", date(2026, 5, 16))
    note = _note(books, "DN-1", first, taxable="50", on=date(2026, 5, 20))
    _post_note(books, note)
    _pay(books, "200.00", when=date(2026, 5, 25))
    return first, second


def _report(books: _Books, **kwargs: object) -> PayablesReport:
    values: dict[str, object] = {"as_of": AS_OF, "months": 3}
    values.update(kwargs)
    return PayablesReportService(books.session).report(
        books.firm.id, **values  # type: ignore[arg-type]
    )


def test_the_total_is_trade_payables() -> None:
    books = _books()
    _trade(books)

    report = _report(books)

    assert report.months == ["2026-03", "2026-04", "2026-05"]
    [row] = report.rows
    assert row.vendor_name == "Vendor One"
    assert row.amounts == [Decimal("0.00"), Decimal("350.00"), Decimal("400.00")]
    assert row.counts == [0, 1, 1]
    assert row.older == Decimal("0.00")
    assert row.credits == Decimal("-280.00")
    assert row.total == Decimal("470.00")
    assert report.total.total == Decimal("470.00")
    assert _payables(books) == Decimal("470.00")
    assert report.books_check.ledger_balance == Decimal("470.00")
    assert report.books_check.difference == Decimal("0.00")


def test_one_supplier_is_checked_against_its_own_payables_lines() -> None:
    books = _books()
    _trade(books)

    report = _report(books, vendor_id=books.vendor.id)

    assert report.total.total == Decimal("470.00")
    assert report.books_check.difference == Decimal("0.00")


def test_older_months_fall_in_older() -> None:
    books = _books()
    _trade(books)

    report = _report(books, months=1)

    assert report.months == ["2026-05"]
    assert report.total.older == Decimal("350.00")
    assert report.total.amounts == [Decimal("400.00")]
    assert report.total.total == Decimal("470.00")


def test_as_of_leaves_out_what_came_later() -> None:
    books = _books()
    _trade(books)

    report = _report(books, as_of=date(2026, 4, 30))

    assert report.months == ["2026-02", "2026-03", "2026-04"]
    assert report.total.amounts == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("400.00"),
    ]
    assert report.total.credits == Decimal("0.00")
    assert report.total.total == Decimal("400.00")
    assert report.books_check.ledger_balance == Decimal("400.00")
    assert report.books_check.difference == Decimal("0.00")


def test_due_date_basis_puts_a_bill_in_the_month_it_falls_due() -> None:
    books = _books()
    first, second = _trade(books)
    first.due_date = date(2026, 5, 5)
    second.due_date = date(2026, 7, 15)
    books.session.commit()

    report = _report(books, basis="due")

    assert report.total.amounts == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("350.00"),
    ]
    assert report.total.later == Decimal("400.00")
    assert report.total.total == Decimal("470.00")


def test_the_paid_view_is_the_payments() -> None:
    books = _books()
    _trade(books)

    report = _report(books, view="paid")

    assert report.total.amounts == [
        Decimal("0.00"),
        Decimal("600.00"),
        Decimal("200.00"),
    ]
    assert report.total.counts == [0, 1, 1]
    assert report.total.total == Decimal("800.00")
    assert report.books_check.ledger_balance == Decimal("800.00")
    assert report.books_check.difference == Decimal("0.00")


def test_the_paid_view_cannot_be_narrowed_to_a_branch() -> None:
    books = _books()
    with pytest.raises(ValidationError):
        _report(books, view="paid", branch_id=books.branch_id)


def test_a_branch_has_no_books_check() -> None:
    books = _books()
    _trade(books)

    report = _report(books, branch_id=books.branch_id)

    assert report.total.amounts[1:] == [Decimal("350.00"), Decimal("400.00")]
    assert report.books_check.ledger_balance is None
    assert report.books_check.note


@contextmanager
def _counting(books: _Books) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = books.session.get_bind()

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_the_statement_count_does_not_grow_with_the_bills() -> None:
    books = _books()
    _trade(books)
    with _counting(books) as few:
        _report(books)
    for number in range(10):
        _bill(books, f"PI-X{number}", "10.00", when=date(2026, 5, 1))
    with _counting(books) as many:
        report = _report(books)

    assert report.total.total == Decimal("570.00")
    assert len(many) == len(few)


def test_the_route_answers_the_report() -> None:
    books = _books()
    _trade(books)
    user_id = uuid4()
    scope = ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset({"PURCHASE_VIEW"}),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=books.firm.id,
    )

    body = payables_report(
        scope,
        as_of=AS_OF,
        basis="invoice",
        months=3,
        vendor_id=None,
        branch_id=None,
        view="owed",
        db=books.session,
    ).data

    assert body is not None
    assert body.months == ["2026-03", "2026-04", "2026-05"]
    assert body.total.total == Decimal("470.00")
    assert body.total.vendor_id is None
    assert body.rows[0].vendor_id == books.vendor.id
    assert body.books_check.difference == Decimal("0.00")
