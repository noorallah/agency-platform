"""Points past their date are not spent, swept or not (D-PRC-3, PRCQ-21).

A batch nine days past its expiry settled 70.00 of a bill: the balance a
redemption was checked against was the sum of the ledger, a batch left it only
when ``POST /loyalty/expire`` was called, and nothing called it. A point is
now spendable only while its batch has not lapsed on the firm's day; the
balance and the balances report leave lapsed points out; redeeming stages the
lapse with its cost reversal first; and the sweep is a subcommand of the
shipped binary, over every firm.

Every case runs on a request-shaped session (autoflush off).
"""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import build_parser
from app.common.firm_metadata import firm_today
from app.core.exceptions import ValidationError
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.services import LoyaltyService
from app.loyalty.services.expiry_sweep import SYSTEM_ACTOR, sweep_every_firm
from tests.unit.test_loyalty import _Books, _payable
from tests.unit.test_sales_chain_synthesis import _request_session

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal


class _Counter:
    """A firm running a scheme, on a session shaped like a request's."""

    def __init__(self) -> None:
        """Build the books and read the firm's own day."""
        self.books = _Books(_request_session())
        self.session: Session = self.books.session
        self.service = LoyaltyService(self.session)
        self.firm_id: UUID = self.books.firm.id
        self.today: date = firm_today(self.session, self.firm_id)

    def batch(self, points: str, *, expires_in: int | None, age: int = 40) -> None:
        """Credit a batch earned ``age`` days ago, expiring in so many days."""
        self.books.batch(
            points,
            earned_on=self.today - timedelta(days=age),
            expires_on=(
                None if expires_in is None else self.today + timedelta(days=expires_in)
            ),
        )

    def redeem(self, points: str) -> LoyaltyEntry:
        """Spend points on a fresh bill of 500.00."""
        bill = self.books.invoice(f"SI-{uuid4().hex[:6]}", total="500")
        return self.service.redeem(
            firm_scope=self.firm_id,
            invoice_id=bill.id,
            points=D(points),
            actor_id=self.books.actor_id,
        )

    def expired(self) -> list[LoyaltyEntry]:
        """Return the lapses written so far."""
        return list(
            self.session.scalars(
                select(LoyaltyEntry).where(
                    LoyaltyEntry.firm_id == self.firm_id,
                    LoyaltyEntry.kind == LoyaltyEntryKind.EXPIRED.value,
                )
            ).all()
        )


def test_lapsed_points_are_out_of_the_balance_before_any_sweep() -> None:
    """70.8 points nine days past their date, and 2.36 earned today."""
    counter = _Counter()
    counter.batch("70.8", expires_in=-9)
    counter.batch("2.36", expires_in=700, age=0)

    balance = counter.service.balance(
        counter.books.customer.id, firm_scope=counter.firm_id
    )

    assert balance.points == D("2.3600")
    assert balance.amount == D("2.36")
    assert balance.lapsed_points == D("70.8000")
    assert balance.expiring_soon == D("0.0000")
    assert balance.redeemable is True
    assert counter.expired() == []


def test_lapsed_points_cannot_be_spent_and_the_refusal_says_why() -> None:
    """The reproduction: 70 of the lapsed 70.8 are asked for at the counter."""
    counter = _Counter()
    counter.batch("70.8", expires_in=-9)
    counter.batch("2.36", expires_in=700, age=0)
    lapsed_on = counter.today - timedelta(days=9)

    with pytest.raises(ValidationError) as refused:
        counter.redeem("70")
    counter.session.rollback()

    assert str(refused.value.message) == (
        "That customer holds 2.3600 points, not 70.0000. 70.8000 more ran out "
        f"of time on {lapsed_on} and can no longer be spent."
    )
    # The refusal wrote nothing; the balance leaves them out all the same.
    assert counter.expired() == []
    assert counter.books.points() == D("2.3600")


def test_redeeming_stages_the_lapse_and_gives_its_cost_back() -> None:
    """Spending 2 writes the 70.8 off in the same transaction, journal and all."""
    counter = _Counter()
    counter.batch("70.8", expires_in=-9)
    counter.batch("2.36", expires_in=700, age=0)
    owed_before = _payable(counter.books)

    spent = counter.redeem("2")

    assert (spent.points, spent.amount) == (D("-2.0000"), D("2.00"))
    (lapse,) = counter.expired()
    assert (lapse.points, lapse.amount) == (D("-70.8000"), D("70.80"))
    assert lapse.journal_entry_id is not None
    assert lapse.earned_on == counter.today
    assert _payable(counter.books) == owed_before - D("70.80") - D("2.00")
    after = counter.service.balance(
        counter.books.customer.id, firm_scope=counter.firm_id
    )
    assert (after.points, after.lapsed_points) == (D("0.3600"), D("0.0000"))
    # The sweep finds nothing left of that batch.
    assert counter.service.expire(firm_scope=counter.firm_id, actor_id=uuid4()) == 0


def test_a_batch_is_good_through_its_expiry_date() -> None:
    """Expiring today it is spent today; the report and the sweep agree."""
    counter = _Counter()
    counter.batch("50", expires_in=0)

    (row,) = counter.service.expiring_report(firm_scope=counter.firm_id)
    assert (row.days_remaining, row.awaiting_sweep) == (0, False)
    assert counter.books.points() == D("50.0000")
    assert counter.service.expire(firm_scope=counter.firm_id, actor_id=uuid4()) == 0

    counter.redeem("50")

    assert counter.books.points() == D("0.0000")
    assert counter.expired() == []


def test_two_batches_of_one_day_are_spent_in_the_order_they_were_earned() -> None:
    """PRCQ-21: 59.472 at 1.00 then 59.472 at 2.00; 70 points cost 80.53."""
    counter = _Counter()
    earlier = datetime(2026, 9, 1, 10, 0, 0)
    for identity, amount, written in (
        # The older batch holds the later id, which is what used to decide.
        (UUID(int=2**127), "59.47", earlier),
        (UUID(int=1), "118.94", earlier + timedelta(hours=3)),
    ):
        counter.session.add(
            LoyaltyEntry(
                id=identity,
                firm_id=counter.firm_id,
                customer_id=counter.books.customer.id,
                kind=LoyaltyEntryKind.EARNED.value,
                points=D("59.472"),
                amount=D(amount),
                earned_on=counter.today,
                created_at=written,
                created_by=counter.books.actor_id,
                updated_by=counter.books.actor_id,
            )
        )
    counter.session.commit()

    spent = counter.redeem("70")

    assert spent.amount == D("80.53")
    left = counter.service.unspent_batches(
        counter.books.customer.id, firm_scope=counter.firm_id
    )
    assert [(batch.id, remaining) for batch, remaining in left] == [
        (UUID(int=1), D("48.9440"))
    ]


def test_the_balances_report_agrees_with_the_balance_and_with_the_books() -> None:
    """Lapsed points are beside the balance, not in it, until the sweep runs."""
    counter = _Counter()
    for points, expires_in in (("70.8", -9), ("30", 700)):
        bill = counter.books.invoice(f"SI-{points}", total="100")
        entry = counter.books.earn(bill)
        assert entry is not None
        entry.points = D(points)
        entry.amount = D(points)
        entry.expires_on = counter.today + timedelta(days=expires_in)
        counter.session.commit()
    # Earning accrued 2 points a rupee on each bill; restate the accrual to
    # the points the batches were set to, so the account can be compared.
    owed = D("100.80")

    (row,) = counter.service.balances_report(firm_scope=counter.firm_id)

    assert (row.points, row.amount) == (D("30.0000"), D("30.00"))
    assert (row.lapsed_points, row.lapsed_amount) == (D("70.8000"), D("70.80"))
    assert row.amount + row.lapsed_amount == owed
    assert row.points == counter.books.points()

    assert counter.service.expire(firm_scope=counter.firm_id, actor_id=uuid4()) == 1

    (swept,) = counter.service.balances_report(firm_scope=counter.firm_id)
    assert (swept.points, swept.lapsed_points) == (D("30.0000"), D("0.0000"))


def test_the_shipped_binary_can_run_the_sweep() -> None:
    """``agency-server loyalty-expire`` parses, as an installed copy calls it."""
    parsed = build_parser().parse_args(["loyalty-expire"])
    assert parsed.handler.__name__ == "_loyalty_expire"


def test_the_sweep_reaches_every_firm_and_reports_one_it_could_not() -> None:
    """Each firm in its own store; a store that fails never stops the rest."""
    lapsing, quiet, broken = _Counter(), _Counter(), uuid4()
    lapsing.batch("70.8", expires_in=-9)
    quiet.batch("10", expires_in=30)
    stores = {lapsing.firm_id: lapsing.session, quiet.firm_id: quiet.session}

    @contextmanager
    def open_store(firm_id: UUID) -> Generator[Session]:
        """Open one firm's store, or fail as an unreachable one does."""
        if firm_id not in stores:
            raise ConnectionError("store is not reachable")
        yield stores[firm_id]

    def firm_ids() -> list[UUID]:
        """Return the registry's firms."""
        return [lapsing.firm_id, broken, quiet.firm_id]

    first = sweep_every_firm(firm_ids, open_store)
    second = sweep_every_firm(firm_ids, open_store)

    assert first.lapsed == {lapsing.firm_id: 1, quiet.firm_id: 0}
    assert first.errors == [f"{broken}: ConnectionError: store is not reachable"]
    assert second.lapsed == {lapsing.firm_id: 0, quiet.firm_id: 0}
    (lapse,) = lapsing.expired()
    assert lapse.created_by == SYSTEM_ACTOR
    assert lapse.journal_entry_id is not None
