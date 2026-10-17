"""The money consistency check (AWAY_WORK_LIST item 30, part 1).

One clean firm reports nothing; then each check is given the one defect it
exists to find, and has to name the month and the document.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.commission.models import CommissionPayout, CommissionPayoutStatus
from app.credit_note.models import CreditNote
from app.customers.models import CustomerReceivableTransaction
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.finance.models import JournalEntry, JournalLine
from app.finance.services import money_consistency
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.finance.services.money_consistency import (
    COMMISSION_VS_PAYOUTS,
    DOCUMENT_WITHOUT_JOURNAL,
    GST_VS_RETURN,
    JOURNAL_UNBALANCED,
    JOURNAL_WITHOUT_DOCUMENT,
    LOYALTY_VS_LEDGER,
    PAYABLES_BILLS,
    PAYABLES_LEDGER,
    RECEIVABLES_BILLS,
    RECEIVABLES_LEDGER,
    STOCK_VS_INVENTORY,
    TAX_AT_SOURCE_VS_REGISTER,
    TRIAL_BALANCE,
    Difference,
    check_money_consistency,
)
from app.firms.models import Firm
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.salesmen.models import Salesman
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService
from app.tcs.models import TcsCollection, TcsCollectionStatus
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


def _credit_note_on_a_paid_bill(books: _Books, total: str) -> SalesInvoice:
    """Approve a credit note on a bill paid in full, the way approval does.

    The bill has nothing left to come off, so the whole note is credit on
    the customer's account: held as an advance, on no open bill.
    """
    sale = _sale(books, "SI-9", "1000.00")
    _settle(books, "1000.00", sale.id, receipt=True)
    note = CreditNote(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch_id,
        sales_invoice_id=sale.id,
        credit_note_number="CN-9",
        credit_note_date=WHEN,
        status="APPROVED",
        total_amount=Decimal(total),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(note)
    books.session.flush()
    CustomerService(books.session).post_receivable_transaction(
        books.customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
            transaction_date=WHEN,
            amount=Decimal(total),
            reference_type="CREDIT_NOTE",
            reference_id=note.id,
            reference_number="CN-9",
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        commit=False,
    )
    DocumentPostingService(books.session).post_credit_note_document(
        firm_id=books.firm.id,
        credit_note_id=note.id,
        credit_note_number="CN-9",
        note_date=WHEN,
        taxable_amount=Decimal(total),
        tax_amount=Decimal("0"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    return sale


def test_credit_no_bill_absorbed_is_not_a_difference() -> None:
    books = _books()
    _credit_note_on_a_paid_bill(books, "300.00")

    found = _check(books)

    # The account holds 300.00 for the customer and no bill owes anything:
    # the note's unused credit is what the account holds, not a difference.
    assert [row for row in found if row.check == RECEIVABLES_BILLS] == []
    assert found == []


def test_credit_netted_still_leaves_a_real_difference_found() -> None:
    books = _books()
    sale = _credit_note_on_a_paid_bill(books, "300.00")
    sale.grand_total = Decimal("1100.00")  # the bill now owes 100.00 more
    books.session.commit()

    found = _check(books)

    bills = [row for row in found if row.check == RECEIVABLES_BILLS]
    # The bill absorbs 100.00 of the note, so 200.00 is credit; the account
    # still holds 300.00.
    assert [(row.document_ref, row.expected, row.actual) for row in bills] == [
        ("Customer C1", Decimal("-300.00"), Decimal("-200.00"))
    ]


def test_without_netting_the_credit_reads_as_a_difference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books()
    _credit_note_on_a_paid_bill(books, "300.00")
    monkeypatch.setattr(money_consistency, "_unused_customer_credit", lambda *_: {})

    found = _check(books)

    # The false positive the netting removes (TEST01, 2026-10-17).
    assert [
        (row.document_ref, row.expected, row.actual)
        for row in found
        if row.check == RECEIVABLES_BILLS
    ] == [("Customer C1", Decimal("-300.00"), Decimal("0.00"))]


@pytest.mark.parametrize("opening", ["-300.00", "250.00"])
def test_an_opening_balance_on_the_master_is_not_a_difference(
    monkeypatch: pytest.MonkeyPatch, opening: str
) -> None:
    """A day-one figure typed on the customer agrees with the bills.

    In credit it is held as an advance no receipt holds and no bill carries:
    TEST01 read four such customers as -300.00 against 0.00 (2026-10-17).
    In debit the ageing carries it as an "Opening balance" row already.
    """
    from app.customers.services import customer_service

    monkeypatch.setattr(customer_service, "firm_today", lambda *_: WHEN)
    books = _books()
    _trading(books)
    CustomerService(books.session)._record_opening_balance_transaction(
        customer=books.customer, amount=Decimal(opening), actor_id=books.actor_id
    )
    books.session.commit()

    assert _check(books) == []


def _charge(books: _Books, kind: CustomerReceivableTransactionType) -> UUID:
    """Charge the customer on top of every bill, the way the services do.

    Tax collected at source on a receipt, or the charge for a bounced
    cheque: the account goes up and no invoice carries it.
    """
    row = CustomerService(books.session).post_receivable_transaction(
        books.customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=kind,
            transaction_date=WHEN,
            amount=Decimal("19.64"),
            reference_type="TCS_COLLECTION",
            reference_id=uuid4(),
            reference_number="RC-TCS",
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        commit=False,
    )
    books.session.commit()
    return row.id


def _bills_rows(found: list[Difference]) -> list[tuple[str, Decimal, Decimal]]:
    return [
        (row.document_ref, row.expected, row.actual)
        for row in found
        if row.check == RECEIVABLES_BILLS
    ]


@pytest.mark.parametrize(
    "kind",
    [
        CustomerReceivableTransactionType.TCS,
        CustomerReceivableTransactionType.CHEQUE_RETURN_CHARGE,
    ],
)
def test_a_charge_no_bill_carries_is_not_a_difference(
    kind: CustomerReceivableTransactionType,
) -> None:
    """TCS and a cheque return charge are owed on top of the bills.

    MEDI01C02 read 20764.31 against 20744.67 -- its 19.64 of TCS -- and a
    bounced cheque's 100.00 charge read the same way (2026-10-17).
    """
    books = _books()
    _trading(books)
    _charge(books, kind)

    assert _bills_rows(_check(books)) == []


def test_a_charge_reversed_with_its_receipt_counts_nothing() -> None:
    books = _books()
    _trading(books)
    charge = _charge(books, CustomerReceivableTransactionType.TCS)
    CustomerService(books.session).reverse_receivable_transaction(
        charge, firm_scope=books.firm.id, actor_id=books.actor_id, on=WHEN
    )
    books.session.commit()

    assert _bills_rows(_check(books)) == []


def test_without_the_charge_it_reads_as_a_difference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books()
    _trading(books)
    _charge(books, CustomerReceivableTransactionType.TCS)
    monkeypatch.setattr(money_consistency, "_charges_on_no_bill", lambda *_: {})

    # The false positive the netting removes: 600.00 on the bill less 50.00
    # held, against an account that also carries the 19.64.
    assert _bills_rows(_check(books)) == [
        ("Customer C1", Decimal("569.64"), Decimal("550.00"))
    ]


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


def _stocked_firm(monkeypatch: pytest.MonkeyPatch) -> tuple[Session, Firm]:
    """Bring opening stock in at cost: Dr Inventory 1,050.00, stock the same."""
    from tests.unit.test_stock_valuation import _stocked

    monkeypatch.setattr(money_consistency, "firm_today", lambda *_: date(2026, 8, 15))
    return _stocked()


def _stock_rows(found: list[Difference]) -> list[tuple[str, Decimal, Decimal]]:
    return [
        (row.period, row.expected, row.actual)
        for row in found
        if row.check == STOCK_VS_INVENTORY
    ]


def test_stock_and_the_inventory_account_agree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, firm = _stocked_firm(monkeypatch)

    found = check_money_consistency(session, firm.id)

    assert _stock_rows(found) == []


def test_stock_that_moved_with_no_journal_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.inventory.models import InventoryTransaction
    from app.products.models import Product

    session, firm = _stocked_firm(monkeypatch)
    rice = session.scalars(select(Product).where(Product.code == "RICE")).one()
    moved = session.scalars(
        select(InventoryTransaction).where(InventoryTransaction.product_id == rice.id)
    ).first()
    assert moved is not None
    # Two more units counted onto the shelf, and nothing posted for them.
    copied = {
        attr.key: getattr(moved, attr.key)
        for attr in sa_inspect(InventoryTransaction).column_attrs
        if attr.key not in ("id", "version", "created_at", "updated_at")
    }
    copied.update(
        quantity=Decimal("2"),
        current_quantity_delta=Decimal("2"),
        owned_quantity_delta=None,
        reference_number="STOCK-ONLY-1",
    )
    session.add(InventoryTransaction(**copied))
    session.commit()

    found = check_money_consistency(session, firm.id)

    # The books hold 1,050.00; the shelf now holds two more at 50.00.
    assert _stock_rows(found) == [("2026-08", Decimal("1050.00"), Decimal("1150.00"))]


def _valued_at(
    monkeypatch: pytest.MonkeyPatch,
    total: str,
    items: list[tuple[str, str]],
) -> None:
    """Have the stock valuation report these (quantity, rate) items and total."""
    from app.inventory.services.stock_valuation import (
        StockValuationRow,
        StockValuationService,
    )

    def item(quantity: str, rate: str) -> StockValuationRow:
        return StockValuationRow(
            row_type="ITEM",
            product_code="P",
            product_name="P",
            category="",
            unit="",
            quantity=Decimal(quantity),
            rate=Decimal(rate),
            value=ZERO_VALUE,
        )

    rows = [item(quantity, rate) for quantity, rate in items]
    rows.append(
        StockValuationRow(
            row_type="TOTAL",
            product_code="",
            product_name="Grand total",
            category="",
            unit="",
            quantity=None,
            rate=None,
            value=Decimal(total),
        )
    )

    def valuation(*_: object, **__: object) -> list[StockValuationRow]:
        """Return the rows the test set."""
        return rows

    monkeypatch.setattr(StockValuationService, "valuation", valuation)


ZERO_VALUE = Decimal("0")

#: Two items held at averages of four places: D-STK-20 allows 0.01 + 2 x 0.01.
_UNEVEN = [("7", "50.0276"), ("3", "61.3333")]


def test_stock_within_the_d_stk_20_allowance_is_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, firm = _stocked_firm(monkeypatch)
    _valued_at(monkeypatch, "1050.03", _UNEVEN)

    assert _stock_rows(check_money_consistency(session, firm.id)) == []


def test_stock_beyond_the_d_stk_20_allowance_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, firm = _stocked_firm(monkeypatch)
    _valued_at(monkeypatch, "1050.04", _UNEVEN)

    found = check_money_consistency(session, firm.id)

    assert _stock_rows(found) == [("2026-08", Decimal("1050.00"), Decimal("1050.04"))]
    note = next(row.note for row in found if row.check == STOCK_VS_INVENTORY)
    assert "D-STK-20" in note
    assert "0.03" in note


def test_stock_at_two_decimal_averages_keeps_the_single_paisa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, firm = _stocked_firm(monkeypatch)
    # Two-place averages widen nothing, nor does an uneven item with no units.
    _valued_at(
        monkeypatch,
        "1050.02",
        [("7", "50.00"), ("3", "61.3000"), ("0", "9.3333")],
    )

    found = check_money_consistency(session, firm.id)

    assert _stock_rows(found) == [("2026-08", Decimal("1050.00"), Decimal("1050.02"))]
    note = next(row.note for row in found if row.check == STOCK_VS_INVENTORY)
    assert "D-STK-20" not in note


def _taxed_month(books: _Books) -> None:
    """Sell 100 + CGST 9 + SGST 9, and buy 200 + IGST 36, in April."""
    sale = books.sales_invoice("SI-T", "118.00")
    DocumentPostingService(books.session).post_sales_invoice(
        firm_id=books.firm.id,
        invoice_id=sale.id,
        invoice_number="SI-T",
        invoice_date=WHEN,
        taxable_amount=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        total_amount=Decimal("118.00"),
        actor_id=books.actor_id,
        tax_by_component={"CGST": Decimal("9.00"), "SGST": Decimal("9.00")},
    )
    bill = books.purchase_invoice("PI-T", "236.00")
    DocumentPostingService(books.session).post_purchase_invoice(
        firm_id=books.firm.id,
        invoice_id=bill.id,
        invoice_number="PI-T",
        invoice_date=WHEN,
        goods_amount=Decimal("200.00"),
        tax_amount=Decimal("36.00"),
        total_amount=Decimal("236.00"),
        actor_id=books.actor_id,
        tax_by_component={"IGST": Decimal("36.00")},
    )
    books.session.commit()


def _return_says(
    monkeypatch: pytest.MonkeyPatch, *, cgst: str = "9.00", igst_credit: str = "36"
) -> None:
    """Make GSTR-3B report April's figures, whatever the store holds."""
    from app.gst_returns.services.gstr_service import GstReturnService

    def gstr3b(_self: object, **_kwargs: object) -> dict[str, object]:
        return {
            "outward_taxable_supplies": {
                "integrated_tax": 0.0,
                "central_tax": float(cgst),
                "state_tax": 9.0,
            },
            "zero_rated_supplies": {"integrated_tax": 0.0},
            "net_itc": {
                "integrated_tax": float(igst_credit),
                "central_tax": 0.0,
                "state_tax": 0.0,
            },
        }

    monkeypatch.setattr(GstReturnService, "gstr3b", gstr3b)


def _gst_rows(found: list[Difference]) -> list[tuple[str, Decimal, Decimal]]:
    return [
        (row.document_ref, row.expected, row.actual)
        for row in _april(found, GST_VS_RETURN)
    ]


def test_gst_accounts_and_the_return_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    books = _books()
    _taxed_month(books)
    _return_says(monkeypatch)

    assert _gst_rows(_check(books)) == []


def test_a_gst_head_away_from_the_return_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books()
    _taxed_month(books)
    _return_says(monkeypatch, cgst="10.00", igst_credit="30")

    rows = _gst_rows(_check(books))

    assert [(expected, actual) for _, expected, actual in rows] == [
        (Decimal("9.00"), Decimal("10.00")),
        (Decimal("36.00"), Decimal("30.00")),
    ]
    assert "OUTPUT_TAX_CGST" in rows[0][0]
    assert "INPUT_TAX_IGST" in rows[1][0]


def test_the_gst_payment_is_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    books = _books()
    _taxed_month(books)
    _return_says(monkeypatch)
    posting = DocumentPostingService(books.session)
    context = posting.context_for(books.firm.id, WHEN)
    engine = JournalEntryEngine(books.session)
    # The month settled: output CGST cleared from the bank.
    entry = engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=context.journal_type_id,
        voucher_type_id=context.voucher_type_id,
        accounting_period_id=context.accounting_period_id,
        journal_date=WHEN,
        reference_number="GSTPAY-1",
        description="GST paid",
        lines=[
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.OUTPUT_TAX_CGST),
                debit_amount=Decimal("9.00"),
            ),
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.BANK),
                credit_amount=Decimal("9.00"),
            ),
        ],
        source_module=money_consistency.GST_PAYMENT_MODULE,
        source_id=uuid4(),
        actor_id=books.actor_id,
    )
    engine.post_entry(entry.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    assert _gst_rows(_check(books)) == []


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


def _withheld(books: _Books) -> None:
    """Trade with tax at source each way, the way the services post it.

    A customer deducts 10.00 TDS from a receipt, the firm deducts 5.00 from
    a payment, a supplier charges 7.00 TCS on a bill, and the firm collects
    3.00 TCS on a receipt.
    """
    sale = _sale(books, "SI-W", "1000.00")
    for service, party, amount, tds, invoice in (
        (ReceiptService, books.customer.id, "400.00", "10.00", sale.id),
        (PaymentService, books.vendor.id, "200.00", "5.00", None),
    ):
        service(books.session).create(
            SettlementCreate(
                party_id=party,
                settlement_date=WHEN,
                amount=Decimal(amount),
                method=SettlementMethodEnum.BANK,
                tds_amount=Decimal(tds),
                tds_section="194Q",
                allocations=(
                    [
                        SettlementAllocationWrite(
                            invoice_id=invoice, amount=Decimal(amount)
                        )
                    ]
                    if invoice is not None
                    else []
                ),
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    bill = books.purchase_invoice("PI-W", "700.00")
    bill.tcs_amount = Decimal("7.00")
    DocumentPostingService(books.session).post_purchase_invoice(
        firm_id=books.firm.id,
        invoice_id=bill.id,
        invoice_number="PI-W",
        invoice_date=WHEN,
        goods_amount=Decimal("700.00"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("700.00"),
        actor_id=books.actor_id,
        tcs_amount=Decimal("7.00"),
    )
    receipt = books.session.scalars(
        select(Settlement).where(Settlement.direction == "RECEIPT")
    ).one()
    collection = TcsCollection(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        settlement_id=receipt.id,
        financial_year_start=APRIL,
        collected_on=WHEN,
        consideration_amount=Decimal("400.00"),
        cumulative_before=Decimal("0"),
        taxable_amount=Decimal("3000.00"),
        rate_percent=Decimal("0.1"),
        tcs_amount=Decimal("3.00"),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(collection)
    books.session.flush()
    DocumentPostingService(books.session).post_tcs_collection(
        firm_id=books.firm.id,
        collection_id=collection.id,
        reference="TCS-W",
        collected_on=WHEN,
        amount=Decimal("3.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()


def _at_source_rows(found: list[Difference]) -> list[tuple[str, Decimal, Decimal]]:
    return [
        (row.document_ref, row.expected, row.actual)
        for row in found
        if row.check == TAX_AT_SOURCE_VS_REGISTER
    ]


def test_tds_and_tcs_accounts_agree_with_their_registers() -> None:
    books = _books()
    _withheld(books)

    assert _at_source_rows(_check(books)) == []


def test_each_tds_and_tcs_register_is_read() -> None:
    """The clean case is not clean because nothing was read."""
    books = _books()
    _withheld(books)

    held = {
        purpose: money_consistency._tax_at_source_register(
            books.session, books.firm.id, purpose, date(2026, 6, 15)
        )
        for purpose in (
            ControlAccountPurpose.TDS_PAYABLE,
            ControlAccountPurpose.TDS_RECEIVABLE,
            ControlAccountPurpose.TCS_PAYABLE,
            ControlAccountPurpose.TCS_RECEIVABLE,
        )
    }

    assert held == {
        ControlAccountPurpose.TDS_PAYABLE: Decimal("5.00"),
        ControlAccountPurpose.TDS_RECEIVABLE: Decimal("10.00"),
        ControlAccountPurpose.TCS_PAYABLE: Decimal("3.00"),
        ControlAccountPurpose.TCS_RECEIVABLE: Decimal("7.00"),
    }


def test_a_deduction_away_from_its_journal_is_found() -> None:
    books = _books()
    _withheld(books)
    payment = books.session.scalars(
        select(Settlement).where(Settlement.direction == "PAYMENT")
    ).one()
    payment.tds_amount = Decimal("8.00")  # the register now says more
    books.session.commit()

    rows = _at_source_rows(_check(books))

    assert [(expected, actual) for _, expected, actual in rows] == [
        (Decimal("5.00"), Decimal("8.00"))
    ]
    assert "TDS_PAYABLE" in rows[0][0]


def test_tcs_undone_without_its_journal_is_found() -> None:
    books = _books()
    _withheld(books)
    collection = books.session.scalars(select(TcsCollection)).one()
    collection.status = TcsCollectionStatus.REVERSED.value
    bill = books.session.scalars(
        select(PurchaseInvoice).where(PurchaseInvoice.invoice_number == "PI-W")
    ).one()
    bill.status = "CANCELLED"
    books.session.commit()

    rows = _at_source_rows(_check(books))

    assert [(expected, actual) for _, expected, actual in rows] == [
        (Decimal("3.00"), Decimal("0.00")),
        (Decimal("7.00"), Decimal("0.00")),
    ]
    assert "TCS_PAYABLE" in rows[0][0]
    assert "TCS_RECEIVABLE" in rows[1][0]


def test_a_hand_journal_on_tcs_payable_is_not_counted() -> None:
    """TCS paid over is a hand journal no register records."""
    books = _books()
    _withheld(books)
    posting = DocumentPostingService(books.session)
    context = posting.context_for(books.firm.id, WHEN)
    engine = JournalEntryEngine(books.session)
    entry = engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=context.journal_type_id,
        voucher_type_id=context.voucher_type_id,
        accounting_period_id=context.accounting_period_id,
        journal_date=WHEN,
        reference_number="JV-TCS-1",
        description="TCS paid over",
        lines=[
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.TCS_PAYABLE),
                debit_amount=Decimal("3.00"),
            ),
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.BANK),
                credit_amount=Decimal("3.00"),
            ),
        ],
        actor_id=books.actor_id,
    )
    engine.post_entry(entry.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    assert _at_source_rows(_check(books)) == []


def test_a_firm_with_no_tds_or_tcs_accounts_is_not_checked() -> None:
    books = _books()
    _withheld(books)

    found = money_consistency._tax_at_source_vs_registers(
        books.session, books.firm.id, {}, date(2026, 6, 15)
    )

    assert found == []


# ---- 8. loyalty payable against the points held ------------------------------


def _points(
    books: _Books,
    kind: LoyaltyEntryKind,
    points: str,
    amount: str,
    on: date,
    *,
    expires_on: date | None = None,
    post: bool = True,
) -> LoyaltyEntry:
    """Write one loyalty movement and post it the way the service does."""
    entry = LoyaltyEntry(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        kind=kind.value,
        points=Decimal(points),
        amount=Decimal(amount),
        earned_on=on,
        expires_on=expires_on,
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(entry)
    books.session.flush()
    if post:
        posted = DocumentPostingService(books.session).post_loyalty(
            firm_id=books.firm.id,
            entry_id=entry.id,
            reference=f"LOY-{entry.id.hex[:8]}",
            on=on,
            amount=Decimal(amount),
            earning=Decimal(points) > 0,
            actor_id=books.actor_id,
        )
        entry.journal_entry_id = None if posted is None else posted.id
    books.session.commit()
    return entry


def _loyal(books: _Books) -> None:
    """Earn 100 points at 50.00, spend 20 (10.00), and let a 20.00 batch lapse.

    The lapsed batch is past its date and not yet swept, so Loyalty Payable
    still carries it: 50.00 + 20.00 - 10.00 = 60.00.
    """
    _points(books, LoyaltyEntryKind.EARNED, "100", "50.00", date(2026, 4, 10))
    _points(
        books,
        LoyaltyEntryKind.EARNED,
        "40",
        "20.00",
        date(2026, 4, 20),
        expires_on=date(2026, 5, 31),
    )
    _points(books, LoyaltyEntryKind.REDEEMED, "-20", "10.00", date(2026, 5, 2))


def _loyalty_rows(found: list[Difference]) -> list[tuple[str, Decimal, Decimal]]:
    return [
        (row.document_ref, row.expected, row.actual)
        for row in found
        if row.check == LOYALTY_VS_LEDGER
    ]


def test_loyalty_payable_agrees_with_the_points_held() -> None:
    books = _books()
    _loyal(books)

    assert _loyalty_rows(_check(books)) == []


def test_the_points_held_are_read_at_cost() -> None:
    """The clean case is not clean because nothing was read."""
    books = _books()
    _loyal(books)

    assert money_consistency._loyalty_held(books.session, books.firm.id) == Decimal(
        "60.00"
    )


def test_points_earned_with_no_journal_are_found() -> None:
    books = _books()
    _loyal(books)
    _points(books, LoyaltyEntryKind.EARNED, "30", "15.00", WHEN, post=False)

    rows = _loyalty_rows(_check(books))

    assert [(expected, actual) for _, expected, actual in rows] == [
        (Decimal("60.00"), Decimal("75.00"))
    ]
    assert "LOYALTY_PAYABLE" in rows[0][0]


def _hand_journal(
    books: _Books, purpose: ControlAccountPurpose, reference: str, amount: str
) -> None:
    """Credit an account by hand against the bank, as an opening balance is."""
    context = DocumentPostingService(books.session).context_for(books.firm.id, WHEN)
    engine = JournalEntryEngine(books.session)
    entry = engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=context.journal_type_id,
        voucher_type_id=context.voucher_type_id,
        accounting_period_id=context.accounting_period_id,
        journal_date=WHEN,
        reference_number=reference,
        description="Typed by hand",
        lines=[
            JournalLineData(
                ledger_account_id=books.account(ControlAccountPurpose.BANK),
                debit_amount=Decimal(amount),
            ),
            JournalLineData(
                ledger_account_id=books.account(purpose),
                credit_amount=Decimal(amount),
            ),
        ],
        actor_id=books.actor_id,
    )
    engine.post_entry(entry.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()


def test_a_hand_journal_on_loyalty_payable_is_not_counted() -> None:
    books = _books()
    _loyal(books)
    _hand_journal(books, ControlAccountPurpose.LOYALTY_PAYABLE, "JV-LOY-1", "12.00")

    assert _loyalty_rows(_check(books)) == []


# ---- 9. commission payable against the payouts -------------------------------


def _payout(
    books: _Books, salesman: Salesman, month: int, amount: str, status: str
) -> CommissionPayout:
    """Write a payout and post what its status would have posted."""
    start = date(2026, month, 1)
    row = CommissionPayout(
        firm_id=books.firm.id,
        salesman_id=salesman.id,
        period_start=start,
        period_end=date(2026, month, 28),
        earned_amount=Decimal(amount),
        payable_amount=Decimal(amount),
        status=status,
        accrued_on=date(2026, month, 28),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.flush()
    posting = DocumentPostingService(books.session)
    reference = f"COM-{month}"
    if status != CommissionPayoutStatus.DRAFT.value:
        accrual = posting.post_commission_accrual(
            firm_id=books.firm.id,
            payout_id=row.id,
            reference=reference,
            accrued_on=row.accrued_on,
            amount=Decimal(amount),
            actor_id=books.actor_id,
        )
        row.journal_entry_id = accrual.id
    if status == CommissionPayoutStatus.PAID.value:
        paid = posting.post_commission_payment(
            firm_id=books.firm.id,
            payout_id=row.id,
            reference=f"{reference}-PAY",
            paid_on=row.accrued_on,
            amount=Decimal(amount),
            money_account_id=books.account(ControlAccountPurpose.BANK),
            actor_id=books.actor_id,
        )
        row.payment_journal_entry_id = paid.id
    if status == CommissionPayoutStatus.CANCELLED.value:
        assert row.journal_entry_id is not None
        JournalEntryEngine(books.session).reverse_entry(
            row.journal_entry_id,
            firm_id=books.firm.id,
            reference_number=f"{reference}-REV",
            journal_date=row.accrued_on,
            actor_id=books.actor_id,
        )
    books.session.commit()
    return row


def _commissioned(books: _Books) -> Salesman:
    """One salesman: April paid, May approved, June cancelled, a draft for July."""
    salesman = Salesman(
        firm_id=books.firm.id,
        name="Salesman One",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(salesman)
    books.session.commit()
    _payout(books, salesman, 4, "200.00", CommissionPayoutStatus.PAID.value)
    _payout(books, salesman, 5, "300.00", CommissionPayoutStatus.APPROVED.value)
    _payout(books, salesman, 6, "150.00", CommissionPayoutStatus.CANCELLED.value)
    return salesman


def _commission_rows(found: list[Difference]) -> list[tuple[str, Decimal, Decimal]]:
    return [
        (row.document_ref, row.expected, row.actual)
        for row in found
        if row.check == COMMISSION_VS_PAYOUTS
    ]


def test_commission_payable_agrees_with_the_payouts() -> None:
    books = _books()
    _commissioned(books)

    assert _commission_rows(_check(books)) == []


def test_an_approved_payout_with_no_journal_is_found() -> None:
    books = _books()
    salesman = _commissioned(books)
    stray = _payout(books, salesman, 3, "80.00", CommissionPayoutStatus.DRAFT.value)
    stray.status = CommissionPayoutStatus.APPROVED.value  # approved, never posted
    books.session.commit()

    rows = _commission_rows(_check(books))

    assert [(expected, actual) for _, expected, actual in rows] == [
        (Decimal("300.00"), Decimal("380.00"))
    ]
    assert "COMMISSION_PAYABLE" in rows[0][0]


def test_a_hand_journal_on_commission_payable_is_not_counted() -> None:
    books = _books()
    _commissioned(books)
    _hand_journal(books, ControlAccountPurpose.COMMISSION_PAYABLE, "JV-COM-1", "40.00")

    assert _commission_rows(_check(books)) == []


def test_loyalty_and_commission_are_skipped_without_their_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books()
    _loyal(books)
    _points(books, LoyaltyEntryKind.EARNED, "30", "15.00", WHEN, post=False)
    salesman = _commissioned(books)
    stray = _payout(books, salesman, 3, "80.00", CommissionPayoutStatus.DRAFT.value)
    stray.status = CommissionPayoutStatus.APPROVED.value
    books.session.commit()
    mapping = ControlAccountService.mapping
    unmapped = {
        ControlAccountPurpose.LOYALTY_PAYABLE.value,
        ControlAccountPurpose.COMMISSION_PAYABLE.value,
    }

    def _without(self: ControlAccountService, firm_id: UUID) -> dict[str, UUID]:
        return {
            purpose: account
            for purpose, account in mapping(self, firm_id).items()
            if purpose not in unmapped
        }

    monkeypatch.setattr(ControlAccountService, "mapping", _without)

    found = _check(books)

    assert _loyalty_rows(found) == []
    assert _commission_rows(found) == []
