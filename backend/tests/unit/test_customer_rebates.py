"""Turnover rebates to customers (SG-9, backlog 87 row 9).

The mirror of ``test_supplier_rebates.py``. Sales to the customer in the
period -- approved bills at taxable value, less returns and credit notes, plus
debit notes -- reach a slab, and that slab's rate applies to all of them.
After the period the rebate is accrued once (Dr rebates allowed, Cr customer
rebate payable), then settled by a ``CUSTOMER_REBATE`` adjustment set against
the customer's account (Dr customer rebate payable, Cr receivable).
"""

# ruff: noqa: D103

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.core.utils.dates import utc_now
from app.credit_note.models import CreditNote
from app.customer_debit_note.models import CustomerDebitNote
from app.customer_rebates.api.router import (
    customer_rebate_statement_report,
    get_customer_rebate,
    list_customer_rebates,
    router,
)
from app.customer_rebates.models import CustomerRebateAgreement
from app.customer_rebates.schemas import (
    CustomerRebateCreate,
    CustomerRebateResponse,
    CustomerRebateUpdate,
    RebateSlabWrite,
)
from app.customer_rebates.services import CustomerRebateService
from app.customers.models import Customer, CustomerGroup
from app.finance.models import (
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    LedgerAccount,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from app.party_adjustments.models import PartyAdjustment
from app.party_adjustments.schemas import (
    PartyAdjustmentAllocationWrite,
    PartyAdjustmentCreate,
    PartyAdjustmentKindEnum,
    PartyAdjustmentSideEnum,
    PartyAdjustmentUpdate,
)
from app.party_adjustments.services import PartyAdjustmentService
from app.sales_invoice.models import SalesInvoice
from app.sales_return.models import SalesReturn
from tests.unit.report_windows import assert_page_size_is_bounded, report_scope
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

APRIL = (date(2026, 4, 1), date(2026, 4, 30))
MAY = (date(2026, 5, 1), date(2026, 5, 31))
ALLOWED, PAYABLE, RECEIVABLES = "5310", "2900", "1100"


def _books() -> _Books:
    return _Books(_session_factory()())


def _customer(books: _Books, code: str, group: CustomerGroup | None = None) -> Customer:
    row = Customer(
        firm_id=books.firm.id,
        code=code,
        customer_type="BUSINESS",
        name=f"Customer {code}",
        display_name=f"Customer {code}",
        currency_code="INR",
        status="ACTIVE",
        customer_group_id=None if group is None else group.id,
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _group(books: _Books, code: str = "STOCKISTS") -> CustomerGroup:
    row = CustomerGroup(firm_id=books.firm.id, code=code, name=code.title())
    books.session.add(row)
    books.session.commit()
    return row


def _bill(
    books: _Books,
    number: str,
    taxable: str,
    *,
    customer: Customer | None = None,
    on: date = WHEN,
    status: str = "APPROVED",
) -> SalesInvoice:
    """Add a sales bill of ``taxable`` before 18% tax, rounded up by 0.40."""
    tax = Decimal(taxable) * Decimal("0.18")
    row = SalesInvoice(
        firm_id=books.firm.id,
        customer_id=(customer or books.customer).id,
        branch_id=books.branch_id,
        invoice_number=number,
        invoice_date=on,
        status=status,
        tax_total=tax,
        round_off=Decimal("0.40"),
        grand_total=Decimal(taxable) + tax + Decimal("0.40"),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _returned(
    books: _Books, number: str, taxable: str, *, status: str = "COMPLETED"
) -> None:
    tax = Decimal(taxable) * Decimal("0.18")
    books.session.add(
        SalesReturn(
            firm_id=books.firm.id,
            customer_id=books.customer.id,
            branch_id=books.branch_id,
            warehouse_id=uuid4(),
            return_number=number,
            return_date=WHEN,
            status=status,
            tax_total=tax,
            grand_total=Decimal(taxable) + tax,
            created_by=books.actor_id,
            updated_by=books.actor_id,
        )
    )
    books.session.commit()


def _note(
    books: _Books,
    model: type[CreditNote] | type[CustomerDebitNote],
    number: str,
    bill: SalesInvoice,
    taxable: str,
    *,
    status: str = "APPROVED",
) -> None:
    tax = Decimal(taxable) * Decimal("0.18")
    values: dict[str, Any] = {
        "firm_id": books.firm.id,
        "customer_id": bill.customer_id,
        "branch_id": books.branch_id,
        "sales_invoice_id": bill.id,
        "status": status,
        "taxable_amount": Decimal(taxable),
        "tax_amount": tax,
        "total_amount": Decimal(taxable) + tax,
    }
    if model is CreditNote:
        values |= {"credit_note_number": number, "credit_note_date": WHEN}
    else:
        values |= {"debit_note_number": number, "debit_note_date": WHEN}
    books.session.add(model(**values))
    books.session.commit()


def _write(
    books: _Books,
    *,
    period: tuple[date, date] = APRIL,
    code: str = "TR-1",
    customer: Customer | None = None,
    group: CustomerGroup | None = None,
    agreed_before_sale: bool = False,
) -> CustomerRebateCreate:
    return CustomerRebateCreate(
        customer_id=None if group is not None else (customer or books.customer).id,
        customer_group_id=None if group is None else group.id,
        code=code,
        name="Turnover rebate, April",
        period_from=period[0],
        period_to=period[1],
        agreed_before_sale=agreed_before_sale,
        slabs=[
            RebateSlabWrite(threshold=Decimal("1000"), rate_percent=Decimal("1")),
            RebateSlabWrite(threshold=Decimal("5000"), rate_percent=Decimal("2")),
        ],
    )


def _agreement(books: _Books, **how: Any) -> CustomerRebateAgreement:  # noqa: ANN401
    return CustomerRebateService(books.session).create(
        _write(books, **how), firm_id=books.firm.id, actor_id=books.actor_id
    )


def _view(books: _Books, row: CustomerRebateAgreement) -> CustomerRebateResponse:
    service = CustomerRebateService(books.session)
    return service.responses([service.get(row.id, firm_id=books.firm.id)])[0]


def _legs(books: _Books, entry_id: UUID | None) -> dict[str, tuple[Decimal, Decimal]]:
    rows = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == entry_id)
    ).all()
    return {code: (debit, credit) for code, debit, credit in rows}


def _net(books: _Books, *codes: str) -> dict[str, Decimal]:
    """Return debits less credits on each account, over every journal."""
    rows = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(LedgerAccount.code.in_(codes))
    ).all()
    return {
        code: sum((d - c for found, d, c in rows if found == code), Decimal("0"))
        for code in codes
    }


def _accrue(books: _Books, row: CustomerRebateAgreement) -> CustomerRebateAgreement:
    return CustomerRebateService(books.session).accrue(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id
    )


def _settle(
    books: _Books,
    row: CustomerRebateAgreement,
    amount: str,
    *,
    bill: UUID | None = None,
    customer: Customer | None = None,
) -> PartyAdjustment:
    service = PartyAdjustmentService(books.session)
    draft = service.create(
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.CUSTOMER_REBATE,
            adjustment_date=WHEN + timedelta(days=15),
            customer_id=(customer or books.customer).id,
            amount=Decimal(amount),
            reason="April turnover rebate set against the account.",
            customer_rebate_agreement_id=row.id,
            allocations=(
                []
                if bill is None
                else [
                    PartyAdjustmentAllocationWrite(
                        side=PartyAdjustmentSideEnum.CUSTOMER,
                        bill_id=bill,
                        amount=Decimal(amount),
                    )
                ]
            ),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    approved = service.approve(
        draft.id,
        firm_scope=books.firm.id,
        actor_id=uuid4(),
        may_approve_above_threshold=True,
    )
    books.session.commit()
    return approved


def _owing(books: _Books) -> Decimal:
    books.session.refresh(books.customer)
    return Decimal(str(books.customer.current_outstanding))


# ---- slabs -------------------------------------------------------------


@pytest.mark.parametrize(
    ("taxable", "rate", "earned", "next_at", "to_next"),
    [
        ("999.99", "0", "0.00", "1000", "0.01"),
        ("1000", "1", "10.00", "5000", "4000.00"),
        ("4999.99", "1", "50.00", "5000", "0.01"),
        ("5000", "2", "100.00", None, None),
        ("7500", "2", "150.00", None, None),
    ],
)
def test_the_slab_reached_sets_the_rate_on_the_whole_turnover(
    taxable: str, rate: str, earned: str, next_at: str | None, to_next: str | None
) -> None:
    books = _books()
    _bill(books, "SI-1", taxable)

    view = _view(books, _agreement(books))

    assert (view.turnover, view.rate_percent, view.earned) == (
        Decimal(taxable).quantize(Decimal("0.01")),
        Decimal(rate),
        Decimal(earned),
    )
    assert view.next_threshold == (None if next_at is None else Decimal(next_at))
    assert view.to_next == (None if to_next is None else Decimal(to_next))


def test_two_slabs_cannot_start_at_one_turnover_and_one_party_is_named() -> None:
    books = _books()
    with pytest.raises(ValueError, match="same turnover"):
        CustomerRebateCreate(
            customer_id=books.customer.id,
            code="X",
            name="X",
            period_from=APRIL[0],
            period_to=APRIL[1],
            slabs=[
                RebateSlabWrite(threshold=Decimal("1"), rate_percent=Decimal("1")),
                RebateSlabWrite(threshold=Decimal("1"), rate_percent=Decimal("2")),
            ],
        )
    for both in (
        {"customer_id": books.customer.id, "customer_group_id": uuid4()},
        {},
    ):
        with pytest.raises(ValueError, match="one customer or one customer group"):
            CustomerRebateCreate(
                code="X",
                name="X",
                period_from=APRIL[0],
                period_to=APRIL[1],
                slabs=[
                    RebateSlabWrite(threshold=Decimal("1"), rate_percent=Decimal("1"))
                ],
                **both,
            )


# ---- turnover ----------------------------------------------------------


def test_returns_and_credit_notes_come_off_and_a_debit_note_goes_on() -> None:
    books = _books()
    bill = _bill(books, "SI-1", "5000")
    _returned(books, "SR-1", "400")
    _returned(books, "SR-2", "999", status="APPROVED")  # not completed
    _note(books, CreditNote, "CN-1", bill, "100")
    _note(books, CreditNote, "CN-2", bill, "999", status="DRAFT")
    _note(books, CustomerDebitNote, "DN-1", bill, "50")
    _note(books, CustomerDebitNote, "DN-2", bill, "999", status="CANCELLED")
    row = _agreement(books)

    statement = CustomerRebateService(books.session).statement(
        row.id, firm_id=books.firm.id
    )

    assert (
        statement.invoiced,
        statement.returned,
        statement.credit_notes,
        statement.debit_notes,
        statement.turnover_today,
    ) == (
        Decimal("5000.00"),
        Decimal("400.00"),
        Decimal("100.00"),
        Decimal("50.00"),
        Decimal("4550.00"),
    )
    # 4,550 is back under the 5,000 slab the bill alone reached.
    assert (statement.agreement.rate_percent, statement.agreement.earned) == (
        Decimal("1"),
        Decimal("45.50"),
    )
    assert [item.customer_id for item in statement.customers] == [books.customer.id]


def test_only_this_customers_approved_bills_in_the_period_count() -> None:
    books = _books()
    other = _customer(books, "C2")
    _bill(books, "SI-1", "1000")
    _bill(books, "SI-2", "1000", status="DRAFT")
    _bill(books, "SI-3", "1000", status="CANCELLED")
    _bill(books, "SI-4", "1000", customer=other)
    _bill(books, "SI-5", "1000", on=date(2026, 5, 2))
    _bill(books, "SI-6", "1000", status="CLOSED")
    may = _agreement(books, period=MAY, code="TR-5")

    assert _view(books, _agreement(books)).turnover == Decimal("2000.00")
    assert _view(books, may).turnover == Decimal("1000.00")


def test_a_group_agreement_sums_its_customers() -> None:
    books = _books()
    group = _group(books)
    first, second = _customer(books, "G1", group), _customer(books, "G2", group)
    _bill(books, "SI-1", "3000", customer=first)
    _bill(books, "SI-2", "2500", customer=second)
    _bill(books, "SI-3", "9000")  # books.customer is in no group
    row = _agreement(books, group=group)

    statement = CustomerRebateService(books.session).statement(
        row.id, firm_id=books.firm.id
    )

    assert statement.agreement.customer_group_name == "Stockists"
    assert statement.agreement.customer_id is None
    assert (statement.agreement.turnover, statement.agreement.earned) == (
        Decimal("5500.00"),
        Decimal("110.00"),
    )
    assert {item.customer_name: item.turnover for item in statement.customers} == {
        "Customer G1": Decimal("3000.00"),
        "Customer G2": Decimal("2500.00"),
    }


# ---- accrual -----------------------------------------------------------


def test_the_period_must_be_over_before_it_is_accrued() -> None:
    books = _books()
    today = utc_now().date()
    row = _agreement(books, period=(today - timedelta(days=10), today))

    with pytest.raises(ValidationError, match="accrue it after"):
        _accrue(books, row)


def test_accrual_books_the_rebate_and_keeps_what_it_booked() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    row = _accrue(books, _agreement(books))

    assert _legs(books, row.accrual_journal_id) == {
        ALLOWED: (Decimal("100.00"), Decimal("0.00")),
        PAYABLE: (Decimal("0.00"), Decimal("100.00")),
    }
    for purpose, code in (
        (ControlAccountPurpose.REBATES_ALLOWED, ALLOWED),
        (ControlAccountPurpose.CUSTOMER_REBATE_PAYABLE, PAYABLE),
    ):
        assert (
            books.session.get(LedgerAccount, books.account(purpose)).code  # type: ignore[union-attr]
            == code
        )
    # A bill booked into the period afterwards does not move what was booked,
    # though the statement still shows it.
    _bill(books, "SI-9", "1000")
    after = _view(books, row)
    assert (after.status, after.turnover, after.earned, after.to_settle) == (
        "ACCRUED",
        Decimal("5000.00"),
        Decimal("100.00"),
        Decimal("100.00"),
    )
    assert CustomerRebateService(books.session).statement(
        row.id, firm_id=books.firm.id
    ).turnover_today == Decimal("6000.00")
    with pytest.raises(ValidationError, match="accrued cannot be accrued"):
        _accrue(books, row)
    with pytest.raises(ValidationError, match="cannot be changed"):
        CustomerRebateService(books.session).update(
            row.id,
            CustomerRebateUpdate(name="New name"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="cannot be cancelled"):
        CustomerRebateService(books.session).cancel(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id
        )


def test_nothing_earned_is_not_accrued() -> None:
    books = _books()
    with pytest.raises(ValidationError, match="nothing to accrue"):
        _accrue(books, _agreement(books))


def test_an_accrual_needs_both_accounts_mapped() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    mapping = books.session.scalars(
        select(FirmControlAccount).where(
            FirmControlAccount.firm_id == books.firm.id,
            FirmControlAccount.purpose
            == ControlAccountPurpose.CUSTOMER_REBATE_PAYABLE.value,
        )
    ).one()
    books.session.delete(mapping)
    books.session.commit()

    with pytest.raises(ValidationError, match="CUSTOMER_REBATE_PAYABLE"):
        _accrue(books, _agreement(books))


def test_a_reversed_accrual_balances_and_the_next_takes_its_own_reference() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    service = CustomerRebateService(books.session)
    row = _accrue(books, _agreement(books))

    reversed_row = service.reverse_accrual(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id
    )

    assert (reversed_row.status, reversed_row.accrued_amount) == ("ACTIVE", None)
    assert _net(books, ALLOWED, PAYABLE) == {
        ALLOWED: Decimal("0.00"),
        PAYABLE: Decimal("0.00"),
    }
    # A bill booked late into the period is counted by the second accrual,
    # which posts the whole new figure under a reference of its own.
    _bill(books, "SI-2", "2500")
    again = _accrue(books, row)
    assert _legs(books, again.accrual_journal_id) == {
        ALLOWED: (Decimal("150.00"), Decimal("0.00")),
        PAYABLE: (Decimal("0.00"), Decimal("150.00")),
    }
    assert _net(books, ALLOWED, PAYABLE) == {
        ALLOWED: Decimal("150.00"),
        PAYABLE: Decimal("-150.00"),
    }
    references = sorted(
        books.session.scalars(
            select(JournalEntry.reference_number).where(
                JournalEntry.source_module == "customer_rebates"
            )
        ).all()
    )
    assert references == ["CREBATE-TR-1", "CREBATE-TR-1-2", "CREBATE-TR-1-REV"]


# ---- settlement --------------------------------------------------------


def test_a_settlement_comes_off_the_customers_account_and_the_payable() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    # Billed in March: owed, and outside the April turnover.
    owed = books.sales_invoice("SI-OPEN", "800.00", date(2026, 3, 20))
    books.owe_us("800.00")
    row = _accrue(books, _agreement(books))

    settled = _settle(books, row, "60.00", bill=owed.id)

    assert _legs(books, settled.journal_entry_id) == {
        PAYABLE: (Decimal("60.00"), Decimal("0.00")),
        RECEIVABLES: (Decimal("0.00"), Decimal("60.00")),
    }
    assert _owing(books) == Decimal("740.00")
    view = _view(books, row)
    assert (view.settled, view.to_settle) == (Decimal("60.00"), Decimal("40.00"))
    with pytest.raises(ValidationError, match="40.00 still to settle"):
        _settle(books, row, "50.00")
    with pytest.raises(ValidationError, match="already set against"):
        CustomerRebateService(books.session).reverse_accrual(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id
        )

    PartyAdjustmentService(books.session).cancel(
        settled.id,
        reason="Settled against the wrong month.",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        may_approve_above_threshold=True,
    )
    books.session.commit()

    assert _owing(books) == Decimal("800.00")
    assert _net(books, PAYABLE)[PAYABLE] == Decimal("-100.00")
    view = _view(books, row)
    assert (view.settled, view.to_settle) == (Decimal("0.00"), Decimal("100.00"))
    statement = CustomerRebateService(books.session).statement(
        row.id, firm_id=books.firm.id
    )
    assert [(item.amount, item.status) for item in statement.settlements] == [
        (Decimal("60.00"), "CANCELLED")
    ]


def test_a_rebate_is_not_settled_past_what_the_customer_owes() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    books.owe_us("30.00")
    row = _accrue(books, _agreement(books))

    with pytest.raises(ValidationError, match="owes 30.00"):
        _settle(books, row, "60.00")


def test_a_rebate_still_counting_or_somebody_elses_cannot_be_settled() -> None:
    books = _books()
    other = _customer(books, "C2")
    _bill(books, "SI-1", "5000")
    books.owe_us("500.00")
    row = _agreement(books)

    with pytest.raises(ValidationError, match="Only an accrued rebate"):
        _settle(books, row, "10.00")
    _accrue(books, row)
    with pytest.raises(ValidationError, match="another customer's"):
        _settle(books, row, "10.00", customer=other)


def test_a_group_rebate_settles_on_a_member_and_nobody_else() -> None:
    books = _books()
    group = _group(books)
    member = _customer(books, "G1", group)
    _bill(books, "SI-1", "5000", customer=member)
    books.owe_us("500.00")
    row = _accrue(books, _agreement(books, group=group))

    with pytest.raises(ValidationError, match="is not in"):
        _settle(books, row, "10.00")


def test_a_drafted_settlement_can_be_edited() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    books.owe_us("500.00")
    row = _accrue(books, _agreement(books))
    service = PartyAdjustmentService(books.session)
    draft = service.create(
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.CUSTOMER_REBATE,
            adjustment_date=WHEN + timedelta(days=15),
            customer_id=books.customer.id,
            amount=Decimal("60.00"),
            reason="April turnover rebate.",
            customer_rebate_agreement_id=row.id,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    changed = service.update(
        draft.id,
        PartyAdjustmentUpdate(amount=Decimal("70.00")),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )

    assert changed.amount == Decimal("70.00")
    assert changed.customer_rebate_agreement_id == row.id
    with pytest.raises(ValidationError, match="100.00 still to settle"):
        service.update(
            draft.id,
            PartyAdjustmentUpdate(amount=Decimal("170.00")),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_rebate_settlement_must_name_its_agreement() -> None:
    with pytest.raises(ValueError, match="Name the rebate agreement"):
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.CUSTOMER_REBATE,
            adjustment_date=WHEN,
            customer_id=uuid4(),
            amount=Decimal("1"),
            reason="Rebate",
        )
    with pytest.raises(ValueError, match="names a customer rebate agreement"):
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.CUSTOMER_WRITE_OFF,
            adjustment_date=WHEN,
            customer_id=uuid4(),
            amount=Decimal("1"),
            reason="Write off",
            customer_rebate_agreement_id=uuid4(),
        )


# ---- one live agreement over the same sales -----------------------------


def test_one_live_agreement_per_customer_per_overlapping_period() -> None:
    books = _books()
    service = CustomerRebateService(books.session)
    first = _agreement(books)

    with pytest.raises(ValidationError, match="already has rebate agreement TR-1"):
        _agreement(books, code="TR-2", period=(date(2026, 4, 30), date(2026, 6, 30)))
    with pytest.raises(ConflictError, match="TR-1 already exists"):
        _agreement(books, period=MAY)
    may = _agreement(books, code="TR-5", period=MAY)
    with pytest.raises(ValidationError, match="already has rebate agreement TR-1"):
        service.update(
            may.id,
            CustomerRebateUpdate(period_from=date(2026, 4, 15)),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    # Another customer is free to hold the same dates, and a withdrawn
    # agreement frees them.
    _agreement(books, code="TR-9", customer=_customer(books, "C2"))
    service.cancel(first.id, firm_id=books.firm.id, actor_id=books.actor_id)
    _agreement(books, code="TR-3")


def test_a_customer_and_its_group_cannot_both_cover_the_same_sales() -> None:
    books = _books()
    group = _group(books)
    member = _customer(books, "G1", group)
    _agreement(books, code="GRP", group=group)

    with pytest.raises(
        ValidationError, match="Customer G1 is in the customer group Stockists"
    ):
        _agreement(books, code="OWN", customer=member)
    with pytest.raises(ValidationError, match="Stockists already has rebate"):
        _agreement(books, code="GRP-2", group=group)
    _agreement(books, code="OWN-MAY", customer=member, period=MAY)

    with pytest.raises(
        ValidationError, match="Customer G1 is in the customer group Stockists and"
    ):
        _agreement(books, code="GRP-MAY", group=group, period=MAY)


def test_a_party_that_is_not_the_firms_is_refused() -> None:
    books = _books()
    service = CustomerRebateService(books.session)
    with pytest.raises(ValidationError, match="customer is not one of"):
        service.create(
            _write(books).model_copy(update={"customer_id": uuid4()}),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="group is not one of"):
        service.create(
            _write(books).model_copy(
                update={"customer_id": None, "customer_group_id": uuid4()}
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


# ---- update ------------------------------------------------------------


def test_an_update_leaves_alone_what_it_does_not_name() -> None:
    books = _books()
    service = CustomerRebateService(books.session)
    row = _agreement(books, agreed_before_sale=True)

    service.update(
        row.id,
        CustomerRebateUpdate(name="Renamed"),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )

    view = _view(books, row)
    assert (view.name, view.agreed_before_sale, view.period_to) == (
        "Renamed",
        True,
        APRIL[1],
    )
    assert [slab.threshold for slab in view.slabs] == [
        Decimal("1000.00"),
        Decimal("5000.00"),
    ]
    assert "status" not in CustomerRebateUpdate.model_fields
    assert "customer_id" not in CustomerRebateUpdate.model_fields
    with pytest.raises(ConflictError, match="changed since you loaded"):
        service.update(
            row.id,
            CustomerRebateUpdate(name="Stale"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
            expected_version=row.version - 1,
        )


# ---- statement and routes ----------------------------------------------


def test_the_statement_says_what_the_ca_needs_about_gst() -> None:
    books = _books()
    service = CustomerRebateService(books.session)
    after = _agreement(books)
    before = _agreement(books, code="TR-5", period=MAY, agreed_before_sale=True)

    assert (
        "financial credit"
        in service.statement(after.id, firm_id=books.firm.id).gst_note
    )
    assert "s.15(3)(b)" in service.statement(before.id, firm_id=books.firm.id).gst_note


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        """Keep the statement text."""
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _statements(bills: int) -> tuple[int, int]:
    """Return the statements the statement and a list page read."""
    books = _books()
    row = _agreement(books)
    for index in range(bills):
        bill = _bill(books, f"SI-{index:03d}", "100")
        _returned(books, f"SR-{index:03d}", "10")
        _note(books, CreditNote, f"CN-{index:03d}", bill, "5")
        _note(books, CustomerDebitNote, f"DN-{index:03d}", bill, "5")
    books.session.expire_all()
    service = CustomerRebateService(books.session)
    with _counting(books.session) as statement:
        service.statement(row.id, firm_id=books.firm.id)
    with _counting(books.session) as page:
        service.responses(service.list_agreements(firm_id=books.firm.id))
    return len(statement), len(page)


def test_the_statements_do_not_grow_with_the_bills() -> None:
    assert _statements(2) == _statements(12)


def test_the_routes_page_and_publish_the_version() -> None:
    books = _books()
    _bill(books, "SI-1", "5000")
    april = _accrue(books, _agreement(books))
    _agreement(books, code="TR-5", period=MAY)
    withdrawn = _agreement(
        books, code="TR-6", period=(date(2026, 6, 1), date(2026, 6, 30))
    )
    CustomerRebateService(books.session).cancel(
        withdrawn.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.owe_us("500.00")
    _settle(books, april, "25.00")
    scope = report_scope(books.firm.id)

    page = list_customer_rebates(scope=scope, page=1, page_size=2, db=books.session)
    assert page.pagination.total_records == 3
    assert [item.code for item in page.data] == ["TR-6", "TR-5"]
    found = list_customer_rebates(
        scope=scope, search="tr-1", page=1, page_size=20, db=books.session
    )
    assert [item.code for item in found.data] == ["TR-1"]

    response = Response()
    one = get_customer_rebate(
        april.id, scope=scope, response=response, db=books.session
    )
    assert one.data is not None
    assert response.headers["ETag"] == f'"{one.data.version}"'

    report = customer_rebate_statement_report(
        scope=scope,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 6, 30),
        page=1,
        page_size=50,
        db=books.session,
    )
    assert report.pagination.total_records == 2, "a withdrawn agreement is left out"
    assert [
        (row.code, row.accrued, row.settled, row.balance) for row in report.data
    ] == [
        ("TR-5", Decimal("0"), Decimal("0"), Decimal("0")),
        ("TR-1", Decimal("100.00"), Decimal("25.00"), Decimal("75.00")),
    ]
    only_may = customer_rebate_statement_report(
        scope=scope,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        page=1,
        page_size=50,
        db=books.session,
    )
    assert [row.code for row in only_may.data] == ["TR-5"]
    for path in ("", "/reports/statement"):
        assert_page_size_is_bounded(router, f"/api/v1/customer-rebates{path}")


def test_the_codes_the_routes_take_are_seeded_and_settling_is_held_back() -> None:
    seeded = {code for codes in PERMISSION_GROUPS.values() for code in codes}
    assert {"SALES_VIEW", "SALES_APPROVE"} <= seeded
    assert {
        "PARTY_ADJUSTMENT_VIEW",
        "PARTY_ADJUSTMENT_MANAGE",
        "PARTY_ADJUSTMENT_APPROVE",
    } <= seeded
    # Whoever promises the rebate must not be the one who moves the account.
    assert (
        not {
            "PARTY_ADJUSTMENT_MANAGE",
            "PARTY_ADJUSTMENT_APPROVE",
        }
        & ROLE_PERMISSION_CODES["SALES_MANAGER"]
    )
