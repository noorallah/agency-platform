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
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.finance.models import (
    AccountingPeriod,
    FirmControlAccount,
    GLPosting,
    JournalEntry,
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

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

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


def test_a_receipt_whose_advance_was_applied_reverses_in_full() -> None:
    """A bounced cheque is taken back even after its advance was applied.

    D-SELL-8: applying an advance writes an `ADVANCE_APPLY` row beside the
    receipt's own, and the reversal took "the" row with `scalar()`. Undoing the
    receipt alone put back an advance the applications had already spent and
    was refused as overtaken; undoing an application alone left the customer's
    balance out of step with 1100 by the receipt. Every row goes back.
    """
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    first = books.sales_invoice("SI-1", "300.00")
    # 500 against 300 owed: 300 off the balance, 200 held as advance.
    settlement = _receipt(
        books,
        "500.00",
        [SettlementAllocationWrite(invoice_id=first.id, amount=Decimal("300.00"))],
    )
    books.session.commit()
    books.owe_us("200.00")
    service = ReceiptService(books.session)
    # The advance goes to two later bills, so the receipt carries two
    # applications beside its own row.
    for number, part in (("SI-2", "120.00"), ("SI-3", "80.00")):
        service.allocate(
            settlement.id,
            invoice_id=books.sales_invoice(number, part).id,
            amount=Decimal(part),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("0.00")
    assert books.customer.unapplied_advance_balance == Decimal("0.00")

    service.reverse(
        settlement.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Cheque bounced",
    )
    books.session.commit()

    books.session.refresh(books.customer)
    # Everything the 500 cleared is owed again, and no advance is left over.
    assert books.customer.current_outstanding == Decimal("500.00")
    assert books.customer.unapplied_advance_balance == Decimal("0.00")
    rows = books.session.scalars(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.customer_id == books.customer.id
        )
    ).all()
    # The customer's own ledger agrees with the balance it carries.
    assert sum(row.outstanding_delta for row in rows) == Decimal("500.00")
    assert sum(row.advance_delta for row in rows) == Decimal("0.00")
    assert [
        row.transaction_type for row in rows if row.reference_type == "reversal"
    ].count("REVERSAL") == 3, "the receipt and both applications are undone"


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


def test_a_receipt_steps_over_a_number_a_journal_already_holds() -> None:
    """D-FIN-9: a taken number failed the receipt, and every retry got it again.

    Driven on a fixture firm: a hand journal typed RC-2026-2027-000002 made
    the next three POST /receipts fail "A journal entry with this reference
    number already exists." -- the failure rolled the reservation back, so each
    retry was issued the same number. The number is now stepped over.
    """
    from app.finance.models import JournalType, VoucherType
    from app.finance.services.journal_engine import (
        JournalEntryEngine,
        JournalLineData,
    )

    books = _Books(_session_factory()())
    first = _receipt(books, "10.00")
    books.session.commit()
    stem, sequence = first.settlement_number.rsplit("-", 1)
    width = len(sequence)
    taken = f"{stem}-{int(sequence) + 1:0{width}d}"

    # A journal that already holds the next number -- written before hand
    # journals were kept to JV-, as a store may hold one.
    session = books.session
    period = session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.firm_id == books.firm.id,
            AccountingPeriod.starts_on <= WHEN,
            AccountingPeriod.ends_on >= WHEN,
        )
    )
    assert period is not None
    engine = JournalEntryEngine(session)
    engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=session.scalars(select(JournalType.id)).first(),  # type: ignore[arg-type]
        voucher_type_id=session.scalars(select(VoucherType.id)).first(),  # type: ignore[arg-type]
        accounting_period_id=period.id,
        journal_date=WHEN,
        reference_number=taken,
        description="Typed by hand with a receipt's number",
        lines=[
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.CASH),
                debit_amount=Decimal("1.00"),
            ),
            JournalLineData(
                ledger_account_id=books.account(
                    ControlAccountPurpose.OPENING_BALANCE_EQUITY
                ),
                credit_amount=Decimal("1.00"),
            ),
        ],
        actor_id=books.actor_id,
    )
    session.commit()

    second = _receipt(books, "20.00")
    session.commit()

    assert second.settlement_number == f"{stem}-{int(sequence) + 2:0{width}d}"
    assert second.status == "POSTED"


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


@pytest.mark.parametrize(
    ("transaction_type", "destination"),
    [
        (CustomerReceivableTransactionType.INVOICE, "/api/v1/sales-invoices"),
        (CustomerReceivableTransactionType.TCS, "/api/v1/receipts"),
        (CustomerReceivableTransactionType.LOYALTY, "/api/v1/loyalty/redeem"),
        (
            CustomerReceivableTransactionType.ADVANCE_APPLY,
            "/api/v1/receipts/{receipt_id}/allocate",
        ),
        (CustomerReceivableTransactionType.REFUND, "/api/v1/refunds"),
    ],
)
def test_the_receivable_endpoint_refuses_what_another_module_records(
    transaction_type: CustomerReceivableTransactionType, destination: str
) -> None:
    """D-FIN-4: five more types moved a customer's balance with no journal.

    Driven on a fixture firm: an INVOICE of 25.00, a TCS of 1.00, a LOYALTY of
    5.00 and a REFUND of 10.00 each moved the customer's balance and left the
    journal count where it was. Each has a module that records it together
    with its journal, and the refusal names it.
    """
    from app.customers.api.router import post_customer_receivable_transaction

    books = _Books(_session_factory()())
    books.owe_us("300.00")
    _receipt(books, "500.00")
    books.session.commit()
    books.session.refresh(books.customer)
    outstanding = books.customer.current_outstanding
    advance = books.customer.unapplied_advance_balance
    journals = books.session.scalar(select(func.count()).select_from(JournalEntry))
    scope = SimpleNamespace(firm_id=books.firm.id, actor_id=books.actor_id)

    with pytest.raises(ValidationError) as error:
        post_customer_receivable_transaction(
            books.customer.id,
            CustomerReceivableTransactionCreate(
                transaction_type=transaction_type,
                amount=Decimal("10.00"),
                transaction_date=WHEN,
            ),
            scope,  # type: ignore[arg-type]
            db=books.session,
        )
    books.session.rollback()

    assert destination in str(error.value)
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == outstanding
    assert books.customer.unapplied_advance_balance == advance
    assert (
        books.session.scalar(select(func.count()).select_from(JournalEntry)) == journals
    )


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


def test_reversing_a_refund_puts_the_advance_back() -> None:
    """The refund's own defect, and the reason its endpoint could not just be added.

    `reverse` put the customer's balances back only for a receipt, while
    `create` posts a receivable transaction for a **refund** as well -- handing
    an advance back is what a refund is. Nothing exposed it, because the router
    had no reverse route for refunds at all; the desktop offered the button
    anyway and got a 405. Wiring the route without this would have mirrored the
    journal and left the customer's advance short by the whole refund.
    """
    books = _Books(_session_factory()())
    books.owe_us("300.00")
    _receipt(books, "500.00")
    books.session.commit()

    service = RefundService(books.session)
    refund = service.create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("200.00"),
            method=SettlementMethodEnum.BANK,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("0.00")

    reversed_row = service.reverse(
        refund.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Paid the wrong account",
    )
    books.session.commit()

    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal(
        "200.00"
    ), "the advance the refund handed back is held again"
    assert books.customer.current_outstanding == Decimal("0.00")
    assert reversed_row.status == "REVERSED"

    mirror = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == reversed_row.reversal_journal_entry_id)
    ).all()
    postings = {code: (debit, credit) for code, debit, credit in mirror}
    assert postings["1100"] == (
        Decimal("0.00"),
        Decimal("200.00"),
    ), "the customer is owed the advance again"
    assert postings["1010"] == (
        Decimal("200.00"),
        Decimal("0.00"),
    ), "the bank has the money back"


def test_the_party_picker_names_who_is_paying_and_nothing_else() -> None:
    """A cashier can name the customer without reading the customer master.

    `CASHIER` holds `RECEIPT_CREATE`, `RECEIPT_VIEW`, `PAYMENT_CREATE` and
    `PAYMENT_VIEW`, and **not** `CUSTOMER_VIEW`. The Receipts screen reached
    for `GET /api/v1/customers` to fill its party picker, so recording a
    receipt was gated on a code the role recording it does not hold: the
    refusal arrived at the party lookup, before the receipt anybody was
    authorised for had been attempted.

    Found at plan step 22.4 on 2026-09-15, driving the screen as a cashier.
    The row asserted this works, having been written from the permission table
    rather than from a sign-in.

    The alternative was granting `CUSTOMER_VIEW` to `CASHIER`, which widens a
    counter role to credit limits, balances and addresses to fix a name
    lookup. This is the answer `GET /api/v1/firm-members` already gave to the
    same shape of problem.
    """
    books = _Books(_session_factory()())
    books.session.commit()

    parties = ReceiptService(books.session).parties(firm_id=books.firm.id)

    assert [row[0] for row in parties] == [books.customer.id]
    # Three fields. Anything more and this is the customer master again.
    assert parties[0] == (books.customer.id, books.customer.code, books.customer.name)


def test_the_party_picker_is_searchable_and_scoped_to_the_firm() -> None:
    """Somebody else's customers are not offered, and the search narrows."""
    books = _Books(_session_factory()())
    books.session.commit()
    service = ReceiptService(books.session)

    assert service.parties(firm_id=books.firm.id, search=books.customer.code)
    assert service.parties(firm_id=books.firm.id, search="nothing-matches") == []
    assert service.parties(firm_id=uuid4()) == []


def test_every_party_is_reachable_a_page_at_a_time() -> None:
    """D-SELL-18: the picker stopped at the first 200 customers by code.

    A firm with more could not take money from the rest from the desktop.
    The list is paged now, and the last customer is on the last page.
    """
    books = _Books(_session_factory()())
    books.session.add_all(
        Customer(
            firm_id=books.firm.id,
            code=f"Z{index:03d}",
            customer_type="BUSINESS",
            name=f"Customer Z{index:03d}",
            display_name=f"Customer Z{index:03d}",
            currency_code="INR",
            status="ACTIVE",
        )
        for index in range(205)
    )
    books.session.commit()
    service = ReceiptService(books.session)

    pages = [
        service.parties(firm_id=books.firm.id, page=page, page_size=100)
        for page in (1, 2, 3)
    ]

    assert [len(page) for page in pages] == [100, 100, 6]
    assert pages[2][-1][1] == "Z204"
    codes = [row[1] for page in pages for row in page]
    assert len(set(codes)) == 206


def test_goods_returned_against_a_bill_come_off_what_it_owes() -> None:
    """D-BUY-6, decided by the owner on 2026-09-18.

    A completed return posts Dr payable, but the bill kept its full outstanding,
    so a payment could settle the returned goods again (driven on TEST01:
    PI-2026-2027-000005 showed 708.00 after a 236.00 return against it). Only a
    completed return raised from the bill's own lines counts; one raised from a
    goods receipt, or one cancelled, leaves the bill alone.
    """
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-RET", "708.00")

    def _return(number: str, status: str, source_type: str, net: str) -> None:
        row = PurchaseReturn(
            firm_id=books.firm.id,
            vendor_id=books.vendor.id,
            branch_id=books.branch_id,
            warehouse_id=uuid4(),
            return_number=number,
            return_date=WHEN,
            status=status,
            created_by=books.actor_id,
            updated_by=books.actor_id,
        )
        books.session.add(row)
        books.session.flush()
        books.session.add(
            PurchaseReturnLine(
                purchase_return_id=row.id,
                firm_id=books.firm.id,
                line_number=1,
                source_document_type=source_type,
                source_document_id=bill.id,
                source_document_number=bill.invoice_number,
                source_document_line_id=uuid4(),
                source_document_line_number=1,
                product_id=uuid4(),
                received_quantity=Decimal("6"),
                already_returned_quantity=Decimal("0"),
                current_return_quantity=Decimal("2"),
                net_amount=Decimal(net),
                created_by=books.actor_id,
                updated_by=books.actor_id,
            )
        )
        books.session.commit()

    _return("PR-1", "COMPLETED", "PURCHASE_INVOICE", "236.00")
    _return("PR-2", "CANCELLED", "PURCHASE_INVOICE", "100.00")
    _return("PR-3", "APPROVED", "PURCHASE_INVOICE", "50.00")

    payments = PaymentService(books.session)
    owed = {
        record.invoice_id: record.outstanding_amount
        for record in payments.outstanding_invoices(
            firm_id=books.firm.id, party_id=books.vendor.id
        )
    }
    assert owed[bill.id] == Decimal("472.00")

    with pytest.raises(ValidationError, match="472.00 outstanding"):
        payments.create(
            SettlementCreate(
                party_id=books.vendor.id,
                settlement_date=WHEN,
                amount=Decimal("708.00"),
                method=SettlementMethodEnum.BANK,
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=bill.id, amount=Decimal("708.00")
                    )
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_returns_and_credit_notes_against_a_bill_come_off_what_it_owes() -> None:
    """D-SELL-10, the sales twin of D-BUY-6.

    A completed sales return and an approved credit note both post Cr
    receivable, but Record Receipt kept offering the bill's full remainder, so
    a receipt could collect the returned or credited money again (driven on
    fixture store `fx_t091908qh_s`: SI-2026-2027-000002 offered at 576.49
    after SR-2026-2027-000001 of 193.28 and CN-2026-2027-000001 of 59.00
    against it). A return raised from a delivery note, and a cancelled or
    unfinished return or credit note, leave the bill alone.
    """
    from app.credit_note.models import CreditNote
    from app.sales_return.models import SalesReturn, SalesReturnLine

    books = _Books(_session_factory()())
    books.owe_us("1000.00")
    bill = books.sales_invoice("SI-RET", "1000.00")

    def _return(number: str, status: str, source_type: str, net: str) -> None:
        row = SalesReturn(
            firm_id=books.firm.id,
            customer_id=books.customer.id,
            branch_id=books.branch_id,
            warehouse_id=uuid4(),
            return_number=number,
            return_date=WHEN,
            status=status,
            created_by=books.actor_id,
            updated_by=books.actor_id,
        )
        books.session.add(row)
        books.session.flush()
        books.session.add(
            SalesReturnLine(
                sales_return_id=row.id,
                firm_id=books.firm.id,
                line_number=1,
                source_document_type=source_type,
                source_document_id=bill.id,
                source_document_number=bill.invoice_number,
                source_document_line_id=uuid4(),
                source_document_line_number=1,
                product_id=uuid4(),
                current_return_quantity=Decimal("2"),
                net_amount=Decimal(net),
                created_by=books.actor_id,
                updated_by=books.actor_id,
            )
        )
        books.session.commit()

    def _credit_note(number: str, status: str, total: str) -> None:
        books.session.add(
            CreditNote(
                firm_id=books.firm.id,
                customer_id=books.customer.id,
                branch_id=books.branch_id,
                sales_invoice_id=bill.id,
                credit_note_number=number,
                credit_note_date=WHEN,
                status=status,
                total_amount=Decimal(total),
                created_by=books.actor_id,
                updated_by=books.actor_id,
            )
        )
        books.session.commit()

    _return("SR-1", "COMPLETED", "SALES_INVOICE", "193.28")
    _return("SR-2", "CANCELLED", "SALES_INVOICE", "100.00")
    _return("SR-3", "APPROVED", "SALES_INVOICE", "50.00")
    # Raised from the delivery note: a credit on the account, not on this bill.
    _return("SR-4", "COMPLETED", "DELIVERY_NOTE", "40.00")
    _credit_note("CN-1", "APPROVED", "59.00")
    _credit_note("CN-2", "CANCELLED", "30.00")
    _credit_note("CN-3", "DRAFT", "20.00")

    receipts = ReceiptService(books.session)
    owed = {
        record.invoice_id: record.outstanding_amount
        for record in receipts.outstanding_invoices(
            firm_id=books.firm.id, party_id=books.customer.id
        )
    }
    assert owed[bill.id] == Decimal("747.72")

    with pytest.raises(ValidationError, match="747.72 outstanding"):
        _receipt(
            books,
            "1000.00",
            [SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal("1000.00"))],
        )
