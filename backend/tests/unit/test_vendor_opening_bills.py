"""What a firm owed its suppliers on day one, bill by bill (backlog 36).

A supplier's balance is derived from the bills still owing, so a day-one debt
has to be a bill too -- one Record Payment offers, a payment clears, the
reports count and the vendor delete guard sees -- without being a purchase
invoice, which the GST returns and purchase registers would read as trading.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import GLPosting, JournalEntry
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.services import PurchaseInvoiceService
from app.settlements.api.router import _to_response
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService
from app.vendors.models import Vendor, VendorOpeningBill
from app.vendors.schemas.opening_bill import (
    VendorOpeningBillImportRow,
    VendorOpeningBillWrite,
)
from app.vendors.services import VendorService
from app.vendors.services.opening_bill_service import VendorOpeningBillService

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

#: The cutover day: inside the seeded 2026-2027 financial year.
CUTOVER = date(2026, 4, 1)


class _Books:
    """A firm with a chart of accounts and two suppliers."""

    def __init__(self) -> None:
        """Seed everything an opening bill needs."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Acme Firm",
            code="ACME",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        seed_finance_setup(
            self.session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.vendor = self._vendor("V1", "Vendor One")
        self.other = self._vendor("V2", "Vendor Two")
        self.session.commit()
        self.bills = VendorOpeningBillService(self.session)
        self.payments = PaymentService(self.session)

    def _vendor(self, code: str, name: str) -> Vendor:
        """Add one supplier."""
        row = Vendor(
            firm_id=self.firm.id,
            code=code,
            name=name,
            display_name=name,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        return row

    def opening_bill(
        self,
        amount: str,
        *,
        reference: str | None = "INV-9",
        due: date | None = None,
        vendor: Vendor | None = None,
    ) -> VendorOpeningBill:
        """Record one opening bill for a supplier."""
        return self.bills.create(
            (vendor or self.vendor).id,
            VendorOpeningBillWrite(
                reference_number=reference,
                bill_date=date(2026, 2, 10),
                due_date=due,
                posting_date=CUTOVER,
                amount=Decimal(amount),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def pay(
        self, amount: str, allocations: list[tuple[UUID, str]] | None = None
    ) -> UUID:
        """Pay the first supplier, applied as given; return the settlement id."""
        row = self.payments.create(
            SettlementCreate(
                party_id=self.vendor.id,
                settlement_date=date(2026, 4, 20),
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
        """Return what Record Payment offers for the first supplier."""
        return [
            (row.invoice_number, row.outstanding_amount, row.is_opening_bill)
            for row in self.payments.outstanding_invoices(
                firm_id=self.firm.id, party_id=self.vendor.id
            )
        ]

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


def test_an_opening_bill_posts_to_payables_and_is_offered_for_payment() -> None:
    """Dr opening balance equity, Cr payables, on the cutover day -- no tax."""
    books = _Books()
    bill = books.opening_bill("1500.00", due=date(2026, 3, 12))

    assert bill.bill_number == "OB-00001"
    journal = books.session.get(JournalEntry, bill.journal_entry_id)
    assert journal is not None and journal.journal_date == CUTOVER
    legs = books.legs(bill.journal_entry_id)
    assert legs == {
        books.account(ControlAccountPurpose.OPENING_BALANCE_EQUITY): (
            Decimal("1500.00"),
            Decimal("0.00"),
        ),
        books.account(ControlAccountPurpose.ACCOUNTS_PAYABLE): (
            Decimal("0.00"),
            Decimal("1500.00"),
        ),
    }
    assert books.owed() == [("INV-9 (opening)", Decimal("1500.00"), True)]
    # And it is not a purchase invoice: nothing a GST return reads was written.
    assert books.session.scalar(select(func.count(PurchaseInvoice.id))) == 0


def test_a_payment_clears_an_opening_bill_and_the_reports_follow() -> None:
    """Part-paid, it owes the rest; the settlement names it by its reference."""
    books = _Books()
    bill = books.opening_bill("1500.00", due=date(2026, 3, 12))
    reports = PurchaseInvoiceService(books.session)

    # Owed and overdue before any money moves.
    [row] = reports.outstanding_report(firm_scope=books.firm.id)
    assert (row.outstanding_amount, row.invoice_count) == (Decimal("1500.00"), 1)
    [overdue] = reports.overdue_report(firm_scope=books.firm.id)
    assert (overdue.invoice_number, overdue.vendor_name) == (
        "INV-9 (opening)",
        "Vendor One",
    )

    settlement_id = books.pay("1000.00", [(bill.id, "1000.00")])

    assert books.owed() == [("INV-9 (opening)", Decimal("500.00"), True)]
    response = _to_response(
        books.payments, books.payments.get(settlement_id, firm_id=books.firm.id)
    )
    [allocation] = response.allocations
    assert (allocation.invoice_id, allocation.invoice_number) == (
        bill.id,
        "INV-9 (opening)",
    )
    listed = books.bills.list_for_vendor(books.vendor.id, firm_id=books.firm.id)
    assert [(item.paid_amount, item.outstanding_amount) for item in listed] == [
        (Decimal("1000.00"), Decimal("500.00"))
    ]


def test_an_advance_can_be_set_against_an_opening_bill_later() -> None:
    """Money paid on account first, applied to the opening bill afterwards."""
    books = _Books()
    bill = books.opening_bill("800.00")
    settlement_id = books.pay("800.00")

    books.payments.allocate(
        settlement_id,
        invoice_id=bill.id,
        amount=Decimal("800.00"),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.owed() == []


def test_reversing_the_payment_puts_the_opening_bill_back() -> None:
    """A reversed payment stops clearing it, as it would a purchase bill."""
    books = _Books()
    bill = books.opening_bill("800.00")
    settlement_id = books.pay("800.00", [(bill.id, "800.00")])

    books.payments.reverse(
        settlement_id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    assert books.owed() == [("INV-9 (opening)", Decimal("800.00"), True)]


def test_a_paid_opening_bill_cannot_be_cancelled_and_an_unpaid_one_reverses() -> None:
    """Cancelling posts the mirror and takes the bill off the payment list."""
    books = _Books()
    bill = books.opening_bill("800.00")
    settlement_id = books.pay("300.00", [(bill.id, "300.00")])

    with pytest.raises(ValidationError, match="Reverse those payments"):
        books.bills.cancel(
            bill.id, reason="typed twice", firm_id=books.firm.id, actor_id=uuid4()
        )

    books.payments.reverse(
        settlement_id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    books.bills.cancel(
        bill.id, reason="typed twice", firm_id=books.firm.id, actor_id=books.actor_id
    )

    assert bill.status == "CANCELLED"
    assert bill.reversal_journal_entry_id is not None
    mirror = books.legs(bill.reversal_journal_entry_id)
    assert mirror[books.account(ControlAccountPurpose.ACCOUNTS_PAYABLE)] == (
        Decimal("800.00"),
        Decimal("0.00"),
    )
    assert books.owed() == []
    # The number is not handed out again: its journal still holds it.
    assert books.opening_bill("800.00").bill_number == "OB-00002"


def test_the_same_supplier_bill_cannot_be_recorded_twice() -> None:
    """One supplier's reference once; another supplier may use the same one."""
    books = _Books()
    books.opening_bill("100.00", reference="INV-9")

    with pytest.raises(ValidationError, match="already recorded as OB-00001"):
        books.opening_bill("100.00", reference="inv-9")
    assert books.opening_bill("100.00", reference="INV-9", vendor=books.other)


def test_a_supplier_owed_an_opening_bill_cannot_be_deleted() -> None:
    """The vendor delete guard reads the same derivation."""
    books = _Books()
    books.opening_bill("250.00")

    with pytest.raises(ValidationError, match="is owed 250.00"):
        VendorService(books.session).delete(
            books.vendor.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )


def _row(code: str, amount: str, **overrides: object) -> VendorOpeningBillImportRow:
    """Build one import row."""
    values: dict[str, object] = {
        "vendor_code": code,
        "reference_number": f"R-{code}-{amount}",
        "bill_date": date(2026, 3, 1),
        "posting_date": CUTOVER,
        "amount": Decimal(amount),
    }
    values.update(overrides)
    return VendorOpeningBillImportRow.model_validate(values)


def test_an_import_names_every_unknown_supplier_and_writes_nothing() -> None:
    """All the bad codes in one refusal, with their row numbers."""
    books = _Books()

    with pytest.raises(ValidationError) as refused:
        books.bills.import_bills(
            [_row("V1", "10"), _row("NOPE", "20"), _row("GONE", "30")],
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )

    assert "row 2: NOPE; row 3: GONE" in refused.value.message
    assert books.session.scalar(select(func.count(VendorOpeningBill.id))) == 0


def test_an_import_is_all_or_nothing() -> None:
    """A row refused at posting takes the rows before it with it."""
    books = _Books()

    with pytest.raises(ValidationError, match="Row 2:"):
        books.bills.import_bills(
            [
                _row("V1", "10"),
                # Before the seeded financial year: no open period to post in.
                _row(
                    "v2", "20", bill_date=date(2025, 1, 1), posting_date=None
                ).model_copy(update={"posting_date": date(2025, 3, 1)}),
            ],
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    assert books.session.scalar(select(func.count(VendorOpeningBill.id))) == 0

    rows = books.bills.import_bills(
        [_row("V1", "10"), _row("v2", "20")],
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    assert [row.bill_number for row in rows] == ["OB-00001", "OB-00002"]
    assert rows[1].vendor_id == books.other.id


def test_an_opening_bill_dated_after_cutover_is_refused() -> None:
    """An opening bill is raised before the books here start."""
    with pytest.raises(ValueError, match="cannot be after the posting date"):
        VendorOpeningBillWrite(
            bill_date=date(2026, 5, 1),
            posting_date=CUTOVER,
            amount=Decimal("1"),
        )
