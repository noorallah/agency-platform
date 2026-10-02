"""A debit note to a customer: more charged on an invoice already raised.

Backlog 77 row 5. GST allows one instrument for raising the value of a supply
already invoiced -- a debit note against that invoice (CGST Act s.34(3)) --
and the selling side had none. The cases that decide whether it can be
trusted:

- the tax is charged at the rate the **invoice** charged;
- approving posts Dr receivable, Cr sales and output tax, *and* raises the
  balance; cancelling undoes both;
- the extra is owed **on the invoice** (A40): Record Receipt offers it, a
  receipt can settle it, the ageing ages it;
- GSTR-1 declares it as note type D and 3B adds it to 3.1(a);
- an invoice with a live debit note cannot be cancelled from under it.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.customer_debit_note.models import CustomerDebitNote, CustomerDebitNoteStatus
from app.customer_debit_note.schemas import (
    CustomerDebitNoteCreate,
    CustomerDebitNoteLineWrite,
    CustomerDebitNoteReasonEnum,
    CustomerDebitNoteUpdate,
)
from app.customer_debit_note.services import CustomerDebitNoteService
from app.customers.models import CustomerReceivableTransaction
from app.customers.services.statement_service import CustomerStatementService
from app.finance.models import JournalEntry
from app.finance.services.control_accounts import ControlAccountPurpose
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services.sales_analysis import SalesAnalysisService
from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService
from app.settlements.models import Settlement, SettlementAllocation
from app.settlements.services.settlement_service import ReceiptService
from tests.unit.test_credit_note import WHEN, _Books, _session_factory
from tests.unit.test_gst_returns import _Books as _FilingBooks
from tests.unit.test_gst_returns import _session_factory as _filing_session

pytestmark = pytest.mark.typed_document_numbers


def _payload(books: _Books, taxable: str = "100") -> CustomerDebitNoteCreate:
    """Charge more on the invoice's one line."""
    return CustomerDebitNoteCreate(
        sales_invoice_id=books.invoice.id,
        debit_note_date=WHEN,
        reason=CustomerDebitNoteReasonEnum.PRICE_INCREASE,
        lines=[
            CustomerDebitNoteLineWrite(
                sales_invoice_line_id=books.line.id,
                line_number=1,
                quantity=Decimal("10"),
                taxable_amount=Decimal(taxable),
            )
        ],
    )


def _raised(books: _Books, taxable: str = "100") -> CustomerDebitNote:
    """Raise one draft debit note."""
    row = CustomerDebitNoteService(books.session).create_note(
        _payload(books, taxable), firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    return row


def _approved(books: _Books, taxable: str = "100") -> CustomerDebitNote:
    """Raise and approve one debit note."""
    row = _raised(books, taxable)
    CustomerDebitNoteService(books.session).approve_note(
        row.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    return row


def test_the_tax_is_charged_at_the_rate_the_invoice_charged() -> None:
    """100 more on a line taxed at 18% charges 18 of tax."""
    books = _Books(_session_factory()())

    note = _raised(books)

    assert note.debit_note_number.startswith("SDN")
    assert note.taxable_amount == Decimal("100.00")
    assert note.tax_amount == Decimal("18.00")
    assert note.total_amount == Decimal("118.00")


def test_a_preview_prices_the_note_and_saves_nothing() -> None:
    """The screen's tax is the note's, and nothing lands."""
    books = _Books(_session_factory()())

    preview = CustomerDebitNoteService(books.session).preview_note(
        _payload(books), firm_id=books.firm.id, actor_id=books.actor_id
    )

    assert preview.total_amount == Decimal("118.00")
    assert preview.lines[0].tax_rate_percent == Decimal("18.00")
    count = select(func.count()).select_from(CustomerDebitNote)
    assert books.session.scalar(count) == 0


def test_approving_posts_the_receivable_the_sale_and_the_tax() -> None:
    """Dr receivable 118, Cr sales 100, Cr output tax 18 -- a sale's accounts."""
    books = _Books(_session_factory()())

    note = _approved(books)

    assert note.status == CustomerDebitNoteStatus.APPROVED.value
    assert note.journal_entry_id is not None
    legs = books.legs(note.journal_entry_id)
    assert legs[books.account(ControlAccountPurpose.ACCOUNTS_RECEIVABLE)] == (
        Decimal("118.00"),
        Decimal("0.00"),
    )
    assert legs[books.account(ControlAccountPurpose.SALES_REVENUE)] == (
        Decimal("0.00"),
        Decimal("100.00"),
    )
    assert legs[books.account(ControlAccountPurpose.OUTPUT_TAX)] == (
        Decimal("0.00"),
        Decimal("18.00"),
    )


def test_approving_raises_what_the_customer_owes() -> None:
    """Both books, or neither."""
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("1180.00")
    books.session.commit()

    note = _approved(books)
    books.session.refresh(books.customer)

    assert books.customer.current_outstanding == Decimal("1298.0000")
    row = books.session.scalars(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.id == note.receivable_transaction_id
        )
    ).one()
    assert row.transaction_type == "DEBIT_NOTE"
    assert row.reference_number == note.debit_note_number


def test_cancelling_reverses_the_journal_and_the_balance() -> None:
    """A posted entry is mirrored, never deleted."""
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("1180.00")
    books.session.commit()
    note = _approved(books)
    original = note.journal_entry_id

    CustomerDebitNoteService(books.session).cancel_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    books.session.refresh(books.customer)

    mirror = books.session.scalars(
        select(JournalEntry).where(JournalEntry.reversal_of_id == original)
    ).one()
    assert books.legs(mirror.id)[books.account(ControlAccountPurpose.OUTPUT_TAX)] == (
        Decimal("18.00"),
        Decimal("0.00"),
    )
    assert books.customer.current_outstanding == Decimal("1180.0000")


def test_record_receipt_offers_the_extra_on_the_invoice() -> None:
    """The debit note is owed on the bill it names (A40), not beside it."""
    books = _Books(_session_factory()())
    _approved(books)

    owing = ReceiptService(books.session).outstanding_invoices(
        firm_id=books.firm.id, party_id=books.customer.id
    )

    assert len(owing) == 1
    assert owing[0].invoice_id == books.invoice.id
    assert owing[0].invoice_total == Decimal("1298.00")
    assert owing[0].allocated_amount == Decimal("0.00")
    assert owing[0].outstanding_amount == Decimal("1298.00")


def test_the_ageing_ages_the_extra_with_the_invoice() -> None:
    """One derivation: the ageing and Record Receipt agree on the bill."""
    books = _Books(_session_factory()())
    _approved(books)

    ageing = CustomerStatementService(books.session).ageing(
        firm_scope=books.firm.id, customer_id=books.customer.id, as_of=WHEN
    )

    assert ageing[0].total_outstanding == Decimal("1298.00")


def _pay(books: _Books, amount: str) -> None:
    """Record money allocated to the invoice, as a posted receipt leaves it."""
    receipt = Settlement(
        firm_id=books.firm.id,
        direction="RECEIPT",
        customer_id=books.customer.id,
        settlement_number="RC-1",
        settlement_date=WHEN,
        method="CASH",
        status="POSTED",
        amount=Decimal(amount),
        ledger_account_id=books.account(ControlAccountPurpose.ACCOUNTS_RECEIVABLE),
        journal_entry_id=books.session.scalars(select(JournalEntry.id)).first(),
    )
    books.session.add(receipt)
    books.session.flush()
    books.session.add(
        SettlementAllocation(
            firm_id=books.firm.id,
            settlement_id=receipt.id,
            sales_invoice_id=books.invoice.id,
            amount=Decimal(amount),
        )
    )
    books.session.commit()


def test_a_note_already_paid_for_cannot_be_cancelled() -> None:
    """Undoing a charge money has met would leave the receipt over-settling."""
    books = _Books(_session_factory()())
    note = _approved(books)
    _pay(books, "1250.00")

    with pytest.raises(ValidationError, match="Reverse that receipt"):
        CustomerDebitNoteService(books.session).cancel_note(
            note.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )


def test_a_note_the_money_has_not_reached_can_be_cancelled() -> None:
    """Paying only the invoice leaves the extra free to withdraw."""
    books = _Books(_session_factory()())
    note = _approved(books)
    _pay(books, "1180.00")

    cancelled = CustomerDebitNoteService(books.session).cancel_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )

    assert cancelled.status == CustomerDebitNoteStatus.CANCELLED.value


def test_an_invoice_with_a_live_debit_note_cannot_be_cancelled() -> None:
    """The note would charge more on a sale that had been undone."""
    books = _Books(_session_factory()())
    note = _raised(books)

    with pytest.raises(ValidationError, match=note.debit_note_number):
        SalesInvoiceService(books.session).cancel_invoice(
            books.invoice.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )


def test_a_draft_invoice_takes_no_debit_note() -> None:
    """A draft is not a sale yet; change it instead."""
    books = _Books(_session_factory()())
    books.invoice.status = "DRAFT"
    books.session.commit()

    with pytest.raises(ValidationError, match="approved invoice"):
        _raised(books)


def test_a_note_cannot_be_dated_before_its_invoice() -> None:
    """It corrects a supply that had not happened yet."""
    books = _Books(_session_factory()())
    payload = _payload(books)
    payload.debit_note_date = date(2026, 4, 1)

    with pytest.raises(ValidationError, match="before invoice"):
        CustomerDebitNoteService(books.session).create_note(
            payload, firm_id=books.firm.id, actor_id=books.actor_id
        )


def test_an_approved_note_cannot_be_edited() -> None:
    """Cancel and raise another; the posted one is history."""
    books = _Books(_session_factory()())
    note = _approved(books)

    with pytest.raises(ValidationError, match="Only a draft"):
        CustomerDebitNoteService(books.session).update_note(
            note.id,
            CustomerDebitNoteUpdate(remarks="later"),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_editing_the_lines_reprices_the_draft() -> None:
    """A list replaces the lines; an omitted field is left alone."""
    books = _Books(_session_factory()())
    note = _raised(books)
    service = CustomerDebitNoteService(books.session)

    service.update_note(
        note.id,
        CustomerDebitNoteUpdate(
            lines=[
                CustomerDebitNoteLineWrite(
                    sales_invoice_line_id=books.line.id,
                    line_number=1,
                    taxable_amount=Decimal("50"),
                )
            ]
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert note.total_amount == Decimal("59.00")
    assert note.reason == CustomerDebitNoteReasonEnum.PRICE_INCREASE.value
    assert len(service.lines_of(note)) == 1


def test_the_sales_analysis_counts_the_extra_as_sales() -> None:
    """More of a sale already made, whether or not returns are netted off."""
    books = _Books(_session_factory()())
    _approved(books)

    for netted in (True, False):
        analysis = SalesAnalysisService(books.session).analyse(
            books.firm.id,
            rows="customer",
            columns=None,
            from_date=WHEN,
            to_date=WHEN,
            net_of_returns=netted,
        )
        assert analysis.grand_total.taxable == Decimal("1100.00")
        # Value, not units: the goods were counted on the invoice.
        assert analysis.grand_total.quantity == Decimal("10")


def _filing_debit(
    books: _FilingBooks, invoice: SalesInvoice, *, taxable: str, tax: str
) -> None:
    """Approve a debit note on an invoice, as the service leaves it."""
    from app.customer_debit_note.models import CustomerDebitNoteLine
    from app.sales_invoice.models import SalesInvoiceLine

    line = books.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    ).one()
    note = CustomerDebitNote(
        firm_id=books.firm.id,
        customer_id=invoice.customer_id,
        branch_id=books.branch.id,
        sales_invoice_id=invoice.id,
        debit_note_number="SDN-1",
        debit_note_date=date(2026, 4, 25),
        reason="PRICE_INCREASE",
        status="APPROVED",
        taxable_amount=Decimal(taxable),
        tax_amount=Decimal(tax),
        total_amount=Decimal(taxable) + Decimal(tax),
    )
    books.session.add(note)
    books.session.flush()
    books.session.add(
        CustomerDebitNoteLine(
            debit_note_id=note.id,
            firm_id=books.firm.id,
            line_number=1,
            sales_invoice_line_id=line.id,
            product_id=books.product.id,
            quantity=Decimal("10"),
            taxable_amount=Decimal(taxable),
            tax_rate_percent=Decimal("18"),
            tax_amount=Decimal(tax),
            total_amount=Decimal(taxable) + Decimal(tax),
        )
    )
    books.session.commit()


def test_a_registered_buyer_s_debit_note_is_declared_as_note_type_d() -> None:
    """CDNR, stated positive, with the note type the return asks for."""
    books = _FilingBooks(_filing_session()())
    invoice = books.invoice("SI-1")
    _filing_debit(books, invoice, taxable="100", tax="18")

    cdnr = books.gstr1()["cdnr"]

    assert len(cdnr) == 1
    assert cdnr[0]["note_number"] == "SDN-1"
    assert cdnr[0]["note_type"] == "D"
    assert cdnr[0]["document_type"] == "DEBIT_NOTE"
    assert cdnr[0]["against_invoice"] == "SI-1"
    assert cdnr[0]["taxable_value"] == 100.0
    assert (cdnr[0]["central_tax"], cdnr[0]["state_tax"]) == (9.0, 9.0)


def test_an_unregistered_buyer_s_debit_note_is_added_to_the_summary() -> None:
    """Netted onto the B2CS row the way a credit note is taken off it."""
    books = _FilingBooks(_filing_session()())
    invoice = books.invoice("SI-1", customer=books.walk_in)
    _filing_debit(books, invoice, taxable="100", tax="18")

    answer = books.gstr1()

    assert answer["cdnr"] == []
    assert answer["b2cs"][0]["taxable_value"] == 1100.0
    assert answer["b2cs"][0]["central_tax"] == 99.0


def test_the_hsn_summary_takes_the_value_and_no_units() -> None:
    """Table 12 is net of notes; a debit note adds value, not quantity."""
    books = _FilingBooks(_filing_session()())
    invoice = books.invoice("SI-1")
    _filing_debit(books, invoice, taxable="100", tax="18")

    hsn = books.gstr1()["hsn"]

    assert len(hsn) == 1
    assert hsn[0]["taxable_value"] == 1100.0
    assert hsn[0]["quantity"] == 10.0


def test_3b_adds_debit_notes_to_outward_supplies() -> None:
    """3.1(a) carries the extra, and says so beside the credits."""
    books = _FilingBooks(_filing_session()())
    registered = books.invoice("SI-1")
    walk_in = books.invoice("SI-2", customer=books.walk_in)
    _filing_debit(books, registered, taxable="100", tax="18")
    books.credit("CN-1", walk_in, taxable="50", tax="9")

    summary = books.gstr3b()

    assert summary["outward_taxable_supplies"]["taxable_value"] == 2050.0
    assert summary["outward_taxable_supplies"]["central_tax"] == 184.5
    assert summary["credit_notes_deducted"]["taxable_value"] == 50.0
    assert summary["debit_notes_added"] == {"taxable_value": 100.0, "tax": 18.0}
