"""PG-3 (§86 #19): a cash purchase approved and paid in one step.

A small trader buys over the counter and pays at once. The bill's approve
request carries an optional ``payment`` block; approving then also records an
ordinary payment -- the row ``POST /payments`` writes -- allocated to the bill,
in the same commit. A refused payment takes the approval back with it.

Every session here is shaped like a request's (no autoflush): the payment asks
what the bill owes straight after approving it, and a fixture that autoflushes
would hide an approval that was never flushed.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.exceptions import AuthorizationError, ValidationError
from app.finance.models import FirmControlAccount, GLPosting, LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.purchase_invoice.api.router import approve_purchase_invoice
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import (
    PurchaseInvoiceApproveRequest,
    PurchaseInvoicePaymentNow,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.settlements.models import Settlement, SettlementAllocation
from app.settlements.schemas import SettlementMethodEnum, SettlementModeEnum
from app.settlements.services import PaymentService
from tests.unit.test_purchase_chain_synthesis import _Firm
from tests.unit.test_sales_order_module import _principal
from tests.unit.test_settlements import WHEN, _Books

pytestmark = pytest.mark.typed_document_numbers

APPROVER = {"PURCHASE_APPROVE", "PURCHASE_APPROVE_OVER_TOLERANCE"}


def _books() -> _Books:
    """Seed a firm on a session that does not autoflush, as a request's does not."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    return _Books(factory())


def _draft_bill(books: _Books, total: str = "708.00") -> PurchaseInvoice:
    """Add one draft supplier bill, ready to approve."""
    PurchaseInvoiceService(books.session)._ensure_document_setup(
        firm_id=books.firm.id, actor_id=books.actor_id
    )
    row = PurchaseInvoice(
        firm_id=books.firm.id,
        vendor_id=books.vendor.id,
        branch_id=books.branch_id,
        invoice_number="PI-CASH-1",
        invoice_date=WHEN,
        supplier_invoice_number="S-CASH-1",
        supplier_invoice_date=WHEN,
        status="DRAFT",
        grand_total=Decimal(total),
        tax_total=Decimal("0"),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _scope(books: _Books, *codes: str) -> ResolvedFirmScope:
    """Return the scope the approve handler receives once authorized."""
    return ResolvedFirmScope(
        principal=_principal(uuid4(), set(codes)), firm_id=books.firm.id
    )


def _approve(
    books: _Books,
    bill: PurchaseInvoice,
    payment: PurchaseInvoicePaymentNow | None,
    codes: set[str] | None = None,
) -> str:
    """Call the approve endpoint as a request would, returning its message."""
    response = approve_purchase_invoice(
        invoice_id=bill.id,
        scope=_scope(books, *(codes or APPROVER | {"PAYMENT_CREATE"})),
        data=(
            None if payment is None else PurchaseInvoiceApproveRequest(payment=payment)
        ),
        db=books.session,
    )
    return response.message or ""


def _status(books: _Books, bill_id: UUID) -> str:
    """Read a bill's status as stored."""
    books.session.expire_all()
    row = books.session.get(PurchaseInvoice, bill_id)
    assert row is not None
    return row.status


def _owed(books: _Books) -> dict[UUID, Decimal]:
    """Return what each of the vendor's bills still owes."""
    return {
        record.invoice_id: record.outstanding_amount
        for record in PaymentService(books.session).outstanding_invoices(
            firm_id=books.firm.id, party_id=books.vendor.id
        )
    }


def _payments(books: _Books) -> list[Settlement]:
    """Return every payment recorded."""
    return list(books.session.scalars(select(Settlement)).all())


def _postings(books: _Books, journal_id: UUID) -> dict[str, tuple[Decimal, Decimal]]:
    """Return debit and credit by account code for one journal."""
    rows = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == journal_id)
    ).all()
    return {code: (debit, credit) for code, debit, credit in rows}


def _code(books: _Books, purpose: ControlAccountPurpose) -> str:
    """Return the ledger code a purpose is mapped to."""
    account = books.session.get(LedgerAccount, books.account(purpose))
    assert account is not None
    return account.code


def test_the_bill_and_its_payment_are_one_commit() -> None:
    """Approved, paid in cash for the whole bill, allocated to it, posted."""
    books = _books()
    bill = _draft_bill(books)

    message = _approve(
        books, bill, PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH)
    )

    assert _status(books, bill.id) == "APPROVED"
    [payment] = _payments(books)
    assert payment.direction == "PAYMENT"
    assert payment.vendor_id == books.vendor.id
    assert payment.amount == Decimal("708.00")
    assert payment.settlement_date == WHEN, "defaults to the bill's date"
    assert payment.payment_mode == "CASH"
    assert payment.allocated_amount == Decimal("708.00")
    assert payment.unallocated_amount == Decimal("0.00")
    assert payment.settlement_number in message
    [allocation] = books.session.scalars(select(SettlementAllocation)).all()
    assert allocation.settlement_id == payment.id
    assert allocation.purchase_invoice_id == bill.id
    assert allocation.amount == Decimal("708.00")

    postings = _postings(books, payment.journal_entry_id)
    payable = _code(books, ControlAccountPurpose.ACCOUNTS_PAYABLE)
    cash = _code(books, ControlAccountPurpose.CASH)
    assert postings[payable] == (Decimal("708.00"), Decimal("0.00"))
    assert postings[cash] == (Decimal("0.00"), Decimal("708.00"))
    assert bill.id not in _owed(books), "paid in full"

    actions = set(books.session.scalars(select(AuditLog.action)).all())
    assert {"purchase_invoice.approved", "settlement.payment.recorded"} <= actions


def test_a_refused_payment_takes_the_approval_back_with_it() -> None:
    """No cash account mapped: no payment, and the bill is still a draft."""
    books = _books()
    bill = _draft_bill(books)
    cash = ControlAccountService(books.session).resolve(
        books.firm.id, ControlAccountPurpose.CASH
    )
    mapping = books.session.scalar(
        select(FirmControlAccount).where(
            FirmControlAccount.firm_id == books.firm.id,
            FirmControlAccount.ledger_account_id == cash,
        )
    )
    assert mapping is not None
    mapping.is_deleted = True
    books.session.commit()

    with pytest.raises(ValidationError, match="CASH"):
        _approve(
            books, bill, PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH)
        )

    assert _status(books, bill.id) == "DRAFT"
    assert _payments(books) == []
    assert _owed(books) == {}, "a draft owes nothing"


def test_more_than_the_bill_owes_is_refused_and_nothing_is_kept() -> None:
    """An overpayment is refused rather than kept as an advance."""
    books = _books()
    bill = _draft_bill(books)

    with pytest.raises(ValidationError, match="owes 708.00"):
        _approve(
            books,
            bill,
            PurchaseInvoicePaymentNow(
                method=SettlementMethodEnum.CASH, amount=Decimal("800.00")
            ),
        )

    assert _status(books, bill.id) == "DRAFT"
    assert _payments(books) == []


def test_a_part_payment_leaves_the_rest_outstanding() -> None:
    """Paid 500 of 708 by bank, on its own date and reference."""
    books = _books()
    bill = _draft_bill(books)
    paid_on = WHEN.replace(day=22)

    _approve(
        books,
        bill,
        PurchaseInvoicePaymentNow(
            method=SettlementMethodEnum.BANK,
            payment_mode=SettlementModeEnum.UPI,
            amount=Decimal("500.00"),
            payment_date=paid_on,
            instrument_reference="UPI-123",
        ),
    )

    [payment] = _payments(books)
    assert payment.amount == Decimal("500.00")
    assert payment.settlement_date == paid_on
    assert payment.instrument_reference == "UPI-123"
    bank = _code(books, ControlAccountPurpose.BANK)
    assert _postings(books, payment.journal_entry_id)[bank] == (
        Decimal("0.00"),
        Decimal("500.00"),
    )
    assert _owed(books) == {bill.id: Decimal("208.00")}


def test_reversing_the_payment_leaves_the_bill_owing() -> None:
    """The usual payment reversal; the bill stays approved and owes it all."""
    books = _books()
    bill = _draft_bill(books)
    _approve(books, bill, PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH))
    [payment] = _payments(books)

    PaymentService(books.session).reverse(
        payment.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="wrong"
    )
    books.session.commit()

    assert payment.status == "REVERSED"
    assert _status(books, bill.id) == "APPROVED"
    assert _owed(books) == {bill.id: Decimal("708.00")}


def test_a_payment_block_needs_the_payment_permission() -> None:
    """403 without PAYMENT_CREATE, and nothing is approved."""
    books = _books()
    bill = _draft_bill(books)

    with pytest.raises(AuthorizationError, match="PAYMENT_CREATE"):
        _approve(
            books,
            bill,
            PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH),
            codes=APPROVER,
        )
    assert AuthorizationError.status_code == 403
    assert _status(books, bill.id) == "DRAFT"

    # Without the block the same person approves the bill as before.
    _approve(books, bill, None, codes=APPROVER)
    assert _status(books, bill.id) == "APPROVED"
    assert _payments(books) == []


def test_without_a_block_the_approval_is_unchanged() -> None:
    """No body, or a body with no payment: approved, owing it all, no payment."""
    books = _books()
    bill = _draft_bill(books)

    response = approve_purchase_invoice(
        invoice_id=bill.id,
        scope=_scope(books, *APPROVER),
        data=PurchaseInvoiceApproveRequest(),
        db=books.session,
    )

    assert response.data is not None
    assert _status(books, bill.id) == "APPROVED"
    assert _payments(books) == []
    assert _owed(books) == {bill.id: Decimal("708.00")}


def test_a_cash_payment_cannot_name_a_bank_mode() -> None:
    """The block holds the mode to its method, as a payment does."""
    with pytest.raises(SchemaError, match="matching method"):
        PurchaseInvoicePaymentNow(
            method=SettlementMethodEnum.CASH, payment_mode=SettlementModeEnum.UPI
        )


def _chain_firm() -> _Firm:
    """Build a firm typing only the bill (§38), on a request-shaped session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    firm = _Firm(sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)())
    firm.stages(order=False, receipt=False)
    return firm


def test_a_bill_typed_alone_brings_the_goods_in_and_is_paid() -> None:
    """With the order and receipt switched off, one approval does all of it.

    The bill raised its own order and receipt when saved; approving it with
    the money completes the receipt, raises the payable and pays it.
    """
    firm = _chain_firm()
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )

    bills.approve_and_pay(
        bill.id,
        PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )

    order, receipt = firm.raised(bill)
    assert receipt.status == "COMPLETED"
    assert order.status == "RECEIVED"
    assert firm.stock() == Decimal("10")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.balance(ControlAccountPurpose.CASH) == Decimal("-1000")


def test_a_refused_payment_leaves_the_raised_receipt_a_draft() -> None:
    """The rollback reaches the receipt the approval would have completed."""
    firm = _chain_firm()
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )

    with pytest.raises(ValidationError, match="cannot be paid"):
        bills.approve_and_pay(
            bill.id,
            PurchaseInvoicePaymentNow(
                method=SettlementMethodEnum.CASH, amount=Decimal("1000.01")
            ),
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
        )

    firm.session.expire_all()
    _, receipt = firm.raised(bill)
    assert receipt.status == "DRAFT"
    assert firm.stock() == Decimal("0")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.session.scalars(select(Settlement)).all() == []
