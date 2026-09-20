"""Commission that actually pays: accrue, adjust, approve, pay, cancel.

`app/commission` reported what a period earned and paid nobody. These are the
cases that decide whether the payout that closes that gap can be trusted:

- the amounts are **snapshotted at accrual**, because the report reads live
  documents and would answer differently the next time it is asked;
- **one live payout per person per overlapping period**, because two would pay
  the same collections twice;
- approval **posts** and cancellation **reverses**, so the ledger and the
  record never disagree about what the firm owes.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.commission.models import CommissionPayoutStatus, CommissionRule
from app.commission.schemas import CommissionRuleCreate
from app.commission.schemas.payout import (
    CommissionPayoutAccrue,
    CommissionPayoutPay,
    CommissionPayoutUpdate,
)
from app.commission.services import CommissionPayoutService, CommissionService
from app.core.database.base import Base
from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.credit_note.models import CreditNote
from app.customers.models import Customer
from app.finance.models import JournalEntry, JournalLine, LedgerAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales_invoice.models import SalesInvoice
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

WHEN = date(2026, 4, 20)
APRIL = (date(2026, 4, 1), date(2026, 4, 30))
MAY = (date(2026, 5, 1), date(2026, 5, 31))


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
    """A firm with a chart, a customer, a salesman and money collected."""

    def __init__(self, session: Session, code: str = "PAYO") -> None:
        """Seed everything an accrual needs to have something to accrue."""
        self.session = session
        #: Three people, because the service insists on three (D-TER-4): one
        #: accrues, a second approves, a third pays -- and none is Asha.
        self.actor_id = uuid4()
        self.approver_id = uuid4()
        self.payer_id = uuid4()
        self.firm = Firm(
            name=f"{code} Firm",
            code=code,
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
        session.commit()
        self.branch_id = uuid4()
        self.customer = Customer(
            firm_id=self.firm.id,
            code=f"C1-{code}",
            customer_type="BUSINESS",
            name="Customer One",
            display_name="Customer One",
            currency_code="INR",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        session.add(self.customer)
        session.commit()
        self.asha = self.salesman("Asha Rao", f"asha@{code.lower()}.example.com")

    def salesman(self, name: str, email: str) -> UUID:
        """Add one active member of the firm and return their id."""
        user = User(email=email, full_name=name, password_hash="x", is_active=True)
        self.session.add(user)
        self.session.flush()
        self.session.add(
            UserFirm(user_id=user.id, firm_id=self.firm.id, is_active=True)
        )
        self.session.commit()
        return user.id

    def rule(self, percentage: str) -> None:
        """Agree a flat rate for Asha."""
        CommissionService(self.session).create_rule(
            CommissionRuleCreate(
                salesman_id=self.asha,
                percentage=Decimal(percentage),
                effective_from=date(2026, 4, 1),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def collect(self, number: str, amount: str, when: date = WHEN) -> None:
        """Bill Asha's customer and collect all of it."""
        invoice = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch_id,
            salesman_id=self.asha,
            invoice_number=number,
            invoice_date=when,
            status="APPROVED",
            grand_total=Decimal(amount),
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(invoice)
        self.session.commit()
        ReceiptService(self.session).create(
            SettlementCreate(
                party_id=self.customer.id,
                settlement_date=when,
                amount=Decimal(amount),
                method=SettlementMethodEnum.CASH,
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=invoice.id, amount=Decimal(amount)
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def credit(self, number: str, amount: str, when: date) -> None:
        """Credit part of one of Asha's bills, as an approved credit note."""
        invoice = self.session.scalars(
            select(SalesInvoice).where(SalesInvoice.invoice_number == number)
        ).one()
        self.session.add(
            CreditNote(
                firm_id=self.firm.id,
                customer_id=self.customer.id,
                branch_id=self.branch_id,
                sales_invoice_id=invoice.id,
                credit_note_number=f"CN-{number}-{amount}",
                credit_note_date=when,
                status="APPROVED",
                taxable_amount=Decimal(amount),
                tax_amount=Decimal("0"),
                total_amount=Decimal(amount),
                created_by=self.actor_id,
                updated_by=self.actor_id,
            )
        )
        self.session.commit()

    def settle(self, payout_id: UUID, *, paid_on: date = date(2026, 5, 5)) -> None:
        """Approve and pay one payout."""
        service = CommissionPayoutService(self.session)
        service.approve(payout_id, firm_id=self.firm.id, actor_id=self.approver_id)
        self.session.commit()
        service.pay(
            payout_id,
            CommissionPayoutPay(
                paid_on=paid_on,
                money_account_id=self.account(ControlAccountPurpose.CASH),
            ),
            firm_id=self.firm.id,
            actor_id=self.payer_id,
        )
        self.session.commit()

    def account(self, purpose: ControlAccountPurpose) -> UUID:
        """Resolve one of the firm's control accounts."""
        from app.finance.models import FirmControlAccount

        account_id = self.session.scalar(
            select(FirmControlAccount.ledger_account_id).where(
                FirmControlAccount.firm_id == self.firm.id,
                FirmControlAccount.purpose == purpose.value,
                FirmControlAccount.is_deleted.is_(False),
            )
        )
        assert account_id is not None, f"{purpose.value} is not mapped"
        return account_id

    def accrue(self, period: tuple[date, date] = APRIL) -> list[object]:  # noqa: ANN401
        """Run the accrual for a period."""
        service = CommissionPayoutService(self.session)
        rows = service.accrue(
            CommissionPayoutAccrue(period_start=period[0], period_end=period[1]),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return list(rows)

    def legs(self, entry_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return one journal's lines, by account."""
        lines = self.session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
        ).all()
        return {
            line.ledger_account_id: (line.debit_amount, line.credit_amount)
            for line in lines
        }


def _ready(percentage: str = "10", collected: str = "5000.00") -> _Books:
    """Build a firm with a rate agreed and money collected under it."""
    books = _Books(_session_factory()())
    books.rule(percentage)
    books.collect("SI-1", collected)
    return books


def test_an_accrual_stores_what_the_report_said() -> None:
    """The simplest case, and the one everything else builds on."""
    books = _ready()

    [payout] = books.accrue()

    assert payout.salesman_id == books.asha
    assert payout.measured_amount == Decimal("5000.00")
    assert payout.earned_amount == Decimal("500.00")
    assert payout.payable_amount == Decimal("500.00")
    assert payout.basis == "COLLECTED"
    assert payout.status == CommissionPayoutStatus.DRAFT.value
    # Nothing has reached the ledger: a payout nobody approved is not a debt.
    assert payout.journal_entry_id is None


def test_an_approved_payout_is_not_recomputed_when_the_world_moves() -> None:
    """What a firm approved is what it owes.

    The report walks live documents, so a rate corrected in May would change
    what April's payout said if the number were read again -- and the journal
    posted at approval would then disagree with the record beside it.
    """
    books = _ready()
    [payout] = books.accrue()
    CommissionPayoutService(books.session).approve(
        payout.id, firm_id=books.firm.id, actor_id=books.approver_id
    )
    books.session.commit()

    # The arrangement changes afterwards, as arrangements do.
    rule = books.session.scalars(
        select(
            __import__(
                "app.commission.models", fromlist=["CommissionRule"]
            ).CommissionRule
        )
    ).one()
    rule.percentage = Decimal("50")
    books.session.commit()

    reread = CommissionPayoutService(books.session).get_payout(
        payout.id, firm_id=books.firm.id
    )
    assert reread.payable_amount == Decimal("500.00")


def test_approving_posts_the_cost_and_the_debt() -> None:
    """Two legs, and the debt is a liability rather than cash going out.

    Booking the expense straight against cash would say the firm owes nobody
    the moment it recognises the cost, which is wrong for every period that
    closes before the money moves -- and that is most of them.
    """
    books = _ready()
    [payout] = books.accrue()

    approved = CommissionPayoutService(books.session).approve(
        payout.id, firm_id=books.firm.id, actor_id=books.approver_id
    )
    books.session.commit()

    assert approved.status == CommissionPayoutStatus.APPROVED.value
    assert approved.journal_entry_id is not None
    legs = books.legs(approved.journal_entry_id)
    expense = books.account(ControlAccountPurpose.COMMISSION_EXPENSE)
    payable = books.account(ControlAccountPurpose.COMMISSION_PAYABLE)
    assert legs[expense] == (Decimal("500.00"), Decimal("0.00"))
    assert legs[payable] == (Decimal("0.00"), Decimal("500.00"))


def test_paying_clears_the_debt_and_does_not_book_the_cost_again() -> None:
    """The expense was recognised at approval.

    Recognising it again at payment would double the cost in whichever period
    the money happened to move.
    """
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)
    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    books.session.commit()
    cash = books.account(ControlAccountPurpose.CASH)

    paid = service.pay(
        payout.id,
        CommissionPayoutPay(paid_on=date(2026, 5, 5), money_account_id=cash),
        firm_id=books.firm.id,
        actor_id=books.payer_id,
    )
    books.session.commit()

    assert paid.status == CommissionPayoutStatus.PAID.value
    legs = books.legs(paid.payment_journal_entry_id)
    payable = books.account(ControlAccountPurpose.COMMISSION_PAYABLE)
    expense = books.account(ControlAccountPurpose.COMMISSION_EXPENSE)
    assert legs[payable] == (Decimal("500.00"), Decimal("0.00"))
    assert legs[cash] == (Decimal("0.00"), Decimal("500.00"))
    assert expense not in legs


def test_a_second_payout_over_the_same_days_is_refused() -> None:
    """Two would pay the same collections twice."""
    books = _ready()
    books.accrue()

    with pytest.raises(ConflictError):
        books.accrue()


def test_a_cancelled_payout_frees_the_period_again() -> None:
    """An accrual withdrawn is an accrual that can be re-run.

    Otherwise a period accrued at the wrong rate could never be corrected,
    which is the whole reason cancelling exists.
    """
    books = _ready()
    [payout] = books.accrue()
    CommissionPayoutService(books.session).cancel(
        payout.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    [again] = books.accrue()
    assert again.payable_amount == Decimal("500.00")


def test_cancelling_an_approved_payout_reverses_its_journal() -> None:
    """A posted entry is history; it is mirrored, never deleted."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)
    approved = service.approve(
        payout.id, firm_id=books.firm.id, actor_id=books.approver_id
    )
    books.session.commit()
    original = approved.journal_entry_id

    service.cancel(payout.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    mirror = books.session.scalars(
        select(JournalEntry).where(JournalEntry.reversal_of_id == original)
    ).one()
    legs = books.legs(mirror.id)
    expense = books.account(ControlAccountPurpose.COMMISSION_EXPENSE)
    payable = books.account(ControlAccountPurpose.COMMISSION_PAYABLE)
    # Every leg flipped, which is right here: what is being undone is worth
    # exactly what it was worth when it happened.
    assert legs[expense] == (Decimal("0.00"), Decimal("500.00"))
    assert legs[payable] == (Decimal("500.00"), Decimal("0.00"))


def test_a_paid_payout_cannot_be_cancelled() -> None:
    """The money has gone; undoing that is a payment the other way."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)
    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    books.session.commit()
    service.pay(
        payout.id,
        CommissionPayoutPay(
            paid_on=date(2026, 5, 5),
            money_account_id=books.account(ControlAccountPurpose.CASH),
        ),
        firm_id=books.firm.id,
        actor_id=books.payer_id,
    )
    books.session.commit()

    with pytest.raises(ValidationError):
        service.cancel(payout.id, firm_id=books.firm.id, actor_id=books.actor_id)


def test_a_payout_cannot_be_paid_before_it_is_approved() -> None:
    """Approval is what recognises the debt the payment clears."""
    books = _ready()
    [payout] = books.accrue()

    with pytest.raises(ValidationError):
        CommissionPayoutService(books.session).pay(
            payout.id,
            CommissionPayoutPay(
                paid_on=date(2026, 5, 5),
                money_account_id=books.account(ControlAccountPurpose.CASH),
            ),
            firm_id=books.firm.id,
            actor_id=books.payer_id,
        )


def test_an_adjustment_changes_what_is_owed_and_needs_a_reason() -> None:
    """A number nobody can explain at the year end is not an adjustment."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)

    with pytest.raises(ValidationError):
        service.update_payout(
            payout.id,
            CommissionPayoutUpdate(adjustment_amount=Decimal("-100")),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.rollback()

    adjusted = service.update_payout(
        payout.id,
        CommissionPayoutUpdate(
            adjustment_amount=Decimal("-100"),
            adjustment_reason="Advance drawn in April.",
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert adjusted.payable_amount == Decimal("400.00")


def test_an_adjustment_cannot_make_a_payout_negative() -> None:
    """A payout cannot take money back; that is a different transaction."""
    books = _ready()
    [payout] = books.accrue()

    with pytest.raises(ValidationError):
        CommissionPayoutService(books.session).update_payout(
            payout.id,
            CommissionPayoutUpdate(
                adjustment_amount=Decimal("-900"), adjustment_reason="Too much."
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_approved_payout_cannot_be_adjusted() -> None:
    """The journal is posted; changing the record would leave the two apart."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)
    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    books.session.commit()

    with pytest.raises(ValidationError):
        service.update_payout(
            payout.id,
            CommissionPayoutUpdate(
                adjustment_amount=Decimal("-100"), adjustment_reason="Late."
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_the_adjusted_amount_is_what_posts() -> None:
    """The ledger records what the firm owes, not what the rate produced."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)
    service.update_payout(
        payout.id,
        CommissionPayoutUpdate(
            adjustment_amount=Decimal("-100"), adjustment_reason="Advance drawn."
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    approved = service.approve(
        payout.id, firm_id=books.firm.id, actor_id=books.approver_id
    )
    books.session.commit()
    legs = books.legs(approved.journal_entry_id)
    assert legs[books.account(ControlAccountPurpose.COMMISSION_EXPENSE)] == (
        Decimal("400.00"),
        Decimal("0.00"),
    )


def test_nobody_who_earned_nothing_gets_a_payout() -> None:
    """A payout of zero is paperwork that says nothing the report does not."""
    books = _Books(_session_factory()())
    books.rule("10")

    assert books.accrue() == []


def test_the_unassigned_bucket_never_becomes_a_payout() -> None:
    """Money collected against untagged invoices belongs to nobody.

    It stays in the report so the collections reconcile against the cash book,
    and there is nobody to pay it to.
    """
    books = _Books(_session_factory()())
    books.rule("10")
    invoice = SalesInvoice(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch_id,
        salesman_id=None,
        invoice_number="SI-ORPHAN",
        invoice_date=WHEN,
        status="APPROVED",
        grand_total=Decimal("5000.00"),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(invoice)
    books.session.commit()
    ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("5000.00"),
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("5000.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.accrue() == []


def test_an_adjoining_period_is_free_to_accrue() -> None:
    """The guard is about overlap, not about having been paid before."""
    books = _ready()
    books.accrue(APRIL)
    books.collect("SI-2", "2000.00", when=date(2026, 5, 10))

    [may] = books.accrue(MAY)
    assert may.payable_amount == Decimal("200.00")


def test_a_money_account_from_another_firm_is_refused() -> None:
    """Every firm's ledger accounts sit in one table in a shared store.

    An id from elsewhere would land in somebody else's books, which no trial
    balance would explain. The refusal comes from the journal engine, which
    loads accounts scoped to the firm -- so this proves the payout path is on
    that engine rather than writing lines of its own, which is the way the
    check could actually be lost.
    """
    session = _session_factory()()
    books = _Books(session)
    books.rule("10")
    books.collect("SI-1", "5000.00")
    theirs = _Books(session, code="OTHR")
    intruder = theirs.account(ControlAccountPurpose.CASH)

    [payout] = books.accrue()
    service = CommissionPayoutService(session)
    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    session.commit()

    with pytest.raises(ValidationError):
        service.pay(
            payout.id,
            CommissionPayoutPay(paid_on=date(2026, 5, 5), money_account_id=intruder),
            firm_id=books.firm.id,
            actor_id=books.payer_id,
        )


def test_one_firm_s_payouts_are_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _ready()
    [payout] = books.accrue()

    rows, total = CommissionPayoutService(books.session).list_payouts(
        firm_id=uuid4(), page=1, page_size=20
    )
    assert total == 0
    assert rows == []
    assert payout.firm_id == books.firm.id


def test_the_seeded_chart_nominates_both_commission_accounts() -> None:
    """A purpose with no mapping refuses the posting, naming the purpose.

    That is the right behaviour and the wrong first experience, so a firm's
    default chart carries both accounts rather than leaving the first payout
    to fail.
    """
    books = _Books(_session_factory()())
    for purpose, code in (
        (ControlAccountPurpose.COMMISSION_EXPENSE, "5600"),
        (ControlAccountPurpose.COMMISSION_PAYABLE, "2400"),
    ):
        account = books.session.get(LedgerAccount, books.account(purpose))
        assert account is not None
        assert account.code == code


JUNE = (date(2026, 6, 1), date(2026, 6, 30))


def test_a_credit_after_payment_is_clawed_back_on_the_next_accrual() -> None:
    """D-TER-3: the paid row is never rewritten; the next accrual carries it.

    April: 5,000 collected, 500 earned, paid. Then 2,000 of that bill is
    credited back, so April is worth 300 and was overpaid by 200. May earns
    300 on its own sales; its payout carries the 200 and owes 100. April
    still reads exactly what was paid on it, and June does not recover the
    same 200 a second time.
    """
    books = _ready()
    [april] = books.accrue()
    books.settle(april.id)
    books.credit("SI-1", "2000.00", when=date(2026, 5, 10))
    books.collect("SI-2", "3000.00", when=date(2026, 5, 20))

    [may] = books.accrue(MAY)

    assert may.earned_amount == Decimal("300.00")
    assert may.clawback_amount == Decimal("200.00")
    assert may.payable_amount == Decimal("100.00")
    reread = CommissionPayoutService(books.session).get_payout(
        april.id, firm_id=books.firm.id
    )
    assert reread.earned_amount == Decimal("500.00")
    assert reread.payable_amount == Decimal("500.00")
    assert reread.status == CommissionPayoutStatus.PAID.value

    books.settle(may.id, paid_on=date(2026, 6, 5))
    books.collect("SI-3", "1000.00", when=date(2026, 6, 20))
    [june] = books.accrue(JUNE)
    assert june.clawback_amount == Decimal("0.00")
    assert june.payable_amount == Decimal("100.00")


def test_what_one_period_cannot_recover_waits_for_the_next() -> None:
    """A payout cannot take money back, so the clawback stops at what was earned.

    April paid 500; the whole bill comes back, so April is short by 500. May
    earns 300: all of it is taken and May owes nothing. June earns 100: the
    remaining 200 is taken as far as it goes, and 100 still waits.
    """
    books = _ready()
    [april] = books.accrue()
    books.settle(april.id)
    books.credit("SI-1", "5000.00", when=date(2026, 5, 10))
    books.collect("SI-2", "3000.00", when=date(2026, 5, 20))

    [may] = books.accrue(MAY)
    assert may.clawback_amount == Decimal("300.00")
    assert may.payable_amount == Decimal("0.00")
    # Nothing owed and nothing posted, but approving and paying it is what
    # makes the recovery final.
    books.settle(may.id, paid_on=date(2026, 6, 5))
    settled = CommissionPayoutService(books.session).get_payout(
        may.id, firm_id=books.firm.id
    )
    assert settled.status == CommissionPayoutStatus.PAID.value
    assert settled.journal_entry_id is None
    assert settled.payment_journal_entry_id is None

    books.collect("SI-3", "1000.00", when=date(2026, 6, 20))
    [june] = books.accrue(JUNE)
    assert june.clawback_amount == Decimal("100.00")
    assert june.payable_amount == Decimal("0.00")


def test_cancelling_the_carrying_payout_releases_what_it_recovered() -> None:
    """The recovery lives on the carrier, so withdrawing it puts it back."""
    books = _ready()
    [april] = books.accrue()
    books.settle(april.id)
    books.credit("SI-1", "2000.00", when=date(2026, 5, 10))
    books.collect("SI-2", "3000.00", when=date(2026, 5, 20))
    [may] = books.accrue(MAY)
    assert may.clawback_amount == Decimal("200.00")

    service = CommissionPayoutService(books.session)
    service.cancel(may.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    [again] = books.accrue(MAY)
    assert again.clawback_amount == Decimal("200.00")
    assert again.payable_amount == Decimal("100.00")


def test_a_period_only_worth_more_now_is_not_paid_again() -> None:
    """Only a shortfall is carried: nothing about a paid period was owed."""
    books = _ready()
    [april] = books.accrue()
    books.settle(april.id)
    # The rate goes up afterwards, so April re-read is worth 2,500 against
    # the 500 paid on it. Nothing is carried either way.
    rule = books.session.scalars(select(CommissionRule)).one()
    rule.percentage = Decimal("50")
    books.session.commit()
    books.collect("SI-2", "3000.00", when=date(2026, 5, 20))

    [may] = books.accrue(MAY)

    assert may.clawback_amount == Decimal("0.00")
    assert may.earned_amount == Decimal("1500.00")
    assert may.payable_amount == Decimal("1500.00")


# ----------------------------------------------------------------------
# D-TER-4: one person may not state, agree and pay a debt -- least of all
# their own. Judged per person, not per role, so holding two roles buys
# nothing.
# ----------------------------------------------------------------------


def _cash_payment(books: _Books) -> CommissionPayoutPay:
    """Pay from the firm's cash account on 5 May."""
    return CommissionPayoutPay(
        paid_on=date(2026, 5, 5),
        money_account_id=books.account(ControlAccountPurpose.CASH),
    )


def test_nobody_approves_or_pays_their_own_payout() -> None:
    """A salesman who also holds the accountant's role is still the payee.

    Live: one user holding ACCOUNTANT beside SALES_EXECUTIVE accrued his own
    payout, adjusted it by 5,000 "because", approved it and paid it, with his
    own id on all five audit rows.
    """
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)

    with pytest.raises(AuthorizationError, match="your own"):
        service.approve(payout.id, firm_id=books.firm.id, actor_id=books.asha)
    books.session.rollback()

    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    books.session.commit()
    with pytest.raises(AuthorizationError, match="your own"):
        service.pay(
            payout.id,
            _cash_payment(books),
            firm_id=books.firm.id,
            actor_id=books.asha,
        )


def test_the_accruer_cannot_approve_and_the_approver_cannot_pay() -> None:
    """Maker-checker at the person level: three signatures, three people."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)

    with pytest.raises(AuthorizationError, match="accrued"):
        service.approve(payout.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.rollback()

    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    books.session.commit()
    with pytest.raises(AuthorizationError, match="approved"):
        service.pay(
            payout.id,
            _cash_payment(books),
            firm_id=books.firm.id,
            actor_id=books.approver_id,
        )
    books.session.rollback()

    # The accruer may pay: the rule is that the approver and the payer
    # differ, and that neither is the payee.
    paid = service.pay(
        payout.id,
        _cash_payment(books),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert paid.status == CommissionPayoutStatus.PAID.value


def test_the_row_records_who_approved_and_who_paid() -> None:
    """The row and the audit trail say the same thing about who signed.

    Held on the row because the payment check reads it, and a check that
    has to search the trail is one that quietly stops being made.
    """
    books = _ready()
    [payout] = books.accrue()
    assert payout.approved_by is None
    assert payout.approved_at is None
    assert payout.paid_by is None

    books.settle(payout.id)

    service = CommissionPayoutService(books.session)
    row = service.get_payout(payout.id, firm_id=books.firm.id)
    assert row.created_by == books.actor_id
    assert row.approved_by == books.approver_id
    assert row.approved_at is not None
    assert row.paid_by == books.payer_id
    response = service.payout_response(row, {})
    assert response.accrued_by == books.actor_id
    assert response.approved_by == books.approver_id
    assert response.paid_by == books.payer_id


def test_cancelling_keeps_the_approval_on_record() -> None:
    """What was recorded happened; withdrawing the payout does not unsay it."""
    books = _ready()
    [payout] = books.accrue()
    service = CommissionPayoutService(books.session)
    service.approve(payout.id, firm_id=books.firm.id, actor_id=books.approver_id)
    books.session.commit()

    cancelled = service.cancel(
        payout.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    assert cancelled.status == CommissionPayoutStatus.CANCELLED.value
    assert cancelled.approved_by == books.approver_id
    assert cancelled.approved_at is not None
