"""What customers owed the firm on day one, bill by bill (backlog 36).

The receivable mirror of `test_vendor_opening_bills.py`. A customer's day-one
debt entered bill by bill has to be a bill Record Receipt offers, a receipt
clears and the ageing puts in the right bucket -- and it has to move the
customer's running balance, which a supplier does not have -- without being a
sales invoice, which the GST returns and sales registers would read as trading.
And it is one figure on the master or bills, never both.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import (
    Customer,
    CustomerOpeningBill,
    CustomerReceivableTransaction,
)
from app.customers.schemas.customer import CustomerUpdate
from app.customers.schemas.opening_bill import (
    CustomerOpeningBillImportRow,
    CustomerOpeningBillWrite,
)
from app.customers.services import CustomerService, CustomerStatementService
from app.customers.services.opening_bill_service import CustomerOpeningBillService
from app.finance.models import GLPosting, JournalEntry
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.gst_returns.services import GstReturnService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from app.settlements.api.router import _to_response
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

#: The cutover day: inside the seeded 2026-2027 financial year.
CUTOVER = date(2026, 4, 1)
SELLER = "29AABCU9603R1ZM"


class _Books:
    """A GST-registered firm with a chart of accounts and two customers."""

    def __init__(self) -> None:
        """Seed everything an opening bill needs."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        # Request-shaped: a request's session does not autoflush, and the
        # difference has hidden shipped defects before.
        self.session = sessionmaker(
            bind=engine, expire_on_commit=False, autoflush=False
        )()
        self.actor_id = uuid4()
        self.firm = self._firm("ACME")
        self.customer = self._customer("C1", "Kumar Stores", terms=30)
        self.other = self._customer("C2", "Ravi Traders")
        self.session.commit()
        self.bills = CustomerOpeningBillService(self.session)
        self.receipts = ReceiptService(self.session)

    def _firm(self, code: str) -> Firm:
        """Add one firm with its books set up."""
        firm = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            gst_number=SELLER if code == "ACME" else None,
        )
        self.session.add(firm)
        self.session.commit()
        seed_finance_setup(
            self.session,
            firm_id=firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        return firm

    def _customer(
        self,
        code: str,
        name: str,
        *,
        terms: int = 0,
        firm: Firm | None = None,
    ) -> Customer:
        """Add one customer."""
        row = Customer(
            firm_id=(firm or self.firm).id,
            code=code,
            customer_type="BUSINESS",
            name=name,
            display_name=name,
            currency_code="INR",
            status="ACTIVE",
            payment_terms_days=terms,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def opening_bill(
        self,
        amount: str,
        *,
        reference: str | None = "SI-9",
        due: date | None = None,
        customer: Customer | None = None,
    ) -> CustomerOpeningBill:
        """Record one opening bill for a customer."""
        return self.bills.create(
            (customer or self.customer).id,
            CustomerOpeningBillWrite(
                reference_number=reference,
                bill_date=date(2026, 2, 10),
                due_date=due,
                posting_date=CUTOVER,
                amount=Decimal(amount),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def receive(
        self,
        amount: str,
        allocations: list[tuple[UUID, str]] | None = None,
        *,
        on: date = date(2026, 4, 20),
    ) -> UUID:
        """Receive from the first customer, applied as given; return its id."""
        row = self.receipts.create(
            SettlementCreate(
                party_id=self.customer.id,
                settlement_date=on,
                amount=Decimal(amount),
                method=SettlementMethodEnum.BANK,
                allocations=[
                    SettlementAllocationWrite(invoice_id=bill_id, amount=Decimal(value))
                    for bill_id, value in allocations or []
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row.id

    def owed(self) -> list[tuple[str, Decimal, bool]]:
        """Return what Record Receipt offers for the first customer."""
        return [
            (row.invoice_number, row.outstanding_amount, row.is_opening_bill)
            for row in self.receipts.outstanding_invoices(
                firm_id=self.firm.id, party_id=self.customer.id
            )
        ]

    def balance(self) -> Decimal:
        """Return the first customer's running balance, as stored."""
        self.session.refresh(self.customer)
        return Decimal(self.customer.current_outstanding)

    def account(self, purpose: ControlAccountPurpose) -> UUID:
        """Return the account one purpose is mapped to."""
        return ControlAccountService(self.session).resolve(self.firm.id, purpose)

    def legs(self, journal_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return debit and credit by account for one journal."""
        return {
            account: (debit, credit)
            for account, debit, credit in self.session.execute(
                select(
                    GLPosting.ledger_account_id,
                    GLPosting.debit_amount,
                    GLPosting.credit_amount,
                ).where(GLPosting.journal_entry_id == journal_id)
            ).all()
        }


def test_an_opening_bill_posts_to_receivables_and_moves_the_balance() -> None:
    """Dr receivables, Cr opening balance equity, on the cutover day -- no tax."""
    books = _Books()
    bill = books.opening_bill("1500.00")

    assert bill.bill_number == "OBC-00001"
    # No due date given: the bill date plus the customer's 30 days.
    assert bill.due_date == date(2026, 3, 12)
    journal = books.session.get(JournalEntry, bill.journal_entry_id)
    assert journal is not None and journal.journal_date == CUTOVER
    assert books.legs(bill.journal_entry_id) == {
        books.account(ControlAccountPurpose.ACCOUNTS_RECEIVABLE): (
            Decimal("1500.00"),
            Decimal("0.00"),
        ),
        books.account(ControlAccountPurpose.OPENING_BALANCE_EQUITY): (
            Decimal("0.00"),
            Decimal("1500.00"),
        ),
    }
    assert books.balance() == Decimal("1500.00")
    [written] = books.session.scalars(select(CustomerReceivableTransaction)).all()
    assert (written.transaction_type, written.transaction_date) == (
        "OPENING_BILL",
        CUTOVER,
    )
    assert written.journal_entry_id == bill.journal_entry_id
    assert books.owed() == [("SI-9 (opening)", Decimal("1500.00"), True)]

    # The statement carries it on the day the books start.
    statement = CustomerStatementService(books.session).statement(
        books.customer.id,
        firm_scope=books.firm.id,
        from_date=CUTOVER,
        to_date=date(2026, 4, 30),
    )
    assert [(line.transaction_type, line.debit) for line in statement.lines] == [
        ("OPENING_BILL", Decimal("1500.00"))
    ]
    assert statement.closing_balance == Decimal("1500.00")


def test_an_opening_bill_is_not_a_sale() -> None:
    """Nothing a GST return or a sales register reads was written."""
    books = _Books()
    books.opening_bill("1500.00")

    assert books.session.scalar(select(func.count(SalesInvoice.id))) == 0
    gstr1 = GstReturnService(books.session).gstr1(
        firm_scope=books.firm.id, from_date=date(2026, 2, 1), to_date=CUTOVER
    )
    assert gstr1["b2b"] == [] and gstr1["b2cs"] == []


def test_a_customer_with_a_single_figure_cannot_take_opening_bills() -> None:
    """One figure on the master, or bills -- never both."""
    books = _Books()
    books.customer.opening_balance = Decimal("500.00")
    books.session.commit()

    with pytest.raises(ValidationError, match="not both -- set the customer's"):
        books.opening_bill("100.00")
    assert books.session.scalar(select(func.count(CustomerOpeningBill.id))) == 0


def test_a_customer_with_opening_bills_cannot_take_a_single_figure() -> None:
    """The master refuses an opening balance while live bills stand."""
    books = _Books()
    books.opening_bill("100.00")

    with pytest.raises(ValidationError, match="either as one figure"):
        CustomerService(books.session).update(
            books.customer.id,
            CustomerUpdate(
                code="C1",
                customer_type="BUSINESS",
                name="Kumar Stores",
                currency_code="INR",
                payment_terms_days=30,
                opening_balance=Decimal("250.00"),
            ),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_receipt_clears_an_opening_bill_and_it_shows_as_settled() -> None:
    """Allocated in full, it is off Record Receipt and the balance is nil."""
    books = _Books()
    bill = books.opening_bill("800.00")

    settlement_id = books.receive("800.00", [(bill.id, "800.00")])

    assert books.owed() == []
    assert books.balance() == Decimal("0.00")
    response = _to_response(
        books.receipts, books.receipts.get(settlement_id, firm_id=books.firm.id)
    )
    [allocation] = response.allocations
    assert (allocation.invoice_id, allocation.invoice_number) == (
        bill.id,
        "SI-9 (opening)",
    )
    [listed] = books.bills.list_for_customer(books.customer.id, firm_id=books.firm.id)
    assert (listed.received_amount, listed.outstanding_amount) == (
        Decimal("800.00"),
        Decimal("0.00"),
    )


def test_a_part_receipt_leaves_the_rest_aged_from_the_due_date() -> None:
    """The ageing counts from the bill's own due date, not the cutover day."""
    books = _Books()
    books.opening_bill("1000.00", due=date(2026, 3, 1))
    bill_id = books.session.scalar(select(CustomerOpeningBill.id))
    assert bill_id is not None
    books.receive("400.00", [(bill_id, "400.00")])

    [row] = CustomerStatementService(books.session).ageing(
        firm_scope=books.firm.id, as_of=date(2026, 4, 30)
    )
    [owing] = row.invoices
    assert (owing.invoice_number, owing.outstanding, owing.days_overdue) == (
        "SI-9 (opening)",
        Decimal("600.00"),
        60,
    )
    assert row.total_outstanding == row.account_balance == Decimal("600.00")
    # On a day before the receipt, the whole bill was owed.
    [before] = CustomerStatementService(books.session).ageing(
        firm_scope=books.firm.id, as_of=date(2026, 4, 10)
    )
    assert before.total_outstanding == Decimal("1000.00")
    # And the overdue report lists it like any unpaid bill.
    [overdue] = SalesInvoiceService(books.session).overdue_report(
        firm_scope=books.firm.id
    )
    assert (overdue.invoice_id, overdue.outstanding_amount) == (
        bill_id,
        Decimal("600.00"),
    )


def test_an_advance_can_be_set_against_an_opening_bill_later() -> None:
    """Money taken on account first, applied to the opening bill afterwards."""
    books = _Books()
    bill = books.opening_bill("800.00")
    settlement_id = books.receive("800.00")

    books.receipts.allocate(
        settlement_id,
        invoice_id=bill.id,
        amount=Decimal("800.00"),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.owed() == []
    assert books.balance() == Decimal("0.00")


def test_cancelling_reverses_the_journal_and_the_balance() -> None:
    """Refused while received against; once free, the mirror and the balance."""
    books = _Books()
    bill = books.opening_bill("800.00")
    settlement_id = books.receive("300.00", [(bill.id, "300.00")])

    with pytest.raises(ValidationError, match="Reverse those receipts"):
        books.bills.cancel(
            bill.id, reason="typed twice", firm_id=books.firm.id, actor_id=uuid4()
        )

    books.receipts.reverse(
        settlement_id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert books.balance() == Decimal("800.00")
    books.bills.cancel(
        bill.id, reason="typed twice", firm_id=books.firm.id, actor_id=books.actor_id
    )

    assert bill.status == "CANCELLED"
    assert bill.reversal_journal_entry_id is not None
    mirror = books.legs(bill.reversal_journal_entry_id)
    assert mirror[books.account(ControlAccountPurpose.ACCOUNTS_RECEIVABLE)] == (
        Decimal("0.00"),
        Decimal("800.00"),
    )
    assert books.balance() == Decimal("0.00")
    assert books.owed() == []
    # The number is not handed out again: its journal still holds it.
    assert books.opening_bill("800.00").bill_number == "OBC-00002"


def test_the_same_customer_bill_cannot_be_recorded_twice() -> None:
    """One customer's reference once; another customer may use the same one."""
    books = _Books()
    books.opening_bill("100.00", reference="SI-9")

    with pytest.raises(ValidationError, match="already recorded as OBC-00001"):
        books.opening_bill("100.00", reference="si-9")
    assert books.opening_bill("100.00", reference="SI-9", customer=books.other)


def test_a_customer_owing_an_opening_bill_cannot_be_deleted() -> None:
    """The customer delete guard reads the balance and the same derivation."""
    books = _Books()
    books.opening_bill("250.00")

    with pytest.raises(ValidationError, match=r"owes 250\.00.*SI-9 \(opening\)"):
        CustomerService(books.session).delete(
            books.customer.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )


def _row(code: str, amount: str, **overrides: object) -> CustomerOpeningBillImportRow:
    """Build one import row."""
    values: dict[str, object] = {
        "customer_code": code,
        "reference_number": f"R-{code}-{amount}",
        "bill_date": date(2026, 3, 1),
        "posting_date": CUTOVER,
        "amount": Decimal(amount),
    }
    values.update(overrides)
    return CustomerOpeningBillImportRow.model_validate(values)


def test_an_import_names_every_unknown_customer_and_writes_nothing() -> None:
    """All the bad codes in one refusal, with their row numbers."""
    books = _Books()

    with pytest.raises(ValidationError) as refused:
        books.bills.import_bills(
            [_row("C1", "10"), _row("NOPE", "20"), _row("GONE", "30")],
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )

    assert "row 2: NOPE; row 3: GONE" in refused.value.message
    assert books.session.scalar(select(func.count(CustomerOpeningBill.id))) == 0


def test_an_import_is_all_or_nothing() -> None:
    """A row refused at posting takes the rows before it, and the balance."""
    books = _Books()

    with pytest.raises(ValidationError, match="Row 2:"):
        books.bills.import_bills(
            [
                _row("C1", "10"),
                # Before the seeded financial year: no open period to post in.
                _row(
                    "c2", "20", bill_date=date(2025, 1, 1), posting_date=None
                ).model_copy(update={"posting_date": date(2025, 3, 1)}),
            ],
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    assert books.session.scalar(select(func.count(CustomerOpeningBill.id))) == 0
    assert books.balance() == Decimal("0.00")

    rows = books.bills.import_bills(
        [_row("C1", "10"), _row("c2", "20")],
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    assert [row.bill_number for row in rows] == ["OBC-00001", "OBC-00002"]
    assert rows[1].customer_id == books.other.id
    assert books.balance() == Decimal("10.00")


def test_one_firm_cannot_see_another_firms_opening_bills() -> None:
    """Listing, cancelling and receiving are all scoped to the firm."""
    books = _Books()
    bill = books.opening_bill("100.00")
    rival = books._firm("RIVAL")
    books._customer("C1", "Rival's Kumar", firm=rival)
    books.session.commit()

    with pytest.raises(ResourceNotFoundError):
        books.bills.list_for_customer(books.customer.id, firm_id=rival.id)
    with pytest.raises(ResourceNotFoundError):
        books.bills.cancel(
            bill.id, reason="not ours", firm_id=rival.id, actor_id=books.actor_id
        )
    assert books.receipts.outstanding_invoices(firm_id=rival.id, party_id=None) == []
    # Importing into the rival names the rival's C1, never this firm's.
    [imported] = books.bills.import_bills(
        [_row("C1", "5")], firm_id=rival.id, actor_id=books.actor_id
    )
    assert imported.customer_id != books.customer.id
    assert imported.bill_number == "OBC-00001"


def test_an_opening_bill_dated_after_cutover_is_refused() -> None:
    """An opening bill is raised before the books here start."""
    with pytest.raises(ValueError, match="cannot be after the posting date"):
        CustomerOpeningBillWrite(
            bill_date=date(2026, 5, 1),
            posting_date=CUTOVER,
            amount=Decimal("1"),
        )
