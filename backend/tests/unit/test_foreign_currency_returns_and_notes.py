"""D-BUY-41: a debit note or a return against a bill in another currency.

A supplier abroad bills 10 units at 100 USD at 83. A claim of 100 USD, or two
units sent back, is typed in the bill's currency and is worth that many
dollars at the **bill's** rate: the journal, what the bill still owes in both
currencies, the supplier's credit and the payables report all read rupees.

Sessions are shaped like a request's (no autoflush), as in the PG-12 tests.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.debit_note.models import DebitNote
from app.debit_note.schemas import DebitNoteCreate, DebitNoteLineWrite
from app.debit_note.services import DebitNoteService
from app.finance.services.control_accounts import ControlAccountPurpose
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.services.payables_report import PayablesReportService
from app.purchase_return.models import PurchaseReturn
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services import PurchaseReturnService
from app.settlements.services.supplier_credits import supplier_credits
from tests.unit.test_cash_purchase import _chain_firm
from tests.unit.test_foreign_currency_bills import _pay, _record, _usd_bill
from tests.unit.test_imports_and_assets_through_the_chain import (
    _bill_data,
    _billed,
    _capital_line,
    _order,
    _receive,
)
from tests.unit.test_imports_and_assets_through_the_chain import _firm as _whole_chain
from tests.unit.test_purchase_chain_synthesis import _Firm

pytestmark = pytest.mark.typed_document_numbers

WHEN = date(2026, 8, 15)
AS_OF = date(2026, 8, 31)


def _line(firm: _Firm, bill: PurchaseInvoice) -> PurchaseInvoiceLine:
    """Return the bill's one line."""
    return firm.session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()


def _claim(firm: _Firm, bill: PurchaseInvoice, taxable: str) -> DebitNote:
    """Raise and approve a debit note for an amount in the bill's currency."""
    service = DebitNoteService(firm.session)
    note = service.create_note(
        DebitNoteCreate(
            purchase_invoice_id=bill.id,
            debit_note_date=WHEN,
            lines=[
                DebitNoteLineWrite(
                    purchase_invoice_line_id=_line(firm, bill).id,
                    line_number=1,
                    taxable_amount=Decimal(taxable),
                )
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()
    service.approve_note(note.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.commit()
    return note


def _send_back(firm: _Firm, bill: PurchaseInvoice, quantity: str) -> PurchaseReturn:
    """Raise, approve and complete a return off the bill's line."""
    kind = PurchaseReturnSourceType.PURCHASE_INVOICE
    service = PurchaseReturnService(firm.session)
    row = service.create_return(
        PurchaseReturnCreate(
            return_date=WHEN,
            warehouse_id=firm.warehouse.id,
            source_documents=[
                {"source_document_type": kind, "source_document_id": bill.id}
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=kind,
                    source_document_id=bill.id,
                    source_document_line_id=_line(firm, bill).id,
                    line_number=1,
                    current_return_quantity=Decimal(quantity),
                    warehouse_id=firm.warehouse.id,
                )
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.approve_return(row.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    service.complete_return(row.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.commit()
    return row


def _books_agree(firm: _Firm) -> Decimal:
    """Return the payables report's total, having checked it against the books."""
    report = PayablesReportService(firm.session).report(
        firm.firm.id, as_of=AS_OF, months=3
    )
    assert report.books_check.difference == Decimal("0.00")
    return report.total.total


def test_a_debit_note_against_a_usd_bill_posts_rupees_at_the_bills_rate() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    _claim(firm, bill, "100")

    # 1,000 USD at 83 was owed; 100 USD of it is claimed back: 8,300 rupees.
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-74700.00")
    record = _record(firm, bill.id)
    assert record is not None
    assert (record.outstanding_amount, record.currency_outstanding) == (
        Decimal("74700.00"),
        Decimal("900.00"),
    )
    assert _books_agree(firm) == Decimal("74700.00")


def test_cancelling_the_note_puts_the_rupees_back() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)
    note = _claim(firm, bill, "100")

    DebitNoteService(firm.session).cancel_note(
        note.id, reason="Raised twice", firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    firm.session.commit()

    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-83000.00")
    record = _record(firm, bill.id)
    assert record is not None
    assert record.currency_outstanding == Decimal("1000.00")


def test_a_return_against_a_usd_bill_posts_rupees_at_the_bills_rate() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    sent_back = _send_back(firm, bill, "2")

    # The return carries its bill's currency and rate, whatever was typed.
    assert (sent_back.currency_code, sent_back.exchange_rate) == ("USD", Decimal("83"))
    # Two of ten units at 100 USD: 200 USD, 16,600 rupees, on both legs.
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-66400.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == Decimal("66400.00")
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0
    record = _record(firm, bill.id)
    assert record is not None
    assert (record.outstanding_amount, record.currency_outstanding) == (
        Decimal("66400.00"),
        Decimal("800.00"),
    )
    assert _books_agree(firm) == Decimal("66400.00")


def test_the_rest_of_the_bill_is_paid_in_its_currency_after_a_return() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)
    _send_back(firm, bill, "2")

    # 800 USD is all the bill still owes; paid at the bill's own rate.
    _pay(firm, bill, amount="800", rate="83")

    assert _record(firm, bill.id) is None
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("0.00")
    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == 0


def test_a_return_against_a_paid_usd_bill_is_a_credit_in_rupees() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)
    _pay(firm, bill, amount="1000", rate="83")

    sent_back = _send_back(firm, bill, "2")

    (credit,) = supplier_credits(
        firm.session, firm_id=firm.firm.id, vendor_id=firm.vendor.id
    )
    assert credit.purchase_return_id == sent_back.id
    assert credit.credit_amount == Decimal("16600.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("16600.00")


def test_cancelling_the_return_puts_the_rupees_back() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)
    sent_back = _send_back(firm, bill, "2")

    PurchaseReturnService(firm.session).cancel_return(
        sent_back.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    firm.session.commit()

    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-83000.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == Decimal("83000.00")


def _off_receipt(
    firm: _Firm, receipt_id: UUID, line_id: UUID, quantity: str
) -> PurchaseReturnCreate:
    """Describe a return of some of a receipt line."""
    kind = PurchaseReturnSourceType.GOODS_RECEIPT
    return PurchaseReturnCreate.model_validate(
        {
            "return_date": WHEN.isoformat(),
            "warehouse_id": firm.warehouse.id,
            "source_documents": [
                {"source_document_type": kind, "source_document_id": receipt_id}
            ],
            "lines": [
                {
                    "source_document_type": kind,
                    "source_document_id": receipt_id,
                    "source_document_line_id": line_id,
                    "line_number": 1,
                    "current_return_quantity": quantity,
                    "warehouse_id": firm.warehouse.id,
                }
            ],
        }
    )


def test_a_return_off_the_receipt_goes_back_at_the_bills_rate() -> None:
    """Ordered and received at 83, billed at 84: the payable comes off at 84."""
    firm = _whole_chain()
    order = _order(firm, currency_code="USD", exchange_rate="83")
    receipt, received = _receive(firm, order)
    _billed(firm, _bill_data(receipt, received, exchange_rate="84"))
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-84000.00")

    service = PurchaseReturnService(firm.session)
    row = service.create_return(
        _off_receipt(firm, receipt.id, received.id, "2"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    # Raised in the order's currency, at the order's rate until it completes.
    assert (row.currency_code, row.exchange_rate) == ("USD", Decimal("83"))
    service.approve_return(row.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    service.complete_return(row.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.commit()

    assert row.exchange_rate == Decimal("84")
    # 200 USD at the bill's 84 comes off the payable; the stock leaves at the
    # 83 it was carried at, and the 200 between them is the variance undone.
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-67200.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == Decimal("66400.00")
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == Decimal(
        "800.00"
    )
    assert _books_agree(firm) == Decimal("67200.00")


def test_capital_goods_cannot_go_back_as_a_purchase_return() -> None:
    """Off the receipt or off the bill: it never entered stock (D-BUY-40)."""
    firm = _whole_chain()
    receipt, received = _receive(
        firm, _order(firm, quantity="1", price="100000", capital=True)
    )
    bill = _billed(
        firm, _bill_data(receipt, received, price="100000", line=_capital_line(firm))
    )
    service = PurchaseReturnService(firm.session)

    with pytest.raises(ValidationError, match="capital goods"):
        service.create_return(
            _off_receipt(firm, receipt.id, received.id, "1"),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    kind = PurchaseReturnSourceType.PURCHASE_INVOICE
    with pytest.raises(ValidationError, match="debit note"):
        service.create_return(
            PurchaseReturnCreate(
                return_date=WHEN,
                warehouse_id=firm.warehouse.id,
                source_documents=[
                    {"source_document_type": kind, "source_document_id": bill.id}
                ],
                lines=[
                    PurchaseReturnLineWrite(
                        source_document_type=kind,
                        source_document_id=bill.id,
                        source_document_line_id=_line(firm, bill).id,
                        line_number=1,
                        current_return_quantity=Decimal("1"),
                        warehouse_id=firm.warehouse.id,
                    )
                ],
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    assert firm.stock() == Decimal("0")
