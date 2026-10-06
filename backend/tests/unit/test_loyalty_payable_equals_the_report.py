"""Loyalty Payable holds exactly what the balances report says the points cost.

D-PRC-42, from the third pricing check (round 1's unplaced paisa, PRCQ-17):
a bill earned 8.4960 points booked at 8.50, and a quarter of it came back.
The take-back entry was -2.1240 points for 2.13, so the ledger held 6.37 for
what was left; the balances report valued the 6.3720 points left at their
rate and rounded again, 6.38. Loyalty Payable sat a paisa under the report
(79.17 against 79.18 on the checked firm).

Two rules close it. What a batch is still worth is **what it was booked at
less what the ledger's entries took from it**, never points times a rate
rounded afresh -- so the report is the ledger's own money. And the money a
movement takes out of a batch is the batch's own: a part is `quantize_ledger`
of its share, and the movement that empties the batch takes everything left,
so the parts taken over a batch's life sum exactly to what was accrued.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.loyalty.models import LoyaltyEntry
from app.loyalty.services import LoyaltyService
from app.sales_invoice.models import SalesInvoice
from tests.unit.test_lapsed_points_are_not_spent import _Counter
from tests.unit.test_loyalty import _payable

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal


class _Scheme(_Counter):
    """The check's customer: one bill of 424.80 earning 8.4960 points at 8.50."""

    def __init__(self) -> None:
        """Approve the bill and credit its points."""
        super().__init__()
        self.bill: SalesInvoice = self.books.invoice("SI-EARN", total="424.80")
        earned = self.books.earn(self.bill)
        assert earned is not None
        self.earned: LoyaltyEntry = earned
        assert (earned.points, earned.amount) == (D("8.4960"), D("8.5000"))

    def give_back(self, credited: str, number: str) -> LoyaltyEntry:
        """Take back the points on value returned off the bill."""
        entry = self.service.stage_take_back(
            invoice_id=self.bill.id,
            credited=D(credited),
            source_type="SALES_RETURN",
            source_id=uuid4(),
            source_number=number,
            on=self.today,
            firm_id=self.firm_id,
            actor_id=self.books.actor_id,
        )
        self.session.commit()
        assert entry is not None
        return entry

    def lapse(self) -> LoyaltyEntry:
        """Let the batch run out of time and sweep it."""
        self.earned.expires_on = self.today - timedelta(days=1)
        self.session.commit()
        self.service.expire(firm_scope=self.firm_id, actor_id=self.books.actor_id)
        return self.expired()[-1]

    def report(self) -> Decimal:
        """Return what the balances report says the customer's points cost."""
        rows = self.service.balances_report(firm_scope=self.firm_id)
        return sum((row.amount + row.lapsed_amount for row in rows), D("0"))

    def ledger(self) -> Decimal:
        """Return the sum of the ledger's own amounts, signed by their points."""
        self.session.expire_all()
        total = D("0")
        for row in self.session.scalars(
            select(LoyaltyEntry).where(LoyaltyEntry.firm_id == self.firm_id)
        ):
            amount = D(str(row.amount))
            total += amount if D(str(row.points)) > 0 else -amount
        return total

    def agree(self, expected: str) -> None:
        """Assert the account, the report and the ledger all read one figure."""
        assert (_payable(self.books), self.report(), self.ledger()) == (
            D(expected),
            D(expected),
            D(expected),
        )


def test_a_part_return_leaves_the_report_on_the_ledgers_figure() -> None:
    """The check's paisa: 8.50 booked, 2.13 taken back, 6.37 left -- not 6.38."""
    scheme = _Scheme()
    scheme.agree("8.50")

    taken = scheme.give_back("106.20", "SR-1")

    assert (taken.points, taken.amount) == (D("-2.1240"), D("2.1300"))
    scheme.agree("6.37")
    balance = scheme.service.balance(
        scheme.books.customer.id, firm_scope=scheme.firm_id
    )
    assert (balance.points, balance.amount) == (D("6.3720"), D("6.37"))


def test_one_batch_through_a_return_a_redemption_and_a_lapse() -> None:
    """The account equals the report at every step, and ends at nothing."""
    scheme = _Scheme()
    scheme.agree("8.50")

    scheme.give_back("106.20", "SR-1")
    scheme.agree("6.37")

    spent = scheme.redeem("2")
    assert (spent.points, spent.amount) == (D("-2.0000"), D("2.0000"))
    scheme.agree("4.37")

    lapse = scheme.lapse()
    # The lapse empties the batch, so it takes everything the batch has left.
    assert (lapse.points, lapse.amount) == (D("-4.3720"), D("4.3700"))
    scheme.agree("0.00")
    taken = [
        D(str(row.amount))
        for row in scheme.session.scalars(
            select(LoyaltyEntry).where(
                LoyaltyEntry.firm_id == scheme.firm_id,
                LoyaltyEntry.id != scheme.earned.id,
            )
        )
    ]
    assert sum(taken, D("0")) == D("8.5000"), "the parts sum to what was accrued"


def test_three_equal_redemptions_sum_to_what_the_batch_was_booked_at() -> None:
    """2.83 + 2.84 + 2.83 is 8.50, where a third rounded three times was 8.49.

    Spending names no batch, so each redemption takes what the batch's
    spending comes to after it less what it came to before: 2.83, then 5.67
    less 2.83, then everything left.
    """
    scheme = _Scheme()

    amounts = [scheme.redeem("2.832").amount for _ in range(3)]

    assert amounts == [D("2.8300"), D("2.8400"), D("2.8300")]
    scheme.agree("0.00")


def test_three_equal_returns_sum_to_what_the_batch_was_booked_at() -> None:
    """A bill returned in thirds releases 8.50 in all, not 8.49."""
    scheme = _Scheme()

    amounts = [scheme.give_back("141.60", f"SR-{n}").amount for n in (1, 2, 3)]

    assert amounts == [D("2.8300"), D("2.8300"), D("2.8400")]
    scheme.agree("0.00")


def test_an_adjustment_out_of_a_batch_takes_its_own_cost() -> None:
    """Points taken away by hand: a part is its share, the last takes the rest."""
    scheme = _Scheme()

    def take(points: str) -> Decimal:
        """Take points off the balance and return the money released."""
        entry = scheme.service.adjust(
            firm_scope=scheme.firm_id,
            customer_id=scheme.books.customer.id,
            points=D(points),
            reason="Correction",
            actor_id=scheme.books.actor_id,
        )
        return D(str(entry.amount))

    assert take("-2.832") == D("2.83")
    scheme.agree("5.67")
    assert take("-2.832") == D("2.84")
    scheme.agree("2.83")
    assert take("-2.832") == D("2.83")
    scheme.agree("0.00")


def test_a_cancelled_bill_takes_back_everything_its_batch_has_left() -> None:
    """After a part return and a part redemption, the cancellation takes 4.37."""
    scheme = _Scheme()
    scheme.give_back("106.20", "SR-1")
    scheme.redeem("2")

    entry = LoyaltyService(scheme.session).stage_reversal(
        scheme.bill, firm_id=scheme.firm_id, actor_id=scheme.books.actor_id
    )
    scheme.session.commit()

    assert entry is not None
    assert (entry.points, entry.amount) == (D("-4.3720"), D("4.3700"))
    scheme.agree("0.00")
