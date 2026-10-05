"""Cash discount for early payment, interest on late (SEL-14, decision A91).

A bill of 1,180 dated 20 April. The firm offers 2% within 10 days and charges
18% a year on bills overdue more than 15 days. Paid on 25 April it offers
23.60 off; on 1 May nothing. Unpaid on 19 June -- 60 days past its date, which
is its due date -- it has run up 1,180 x 18% x 60 / 365 = 34.92, which the
statement shows and a draft debit note charges, spread over the bill's lines.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.customer_debit_note.models import CustomerDebitNote, CustomerDebitNoteLine
from app.customers.schemas.customer import (
    CreditControlSettingsWrite,
    CreditEnforcement,
)
from app.customers.services.credit_control import CreditControlService
from app.customers.services.payment_terms import PaymentTermsService
from app.customers.services.statement_service import CustomerStatementService
from tests.unit.test_credit_note import WHEN, _Books, _session_factory

D = Decimal


def _terms(books: _Books) -> PaymentTermsService:
    CreditControlService(books.session).update_settings(
        CreditControlSettingsWrite(
            enforcement=CreditEnforcement.WARN,
            warn_at_percent=D("80"),
            block_at_percent=D("100"),
            cash_discount_days=10,
            cash_discount_percent=D("2"),
            overdue_interest_rate=D("18"),
            interest_grace_days=15,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    return PaymentTermsService(books.session)


def test_a_bill_paid_inside_its_window_offers_the_discount() -> None:
    books = _Books(_session_factory()())
    terms = _terms(books)
    [offer] = terms.cash_discounts(
        books.customer.id, firm_id=books.firm.id, on=date(2026, 4, 25)
    )
    assert (offer.percent, offer.discount_until, offer.amount) == (
        D("2"),
        date(2026, 4, 30),
        D("23.60"),
    )
    assert not terms.cash_discounts(
        books.customer.id, firm_id=books.firm.id, on=date(2026, 5, 1)
    ), "past the tenth day"

    books.customer.cash_discount_days = 0
    books.session.commit()
    assert not terms.cash_discounts(
        books.customer.id, firm_id=books.firm.id, on=date(2026, 4, 25)
    ), "zero days on the customer refuses the firm's terms"


def test_an_overdue_bill_runs_up_interest_shown_and_charged_on_request() -> None:
    books = _Books(_session_factory()())
    terms = _terms(books)
    assert not terms.overdue_interest(
        books.customer.id, firm_id=books.firm.id, as_of=date(2026, 5, 5)
    ), "inside the grace days"

    june = date(2026, 6, 19)
    [row] = terms.overdue_interest(books.customer.id, firm_id=books.firm.id, as_of=june)
    assert (row.days, row.interest) == (60, D("34.92"))

    statement = CustomerStatementService(books.session).statement(
        books.customer.id, firm_scope=books.firm.id, from_date=WHEN, to_date=june
    )
    assert statement.interest_accrued == D("34.92")

    note = terms.raise_interest_note(
        books.customer.id,
        books.invoice.id,
        firm_id=books.firm.id,
        as_of=june,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert note.reason == "LATE_PAYMENT_INTEREST"
    assert note.status == "DRAFT"
    charged = sum(
        line.taxable_amount
        for line in books.session.query(CustomerDebitNoteLine).filter_by(
            debit_note_id=note.id
        )
    )
    assert charged == D("34.92")

    with pytest.raises(ValidationError, match="run up no interest"):
        terms.raise_interest_note(
            books.customer.id,
            books.invoice.id,
            firm_id=books.firm.id,
            as_of=date(2026, 5, 1),
            actor_id=books.actor_id,
        )


def test_the_route_keeps_the_interest_note_it_says_it_raised() -> None:
    """The request owns the commit: what it answers with must still be there.

    The route answered "raised as a draft" with a number and never committed,
    so the note was gone when the request ended (D-SELL-49, 2026-10-05). The
    service test above commits for itself, which is why it could not see it.
    """
    from types import SimpleNamespace

    from app.customers.api.router import raise_interest_debit_note
    from app.customers.schemas.statement import InterestDebitNoteCreate

    books = _Books(_session_factory()())
    _terms(books)
    books.session.commit()

    answer = raise_interest_debit_note(
        customer_id=books.customer.id,
        data=InterestDebitNoteCreate(
            invoice_id=books.invoice.id, as_of=date(2026, 6, 19)
        ),
        scope=SimpleNamespace(firm_id=books.firm.id, actor_id=books.actor_id),  # type: ignore[arg-type]
        db=books.session,
    )
    # A request that ends discards whatever it did not commit.
    books.session.rollback()

    assert answer.data is not None
    kept = books.session.query(CustomerDebitNote).filter_by(
        debit_note_number=answer.data["debit_note_number"]
    )
    assert kept.count() == 1
