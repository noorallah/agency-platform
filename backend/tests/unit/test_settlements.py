"""Receipts from customers and payments to vendors.

The gap these close: nothing in the product could record money arriving. Two
years of seeded trading left Cash at 0.00 while Trade Receivables grew to
249,236.70, because invoices were the only document that reached the ledger.

The one path that did exist was worse than none.
`CustomerService.post_receivable_transaction` accepts a RECEIPT, moves the
customer's outstanding balance and writes no journal, so every use of it put
the subsidiary ledger and the general ledger further apart. The tests here are
mostly about the two staying together.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.finance.models import (
    AccountingPeriod,
    FirmControlAccount,
    GLPosting,
    LedgerAccount,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.general_ledger_service import GeneralLedgerService
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService, RefundService
from app.vendors.models import Vendor

# Every test posts inside the seeded 2026-2027 financial year.
WHEN = date(2026, 4, 20)


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
    """A firm with a chart of accounts, a customer, a vendor and invoices."""

    def __init__(self, session: Session) -> None:
        """Seed everything a settlement needs to exist."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Acme Firm",
            code="ACME",
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
            code="C1",
            customer_type="BUSINESS",
            name="Customer One",
            display_name="Customer One",
            currency_code="INR",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.vendor = Vendor(
            firm_id=self.firm.id,
            code="V1",
            name="Vendor One",
            display_name="Vendor One",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        session.add_all([self.customer, self.vendor])
        session.commit()

    def sales_invoice(self, number: str, total: str, when: date = WHEN) -> SalesInvoice:
        """Add one approved sales invoice the customer owes."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch_id,
            invoice_number=number,
            invoice_date=when,
            status="APPROVED",
            grand_total=Decimal(total),
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def purchase_invoice(self, number: str, total: str) -> PurchaseInvoice:
        """Add one approved purchase invoice the firm owes."""
        row = PurchaseInvoice(
            firm_id=self.firm.id,
            vendor_id=self.vendor.id,
            branch_id=self.branch_id,
            invoice_number=number,
            invoice_date=WHEN,
            supplier_invoice_number=f"S-{number}",
            supplier_invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal(total),
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def owe_us(self, amount: str) -> None:
        """Put an amount on the customer's account the way an invoice does."""
        CustomerService(self.session).post_receivable_transaction(
            self.customer.id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.INVOICE,
                amount=Decimal(amount),
                transaction_date=WHEN,
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def account(self, purpose: ControlAccountPurpose) -> UUID:
        """Return the account one purpose is mapped to."""
        return ControlAccountService(self.session).resolve(self.firm.id, purpose)

    def postings(self, settlement: Settlement) -> dict[str, tuple[Decimal, Decimal]]:
        """Return debit and credit by account code for a settlement's journal."""
        rows = self.session.execute(
            select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
            .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
            .where(GLPosting.journal_entry_id == settlement.journal_entry_id)
        ).all()
        return {code: (debit, credit) for code, debit, credit in rows}


def _receipt(
    books: _Books,
    amount: str,
    allocations: list[SettlementAllocationWrite] | None = None,
    method: SettlementMethodEnum = SettlementMethodEnum.CASH,
) -> Settlement:
    """Record one receipt from the seeded customer."""
    return ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=method,
            allocations=allocations or [],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


def test_a_receipt_reaches_the_ledger_and_the_customer_balance() -> None:
    """Money arriving moves both books, or it is not recorded at all.

    This is the whole point of the module. `post_receivable_transaction` on its
    own moves the customer and leaves the ledger, which is how a subsidiary
    ledger and a general ledger drift apart without anybody noticing.
    """
    books = _Books(_session_factory()())
    books.owe_us("1000.00")

    settlement = _receipt(books, "400.00")
    books.session.commit()

    postings = books.postings(settlement)
    assert postings["1000"] == (Decimal("400.00"), Decimal("0.00")), "cash debited"
    assert postings["1100"] == (
        Decimal("0.00"),
        Decimal("400.00"),
    ), "receivable credited"

    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("600.00")
    assert settlement.journal_entry_id is not None
    assert settlement.settlement_number.startswith("RC")


def test_a_receipt_leaves_the_trial_balance_balanced() -> None:
    """The books still balance after money moves.

    Two legs and no arithmetic to get wrong is the intent; this is the proof,
    and it is the assertion that would fail if the posting ever grew a third
    leg someone forgot to balance.
    """
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    _receipt(books, "400.00")
    books.session.commit()

    april = books.session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.firm_id == books.firm.id,
            AccountingPeriod.starts_on == date(2026, 4, 1),
        )
    )
    assert april is not None
    report = GeneralLedgerService(books.session).trial_balance(
        firm_id=books.firm.id, accounting_period_id=april.id
    )
    assert report.is_balanced


def test_an_allocation_cannot_exceed_what_the_invoice_still_owes() -> None:
    """Over-clearing an invoice is money recorded against nothing."""
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    invoice = books.sales_invoice("SI-1", "300.00")

    with pytest.raises(ValidationError) as error:
        _receipt(
            books,
            "400.00",
            [
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("400.00")
                )
            ],
        )

    assert "SI-1" in str(error.value)
    assert "300.00" in str(error.value)


def test_allocations_cannot_exceed_the_money_that_arrived() -> None:
    """Two invoices cannot be cleared with one invoice's worth of cash."""
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    first = books.sales_invoice("SI-1", "300.00")
    second = books.sales_invoice("SI-2", "300.00")

    with pytest.raises(ValidationError) as error:
        _receipt(
            books,
            "400.00",
            [
                SettlementAllocationWrite(
                    invoice_id=first.id, amount=Decimal("300.00")
                ),
                SettlementAllocationWrite(
                    invoice_id=second.id, amount=Decimal("300.00")
                ),
            ],
        )

    assert "more than the" in str(error.value)


def test_an_invoice_belonging_to_somebody_else_is_refused() -> None:
    """A receipt clears the invoices of the customer who sent it, and no others."""
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    other = Customer(
        firm_id=books.firm.id,
        code="C2",
        customer_type="BUSINESS",
        name="Customer Two",
        display_name="Customer Two",
        currency_code="INR",
        status="ACTIVE",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(other)
    books.session.commit()
    theirs = SalesInvoice(
        firm_id=books.firm.id,
        customer_id=other.id,
        branch_id=books.branch_id,
        invoice_number="SI-OTHER",
        invoice_date=WHEN,
        status="APPROVED",
        grand_total=Decimal("500.00"),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(theirs)
    books.session.commit()

    with pytest.raises(ValidationError) as error:
        _receipt(
            books,
            "100.00",
            [SettlementAllocationWrite(invoice_id=theirs.id, amount=Decimal("100.00"))],
        )

    assert "does not belong to this party" in str(error.value)


def test_what_an_invoice_still_owes_comes_down_as_it_is_settled() -> None:
    """Outstanding is derived from the allocations, so it cannot drift.

    A paid-to-date column on the invoice would be a second copy of the same
    facts, and the copy is wrong the first time anything writes one without
    going through this service.
    """
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    invoice = books.sales_invoice("SI-1", "500.00")
    service = ReceiptService(books.session)

    _receipt(
        books,
        "200.00",
        [SettlementAllocationWrite(invoice_id=invoice.id, amount=Decimal("200.00"))],
    )
    books.session.commit()

    remaining = service.outstanding_invoices(
        firm_id=books.firm.id, party_id=books.customer.id
    )
    assert [row.outstanding_amount for row in remaining] == [Decimal("300.00")]

    _receipt(
        books,
        "300.00",
        [SettlementAllocationWrite(invoice_id=invoice.id, amount=Decimal("300.00"))],
    )
    books.session.commit()

    assert (
        service.outstanding_invoices(firm_id=books.firm.id, party_id=books.customer.id)
        == []
    ), "a fully settled invoice is not offered again"


def test_a_payment_posts_the_other_way_round() -> None:
    """Money out debits the payable and credits the account it left."""
    books = _Books(_session_factory()())
    invoice = books.purchase_invoice("PI-1", "700.00")

    settlement = PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal("700.00"),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("700.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    postings = books.postings(settlement)
    assert postings["2100"] == (Decimal("700.00"), Decimal("0.00")), "payable debited"
    assert postings["1010"] == (Decimal("0.00"), Decimal("700.00")), "bank credited"
    assert settlement.settlement_number.startswith("PY")
    assert settlement.allocated_amount == Decimal("700.00")
    assert settlement.unallocated_amount == Decimal("0.00")


def test_money_not_tied_to_an_invoice_is_recorded_as_such() -> None:
    """A customer paying ahead is normal, and the remainder is visible.

    `unallocated_amount` is money the firm holds against no particular invoice.
    It still reaches the ledger and still reduces what the customer owes in
    total -- what it does not do is claim to have settled a document.
    """
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    invoice = books.sales_invoice("SI-1", "300.00")

    settlement = _receipt(
        books,
        "500.00",
        [SettlementAllocationWrite(invoice_id=invoice.id, amount=Decimal("300.00"))],
    )
    books.session.commit()

    assert settlement.allocated_amount == Decimal("300.00")
    assert settlement.unallocated_amount == Decimal("200.00")
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("500.00"), (
        "the whole 500 reduces the balance; only its attribution to a document "
        "is partial"
    )


def test_a_settlement_with_nowhere_to_post_is_refused_entirely() -> None:
    """No cash account mapped means no receipt, not a receipt with no journal.

    Posting fails the operation it belongs to. A settlement row with no journal
    behind it is exactly the state this module exists to make impossible.
    """
    session = _session_factory()()
    books = _Books(session)
    mapping = ControlAccountService(session)
    cash = mapping.resolve(books.firm.id, ControlAccountPurpose.CASH)
    row = session.scalar(
        select(FirmControlAccount).where(
            FirmControlAccount.firm_id == books.firm.id,
            FirmControlAccount.ledger_account_id == cash,
        )
    )
    assert row is not None
    row.is_deleted = True
    session.commit()

    with pytest.raises(ValidationError) as error:
        _receipt(books, "100.00")
    session.rollback()

    assert "CASH" in str(error.value)
    assert session.scalars(select(Settlement)).all() == []


def test_a_receipt_for_an_unknown_customer_is_refused() -> None:
    """The party is checked before anything is written."""
    books = _Books(_session_factory()())

    with pytest.raises(ResourceNotFoundError):
        ReceiptService(books.session).create(
            SettlementCreate(
                party_id=uuid4(),
                settlement_date=WHEN,
                amount=Decimal("100.00"),
                method=SettlementMethodEnum.CASH,
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_one_invoice_cannot_appear_twice_in_one_settlement() -> None:
    """Two lines against one invoice are one allocation.

    Accepting both would make the invoice's outstanding depend on how somebody
    typed it, and the unique constraint refuses it anyway.
    """
    invoice_id = uuid4()
    with pytest.raises(ValueError, match="only once"):
        SettlementCreate(
            party_id=uuid4(),
            settlement_date=WHEN,
            amount=Decimal("100.00"),
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice_id, amount=Decimal("50.00")
                ),
                SettlementAllocationWrite(
                    invoice_id=invoice_id, amount=Decimal("50.00")
                ),
            ],
        )


def test_reversing_a_receipt_puts_both_books_back() -> None:
    """The undo is exact because it reads the deltas the receipt recorded.

    A receipt of 500 against an outstanding 300 becomes 300 off the balance and
    200 of advance. Recomputing that from the current balance at reversal time
    would put back something else entirely, which is why settlements shipped
    without a reversal until the receivable service could do it properly.
    """
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    settlement = _receipt(books, "500.00")
    books.session.commit()

    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("0.00")
    assert books.customer.unapplied_advance_balance == Decimal("200.00")

    service = ReceiptService(books.session)
    reversed_row = service.reverse(
        settlement.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Keyed against the wrong customer",
    )
    books.session.commit()

    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("300.00"), "balance restored"
    assert books.customer.unapplied_advance_balance == Decimal("0.00")
    assert reversed_row.status == "REVERSED"
    assert reversed_row.reversal_journal_entry_id is not None
    assert reversed_row.reversal_reason == "Keyed against the wrong customer"

    # The mirror journal cancels the original rather than deleting it: both
    # entries stay in the ledger.
    mirror = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == reversed_row.reversal_journal_entry_id)
    ).all()
    postings = {code: (debit, credit) for code, debit, credit in mirror}
    assert postings["1000"] == (
        Decimal("0.00"),
        Decimal("500.00"),
    ), "cash credited back"
    assert postings["1100"] == (
        Decimal("500.00"),
        Decimal("0.00"),
    ), "receivable restored"


def test_a_reversed_receipt_stops_clearing_its_invoice() -> None:
    """The invoice it settled is owed again, and the record of it stays.

    The allocation rows are not deleted: the reversed receipt still shows what
    it had been applied to, which is the first thing anybody asks when a
    correction is queried.
    """
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    invoice = books.sales_invoice("SI-1", "500.00")
    service = ReceiptService(books.session)

    settlement = _receipt(
        books,
        "500.00",
        [SettlementAllocationWrite(invoice_id=invoice.id, amount=Decimal("500.00"))],
    )
    books.session.commit()
    assert (
        service.outstanding_invoices(firm_id=books.firm.id, party_id=books.customer.id)
        == []
    )

    service.reverse(settlement.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    remaining = service.outstanding_invoices(
        firm_id=books.firm.id, party_id=books.customer.id
    )
    assert [row.outstanding_amount for row in remaining] == [Decimal("500.00")]
    assert len(service.allocations_for(settlement.id)) == 1, "the record stays"


def test_a_settlement_cannot_be_reversed_twice() -> None:
    """The second attempt is refused rather than doubling the undo."""
    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    settlement = _receipt(books, "100.00")
    books.session.commit()
    service = ReceiptService(books.session)
    service.reverse(settlement.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    with pytest.raises(ValidationError, match="already been reversed"):
        service.reverse(settlement.id, firm_id=books.firm.id, actor_id=books.actor_id)


def test_a_reversal_overtaken_by_later_trading_is_refused() -> None:
    """An undo that would leave a balance below nothing is refused.

    The customer overpaid, the excess was refunded, and only then does somebody
    try to reverse the original receipt -- putting back 200 of advance that has
    already been paid out. Silently clamping at zero would invent a balance
    nobody can explain, so the message says the reversal has been overtaken.
    """
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    settlement = _receipt(books, "500.00")
    books.session.commit()
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("200.00")

    # The overpayment is refunded, so the advance this receipt created is gone.
    CustomerService(books.session).post_receivable_transaction(
        books.customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=CustomerReceivableTransactionType.REFUND,
            amount=Decimal("200.00"),
            transaction_date=WHEN,
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="overtaken"):
        ReceiptService(books.session).reverse(
            settlement.id, firm_id=books.firm.id, actor_id=books.actor_id
        )


def test_a_payment_reverses_without_touching_a_party_balance() -> None:
    """Vendors carry no denormalised balance, so there is none to put back."""
    books = _Books(_session_factory()())
    invoice = books.purchase_invoice("PI-1", "700.00")
    service = PaymentService(books.session)
    settlement = service.create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal("700.00"),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("700.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    service.reverse(settlement.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    assert settlement.status == "REVERSED"
    owed = service.outstanding_invoices(firm_id=books.firm.id, party_id=books.vendor.id)
    assert [row.outstanding_amount for row in owed] == [Decimal("700.00")]


def test_recording_a_receipt_the_old_way_is_refused() -> None:
    """The endpoint that moved a balance without a journal now says so.

    `post_receivable_transaction` is still used by the sales invoice and
    settlement services as part of a larger unit of work that does post. What
    was left open was the endpoint, reachable by hand: every receipt recorded
    through it put the subsidiary ledger and the general ledger further apart,
    silently and permanently.
    """
    from app.customers.api.router import post_customer_receivable_transaction

    books = _Books(_session_factory()())
    scope = SimpleNamespace(firm_id=books.firm.id, actor_id=books.actor_id)

    with pytest.raises(ValidationError) as error:
        post_customer_receivable_transaction(
            books.customer.id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.RECEIPT,
                amount=Decimal("100.00"),
                transaction_date=WHEN,
            ),
            scope,  # type: ignore[arg-type]
            db=books.session,
        )

    assert "/api/v1/receipts" in str(error.value)
    assert "only moves the customer balance" in str(error.value)


def test_a_credit_note_still_goes_through_the_receivable_endpoint() -> None:
    """It moves no money, so it has no journal to be missing.

    Refusing everything would take away the ways a balance is legitimately
    adjusted without cash changing hands.
    """
    from app.customers.api.router import post_customer_receivable_transaction

    books = _Books(_session_factory()())
    books.owe_us("500.00")
    scope = SimpleNamespace(firm_id=books.firm.id, actor_id=books.actor_id)

    response = post_customer_receivable_transaction(
        books.customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
            amount=Decimal("100.00"),
            transaction_date=WHEN,
        ),
        scope,  # type: ignore[arg-type]
        db=books.session,
    )

    assert response.data.transaction_type == "CREDIT_NOTE"
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("400.00")


def test_a_refund_hands_money_back_and_posts_it() -> None:
    """The mirror of a receipt, and the hole the receivable endpoint left.

    A refund is money out like a payment and about a customer like a receipt,
    so it was neither and could not be recorded -- which left the old
    receivable endpoint accepting one that moved the advance and wrote no
    journal.
    """
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    _receipt(books, "500.00")
    books.session.commit()
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("200.00")

    settlement = RefundService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("200.00"),
            method=SettlementMethodEnum.BANK,
            narration="Overpayment returned",
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    postings = books.postings(settlement)
    assert postings["1100"] == (
        Decimal("200.00"),
        Decimal("0.00"),
    ), "the customer is no longer owed the advance"
    assert postings["1010"] == (Decimal("0.00"), Decimal("200.00")), "the bank paid it"
    assert settlement.settlement_number.startswith("RF")

    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("0.00")


def test_a_refund_larger_than_the_advance_is_refused() -> None:
    """A firm cannot hand back money a customer never left with it."""
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    _receipt(books, "300.00")
    books.session.commit()

    with pytest.raises(ValidationError, match="exceeds unapplied advance"):
        RefundService(books.session).create(
            SettlementCreate(
                party_id=books.customer.id,
                settlement_date=WHEN,
                amount=Decimal("50.00"),
                method=SettlementMethodEnum.CASH,
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_refund_is_not_applied_to_an_invoice() -> None:
    """It returns money held on account, which is the opposite of settling."""
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    invoice = books.sales_invoice("SI-1", "300.00")
    _receipt(books, "500.00")
    books.session.commit()

    with pytest.raises(ValidationError, match="not applied to an invoice"):
        RefundService(books.session).create(
            SettlementCreate(
                party_id=books.customer.id,
                settlement_date=WHEN,
                amount=Decimal("100.00"),
                method=SettlementMethodEnum.CASH,
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=invoice.id, amount=Decimal("100.00")
                    )
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
