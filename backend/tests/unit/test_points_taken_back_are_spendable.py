"""Points are taken back only from what a customer can still spend.

D-PRC-30: a customer with 2.36 points live and 70.80 lapsed (past their date,
not yet swept) had an adjustment of -50 accepted, "Balance adjusted.", Dr 2600
50.00 / Cr 5700 50.00 -- and could still spend 2.36, because the 50 came out
of the lapsed batch, the oldest. A further -2 left the spendable balance at
2.36 again.

Taking points back -- by hand, by a return, by cancelling the bill -- now
lapses what has run out of time first, as a redemption does, and takes only
from what is left. Every case runs on a request-shaped session.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.loyalty.models import LoyaltyEntry
from app.loyalty.services import LoyaltyService
from app.sales_invoice.models import SalesInvoice
from tests.unit.test_lapsed_points_are_not_spent import _Counter
from tests.unit.test_loyalty import _payable

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal


def _live_and_lapsed() -> _Counter:
    """Return the check's customer: 70.80 nine days lapsed, 2.36 earned today."""
    counter = _Counter()
    counter.batch("70.8", expires_in=-9)
    counter.batch("2.36", expires_in=700, age=0)
    return counter


def _adjust(counter: _Counter, points: str) -> LoyaltyEntry:
    """Adjust the customer's balance by hand."""
    return counter.service.adjust(
        firm_scope=counter.firm_id,
        customer_id=counter.books.customer.id,
        points=D(points),
        reason="Correction",
        actor_id=counter.books.actor_id,
    )


def test_more_than_can_be_spent_is_refused_and_names_both_figures() -> None:
    """-50 against 2.36 spendable: refused, and nothing is written."""
    counter = _live_and_lapsed()
    lapsed_on = counter.today - timedelta(days=9)

    with pytest.raises(ValidationError) as refused:
        _adjust(counter, "-50")
    counter.session.rollback()

    assert str(refused.value.message) == (
        "That customer holds 2.3600 points that can be spent, so -50.0000 "
        "would take the balance below zero. 70.8000 more ran out of time on "
        f"{lapsed_on} and are gone already."
    )
    assert counter.expired() == []
    balance = counter.service.balance(
        counter.books.customer.id, firm_scope=counter.firm_id
    )
    assert (balance.points, balance.lapsed_points) == (D("2.3600"), D("70.8000"))


def test_what_is_taken_comes_out_of_the_points_that_can_be_spent() -> None:
    """-2 leaves 0.36 to spend; the 70.80 lapses with its cost, untouched."""
    counter = _live_and_lapsed()
    owed = _payable(counter.books)

    entry = _adjust(counter, "-2")

    assert (entry.points, entry.amount) == (D("-2.0000"), D("2.00"))
    (lapse,) = counter.expired()
    assert (lapse.points, lapse.amount) == (D("-70.8000"), D("70.80"))
    balance = counter.service.balance(
        counter.books.customer.id, firm_scope=counter.firm_id
    )
    assert (balance.points, balance.lapsed_points) == (D("0.3600"), D("0.0000"))
    # The books: the lapse released 70.80 and the adjustment 2.00.
    assert _payable(counter.books) == owed - D("70.80") - D("2.00")
    assert counter.service.expire(firm_scope=counter.firm_id, actor_id=uuid4()) == 0


def test_all_that_can_be_spent_may_be_taken_and_no_more() -> None:
    """Exactly 2.36 is taken; one hundredth more is refused."""
    counter = _live_and_lapsed()

    with pytest.raises(ValidationError, match="2.3600 points that can be spent"):
        _adjust(counter, "-2.37")
    counter.session.rollback()
    _adjust(counter, "-2.36")

    assert counter.books.points() == D("0.0000")


def test_giving_points_lapses_nothing() -> None:
    """A positive adjustment is not a take-back: the sweep is left to run."""
    counter = _live_and_lapsed()

    _adjust(counter, "5")

    assert counter.expired() == []
    balance = counter.service.balance(
        counter.books.customer.id, firm_scope=counter.firm_id
    )
    assert (balance.points, balance.lapsed_points) == (D("7.3600"), D("70.8000"))


def test_with_nothing_lapsed_the_refusal_names_the_two_figures_alone() -> None:
    """No lapsed batch, no sentence about one."""
    counter = _Counter()
    counter.batch("10", expires_in=700, age=0)

    with pytest.raises(ValidationError) as refused:
        _adjust(counter, "-11")
    counter.session.rollback()

    assert str(refused.value.message) == (
        "That customer holds 10.0000 points that can be spent, so -11.0000 "
        "would take the balance below zero."
    )


def _live_and_lapsed_bill() -> tuple[_Counter, LoyaltyEntry, SalesInvoice]:
    """Return a customer with 2.36 live and a bill whose 70.80 has lapsed."""
    counter = _Counter()
    bill = counter.books.invoice(f"SI-{uuid4().hex[:6]}", total="1000")
    earned = counter.books.batch(
        "70.8",
        earned_on=counter.today - timedelta(days=40),
        expires_on=counter.today - timedelta(days=9),
    )
    earned.sales_invoice_id = bill.id
    counter.session.commit()
    counter.batch("2.36", expires_in=700, age=0)
    return counter, earned, bill


def test_a_return_of_a_bill_whose_points_lapsed_takes_nothing_back() -> None:
    """The points lapse, with their cost; the return has nothing left to take."""
    counter, earned, bill = _live_and_lapsed_bill()
    owed = _payable(counter.books)

    taken = LoyaltyService(counter.session).stage_take_back(
        invoice_id=bill.id,
        credited=D("1000"),
        source_type="SALES_RETURN",
        source_id=uuid4(),
        source_number="SR-1",
        on=counter.today,
        firm_id=counter.firm_id,
        actor_id=counter.books.actor_id,
    )
    counter.session.commit()

    assert taken is None
    (lapse,) = counter.expired()
    assert (lapse.reverses_id, lapse.points) == (earned.id, D("-70.8000"))
    assert _payable(counter.books) == owed - D("70.80")
    # The points the customer can spend were not touched for the shortfall.
    assert counter.books.points() == D("2.3600")


def test_cancelling_a_bill_whose_points_lapsed_takes_nothing_back() -> None:
    """The same for a cancelled bill: a lapse, and no reversal row."""
    counter, earned, bill = _live_and_lapsed_bill()

    taken = LoyaltyService(counter.session).stage_reversal(
        bill,
        firm_id=counter.firm_id,
        actor_id=counter.books.actor_id,
    )
    counter.session.commit()

    assert taken is None
    (lapse,) = counter.expired()
    assert lapse.reverses_id == earned.id
    assert counter.books.points() == D("2.3600")
