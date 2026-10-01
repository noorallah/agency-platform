"""Tax deducted at source on payments, receipts and expenses (backlog 53.1).

Until 2026-10-01 a deduction was recorded by hand: the payment for the net,
then a journal for the rest. Now the settlement or expense carries it, as
Tally's voucher does: the party is settled for the whole amount, the cash or
bank moves the net, and the deduction goes to TDS Payable (what the firm owes
the government) or TDS Receivable (what a customer deducted and the firm
claims). The two registers are read straight from those documents.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.core.pagination.reports import ReportWindow
from app.expenses.schemas import ExpenseCreate
from app.expenses.services import ExpenseService
from app.finance.models import GLPosting, LedgerAccount
from app.finance.services.tds_register import NO_PAN, TdsRegisterService, tds_quarter
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService, RefundService
from tests.unit.test_expenses import _Books as _ExpenseBooks
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

# The seeded chart: bank, receivables, TDS receivable, payables, TDS payable.
BANK, RECEIVABLES, TDS_RECEIVABLE = "1010", "1100", "1400"
PAYABLES, TDS_PAYABLE = "2100", "2700"


def _pay(
    books: _Books, *, amount: str, tds: str | None, section: str | None
) -> Settlement:
    invoice = books.purchase_invoice("PI-1", amount)
    payment = PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
            tds_amount=Decimal(tds) if tds else None,
            tds_section=section,
            allocations=[
                SettlementAllocationWrite(invoice_id=invoice.id, amount=Decimal(amount))
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return payment


def test_a_payment_with_tds_settles_the_bill_in_full_and_pays_the_net() -> None:
    books = _Books(_session_factory()())
    books.vendor.pan = "ABCDE1234F"
    payment = _pay(books, amount="100000.00", tds="100.00", section="194q")

    legs = books.postings(payment)
    assert legs[PAYABLES] == (Decimal("100000.00"), Decimal("0.00"))
    assert legs[BANK] == (Decimal("0.00"), Decimal("99900.00"))
    assert legs[TDS_PAYABLE] == (Decimal("0.00"), Decimal("100.00"))
    assert payment.tds_section == "194Q"
    # The bill is settled for its whole value: nothing is left owing.
    owed = PaymentService(books.session).outstanding_invoices(
        firm_id=books.firm.id, party_id=books.vendor.id
    )
    assert [row.outstanding_amount for row in owed] == []

    [row] = TdsRegisterService(books.session).deducted_by_firm(
        books.firm.id, ReportWindow()
    )
    assert (row.document_type, row.pan, row.section, row.section_name) == (
        "Payment",
        "ABCDE1234F",
        "194Q",
        "Purchase of goods",
    )
    assert (row.gross_amount, row.tds_amount, row.net_amount) == (
        Decimal("100000.00"),
        Decimal("100.00"),
        Decimal("99900.00"),
    )
    assert row.quarter == "Q1 2026-27"


def test_reversing_a_payment_takes_the_deduction_off_too() -> None:
    books = _Books(_session_factory()())
    payment = _pay(books, amount="5000.00", tds="50.00", section="194C")
    PaymentService(books.session).reverse(
        payment.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    reversed_row = books.session.get(Settlement, payment.id)
    assert reversed_row is not None and reversed_row.status == "REVERSED"
    assert reversed_row.reversal_journal_entry_id is not None
    mirror = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == reversed_row.reversal_journal_entry_id)
    ).all()
    legs = {code: (debit, credit) for code, debit, credit in mirror}
    # Every leg mirrored: the deduction comes off TDS Payable with the payment.
    assert legs[TDS_PAYABLE] == (Decimal("50.00"), Decimal("0.00"))
    assert legs[BANK] == (Decimal("4950.00"), Decimal("0.00"))
    assert legs[PAYABLES] == (Decimal("0.00"), Decimal("5000.00"))
    # The register still lists it, with its status: a challan may already
    # have been paid, so the accountant has to see the reversal.
    [row] = TdsRegisterService(books.session).deducted_by_firm(
        books.firm.id, ReportWindow()
    )
    assert row.status == "REVERSED"


def test_a_receipt_short_by_tds_clears_the_invoice_and_claims_the_rest() -> None:
    books = _Books(_session_factory()())
    books.customer.tan_number = "DELA12345B"
    books.owe_us("10000.00")
    invoice = books.sales_invoice("SI-1", "10000.00")

    receipt = ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("10000.00"),
            method=SettlementMethodEnum.BANK,
            tds_amount=Decimal("10.00"),
            tds_section="194Q",
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("10000.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    legs = books.postings(receipt)
    assert legs[BANK] == (Decimal("9990.00"), Decimal("0.00"))
    assert legs[TDS_RECEIVABLE] == (Decimal("10.00"), Decimal("0.00"))
    assert legs[RECEIVABLES] == (Decimal("0.00"), Decimal("10000.00"))
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("0.00")

    [row] = TdsRegisterService(books.session).deducted_by_customers(
        books.firm.id, ReportWindow()
    )
    assert (row.tan, row.pan, row.tds_amount) == (
        "DELA12345B",
        NO_PAN,
        Decimal("10.00"),
    )


@pytest.mark.parametrize(
    ("tds", "section", "message"),
    [
        ("10.00", None, "Name the TDS section"),
        ("10.00", "999Z", "is not a TDS section"),
        (None, "194Q", "nothing was deducted"),
        ("700.00", "194Q", "must be less than"),
    ],
)
def test_a_deduction_the_return_could_not_carry_is_refused(
    tds: str | None, section: str | None, message: str
) -> None:
    with pytest.raises(PydanticValidationError, match=message):
        SettlementCreate(
            party_id=uuid4(),
            settlement_date=WHEN,
            amount=Decimal("700.00"),
            method=SettlementMethodEnum.BANK,
            tds_amount=Decimal(tds) if tds else None,
            tds_section=section,
        )


def test_a_refund_carries_no_tds() -> None:
    books = _Books(_session_factory()())
    with pytest.raises(ValidationError, match="no tax deducted at source"):
        RefundService(books.session).create(
            SettlementCreate(
                party_id=books.customer.id,
                settlement_date=WHEN,
                amount=Decimal("100.00"),
                method=SettlementMethodEnum.BANK,
                tds_amount=Decimal("1.00"),
                tds_section="194Q",
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_expense_with_tds_books_the_whole_cost_and_pays_the_net() -> None:
    books = _ExpenseBooks()
    expense = ExpenseService(books.session).create(
        ExpenseCreate(
            expense_date=WHEN,
            expense_account_id=books.account("6000"),
            paid_from_account_id=books.account(BANK),
            amount=Decimal("30000.00"),
            payee="Sharma Properties",
            payee_pan="abcde1234f",
            tds_amount=Decimal("3000.00"),
            tds_section="194I",
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    legs = books.postings(expense.journal_entry_id)
    assert legs["6000"] == (Decimal("30000.00"), Decimal("0.00"))
    assert legs[BANK] == (Decimal("0.00"), Decimal("27000.00"))
    assert legs[TDS_PAYABLE] == (Decimal("0.00"), Decimal("3000.00"))

    [row] = TdsRegisterService(books.session).deducted_by_firm(
        books.firm.id, ReportWindow()
    )
    assert (row.document_type, row.party_name, row.pan, row.section_name) == (
        "Expense",
        "Sharma Properties",
        "ABCDE1234F",
        "Rent",
    )


def test_an_expense_deduction_names_its_payee_and_a_valid_pan() -> None:
    books = _ExpenseBooks()
    base = {
        "expense_date": WHEN,
        "expense_account_id": books.account("6000"),
        "paid_from_account_id": books.account(BANK),
        "amount": Decimal("1000.00"),
        "tds_amount": Decimal("100.00"),
        "tds_section": "194J",
    }
    with pytest.raises(PydanticValidationError, match="Name the payee"):
        ExpenseCreate(**base)  # type: ignore[arg-type]
    with pytest.raises(PydanticValidationError, match="A PAN is five letters"):
        ExpenseCreate(**base, payee="Dr Rao", payee_pan="12345")  # type: ignore[arg-type]


def test_the_return_quarter_runs_april_to_june_first() -> None:
    assert tds_quarter(date(2026, 4, 1)) == "Q1 2026-27"
    assert tds_quarter(date(2026, 9, 30)) == "Q2 2026-27"
    assert tds_quarter(date(2026, 12, 31)) == "Q3 2026-27"
    assert tds_quarter(date(2027, 3, 31)) == "Q4 2026-27"


def test_the_registers_respect_the_dates() -> None:
    books = _Books(_session_factory()())
    _pay(books, amount="1000.00", tds="10.00", section="194C")
    service = TdsRegisterService(books.session)
    assert (
        service.deducted_by_firm(
            books.firm.id, ReportWindow(from_date=date(2026, 5, 1))
        )
        == []
    )
    assert len(service.deducted_by_firm(books.firm.id, ReportWindow(to_date=WHEN))) == 1
