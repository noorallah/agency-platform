"""A cheque to any account, dated today or ahead (row F13, COL-11).

The firm's own cheque pays a supplier, a customer, an expense account or any
other ledger account. Dated today or before it is recorded at once, through
the service that already records that kind of payment; dated ahead it is held
and posts nothing until presented. A cheque is never printed without a
record, and the right it needs is the one the payment it becomes needs.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError as SchemaError
from sqlalchemy import func, select

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.expenses.api.router import expense_cheque
from app.expenses.models import Expense, ExpenseStatus
from app.finance.models import JournalEntry, LedgerAccount
from app.settlements.api.post_dated_cheques_router import (
    bounce_issued_cheque,
    issued_cheque_accounts,
    list_issued_cheques,
    print_issued_cheque,
    write_cheque,
)
from app.settlements.api.router import refund_cheque
from app.settlements.models import Settlement, SettlementDirection
from app.settlements.models.post_dated_cheque import PostDatedCheque
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.schemas.post_dated_cheque import (
    ChequeWrite,
    PostDatedChequeBounce,
    PostDatedChequeCreate,
    PostDatedChequeDeposit,
)
from app.settlements.services import ReceiptService
from app.settlements.services.cheque_print import ChequeService
from app.settlements.services.post_dated_cheques import PostDatedChequeService
from app.vendors.models import Vendor
from tests.unit.test_expenses import _Books
from tests.unit.test_post_dated_cheques import _customer, _vendor

pytestmark = pytest.mark.typed_document_numbers

BANK, RENT = "1010", "6000"
TODAY, AHEAD = date(2026, 4, 30), date(2026, 5, 30)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, date]:
    """Pin the firm's day, so "dated ahead" does not depend on the calendar.

    A test moves the day on by setting ``clock["today"]``.
    """
    day = {"today": TODAY}
    for module in (
        "app.settlements.services.post_dated_cheques",
        "app.settlements.services.settlement_service",
        "app.expenses.services.expense_service",
        "app.finance.services.journal_engine",
    ):
        monkeypatch.setattr(f"{module}.firm_today", lambda *_, **__: day["today"])
    return day


def _service(books: _Books) -> PostDatedChequeService:
    return PostDatedChequeService(books.session, direction=SettlementDirection.PAYMENT)


def _scope(books: _Books, *codes: str) -> ResolvedFirmScope:
    return ResolvedFirmScope(
        principal=Principal(
            subject=books.actor_id,
            roles=frozenset(),
            permissions=frozenset(codes),
            claims=TokenClaims(
                sub=str(books.actor_id),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
            ),
        ),
        firm_id=books.firm.id,
    )


def _loan(books: _Books) -> LedgerAccount:
    """Open a loan account: a ledger account no document keeps."""
    bank = books.session.get(LedgerAccount, books.account(BANK))
    assert bank is not None
    others = _service(books).account_choices(firm_id=books.firm.id)[2]
    liability = next((row for row in others if row.account_type == "LIABILITY"), None)
    account = LedgerAccount(
        firm_id=books.firm.id,
        account_group_id=(liability or bank).account_group_id,
        code="2950",
        name="Term Loan",
        account_type="LIABILITY",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(account)
    books.session.commit()
    return account


def _write(books: _Books, *, when: date = TODAY, **who: object) -> PostDatedCheque:
    row = _service(books).write(
        ChequeWrite.model_validate(
            {
                "bank_account_id": books.account(BANK),
                "amount": Decimal("12000"),
                "cheque_number": who.pop("number", "500001"),
                "cheque_date": when,
                **who,
            }
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _journals(books: _Books) -> int:
    return int(books.session.scalar(select(func.count(JournalEntry.id))) or 0)


def test_a_cheque_names_exactly_one_payee() -> None:
    base = {
        "bank_account_id": uuid4(),
        "amount": Decimal("1"),
        "cheque_number": "1",
        "cheque_date": TODAY,
    }
    with pytest.raises(SchemaError, match="only one of them"):
        ChequeWrite.model_validate(base)
    with pytest.raises(SchemaError, match="only one of them"):
        ChequeWrite.model_validate(
            {**base, "supplier_id": uuid4(), "account_id": uuid4()}
        )


def test_a_cheque_to_an_expense_account_dated_today_posts_the_expense() -> None:
    books = _Books()
    row = _write(books, account_id=books.account(RENT), payee_name="A. Landlord")

    assert (row.paid_to_kind, row.status) == ("EXPENSE", "DEPOSITED")
    expense = books.session.get(Expense, row.expense_id)
    assert expense is not None
    assert expense.expense_date == TODAY
    assert expense.payee == "A. Landlord"
    assert expense.reference == "Cheque 500001"
    assert books.postings(expense.journal_entry_id) == {
        RENT: (Decimal("12000.00"), Decimal("0.00")),
        BANK: (Decimal("0.00"), Decimal("12000.00")),
    }
    # It prints, from the register and from the expense it became.
    pdf, name = ChequeService(books.session).written_cheque(
        row.id, firm_id=books.firm.id
    )
    assert pdf.startswith(b"%PDF") and name == "cheque-500001.pdf"
    response = expense_cheque(
        expense.id, _scope(books, "EXPENSE_CREATE"), payee=None, db=books.session
    )
    assert response.media_type == "application/pdf"


def test_a_cheque_to_a_supplier_dated_ahead_posts_nothing_until_presented(
    clock: dict[str, date],
) -> None:
    books = _Books()
    vendor = _vendor(books)
    before = _journals(books)
    row = _write(books, when=AHEAD, supplier_id=vendor.id)

    assert (row.paid_to_kind, row.status) == ("SUPPLIER", "HELD")
    assert row.payee_name == "Vendor One"
    assert row.received_on == TODAY
    assert _journals(books) == before
    assert books.session.scalar(select(func.count(Settlement.id))) == 0
    # Printed now, with its own date -- the register is the record.
    pdf, _ = ChequeService(books.session).written_cheque(row.id, firm_id=books.firm.id)
    assert pdf.startswith(b"%PDF")

    service = _service(books)
    with pytest.raises(ValidationError, match="will not take it"):
        service.deposit(
            row.id,
            PostDatedChequeDeposit(deposited_on=TODAY),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.rollback()
    clock["today"] = AHEAD
    row = service.deposit(
        row.id,
        PostDatedChequeDeposit(deposited_on=AHEAD),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    payment = books.session.get(Settlement, row.settlement_id)
    assert payment is not None
    assert (payment.direction, payment.payment_mode) == ("PAYMENT", "CHEQUE")
    assert (payment.settlement_date, payment.instrument_date) == (AHEAD, AHEAD)
    assert payment.ledger_account_id == books.account(BANK)


def test_a_cheque_to_a_customer_is_a_refund() -> None:
    books = _Books()
    customer = _customer(books)
    ReceiptService(books.session).create(
        SettlementCreate(
            party_id=customer.id,
            settlement_date=date(2026, 4, 10),
            amount=Decimal("20000"),
            method=SettlementMethodEnum.BANK,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    row = _write(books, customer_id=customer.id)

    assert (row.paid_to_kind, row.status) == ("CUSTOMER", "DEPOSITED")
    assert row.payee_name == "Kumar Stores"
    refund = books.session.get(Settlement, row.settlement_id)
    assert refund is not None
    assert (refund.direction, refund.payment_mode) == ("REFUND", "CHEQUE")
    assert refund.customer_id == customer.id
    books.session.refresh(customer)
    assert customer.unapplied_advance_balance == Decimal("8000.00")
    response = refund_cheque(
        refund.id, _scope(books, "PAYMENT_CREATE"), payee=None, db=books.session
    )
    assert response.media_type == "application/pdf"


def test_a_cheque_to_any_other_account_posts_a_payment_voucher() -> None:
    books = _Books()
    loan = _loan(books)
    row = _write(books, account_id=loan.id, payee_name="State Bank of India")

    assert (row.paid_to_kind, row.status) == ("ACCOUNT", "DEPOSITED")
    assert row.journal_entry_id is not None
    assert books.postings(row.journal_entry_id) == {
        "2950": (Decimal("12000.00"), Decimal("0.00")),
        BANK: (Decimal("0.00"), Decimal("12000.00")),
    }

    # Returned by the bank: the voucher is taken back and the fee posted.
    _service(books).bounce(
        row.id,
        PostDatedChequeBounce(
            bounced_on=TODAY,
            reason="Signature differs",
            bank_charges_amount=Decimal("150"),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert row.status == "BOUNCED"
    assert row.reversal_journal_entry_id is not None
    assert books.net("2950") == Decimal("0.00")
    assert books.net(BANK) == Decimal("-150.00")
    with pytest.raises(ValidationError, match="not printed again"):
        ChequeService(books.session).written_cheque(row.id, firm_id=books.firm.id)


def test_a_returned_cheque_cancels_the_expense_it_became() -> None:
    books = _Books()
    row = _write(books, account_id=books.account(RENT), payee_name="A. Landlord")
    bounce_issued_cheque(
        row.id,
        PostDatedChequeBounce(bounced_on=TODAY, reason="Funds"),
        _scope(books, "EXPENSE_CANCEL"),
        Response(),
        expected_version=None,
        db=books.session,
    )
    expense = books.session.get(Expense, row.expense_id)
    assert expense is not None and expense.status == ExpenseStatus.CANCELLED.value
    assert books.net(RENT) == Decimal("0.00")
    assert books.net(BANK) == Decimal("0.00")


def test_what_a_cheque_may_not_be_written_to_or_drawn_on() -> None:
    books = _Books()
    vendor = _vendor(books)
    cash = books.account("1000")
    with pytest.raises(ValidationError, match="contra entry"):
        _write(books, account_id=cash)
    books.session.rollback()
    with pytest.raises(ValidationError, match="cash account"):
        _service(books).write(
            ChequeWrite(
                bank_account_id=cash,
                supplier_id=vendor.id,
                amount=Decimal("10"),
                cheque_number="9",
                cheque_date=TODAY,
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.rollback()
    # Receivables is kept by its documents: a cheque straight to it would
    # move the ledger and no customer's account.
    with pytest.raises(ValidationError, match="kept by its own documents"):
        _write(books, account_id=books.account("1100"))
    books.session.rollback()

    # One cheque number is written once on a bank account.
    _write(books, when=AHEAD, supplier_id=vendor.id)
    with pytest.raises(ValidationError, match="already been written"):
        _write(books, when=AHEAD, account_id=books.account(RENT))
    books.session.rollback()
    assert books.session.scalar(select(func.count(PostDatedCheque.id))) == 1


def test_a_refused_payment_leaves_no_cheque_behind() -> None:
    """Today's cheque and its payment are one transaction."""
    books = _Books()
    customer = _customer(books)  # holds no advance to hand back
    with pytest.raises(ValidationError):
        _write(books, customer_id=customer.id)
    books.session.rollback()
    assert books.session.scalar(select(func.count(PostDatedCheque.id))) == 0


def test_the_right_a_cheque_needs_is_the_one_its_payment_needs() -> None:
    books = _Books()
    vendor = _vendor(books)
    loan = _loan(books)

    def payload(**who: object) -> ChequeWrite:
        return ChequeWrite.model_validate(
            {
                "bank_account_id": books.account(BANK),
                "amount": Decimal("100"),
                "cheque_number": str(uuid4().int)[:8],
                "cheque_date": AHEAD,
                **who,
            }
        )

    expense_clerk = _scope(books, "EXPENSE_CREATE")
    for who in ({"supplier_id": vendor.id}, {"account_id": loan.id}):
        with pytest.raises(AuthorizationError):
            write_cheque(payload(**who), expense_clerk, Response(), db=books.session)
    answer = write_cheque(
        payload(account_id=books.account(RENT)),
        expense_clerk,
        Response(),
        db=books.session,
    )
    assert answer.data.paid_to_kind == "EXPENSE"
    assert answer.data.party_name and answer.data.bank_account_name

    # Whoever pays suppliers cannot print or return the expense cheque.
    payer = _scope(books, "PAYMENT_CREATE")
    with pytest.raises(AuthorizationError):
        print_issued_cheque(answer.data.id, payer, payee=None, db=books.session)
    with pytest.raises(AuthorizationError):
        write_cheque(payload(account_id=loan.id), payer, Response(), db=books.session)
    voucher = write_cheque(
        payload(account_id=loan.id),
        _scope(books, "JOURNAL_POST"),
        Response(),
        db=books.session,
    )
    assert voucher.data.paid_to_kind == "ACCOUNT"


def test_the_form_is_offered_only_what_the_save_accepts() -> None:
    books = _Books()
    loan = _loan(books)
    choices = issued_cheque_accounts(
        _scope(books, "PAYMENT_CREATE"), db=books.session
    ).data
    banks = {row.code for row in choices.bank_accounts}
    assert BANK in banks and "1000" not in banks
    assert RENT in {row.code for row in choices.expense_accounts}
    others = {row.code for row in choices.other_accounts}
    assert loan.code in others
    assert not others & {BANK, "1000", "1100", RENT}


def test_the_register_lists_every_kind_with_who_it_pays() -> None:
    books = _Books()
    vendor = _vendor(books)
    loan = _loan(books)
    _write(books, when=AHEAD, supplier_id=vendor.id, number="1")
    _write(books, when=AHEAD, account_id=loan.id, number="2")
    _write(books, when=AHEAD, account_id=books.account(RENT), number="3")
    # One the old way in, to a supplier, with no bank account named.
    PostDatedChequeService(books.session, direction=SettlementDirection.PAYMENT).create(
        PostDatedChequeCreate(
            party_id=vendor.id,
            cheque_number="4",
            cheque_date=AHEAD,
            amount=Decimal("5"),
            received_on=TODAY,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    page = list_issued_cheques(
        _scope(books, "PAYMENT_VIEW"),
        page=1,
        page_size=50,
        search="",
        status_filter=None,
        party_id=None,
        due_on=None,
        cheque_from=None,
        cheque_to=None,
        db=books.session,
    )
    seen = {row.cheque_number: row for row in page.data}
    assert [seen[n].paid_to_kind for n in "1234"] == [
        "SUPPLIER",
        "ACCOUNT",
        "EXPENSE",
        "SUPPLIER",
    ]
    assert seen["2"].party_name == "Term Loan"
    assert seen["2"].party_id == loan.id
    assert seen["4"].bank_account_id is None and seen["4"].payee_name is None
    by_account = list_issued_cheques(
        _scope(books, "PAYMENT_VIEW"),
        page=1,
        page_size=50,
        search="",
        status_filter=None,
        party_id=loan.id,
        due_on=None,
        cheque_from=None,
        cheque_to=None,
        db=books.session,
    )
    assert [row.cheque_number for row in by_account.data] == ["2"]
    # The old cheque prints too, drawn on the firm's Bank account.
    pdf, _ = ChequeService(books.session).written_cheque(
        seen["4"].id, firm_id=books.firm.id
    )
    assert pdf.startswith(b"%PDF")


def test_a_cash_expense_and_a_upi_refund_have_no_cheque() -> None:
    books = _Books()
    expense = books.record("500", paid_from="1000", payee="Tea stall")
    with pytest.raises(ValidationError, match="not paid from a bank account"):
        ChequeService(books.session).expense_cheque(expense.id, firm_id=books.firm.id)
    with pytest.raises(ValueError, match="receipt"):
        ChequeService(books.session).payment_cheque(
            uuid4(), firm_id=books.firm.id, direction=SettlementDirection.RECEIPT
        )


def _unused(_: UUID, __: Customer, ___: Vendor) -> None:
    """Keep the model imports the fixtures above are typed with."""
