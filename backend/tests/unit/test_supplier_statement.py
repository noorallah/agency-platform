"""The supplier statement and the balance confirmation letter (74 row 4).

A supplier has no sub-ledger of its own; what the firm owes is the bills still
owing. So the statement reads the payables lines of the general ledger and
traces each to its supplier through the document that posted it. The tests
hold it to the two things that make it trustworthy: it agrees with what the
bills still owe and with the payables account, and its running balance is in
the order things were dated, not the order they were keyed.
"""

# ruff: noqa: D103

import io
import zipfile
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.common import balance_confirmation
from app.common.balance_confirmation import (
    BalanceConfirmationService,
    PartySide,
    balance_sentence,
)
from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.api.router import (
    customer_balance_confirmation,
    customer_balance_confirmations,
)
from app.finance.models import GLPosting
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import DocumentPostingService
from app.party_adjustments.schemas import PartyAdjustmentKindEnum
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.services.invoice_pdf import PartyBlock
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService
from app.vendors.api.router import (
    vendor_balance_confirmation,
    vendor_balance_confirmations,
    vendor_statement,
)
from app.vendors.models import Vendor, VendorOpeningBill
from app.vendors.schemas.statement import SupplierStatement
from app.vendors.services.statement_service import SupplierStatementService
from tests.unit.test_invoice_print import _text_of
from tests.unit.test_party_adjustments import SUPPLIER, _approve, _draft, _on
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

YEAR = (date(2026, 4, 1), date(2027, 3, 31))


@pytest.fixture(autouse=True)
def _letterhead(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the firm without opening the platform store.

    `firm_party` reads `firms` through `platform_reader`, a real connection
    the unit suite does not have; the letterhead is not what these test.
    """
    monkeypatch.setattr(
        balance_confirmation,
        "firm_party",
        lambda firm_id: PartyBlock(name="Acme Firm", address_lines=["Main Road"]),
    )


def _books() -> _Books:
    return _Books(_session_factory()())


def _bill(books: _Books, number: str, total: str, when: date = WHEN) -> PurchaseInvoice:
    """Raise a supplier bill and post it, as approving one does."""
    row = books.purchase_invoice(number, total)
    row.invoice_date = when
    DocumentPostingService(books.session).post_purchase_invoice(
        firm_id=books.firm.id,
        invoice_id=row.id,
        invoice_number=number,
        invoice_date=when,
        goods_amount=Decimal(total),
        tax_amount=Decimal("0"),
        total_amount=Decimal(total),
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _pay(
    books: _Books,
    amount: str,
    when: date = WHEN,
    bill: PurchaseInvoice | None = None,
) -> Settlement:
    row = PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=when,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
            allocations=(
                [SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal(amount))]
                if bill is not None
                else []
            ),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _opening_bill(books: _Books, amount: str) -> VendorOpeningBill:
    row_id = uuid4()
    entry = DocumentPostingService(books.session).post_vendor_opening_bill(
        firm_id=books.firm.id,
        opening_bill_id=row_id,
        bill_number="OB-00001",
        posting_date=date(2026, 4, 1),
        amount=Decimal(amount),
        actor_id=books.actor_id,
    )
    row = VendorOpeningBill(
        id=row_id,
        firm_id=books.firm.id,
        vendor_id=books.vendor.id,
        bill_number="OB-00001",
        bill_date=date(2026, 3, 1),
        posting_date=date(2026, 4, 1),
        amount=Decimal(amount),
        journal_entry_id=entry.id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _statement(books: _Books, period: tuple[date, date] = YEAR) -> SupplierStatement:
    return SupplierStatementService(books.session).statement(
        books.vendor.id,
        firm_scope=books.firm.id,
        from_date=period[0],
        to_date=period[1],
    )


def _payables(books: _Books) -> Decimal:
    """Return what the payables account holds: credits less debits."""
    account = books.account(ControlAccountPurpose.ACCOUNTS_PAYABLE)
    total = books.session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.credit_amount - GLPosting.debit_amount), 0)
        ).where(GLPosting.ledger_account_id == account)
    )
    return Decimal(str(total)).quantize(Decimal("0.01"))


def _words(pdf: bytes) -> str:
    """Return the words a PDF prints, wrapped lines joined back up."""
    return _text_of(pdf).replace(" | ", " ")


def _open_bills(books: _Books) -> Decimal:
    return sum(
        (
            row.outstanding_amount
            for row in PaymentService(books.session).outstanding_invoices(
                firm_id=books.firm.id, party_id=books.vendor.id
            )
        ),
        Decimal("0.00"),
    )


# ---- the statement -----------------------------------------------------------


def test_the_statement_reconciles_to_the_open_bills_and_to_payables() -> None:
    books = _books()
    first = _bill(books, "PI-1", "1000.00", when=date(2026, 4, 5))
    second = _bill(books, "PI-2", "500.00", when=date(2026, 4, 6))
    _pay(books, "600.00", when=date(2026, 4, 10), bill=first)
    write_back = _draft(
        books,
        PartyAdjustmentKindEnum.SUPPLIER_WRITE_BACK,
        "100.00",
        allocations=[_on(SUPPLIER, second.id, "100.00")],
    )
    _approve(books, write_back)

    statement = _statement(books)

    assert statement.opening_balance == Decimal("0.00")
    assert [line.transaction_type for line in statement.lines] == [
        "BILL",
        "BILL",
        "PAYMENT",
        "ADJUSTMENT",
    ]
    assert statement.total_credit == Decimal("1500.00")
    assert statement.total_debit == Decimal("700.00")
    assert statement.closing_balance == Decimal("800.00")
    assert _open_bills(books) == Decimal("800.00")
    assert _payables(books) == Decimal("800.00")


def test_an_opening_bill_and_an_advance_are_on_the_account() -> None:
    books = _books()
    _opening_bill(books, "250.00")
    _pay(books, "400.00")  # on account, before any bill

    statement = _statement(books)

    assert [
        (line.transaction_type, line.credit, line.debit) for line in statement.lines
    ] == [
        ("OPENING_BILL", Decimal("250.00"), Decimal("0.00")),
        ("PAYMENT", Decimal("0.00"), Decimal("400.00")),
    ]
    # The firm has paid 150.00 more than it owed: an advance with the supplier.
    assert statement.closing_balance == Decimal("-150.00")
    assert _payables(books) == Decimal("-150.00")


def test_the_running_balance_is_recomputed_in_date_order() -> None:
    books = _books()
    # Keyed in this order: a payment on the 20th, then a bill dated the 10th.
    _pay(books, "300.00", when=date(2026, 4, 20))
    _bill(books, "PI-1", "1000.00", when=date(2026, 4, 10))
    _bill(books, "PI-2", "200.00", when=date(2026, 4, 25))

    statement = _statement(books)

    assert [
        (line.transaction_date, line.reference_number, line.balance)
        for line in statement.lines
    ] == [
        (date(2026, 4, 10), "PI-1", Decimal("1000.00")),
        (date(2026, 4, 20), statement.lines[1].reference_number, Decimal("700.00")),
        (date(2026, 4, 25), "PI-2", Decimal("900.00")),
    ]


def test_the_opening_balance_is_what_came_before_the_period() -> None:
    books = _books()
    _bill(books, "PI-1", "1000.00", when=date(2026, 4, 10))
    _pay(books, "300.00", when=date(2026, 5, 5))
    _bill(books, "PI-2", "200.00", when=date(2026, 5, 20))

    may = _statement(books, (date(2026, 5, 1), date(2026, 5, 31)))

    assert may.opening_balance == Decimal("1000.00")
    assert [line.balance for line in may.lines] == [
        Decimal("700.00"),
        Decimal("900.00"),
    ]
    assert may.closing_balance == Decimal("900.00")


def test_a_reversed_payment_shows_on_the_day_it_was_undone() -> None:
    books = _books()
    _bill(books, "PI-1", "1000.00", when=date(2026, 4, 5))
    payment = _pay(books, "400.00")
    PaymentService(books.session).reverse(
        payment.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Cheque bounced",
    )
    books.session.commit()

    statement = _statement(books)

    assert [line.transaction_type for line in statement.lines] == [
        "BILL",
        "PAYMENT",
        "PAYMENT_REVERSAL",
    ]
    assert statement.closing_balance == Decimal("1000.00")
    assert _payables(books) == Decimal("1000.00")


def test_another_supplier_s_documents_stay_off_the_statement() -> None:
    books = _books()
    _bill(books, "PI-1", "1000.00")
    other = Vendor(
        firm_id=books.firm.id,
        code="V2",
        name="Vendor Two",
        display_name="Vendor Two",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(other)
    books.session.commit()

    statement = SupplierStatementService(books.session).statement(
        other.id, firm_scope=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    assert statement.lines == []
    assert statement.closing_balance == Decimal("0.00")


def test_a_period_that_runs_backwards_and_a_stranger_are_refused() -> None:
    books = _books()
    service = SupplierStatementService(books.session)
    with pytest.raises(ValidationError):
        service.statement(
            books.vendor.id,
            firm_scope=books.firm.id,
            from_date=date(2026, 5, 1),
            to_date=date(2026, 4, 1),
        )
    with pytest.raises(ResourceNotFoundError):
        service.statement(
            books.vendor.id, firm_scope=uuid4(), from_date=YEAR[0], to_date=YEAR[1]
        )


# ---- balance confirmation ------------------------------------------------------


def test_the_sentence_says_who_owes_whom() -> None:
    day = date(2027, 3, 31)
    assert "due from you to us as at 31-03-2027" in balance_sentence(
        PartySide.CUSTOMER, Decimal("1250.00"), day
    )
    assert "due from us to you" in balance_sentence(
        PartySide.CUSTOMER, Decimal("-80.00"), day
    )
    assert "due from us to you" in balance_sentence(
        PartySide.SUPPLIER, Decimal("1250.00"), day
    )
    assert "due from you to us" in balance_sentence(
        PartySide.SUPPLIER, Decimal("-80.00"), day
    )
    assert "Rs. 1,25,000.00" in balance_sentence(
        PartySide.CUSTOMER, Decimal("125000"), day
    )
    assert "One Lakh Twenty Five Thousand" in balance_sentence(
        PartySide.CUSTOMER, Decimal("125000"), day
    )
    assert "no balance between us" in balance_sentence(
        PartySide.SUPPLIER, Decimal("0.00"), day
    )


def test_the_supplier_letter_states_the_statement_balance_as_of_the_day() -> None:
    books = _books()
    first = _bill(books, "PI-1", "1000.00", when=date(2026, 4, 10))
    _pay(books, "600.00", when=date(2026, 5, 10), bill=first)
    service = BalanceConfirmationService(books.session)

    # Before the payment the firm owed the whole bill; after it, 400.00.
    assert service.supplier_balances(
        firm_id=books.firm.id, as_of=date(2026, 4, 30)
    ) == {books.vendor.id: Decimal("1000.00")}
    assert service.supplier_balances(
        firm_id=books.firm.id, as_of=date(2026, 5, 31)
    ) == {books.vendor.id: Decimal("400.00")}

    pdf, name = service.letter(
        PartySide.SUPPLIER,
        books.vendor.id,
        firm_id=books.firm.id,
        as_of=date(2026, 4, 30),
    )
    text = _words(pdf)
    assert name == "balance-confirmation-V1-2026-04-30.pdf"
    assert "BALANCE CONFIRMATION" in text
    assert "Acme Firm" in text
    assert "Vendor One" in text
    assert "Rs. 1,000.00" in text
    assert "due from us to you" in text
    assert "30-04-2026" in text


def test_the_customer_letter_nets_an_advance_held_on_account() -> None:
    books = _books()
    invoice = books.sales_invoice("SI-1", "500.00")
    books.owe_us("500.00")
    # 700.00 received: 500.00 clears the bill and 200.00 is held on account.
    ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=date(2026, 4, 25),
            amount=Decimal("700.00"),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("500.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    service = BalanceConfirmationService(books.session)

    assert service.customer_balances(
        firm_id=books.firm.id, as_of=date(2026, 4, 20)
    ) == {books.customer.id: Decimal("500.00")}
    assert service.customer_balances(
        firm_id=books.firm.id, as_of=date(2026, 4, 30)
    ) == {books.customer.id: Decimal("-200.00")}

    text = _words(
        service.letter(
            PartySide.CUSTOMER,
            books.customer.id,
            firm_id=books.firm.id,
            as_of=date(2026, 4, 30),
        )[0]
    )
    assert "Customer One" in text
    assert "Rs. 200.00" in text
    assert "due from us to you" in text


def test_every_party_with_a_balance_gets_a_letter_in_one_zip() -> None:
    books = _books()
    _bill(books, "PI-1", "1000.00")
    service = BalanceConfirmationService(books.session)

    archive, name, count = service.letters_for_everyone(
        PartySide.SUPPLIER, firm_id=books.firm.id, as_of=date(2026, 4, 30)
    )

    assert count == 1
    assert name == "balance-confirmations-suppliers-2026-04-30.zip"
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        assert opened.namelist() == ["balance-confirmation-V1-2026-04-30.pdf"]
        assert opened.read(opened.namelist()[0]).startswith(b"%PDF")
    with pytest.raises(ValidationError, match="No customer had a balance"):
        service.letters_for_everyone(
            PartySide.CUSTOMER, firm_id=books.firm.id, as_of=date(2026, 4, 30)
        )


def test_a_letter_for_a_stranger_is_refused() -> None:
    books = _books()
    with pytest.raises(ResourceNotFoundError):
        BalanceConfirmationService(books.session).letter(
            PartySide.SUPPLIER, uuid4(), firm_id=books.firm.id, as_of=WHEN
        )


def test_the_endpoints_serve_the_statement_and_the_letters() -> None:
    books = _books()
    _bill(books, "PI-1", "1000.00")
    books.owe_us("300.00")
    user_id = uuid4()
    scope = ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset({"VENDOR_VIEW", "CUSTOMER_VIEW"}),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=books.firm.id,
    )
    answer = vendor_statement(
        books.vendor.id,
        scope=scope,
        from_date=YEAR[0],
        to_date=YEAR[1],
        db=books.session,
    )
    assert answer.data is not None
    assert answer.data.closing_balance == Decimal("1000.00")
    one = vendor_balance_confirmation(
        books.vendor.id, scope=scope, as_of=date(2026, 4, 30), db=books.session
    )
    assert one.media_type == "application/pdf"
    every = vendor_balance_confirmations(
        scope=scope, as_of=date(2026, 4, 30), db=books.session
    )
    assert every.media_type == "application/zip"
    customer = customer_balance_confirmation(
        books.customer.id, scope=scope, as_of=date(2026, 4, 30), db=books.session
    )
    assert customer.media_type == "application/pdf"
    customers = customer_balance_confirmations(
        scope=scope, as_of=date(2026, 4, 30), db=books.session
    )
    assert customers.media_type == "application/zip"
