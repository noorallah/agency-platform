"""A customer's account over a period, and what of it is overdue.

The cases that decide whether either can be trusted:

- the running balance is **recomputed in date order**, not read off the stored
  `outstanding_after` -- that column was written in the order things were
  *recorded*, and a backdated receipt makes the two disagree;
- the opening balance is **summed from the deltas before the period**, the same
  arithmetic that produced the current balance, so the two cannot drift;
- what a bill still owes is **derived from the allocations**, and a reversed
  settlement cleared nothing;
- and the ageing buckets must add up to the total, or the report is one nobody
  can reconcile.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.services import CustomerStatementService
from app.firms.models import Firm
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement, SettlementAllocation

APRIL = (date(2026, 4, 1), date(2026, 4, 30))


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
    """A firm with one customer whose account has some history."""

    def __init__(self, session: Session) -> None:
        """Seed the firm, a branch and a customer."""
        self.session = session
        self.firm = Firm(
            name="Statement Firm",
            code="STMT",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
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

    def movement(
        self,
        kind: str,
        amount: str,
        on: date,
        *,
        outstanding_after: str | None = None,
        reference: str | None = None,
    ) -> CustomerReceivableTransaction:
        """Record one movement on the account.

        `outstanding_after` can be set to whatever the caller likes, which is
        the point: it is a snapshot taken when the row was written and a
        statement must not believe it.
        """
        delta = Decimal(amount)
        row = CustomerReceivableTransaction(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            transaction_type=kind,
            transaction_date=on,
            amount=abs(delta),
            outstanding_delta=delta,
            advance_delta=Decimal("0"),
            outstanding_after=Decimal(outstanding_after or "0"),
            advance_after=Decimal("0"),
            reference_number=reference,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def invoice(
        self,
        number: str,
        total: str,
        *,
        on: date = date(2026, 4, 10),
        due: date | None = None,
        status: str = "APPROVED",
    ) -> SalesInvoice:
        """Raise a bill the ageing can find."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            invoice_number=number,
            invoice_date=on,
            due_date=due,
            status=status,
            grand_total=Decimal(total),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def settle(
        self,
        invoice: SalesInvoice,
        amount: str,
        *,
        number: str = "RC-1",
        status: str = "POSTED",
    ) -> Settlement:
        """Pay something against a bill."""
        settlement = Settlement(
            firm_id=self.firm.id,
            direction="RECEIPT",
            customer_id=self.customer.id,
            settlement_number=number,
            settlement_date=date(2026, 4, 20),
            amount=Decimal(amount),
            allocated_amount=Decimal(amount),
            unallocated_amount=Decimal("0"),
            method="BANK",
            ledger_account_id=uuid4(),
            status=status,
            journal_entry_id=uuid4(),
        )
        self.session.add(settlement)
        self.session.flush()
        self.session.add(
            SettlementAllocation(
                firm_id=self.firm.id,
                settlement_id=settlement.id,
                sales_invoice_id=invoice.id,
                amount=Decimal(amount),
            )
        )
        self.session.commit()
        return settlement

    def statement(self, period: tuple[date, date] = APRIL) -> object:
        """Read the account over a period."""
        return CustomerStatementService(self.session).statement(
            self.customer.id,
            firm_scope=self.firm.id,
            from_date=period[0],
            to_date=period[1],
        )

    def ageing(self, as_of: date = date(2026, 6, 1)) -> list:
        """Read what is overdue as at a day."""
        return CustomerStatementService(self.session).ageing(
            firm_scope=self.firm.id, as_of=as_of
        )


def test_the_running_balance_is_recomputed_in_date_order() -> None:
    """Not read off `outstanding_after`.

    That column is a snapshot taken in the order rows were *written*. Money
    arriving against a bill raised last month is recorded after it and dated
    before it, so believing the snapshot shows a balance that never existed on
    any day. Both rows below carry a deliberately absurd snapshot.
    """
    books = _Books(_session_factory()())
    books.movement("INVOICE", "1000", date(2026, 4, 10), outstanding_after="99999")
    # Written second, dated first.
    books.movement("RECEIPT", "-400", date(2026, 4, 5), outstanding_after="88888")

    lines = books.statement().lines

    assert [line.transaction_date for line in lines] == [
        date(2026, 4, 5),
        date(2026, 4, 10),
    ]
    assert [str(line.balance) for line in lines] == ["-400.00", "600.00"]


def test_the_opening_balance_is_summed_from_what_came_before() -> None:
    """The same arithmetic that produced the current balance.

    Deriving it by subtracting the period's movement from today's balance
    gives the right answer only while nothing is ever backdated.
    """
    books = _Books(_session_factory()())
    books.movement("INVOICE", "2500", date(2026, 3, 1))
    books.movement("RECEIPT", "-500", date(2026, 3, 20))
    books.movement("INVOICE", "1000", date(2026, 4, 10))

    answer = books.statement()

    assert answer.opening_balance == Decimal("2000.00")
    assert answer.closing_balance == Decimal("3000.00")
    assert len(answer.lines) == 1


def test_a_movement_is_split_into_a_debit_and_a_credit() -> None:
    """One signed delta, read the way a ledger reads."""
    books = _Books(_session_factory()())
    books.movement("INVOICE", "1000", date(2026, 4, 10))
    books.movement("RECEIPT", "-400", date(2026, 4, 20))

    lines = books.statement().lines

    assert lines[0].debit == Decimal("1000.00")
    assert lines[0].credit == Decimal("0")
    assert lines[1].debit == Decimal("0")
    assert lines[1].credit == Decimal("400.00")


def test_a_period_that_runs_backwards_is_refused() -> None:
    """The same guard every report in this repo carries."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        books.statement((date(2026, 4, 30), date(2026, 4, 1)))


def test_one_firm_s_customer_is_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())

    with pytest.raises(ResourceNotFoundError):
        CustomerStatementService(books.session).statement(
            books.customer.id,
            firm_scope=uuid4(),
            from_date=APRIL[0],
            to_date=APRIL[1],
        )


def test_what_a_bill_still_owes_comes_off_the_allocations() -> None:
    """It is a fact about the money received, stored nowhere."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", "1000")
    books.settle(invoice, "400")

    ageing = books.ageing()

    assert len(ageing) == 1
    assert ageing[0].total_outstanding == Decimal("600.00")
    assert ageing[0].invoices[0].invoice_number == "SI-1"


def test_a_reversed_settlement_cleared_nothing() -> None:
    """Counting it would report a bill as paid the firm has no money for."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", "1000")
    books.settle(invoice, "400", status="REVERSED")

    assert books.ageing()[0].total_outstanding == Decimal("1000.00")


def test_a_fully_paid_bill_leaves_the_ageing() -> None:
    """An ageing is what is still owed, not a list of everything sold."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", "1000")
    books.settle(invoice, "1000")

    assert books.ageing() == []


def test_a_draft_or_cancelled_invoice_is_not_a_debt() -> None:
    """A draft is not a sale and a cancelled one has been undone."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", "1000", status="DRAFT")
    books.invoice("SI-2", "1000", status="CANCELLED")

    assert books.ageing() == []


def test_the_buckets_add_up_to_the_total() -> None:
    """A set of buckets that does not is one nobody can reconcile."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", "100", on=date(2026, 5, 28), due=date(2026, 5, 28))
    books.invoice("SI-2", "200", on=date(2026, 4, 25), due=date(2026, 4, 25))
    books.invoice("SI-3", "400", on=date(2026, 3, 25), due=date(2026, 3, 25))
    books.invoice("SI-4", "800", on=date(2026, 1, 1), due=date(2026, 1, 1))

    row = books.ageing(as_of=date(2026, 6, 1))[0]

    assert row.total_outstanding == Decimal("1500.00")
    assert sum(bucket.amount for bucket in row.buckets) == Decimal("1500.00")
    # 4 days, 37 days, 68 days and 151 days overdue -- one per band, and the
    # last band is open-ended.
    assert [str(bucket.amount) for bucket in row.buckets] == [
        "100.00",
        "200.00",
        "400.00",
        "800.00",
    ]
    assert row.buckets[-1].to_days is None


def test_a_bill_with_no_terms_is_due_when_it_is_raised() -> None:
    """Rather than never becoming overdue at all."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", "500", on=date(2026, 4, 1), due=None)

    row = books.ageing(as_of=date(2026, 5, 1))[0]

    assert row.invoices[0].due_date == date(2026, 4, 1)
    assert row.invoices[0].days_overdue == 30


def test_a_bill_not_yet_due_ages_at_zero_days() -> None:
    """Owed, but not late. It still belongs in the total."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", "500", on=date(2026, 4, 1), due=date(2026, 7, 1))

    row = books.ageing(as_of=date(2026, 6, 1))[0]

    assert row.invoices[0].days_overdue == 0
    assert row.total_outstanding == Decimal("500.00")


def test_an_advance_is_reported_beside_the_balance_not_inside_it() -> None:
    """Netting them hides money the customer is entitled to have applied."""
    books = _Books(_session_factory()())
    books.customer.unapplied_advance_balance = Decimal("750.00")
    books.session.commit()
    books.movement("INVOICE", "1000", date(2026, 4, 10))

    answer = books.statement()

    assert answer.closing_balance == Decimal("1000.00")
    assert answer.unapplied_advance == Decimal("750.00")


def test_the_ageing_row_reconciles_with_the_account() -> None:
    """The bills and the account are not the same number, and the row says so.

    A credit note or a sales return reduces the account and sits on no
    invoice, so an ageing that reported only the bills would disagree with the
    customer's own balance by that much, with nothing to explain the gap.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", "1000")
    # The account carries the bill less a credit nobody has set against it.
    books.customer.current_outstanding = Decimal("700.00")
    books.session.commit()

    row = books.ageing()[0]

    assert row.total_outstanding == Decimal("1000.00")
    assert row.account_balance == Decimal("700.00")
    assert row.unapplied_credits == Decimal("300.00")
    assert row.charges_not_billed == Decimal("0")
    # The identity the two figures are joined by.
    assert (
        row.total_outstanding - row.unapplied_credits + row.charges_not_billed
        == row.account_balance
    )


def test_a_charge_that_no_bill_carries_is_named_too() -> None:
    """Tax collected at source raises the account without being invoiced."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", "1000")
    books.customer.current_outstanding = Decimal("1100.00")
    books.session.commit()

    row = books.ageing()[0]

    assert row.unapplied_credits == Decimal("0")
    assert row.charges_not_billed == Decimal("100.00")
