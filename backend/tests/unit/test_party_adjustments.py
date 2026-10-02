"""Adjusting a party's balance without tax (backlog 74 row 2).

Two halves:

- **Deductions on a receipt or payment** -- rounding, bank charges, discount --
  each posted to its own account, so a bill a few rupees short can be closed
  by the money and the deductions together, and a reversal takes every leg
  back.
- **Party adjustments** -- a customer write-off, a supplier write-back and a
  set-off between a customer and a supplier who are the same business -- that
  post at approval, close the bills they name, need a second person above the
  firm's threshold, and are undone by cancelling.

What a bill still owes is derived, never stored, so the assertions read it
back through the derivations the screens and reports use.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.pagination.reports import ReportWindow
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import CustomerReceivableTransaction
from app.customers.services.statement_service import CustomerStatementService
from app.finance.models import GLPosting, LedgerAccount
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.party_adjustments.api.router import approve_party_adjustment
from app.party_adjustments.models import PartyAdjustment
from app.party_adjustments.schemas import (
    PartyAdjustmentAllocationWrite,
    PartyAdjustmentCreate,
    PartyAdjustmentKindEnum,
    PartyAdjustmentSideEnum,
    PartyAdjustmentUpdate,
)
from app.party_adjustments.services import PartyAdjustmentService
from app.party_adjustments.services.settings import stage_adjustment_limits
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from app.settlements.api.router import get_receipt
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

# The seeded chart.
BANK, RECEIVABLES, PAYABLES = "1010", "1100", "2100"
ROUNDING, DISCOUNT_ALLOWED, DISCOUNT_RECEIVED = "4900", "5300", "4200"
BANK_CHARGES, BAD_DEBTS, WRITTEN_BACK = "6700", "6800", "4300"


def _books() -> _Books:
    return _Books(_session_factory()())


def _legs(books: _Books, entry_id: UUID | None) -> dict[str, tuple[Decimal, Decimal]]:
    rows = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == entry_id)
    ).all()
    return {code: (debit, credit) for code, debit, credit in rows}


def _customer_bill(books: _Books, number: str, total: str) -> SalesInvoice:
    """Raise a sales bill the customer owes, on the account as well as the bill."""
    books.owe_us(total)
    return books.sales_invoice(number, total)


def _receipt(
    books: _Books,
    invoice: SalesInvoice,
    *,
    amount: str,
    allocate: str | None = None,
    **deductions: str,
) -> Settlement:
    row = ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal(allocate or amount)
                )
            ],
            **{key: Decimal(value) for key, value in deductions.items()},
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _customer_owes(books: _Books) -> list[Decimal]:
    return [
        row.outstanding_amount
        for row in ReceiptService(books.session).outstanding_invoices(
            firm_id=books.firm.id, party_id=books.customer.id
        )
    ]


def _supplier_owed(books: _Books) -> list[Decimal]:
    return [
        row.outstanding_amount
        for row in PaymentService(books.session).outstanding_invoices(
            firm_id=books.firm.id, party_id=books.vendor.id
        )
    ]


# ---- deductions on a receipt or payment -----------------------------------


@pytest.mark.parametrize(
    ("field", "account"),
    [
        ("rounding_amount", ROUNDING),
        ("bank_charges_amount", BANK_CHARGES),
        ("discount_amount", DISCOUNT_ALLOWED),
    ],
)
def test_a_receipt_deduction_posts_to_its_account_and_closes_the_bill(
    field: str, account: str
) -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "1000.00")
    receipt = _receipt(books, invoice, amount="1000.00", **{field: "3.00"})

    legs = _legs(books, receipt.journal_entry_id)
    assert legs[BANK] == (Decimal("997.00"), Decimal("0.00"))
    assert legs[account] == (Decimal("3.00"), Decimal("0.00"))
    assert legs[RECEIVABLES] == (Decimal("0.00"), Decimal("1000.00"))
    assert _customer_owes(books) == []
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("0.00")
    assert getattr(receipt, field) == Decimal("3.00")


def test_the_receipt_says_how_much_money_moved() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "1000.00")
    receipt = _receipt(
        books,
        invoice,
        amount="1000.00",
        rounding_amount="2.00",
        bank_charges_amount="15.00",
        discount_amount="20.00",
    )
    response = get_receipt(
        receipt.id, scope=_scope(books, frozenset()), db=books.session
    ).data
    assert response is not None
    assert (
        response.rounding_amount,
        response.bank_charges_amount,
        response.discount_amount,
        response.cash_amount,
    ) == (
        Decimal("2.00"),
        Decimal("15.00"),
        Decimal("20.00"),
        Decimal("963.00"),
    )


def test_a_payment_rounded_and_discounted_closes_the_supplier_bill() -> None:
    books = _books()
    invoice = books.purchase_invoice("PI-1", "1000.00")
    payment = PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal("1000.00"),
            method=SettlementMethodEnum.BANK,
            rounding_amount=Decimal("4.00"),
            discount_amount=Decimal("20.00"),
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("1000.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    legs = _legs(books, payment.journal_entry_id)
    assert legs[PAYABLES] == (Decimal("1000.00"), Decimal("0.00"))
    assert legs[BANK] == (Decimal("0.00"), Decimal("976.00"))
    assert legs[ROUNDING] == (Decimal("0.00"), Decimal("4.00"))
    assert legs[DISCOUNT_RECEIVED] == (Decimal("0.00"), Decimal("20.00"))
    assert _supplier_owed(books) == []


def test_bank_charges_on_a_payment_are_refused() -> None:
    books = _books()
    invoice = books.purchase_invoice("PI-1", "1000.00")
    with pytest.raises(ValidationError, match="Expenses screen"):
        PaymentService(books.session).create(
            SettlementCreate(
                party_id=books.vendor.id,
                settlement_date=WHEN,
                amount=Decimal("1000.00"),
                method=SettlementMethodEnum.BANK,
                bank_charges_amount=Decimal("5.00"),
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=invoice.id, amount=Decimal("1000.00")
                    )
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_rounding_above_the_firms_limit_is_refused_until_it_is_raised() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "1000.00")
    with pytest.raises(ValidationError, match="limit of 10.00"):
        _receipt(books, invoice, amount="1000.00", rounding_amount="12.00")
    books.session.rollback()

    stage_adjustment_limits(
        books.session,
        books.firm.id,
        approval_threshold=Decimal("1000.00"),
        rounding_limit=Decimal("20.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    receipt = _receipt(books, invoice, amount="1000.00", rounding_amount="12.00")
    assert receipt.rounding_amount == Decimal("12.00")


def test_a_deduction_must_close_a_bill_not_sit_on_account() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "1000.00")
    with pytest.raises(ValidationError, match="only 500.00 is allocated"):
        _receipt(
            books,
            invoice,
            amount="1000.00",
            allocate="500.00",
            discount_amount="600.00",
        )


def test_deductions_that_leave_no_money_moving_are_refused() -> None:
    with pytest.raises(PydanticValidationError, match="party adjustment"):
        SettlementCreate(
            party_id=uuid4(),
            settlement_date=WHEN,
            amount=Decimal("10.00"),
            method=SettlementMethodEnum.CASH,
            rounding_amount=Decimal("10.00"),
        )


def test_reversing_a_receipt_takes_every_deduction_back() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "1000.00")
    receipt = _receipt(
        books,
        invoice,
        amount="1000.00",
        rounding_amount="2.00",
        bank_charges_amount="15.00",
    )
    ReceiptService(books.session).reverse(
        receipt.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    mirror = _legs(books, receipt.reversal_journal_entry_id)
    assert mirror[BANK] == (Decimal("0.00"), Decimal("983.00"))
    assert mirror[ROUNDING] == (Decimal("0.00"), Decimal("2.00"))
    assert mirror[BANK_CHARGES] == (Decimal("0.00"), Decimal("15.00"))
    assert mirror[RECEIVABLES] == (Decimal("1000.00"), Decimal("0.00"))
    assert _customer_owes(books) == [Decimal("1000.00")]
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("1000.00")


# ---- party adjustments -----------------------------------------------------


def _draft(
    books: _Books,
    kind: PartyAdjustmentKindEnum,
    amount: str,
    *,
    allocations: list[PartyAdjustmentAllocationWrite] | None = None,
    actor_id: UUID | None = None,
) -> PartyAdjustment:
    row = PartyAdjustmentService(books.session).create(
        PartyAdjustmentCreate(
            kind=kind,
            adjustment_date=WHEN,
            customer_id=(
                None
                if kind == PartyAdjustmentKindEnum.SUPPLIER_WRITE_BACK
                else books.customer.id
            ),
            vendor_id=(
                None
                if kind == PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF
                else books.vendor.id
            ),
            amount=Decimal(amount),
            reason="Customer closed down; nothing more will come.",
            allocations=allocations or [],
        ),
        firm_id=books.firm.id,
        actor_id=actor_id or books.actor_id,
    )
    books.session.commit()
    return row


def _approve(
    books: _Books,
    row: PartyAdjustment,
    *,
    actor_id: UUID | None = None,
    may: bool = True,
) -> PartyAdjustment:
    approved = PartyAdjustmentService(books.session).approve(
        row.id,
        firm_scope=books.firm.id,
        actor_id=actor_id or uuid4(),
        may_approve_above_threshold=may,
    )
    books.session.commit()
    return approved


def _on(
    side: PartyAdjustmentSideEnum, bill_id: UUID, amount: str
) -> PartyAdjustmentAllocationWrite:
    return PartyAdjustmentAllocationWrite(
        side=side, bill_id=bill_id, amount=Decimal(amount)
    )


CUSTOMER, SUPPLIER = PartyAdjustmentSideEnum.CUSTOMER, PartyAdjustmentSideEnum.SUPPLIER


def test_a_write_off_closes_the_bill_and_books_the_expense() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "800.00")
    row = _draft(
        books,
        PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
        "800.00",
        allocations=[_on(CUSTOMER, invoice.id, "800.00")],
    )
    # A draft moves nothing.
    assert _customer_owes(books) == [Decimal("800.00")]
    assert row.journal_entry_id is None

    _approve(books, row)
    assert _legs(books, row.journal_entry_id) == {
        BAD_DEBTS: (Decimal("800.00"), Decimal("0.00")),
        RECEIVABLES: (Decimal("0.00"), Decimal("800.00")),
    }
    assert _customer_owes(books) == []
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("0.00")
    # The statement shows it, and the ageing has nothing left to age.
    statement = CustomerStatementService(books.session).statement(
        books.customer.id,
        firm_scope=books.firm.id,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
    )
    # On the statement, not necessarily last: the bill and the write-off share
    # a date, and SQLite stamps both in the same second, so their order is
    # the ids'. PostgreSQL stamps them apart; the balance is what matters.
    assert "WRITE_OFF" in [line.transaction_type for line in statement.lines]
    assert statement.closing_balance == Decimal("0.00")
    assert (
        CustomerStatementService(books.session).ageing(firm_scope=books.firm.id) == []
    )


def test_a_write_off_past_what_the_customer_owes_is_refused() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "800.00")
    with pytest.raises(ValidationError, match="owes 800.00 on account"):
        _draft(books, PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF, "900.00")


def test_a_write_back_closes_the_supplier_bill_as_other_income() -> None:
    books = _books()
    invoice = books.purchase_invoice("PI-1", "450.00")
    row = _draft(
        books,
        PartyAdjustmentKindEnum.SUPPLIER_WRITE_BACK,
        "450.00",
        allocations=[_on(SUPPLIER, invoice.id, "450.00")],
    )
    _approve(books, row)
    assert _legs(books, row.journal_entry_id) == {
        PAYABLES: (Decimal("450.00"), Decimal("0.00")),
        WRITTEN_BACK: (Decimal("0.00"), Decimal("450.00")),
    }
    assert _supplier_owed(books) == []
    with pytest.raises(ValidationError, match="open bills add up to 0"):
        _draft(books, PartyAdjustmentKindEnum.SUPPLIER_WRITE_BACK, "1.00")


def test_a_set_off_moves_both_balances_and_both_bills() -> None:
    books = _books()
    sale = _customer_bill(books, "SI-1", "1000.00")
    bill = books.purchase_invoice("PI-1", "600.00")
    row = _draft(
        books,
        PartyAdjustmentKindEnum.SET_OFF,
        "600.00",
        allocations=[
            _on(CUSTOMER, sale.id, "600.00"),
            _on(SUPPLIER, bill.id, "600.00"),
        ],
    )
    _approve(books, row)

    assert _legs(books, row.journal_entry_id) == {
        PAYABLES: (Decimal("600.00"), Decimal("0.00")),
        RECEIVABLES: (Decimal("0.00"), Decimal("600.00")),
    }
    assert _customer_owes(books) == [Decimal("400.00")]
    assert _supplier_owed(books) == []
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("400.00")
    written = books.session.scalar(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.id == row.receivable_transaction_id
        )
    )
    assert written is not None and written.transaction_type == "SET_OFF"


def test_a_set_off_above_either_side_is_refused() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "1000.00")
    books.purchase_invoice("PI-1", "600.00")
    with pytest.raises(ValidationError, match="open bills add up to 600.00"):
        _draft(books, PartyAdjustmentKindEnum.SET_OFF, "700.00")
    books.session.rollback()
    with pytest.raises(ValidationError, match="owes 1000.00 on account"):
        _draft(books, PartyAdjustmentKindEnum.SET_OFF, "1100.00")


def test_a_set_off_between_two_different_businesses_is_refused() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "1000.00")
    books.purchase_invoice("PI-1", "600.00")
    books.customer.pan_number = "AAAAA1111A"
    books.vendor.gstin = "29BBBBB2222B1Z5"
    books.session.commit()
    with pytest.raises(ValidationError, match="different businesses"):
        _draft(books, PartyAdjustmentKindEnum.SET_OFF, "100.00")


def test_an_allocation_past_its_bill_is_refused() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "800.00")
    books.owe_us("500.00")
    with pytest.raises(ValidationError, match="owes 800.00"):
        _draft(
            books,
            PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
            "900.00",
            allocations=[_on(CUSTOMER, invoice.id, "900.00")],
        )


def test_above_the_threshold_approval_is_a_second_persons() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "5000.00")
    row = _draft(books, PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF, "5000.00")
    service = PartyAdjustmentService(books.session)

    with pytest.raises(AuthorizationError, match="PARTY_ADJUSTMENT_APPROVE"):
        service.approve(
            row.id,
            firm_scope=books.firm.id,
            actor_id=uuid4(),
            may_approve_above_threshold=False,
        )
    with pytest.raises(AuthorizationError, match="other than the person"):
        service.approve(
            row.id,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            may_approve_above_threshold=True,
        )
    approved = _approve(books, row, actor_id=uuid4(), may=True)
    assert approved.status == "APPROVED"


def test_at_or_below_the_threshold_the_maker_may_approve() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "3.00")
    row = _draft(books, PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF, "3.00")
    approved = _approve(books, row, actor_id=books.actor_id, may=False)
    assert approved.status == "APPROVED"


def test_the_router_reads_the_approve_permission_off_the_principal() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "5000.00")
    row = _draft(books, PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF, "5000.00")
    with pytest.raises(AuthorizationError):
        approve_party_adjustment(
            row.id,
            scope=_scope(books, frozenset({"PARTY_ADJUSTMENT_MANAGE"})),
            response=Response(),
            db=books.session,
        )
    books.session.rollback()
    answer = approve_party_adjustment(
        row.id,
        scope=_scope(
            books,
            frozenset({"PARTY_ADJUSTMENT_MANAGE", "PARTY_ADJUSTMENT_APPROVE"}),
        ),
        response=Response(),
        db=books.session,
    ).data
    assert answer is not None and answer.status == "APPROVED"


def test_cancelling_reverses_everything_and_the_bill_owes_again() -> None:
    books = _books()
    # Above the default threshold, so cancelling needs the approve authority.
    invoice = _customer_bill(books, "SI-1", "1800.00")
    row = _draft(
        books,
        PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
        "1800.00",
        allocations=[_on(CUSTOMER, invoice.id, "1800.00")],
    )
    _approve(books, row)
    service = PartyAdjustmentService(books.session)
    with pytest.raises(AuthorizationError):
        service.cancel(
            row.id,
            reason="Paid after all",
            firm_scope=books.firm.id,
            actor_id=uuid4(),
            may_approve_above_threshold=False,
        )
    service.cancel(
        row.id,
        reason="Paid after all",
        firm_scope=books.firm.id,
        actor_id=uuid4(),
        may_approve_above_threshold=True,
    )
    books.session.commit()

    assert row.status == "CANCELLED"
    assert _legs(books, row.reversal_journal_entry_id) == {
        BAD_DEBTS: (Decimal("0.00"), Decimal("1800.00")),
        RECEIVABLES: (Decimal("1800.00"), Decimal("0.00")),
    }
    assert _customer_owes(books) == [Decimal("1800.00")]
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("1800.00")
    # The ageing as of a day when it stood still reads it as written off.
    assert (
        CustomerStatementService(books.session).ageing(
            firm_scope=books.firm.id, as_of=WHEN
        )
        == []
    )


def test_a_draft_is_edited_and_its_status_is_not_writable() -> None:
    books = _books()
    first = _customer_bill(books, "SI-1", "300.00")
    second = _customer_bill(books, "SI-2", "200.00")
    row = _draft(
        books,
        PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
        "300.00",
        allocations=[_on(CUSTOMER, first.id, "300.00")],
    )
    PartyAdjustmentService(books.session).update(
        row.id,
        PartyAdjustmentUpdate(
            amount=Decimal("200.00"),
            allocations=[_on(CUSTOMER, second.id, "200.00")],
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    _approve(books, row)
    assert _customer_owes(books) == [Decimal("300.00")]
    with pytest.raises(PydanticValidationError):
        PartyAdjustmentUpdate.model_validate({"status": "APPROVED"})


def test_a_reason_is_required() -> None:
    with pytest.raises(PydanticValidationError):
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
            adjustment_date=WHEN,
            customer_id=uuid4(),
            amount=Decimal("1.00"),
            reason="   ",
        )


def test_a_bill_under_an_adjustment_cannot_be_cancelled() -> None:
    books = _books()
    invoice = _customer_bill(books, "SI-1", "800.00")
    row = _draft(
        books,
        PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
        "800.00",
        allocations=[_on(CUSTOMER, invoice.id, "800.00")],
    )
    with pytest.raises(ValidationError, match=row.adjustment_number):
        SalesInvoiceService(books.session)._assert_nothing_rests_on(invoice)


def test_the_register_lists_every_adjustment() -> None:
    books = _books()
    _customer_bill(books, "SI-1", "800.00")
    _draft(books, PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF, "100.00")
    rows = PartyAdjustmentService(books.session).register_report(
        firm_scope=books.firm.id, window=ReportWindow()
    )
    assert [(row.kind, row.amount, row.customer_name) for row in rows] == [
        ("CUSTOMER_WRITE_OFF", Decimal("100.00"), "Customer One")
    ]


def test_who_holds_the_party_adjustment_codes() -> None:
    codes = {"PARTY_ADJUSTMENT_VIEW", "PARTY_ADJUSTMENT_MANAGE"}
    approve = "PARTY_ADJUSTMENT_APPROVE"
    for role in ("FIRM_ADMIN", "FIRM_MANAGER"):
        assert codes | {approve} <= ROLE_PERMISSION_CODES[role]
    assert codes <= ROLE_PERMISSION_CODES["ACCOUNTANT"]
    assert approve not in ROLE_PERMISSION_CODES["ACCOUNTANT"]


def _scope(books: _Books, permissions: frozenset[str]) -> ResolvedFirmScope:
    user_id = uuid4()
    return ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=permissions,
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=books.firm.id,
    )
