"""Credit a customer earns on what they buy, and spends on what they buy next.

Loyalty and cashback are one ledger, and the design turns on one decision:
**redeeming settles the bill, it does not discount it.** The supply is worth
what it is worth and the full tax was charged on it; the customer pays part of
it with credit the firm already owes them. Treating a redemption as a discount
would reduce the taxable value and so the GST the firm collects, which is a
decision about tax rather than about loyalty.

The rest follows:

- **the balance is the sum of the ledger**, never a column;
- points cost the firm money **when earned**, not when spent, so a scheme's
  cost lands in the month it was incurred;
- a redemption is **refused rather than trimmed**, because a customer told
  their points cleared a bill and finding otherwise is worse than a refusal;
- and expiry is a **sweep** that names what it takes, so running it twice
  cannot take the same points twice.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.finance.models import JournalEntry, JournalLine
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.schemas import LoyaltySettingsWrite
from app.loyalty.services import LoyaltyService
from app.sales_invoice.models import SalesInvoice

WHEN = date(2026, 6, 10)


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Books:
    """A firm running a scheme, with a customer and a bill."""

    def __init__(self, session: Session, *, enabled: bool = True) -> None:
        """Seed the firm, its chart and a customer."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Loyal Firm",
            code="LOYL",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-1",
            name="Branch One",
            display_name="Branch One",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Kumar Stores",
            display_name="Kumar Stores",
            currency_code="INR",
            status="ACTIVE",
        )
        session.add_all([self.branch, self.customer])
        session.commit()
        if enabled:
            self.enable()

    def enable(self, **overrides: object) -> None:
        """Switch the scheme on."""
        payload: dict[str, object] = {
            "is_enabled": True,
            "points_per_amount": Decimal("2"),
            "amount_per_point": Decimal("1"),
        }
        payload.update(overrides)
        LoyaltyService(self.session).write_settings(
            self.firm.id,
            LoyaltySettingsWrite(**payload),  # type: ignore[arg-type]
            actor_id=self.actor_id,
        )

    def invoice(
        self, number: str, *, total: str = "1000", status: str = "APPROVED"
    ) -> SalesInvoice:
        """Raise a bill."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            invoice_number=number,
            invoice_date=WHEN,
            status=status,
            grand_total=Decimal(total),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def earn(self, invoice: SalesInvoice) -> LoyaltyEntry | None:
        """Credit the customer for the bill."""
        entry = LoyaltyService(self.session).stage_earning(
            invoice, firm_id=self.firm.id, actor_id=self.actor_id
        )
        self.session.commit()
        return entry

    def batch(
        self,
        points: str,
        *,
        earned_on: date,
        expires_on: date | None,
    ) -> LoyaltyEntry:
        """Credit a batch of points directly, on dates a test chooses.

        `earn` derives its dates from the bill, and expiry arithmetic is about
        which batch a spend consumed -- so the dates have to be settable.
        """
        row = LoyaltyEntry(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            kind=LoyaltyEntryKind.EARNED.value,
            points=Decimal(points),
            amount=Decimal(points),
            earned_on=earned_on,
            expires_on=expires_on,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def spend(self, points: str, *, on: date) -> LoyaltyEntry:
        """Take points off the ledger, the way a redemption does."""
        row = LoyaltyEntry(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            kind=LoyaltyEntryKind.REDEEMED.value,
            points=-Decimal(points),
            amount=Decimal(points),
            earned_on=on,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def points(self) -> Decimal:
        """Return what the customer holds."""
        return (
            LoyaltyService(self.session)
            .balance(self.customer.id, firm_scope=self.firm.id)
            .points
        )


def test_a_bill_earns_points_at_the_firm_s_rate() -> None:
    """Two points per hundred on a thousand is twenty."""
    books = _Books(_session_factory()())

    books.earn(books.invoice("SI-1", total="1000"))

    assert books.points() == Decimal("20.0000")


def test_earning_costs_the_firm_money_there_and_then() -> None:
    """`Dr Loyalty Expense / Cr Loyalty Payable`, when the points are promised.

    Booking it only on redemption would leave the liability off the books for
    as long as customers held their points, and put the cost in whatever month
    they happened to collect.
    """
    books = _Books(_session_factory()())

    entry = books.earn(books.invoice("SI-1", total="1000"))

    assert entry is not None and entry.journal_entry_id is not None
    legs = books.session.scalars(
        select(JournalLine).where(
            JournalLine.journal_entry_id == entry.journal_entry_id
        )
    ).all()
    assert sum(Decimal(str(leg.debit_amount)) for leg in legs) == Decimal("20.00")
    assert sum(Decimal(str(leg.credit_amount)) for leg in legs) == Decimal("20.00")


def test_a_firm_with_no_scheme_credits_nobody() -> None:
    """Shipping this credits nobody until a firm says what its scheme is."""
    books = _Books(_session_factory()(), enabled=False)

    assert books.earn(books.invoice("SI-1")) is None
    assert books.points() == Decimal("0.0000")


def test_one_bill_earns_once() -> None:
    """A second credit would pay twice for one sale."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", total="1000")
    books.earn(invoice)

    assert books.earn(invoice) is None
    assert books.points() == Decimal("20.0000")


def test_redeeming_settles_the_bill_rather_than_discounting_it() -> None:
    """`Dr Loyalty Payable / Cr Accounts Receivable`, and no tax moves.

    The supply is worth what it is worth and the full tax was charged on it.
    A discount would reduce the taxable value and so the GST collected, which
    is a decision about tax rather than about loyalty.
    """
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))
    later = books.invoice("SI-2", total="500")

    entry = LoyaltyService(books.session).redeem(
        firm_scope=books.firm.id,
        invoice_id=later.id,
        points=Decimal("20"),
        actor_id=books.actor_id,
    )

    assert entry.points == Decimal("-20.0000")
    assert entry.amount == Decimal("20.00")
    assert books.points() == Decimal("0.0000")
    accounts = {
        leg.ledger_account_id
        for leg in books.session.scalars(
            select(JournalLine).where(
                JournalLine.journal_entry_id == entry.journal_entry_id
            )
        ).all()
    }
    assert len(accounts) == 2


def test_more_points_than_the_customer_holds_is_refused() -> None:
    """Refused, not trimmed.

    A customer told their points cleared a bill and finding otherwise is worse
    than being told no.
    """
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))
    later = books.invoice("SI-2", total="500")

    with pytest.raises(ValidationError, match="holds 20"):
        LoyaltyService(books.session).redeem(
            firm_scope=books.firm.id,
            invoice_id=later.id,
            points=Decimal("50"),
            actor_id=books.actor_id,
        )


def test_more_than_the_bill_owes_is_refused() -> None:
    """A bill cannot be over-settled, by points or by anything else."""
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="10000"))
    small = books.invoice("SI-2", total="50")

    with pytest.raises(ValidationError, match="owes only"):
        LoyaltyService(books.session).redeem(
            firm_scope=books.firm.id,
            invoice_id=small.id,
            points=Decimal("200"),
            actor_id=books.actor_id,
        )


def test_a_balance_below_the_floor_cannot_be_spent() -> None:
    """Firms use it to stop a scheme becoming a two-rupee deduction."""
    books = _Books(_session_factory()(), enabled=False)
    books.enable(minimum_redemption_points=100)
    books.earn(books.invoice("SI-1", total="1000"))
    later = books.invoice("SI-2", total="500")

    with pytest.raises(ValidationError, match="At least 100"):
        LoyaltyService(books.session).redeem(
            firm_scope=books.firm.id,
            invoice_id=later.id,
            points=Decimal("10"),
            actor_id=books.actor_id,
        )


def test_the_balance_says_whether_it_can_be_spent() -> None:
    """Answered by the service so a screen cannot offer what it would refuse."""
    books = _Books(_session_factory()(), enabled=False)
    books.enable(minimum_redemption_points=100)
    books.earn(books.invoice("SI-1", total="1000"))

    answer = LoyaltyService(books.session).balance(
        books.customer.id, firm_scope=books.firm.id
    )

    assert answer.points == Decimal("20.0000")
    assert answer.redeemable is False


def test_an_adjustment_posts_nothing() -> None:
    """It is a correction to a count, not a transaction.

    The money side was either already booked when the points were earned or
    was never right to book, and booking it again would double what the scheme
    appears to have cost.
    """
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))
    before = books.session.scalar(select(func.count()).select_from(JournalEntry))

    LoyaltyService(books.session).adjust(
        firm_scope=books.firm.id,
        customer_id=books.customer.id,
        points=Decimal("5"),
        reason="Goodwill after a late delivery.",
        actor_id=books.actor_id,
    )

    assert books.points() == Decimal("25.0000")
    assert (
        books.session.scalar(select(func.count()).select_from(JournalEntry)) == before
    )


def test_an_adjustment_cannot_take_a_balance_below_zero() -> None:
    """A customer cannot owe the firm points."""
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))

    with pytest.raises(ValidationError, match="below zero"):
        LoyaltyService(books.session).adjust(
            firm_scope=books.firm.id,
            customer_id=books.customer.id,
            points=Decimal("-50"),
            reason="Credited in error.",
            actor_id=books.actor_id,
        )


def test_points_lapse_when_their_time_runs_out() -> None:
    """And the entry that took them says which entry it took."""
    books = _Books(_session_factory()(), enabled=False)
    books.enable(expiry_months=6)
    books.earn(books.invoice("SI-1", total="1000"))

    lapsed = LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2027, 1, 1)
    )

    assert lapsed == 1
    assert books.points() == Decimal("0.0000")
    taken = books.session.scalar(
        select(LoyaltyEntry).where(LoyaltyEntry.kind == LoyaltyEntryKind.EXPIRED.value)
    )
    assert taken is not None and taken.reverses_id is not None


def test_the_sweep_cannot_take_the_same_points_twice() -> None:
    """Which is what naming the entry it takes is for."""
    books = _Books(_session_factory()(), enabled=False)
    books.enable(expiry_months=6)
    books.earn(books.invoice("SI-1", total="1000"))
    service = LoyaltyService(books.session)
    service.expire(firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2027, 1, 1))

    assert (
        service.expire(
            firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2027, 1, 1)
        )
        == 0
    )
    assert books.points() == Decimal("0.0000")


def test_points_with_no_expiry_never_lapse() -> None:
    """Null months is a real choice, not a missing value."""
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))

    LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2099, 1, 1)
    )

    assert books.points() == Decimal("20.0000")


def test_settings_leave_an_omitted_field_alone() -> None:
    """A full dump would reset a rate a firm had agreed with its customers."""
    books = _Books(_session_factory()())
    service = LoyaltyService(books.session)

    service.write_settings(
        books.firm.id,
        LoyaltySettingsWrite(minimum_redemption_points=50),
        actor_id=books.actor_id,
    )
    answer = service.read_settings(books.firm.id)

    assert answer.minimum_redemption_points == 50
    assert answer.points_per_amount == Decimal("2.0000")
    assert answer.is_enabled is True


def test_one_firm_s_customer_is_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())

    with pytest.raises(ResourceNotFoundError):
        LoyaltyService(books.session).balance(books.customer.id, firm_scope=uuid4())


def test_a_draft_invoice_cannot_be_settled_with_points() -> None:
    """A draft is not a sale, so there is nothing to settle."""
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))
    draft = books.invoice("SI-2", total="500", status="DRAFT")

    with pytest.raises(ValidationError, match="approved invoice"):
        LoyaltyService(books.session).redeem(
            firm_scope=books.firm.id,
            invoice_id=draft.id,
            points=Decimal("10"),
            actor_id=books.actor_id,
        )


def test_the_chart_carries_somewhere_to_book_a_scheme() -> None:
    """Every firm gets the two accounts a scheme needs.

    A purpose with no mapping is an error naming the purpose, never a
    fallback, so an unmapped firm could not approve an invoice at all once the
    scheme was switched on.
    """
    books = _Books(_session_factory()())

    service = ControlAccountService(books.session)
    assert service.resolve(books.firm.id, ControlAccountPurpose.LOYALTY_EXPENSE)
    assert service.resolve(books.firm.id, ControlAccountPurpose.LOYALTY_PAYABLE)


def test_redeeming_moves_the_customer_s_balance_too() -> None:
    """Both books, or neither.

    The journal reduces the receivable **control account**; without a matching
    receivable transaction the customer's own balance stays where it was, and
    the subsidiary ledger and the general one drift apart by every redemption.
    `verify_sample_data.py` caught exactly that within minutes of the seed
    running -- "a balance moved without a journal", read from the other side.
    """
    books = _Books(_session_factory()())
    books.earn(books.invoice("SI-1", total="1000"))
    later = books.invoice("SI-2", total="500")
    books.customer.current_outstanding = Decimal("500.00")
    books.session.commit()

    LoyaltyService(books.session).redeem(
        firm_scope=books.firm.id,
        invoice_id=later.id,
        points=Decimal("20"),
        actor_id=books.actor_id,
    )
    books.session.refresh(books.customer)

    assert books.customer.current_outstanding == Decimal("480.0000")


# ---------------------------------------------------------------------------
# Expiry, and the points that had already been spent
# ---------------------------------------------------------------------------
#
# Found by the 2026-09-03 module review. `expire` wrote back the whole earned
# entry -- `points=-entry.points` -- without asking how much of that batch was
# still there, so a batch the customer had already spent lapsed a second time.


def test_expiry_does_not_take_points_that_were_already_spent() -> None:
    """A batch that has been spent has nothing left to lapse.

    Earn 100, spend 100, let the batch lapse: the sweep wrote -100 against a
    balance of nothing, leaving the customer **-100 points** for credit they
    had legitimately used. `balance` sums the ledger with no floor, and
    redeeming is refused above the balance, so expiry was the only way to go
    negative -- and it did so silently, on a customer who had done nothing
    wrong.
    """
    books = _Books(_session_factory()())
    books.batch("100", earned_on=date(2026, 6, 1), expires_on=date(2026, 7, 1))
    books.spend("100", on=date(2026, 6, 15))
    assert books.points() == Decimal("0.0000")

    LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2026, 8, 1)
    )

    assert books.points() == Decimal("0.0000"), (
        "spending a batch before it lapses must not leave the customer owing " "points"
    )


def test_expiry_takes_only_the_unspent_part_of_a_batch() -> None:
    """Sixty spent of a hundred leaves forty to lapse, and no more."""
    books = _Books(_session_factory()())
    books.batch("100", earned_on=date(2026, 6, 1), expires_on=date(2026, 7, 1))
    books.spend("60", on=date(2026, 6, 15))
    assert books.points() == Decimal("40.0000")

    LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2026, 8, 1)
    )

    assert books.points() == Decimal("0.0000")


def test_a_spend_consumes_the_batch_closest_to_lapsing() -> None:
    """FIFO, and it is why the sweep cannot just cap at the balance.

    Two batches -- one expiring, one with a year left -- and the customer
    spends exactly the older one's worth. The spend consumed the expiring
    batch, so nothing lapses and the newer batch survives in full. Capping
    the sweep at the customer's balance instead would have taken the batch
    that had a year on it.
    """
    books = _Books(_session_factory()())
    books.batch("100", earned_on=date(2026, 6, 1), expires_on=date(2026, 7, 1))
    books.batch("50", earned_on=date(2026, 6, 20), expires_on=date(2027, 3, 1))
    books.spend("100", on=date(2026, 6, 25))

    LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2026, 8, 1)
    )

    assert books.points() == Decimal("50.0000"), (
        "the spend consumed the batch about to lapse, so the newer one is " "untouched"
    )


def test_the_sweep_still_runs_twice_without_taking_the_same_points() -> None:
    """The idempotence the method already had has to survive the fix."""
    books = _Books(_session_factory()())
    books.batch("100", earned_on=date(2026, 6, 1), expires_on=date(2026, 7, 1))
    service = LoyaltyService(books.session)

    first = service.expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2026, 8, 1)
    )
    second = service.expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2026, 8, 1)
    )

    assert (first, second) == (1, 0)
    assert books.points() == Decimal("0.0000")


def test_lapsed_points_release_the_liability_they_raised() -> None:
    """Points cost the firm when earned, so points that lapse give it back.

    Earning posts `Dr Loyalty Expense / Cr Loyalty Payable`. Nothing released
    that when the credit ran out of time, so `Loyalty Payable` kept a
    liability for credit no customer could ever claim -- growing with every
    sweep and reconciling to nothing.
    """
    books = _Books(_session_factory()())
    books.batch("100", earned_on=date(2026, 6, 1), expires_on=date(2026, 7, 1))

    LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4(), as_of=date(2026, 8, 1)
    )

    lapsed = books.session.scalar(
        select(LoyaltyEntry).where(
            LoyaltyEntry.firm_id == books.firm.id,
            LoyaltyEntry.kind == LoyaltyEntryKind.EXPIRED.value,
        )
    )
    assert lapsed is not None
    assert (
        lapsed.journal_entry_id is not None
    ), "a liability for credit that can never be claimed has to be released"
    legs = books.session.scalars(
        select(JournalLine).where(
            JournalLine.journal_entry_id == lapsed.journal_entry_id
        )
    ).all()
    # The mirror of the accrual: the payable comes down, the cost comes back.
    payable = next(leg for leg in legs if Decimal(str(leg.debit_amount)) > Decimal("0"))
    assert Decimal(str(payable.debit_amount)) == Decimal("100.00")
