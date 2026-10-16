"""The money consistency check (AWAY_WORK_LIST item 30, part 1).

One clean firm reports nothing; then each check is given the one defect it
exists to find, and has to name the month and the document.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.customers.models import CustomerReceivableTransaction
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.finance.models import JournalEntry, JournalLine
from app.finance.services import money_consistency
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.finance.services.money_consistency import (
    DOCUMENT_WITHOUT_JOURNAL,
    JOURNAL_UNBALANCED,
    JOURNAL_WITHOUT_DOCUMENT,
    PAYABLES_BILLS,
    PAYABLES_LEDGER,
    RECEIVABLES_BILLS,
    RECEIVABLES_LEDGER,
    TRIAL_BALANCE,
    Difference,
    check_money_consistency,
)
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

APRIL = date(2026, 4, 1)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix the check's today inside the seeded year, whatever the clock says."""
    monkeypatch.setattr(money_consistency, "firm_today", lambda *_: date(2026, 6, 15))


def _books() -> _Books:
    return _Books(_session_factory()())


def _sale(books: _Books, number: str, total: str) -> SalesInvoice:
    """Approve a sales invoice the way approval does: account and journal."""
    row = books.sales_invoice(number, total)
    CustomerService(books.session).post_receivable_transaction(
        books.customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=CustomerReceivableTransactionType.INVOICE,
            transaction_date=WHEN,
            amount=Decimal(total),
            reference_type="SALES_INVOICE",
            reference_id=row.id,
            reference_number=number,
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        commit=False,
    )
    DocumentPostingService(books.session).post_sales_invoice(
        firm_id=books.firm.id,
        invoice_id=row.id,
        invoice_number=number,
        invoice_date=WHEN,
        taxable_amount=Decimal(total),
        tax_amount=Decimal("0"),
        total_amount=Decimal(total),
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _bill(books: _Books, number: str, total: str) -> PurchaseInvoice:
    """Approve a supplier bill the way approval does."""
    row = books.purchase_invoice(number, total)
    DocumentPostingService(books.session).post_purchase_invoice(
        firm_id=books.firm.id,
        invoice_id=row.id,
        invoice_number=number,
        invoice_date=WHEN,
        goods_amount=Decimal(total),
        tax_amount=Decimal("0"),
        total_amount=Decimal(total),
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _settle(
    books: _Books, amount: str, invoice_id: object | None, *, receipt: bool
) -> None:
    service = ReceiptService if receipt else PaymentService
    service(books.session).create(
        SettlementCreate(
            party_id=books.customer.id if receipt else books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
            allocations=(
                [
                    SettlementAllocationWrite(
                        invoice_id=invoice_id, amount=Decimal(amount)
                    )
                ]
                if invoice_id is not None
                else []
            ),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()


def _trading(books: _Books) -> tuple[SalesInvoice, PurchaseInvoice]:
    """Trade cleanly for a month: bills both ways, part paid, an advance each."""
    sale = _sale(books, "SI-1", "1000.00")
    _settle(books, "400.00", sale.id, receipt=True)
    _settle(books, "50.00", None, receipt=True)  # held on account
    bill = _bill(books, "PI-1", "700.00")
    _settle(books, "300.00", bill.id, receipt=False)
    _settle(books, "25.00", None, receipt=False)  # advance to the supplier
    return sale, bill


def _check(books: _Books) -> list[Difference]:
    return check_money_consistency(
        books.session, books.firm.id, from_month=APRIL, to_month=None
    )


def _april(found: list[Difference], check: str) -> list[Difference]:
    return [row for row in found if row.check == check and row.period == "2026-04"]


def test_clean_books_report_nothing() -> None:
    books = _books()
    _trading(books)

    assert _check(books) == []


def test_the_check_writes_nothing() -> None:
    books = _books()
    _trading(books)
    _check(books)

    assert not books.session.new
    assert not books.session.dirty


def test_an_unbalanced_journal_is_named() -> None:
    books = _books()
    sale, _ = _trading(books)
    line = books.session.scalars(
        select(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(JournalEntry.source_id == sale.id, JournalLine.debit_amount > 0)
    ).first()
    assert line is not None
    line.debit_amount = line.debit_amount + Decimal("1.00")
    books.session.commit()

    found = _check(books)

    month = _april(found, TRIAL_BALANCE)
    assert [row.document_ref for row in month] == ["posted journal lines"]
    assert month[0].expected - month[0].actual == Decimal("1.00")
    assert [row.document_ref for row in _april(found, JOURNAL_UNBALANCED)] == [
        "Journal SI-1 (sales_invoice)"
    ]


def test_a_customer_balance_moved_without_a_journal_is_found() -> None:
    books = _books()
    _trading(books)
    books.owe_us("100.00")  # the old path: account moved, ledger not

    found = _check(books)

    ledger = _april(found, RECEIVABLES_LEDGER)
    assert len(ledger) == 1
    assert ledger[0].expected == Decimal("600.00") - Decimal("50.00")
    assert ledger[0].actual == Decimal("650.00")


def test_a_customer_account_away_from_the_bills_is_found() -> None:
    books = _books()
    sale, _ = _trading(books)
    sale.grand_total = Decimal("1200.00")  # the bill now says more than posted
    books.session.commit()

    found = _check(books)

    bills = [row for row in found if row.check == RECEIVABLES_BILLS]
    # Owes 550.00 on the account; the bill now owes 800.00, less 50.00 held.
    assert [(row.document_ref, row.expected, row.actual) for row in bills] == [
        ("Customer C1", Decimal("550.00"), Decimal("750.00"))
    ]
    assert _april(found, RECEIVABLES_LEDGER) == []


def test_a_hand_journal_on_payables_is_found() -> None:
    books = _books()
    _trading(books)
    posting = DocumentPostingService(books.session)
    context = posting.context_for(books.firm.id, WHEN)
    engine = JournalEntryEngine(books.session)
    entry = engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=context.journal_type_id,
        voucher_type_id=context.voucher_type_id,
        accounting_period_id=context.accounting_period_id,
        journal_date=WHEN,
        reference_number="JV-HAND-1",
        description="By hand",
        lines=[
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.PURCHASE_EXPENSE),
                debit_amount=Decimal("80.00"),
            ),
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.ACCOUNTS_PAYABLE),
                credit_amount=Decimal("80.00"),
            ),
        ],
        actor_id=books.actor_id,
    )
    engine.post_entry(entry.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    found = _check(books)

    ledger = _april(found, PAYABLES_LEDGER)
    assert len(ledger) == 1
    assert ledger[0].expected - ledger[0].actual == Decimal("80.00")
    assert [row for row in found if row.check == PAYABLES_BILLS] == []


def test_a_supplier_statement_away_from_the_bills_is_found() -> None:
    books = _books()
    _, bill = _trading(books)
    bill.grand_total = Decimal("750.00")
    books.session.commit()

    found = _check(books)

    bills = [row for row in found if row.check == PAYABLES_BILLS]
    assert [(row.document_ref, row.expected, row.actual) for row in bills] == [
        ("Supplier V1", Decimal("375.00"), Decimal("425.00"))
    ]
    assert [row for row in found if row.check == PAYABLES_LEDGER] == []


def test_an_approved_document_with_no_journal_is_named() -> None:
    books = _books()
    _trading(books)
    books.sales_invoice("SI-2", "90.00")  # approved, never posted

    found = _check(books)

    missing = _april(found, DOCUMENT_WITHOUT_JOURNAL)
    assert [(row.document_ref, row.expected) for row in missing] == [
        ("Sales invoice SI-2", Decimal("90.00"))
    ]


def test_a_journal_whose_document_was_cancelled_is_named() -> None:
    books = _books()
    sale, _ = _trading(books)
    sale.status = "CANCELLED"  # undone without taking its journal off
    books.session.commit()

    found = _check(books)

    orphans = _april(found, JOURNAL_WITHOUT_DOCUMENT)
    assert [row.document_ref for row in orphans] == ["Journal SI-1"]
    assert "cancelled" in orphans[0].note
    assert orphans[0].actual == Decimal("1000.00")


def test_a_journal_whose_document_is_gone_is_named() -> None:
    books = _books()
    sale, _ = _trading(books)
    sale.is_deleted = True
    books.session.commit()

    found = _check(books)

    orphans = _april(found, JOURNAL_WITHOUT_DOCUMENT)
    assert [row.document_ref for row in orphans] == ["Journal SI-1"]
    assert "deleted" in orphans[0].note


def test_months_outside_the_range_are_not_read() -> None:
    books = _books()
    _trading(books)
    books.owe_us("100.00")

    found = check_money_consistency(
        books.session,
        books.firm.id,
        from_month=date(2026, 3, 1),
        to_month=date(2026, 3, 31),
    )

    assert found == []
    assert books.session.scalar(select(CustomerReceivableTransaction.id)) is not None
