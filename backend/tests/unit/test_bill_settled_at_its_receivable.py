"""Money is judged against what the customer is asked to pay (D-SELL-83).

A bill carries four decimals and the books carry two. A walk-in bill of
97.1376 debits the receivable 97.14, and that is what the customer hands
over. The over-tender check compared the money with the unrounded total while
the walk-in rule beside it used the rounded one, so 97.14 was "more than the
bill" and 97.13 "less than it" -- no amount could approve the bill.

Every case here runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.customers.services.cash_customer import stage_cash_customer
from app.finance.models import JournalLine
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceTenderWrite,
)
from app.sales_invoice.services import SalesInvoiceService
from app.settlements.models.settlement import Settlement, SettlementAllocation
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

#: A total that is not a whole paisa; the receivable it posts is 97.14.
_TOTAL = Decimal("97.1376")
_PAYABLE = Decimal("97.14")


def _counter() -> tuple[Session, _Firm, Customer]:
    """Return a firm that types only the bill, and its cash customer."""
    session = _request_session()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    cash = stage_cash_customer(session, setup.firm.id, actor_id=uuid4())
    session.commit()
    return session, setup, cash


def _bill(setup: _Firm, customer: Customer, **fields: object) -> SalesInvoice:
    """Save a draft of one unit at a price that leaves a fraction of a paisa."""
    data = SalesInvoiceCreate(
        customer_id=customer.id,
        invoice_date=date(2026, 8, 4),
        lines=[
            SalesInvoiceLineWrite(
                product_id=setup.product.id,
                line_number=1,
                current_invoice_quantity=Decimal("1"),
                unit_price=_TOTAL,
            )
        ],
        **fields,  # type: ignore[arg-type]
    )
    bill = SalesInvoiceService(setup.session).create_invoice(
        data, firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert Decimal(str(bill.grand_total)) == _TOTAL
    return bill


def _approve(setup: _Firm, bill: SalesInvoice) -> SalesInvoice:
    """Approve a bill as the route does."""
    return SalesInvoiceService(setup.session).approve_invoice(
        bill.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )


def _owing(setup: _Firm, customer: Customer) -> list[Decimal]:
    """Return what each of a customer's bills still owes."""
    return [
        record.outstanding_amount
        for record in ReceiptService(setup.session).outstanding_invoices(
            firm_id=setup.firm.id, party_id=customer.id
        )
    ]


def _books_balance(session: Session) -> None:
    """Assert every journal line written so far sums to nothing."""
    debit, credit = session.execute(
        select(
            func.coalesce(func.sum(JournalLine.debit_amount), 0),
            func.coalesce(func.sum(JournalLine.credit_amount), 0),
        )
    ).one()
    assert Decimal(str(debit)) == Decimal(str(credit))
    # Nothing in the books carries the fraction of a paisa.
    for line in session.scalars(select(JournalLine)).all():
        for amount in (line.debit_amount, line.credit_amount):
            assert Decimal(str(amount)) == Decimal(str(amount)).quantize(
                Decimal("0.01")
            )


def test_the_response_states_what_the_customer_is_asked_to_pay() -> None:
    """`amount_payable` is the total at the ledger's two decimals."""
    session, setup, cash = _counter()
    bill = _bill(setup, cash)

    answered = SalesInvoiceService(session).invoice_response(bill)

    assert answered.grand_total == _TOTAL
    assert answered.amount_payable == _PAYABLE


def test_a_walk_in_bill_is_settled_by_its_receivable_exactly() -> None:
    """97.14 received on a bill of 97.1376 approves and leaves nothing owing."""
    session, setup, cash = _counter()
    bill = _bill(setup, cash, received_now_amount=_PAYABLE, received_now_method="CASH")

    approved = _approve(setup, bill)

    assert approved.status == "APPROVED"
    receipt = session.get(Settlement, approved.received_now_settlement_id)
    assert receipt is not None and Decimal(str(receipt.amount)) == _PAYABLE
    allocated = session.scalar(
        select(SettlementAllocation.amount).where(
            SettlementAllocation.settlement_id == receipt.id
        )
    )
    assert Decimal(str(allocated)) == _PAYABLE
    session.refresh(cash)
    assert Decimal(str(cash.current_outstanding)) == Decimal("0")
    assert _owing(setup, cash) == []
    _books_balance(session)


def test_a_paisa_short_on_a_walk_in_bill_is_told_the_rounded_figure() -> None:
    """97.13 is short of 97.14, and the refusal names what the bill comes to."""
    session, setup, cash = _counter()
    bill = _bill(
        setup, cash, received_now_amount=Decimal("97.13"), received_now_method="CASH"
    )

    with pytest.raises(ValidationError) as refused:
        _approve(setup, bill)

    assert "comes to 97.14 and 97.13 was received. Take the rest" in str(refused.value)


def test_a_paisa_over_is_change_measured_from_the_receivable() -> None:
    """97.15 is refused against 97.14, never against 97.1376."""
    session, setup, _ = _counter()
    bill = _bill(
        setup,
        setup.customer,
        received_now_amount=Decimal("97.15"),
        received_now_method="CASH",
    )

    with pytest.raises(ValidationError) as refused:
        _approve(setup, bill)

    assert "97.15 was received against a bill of 97.14." in str(refused.value)
    assert "change is handed back" in str(refused.value)


def test_split_tenders_settle_the_receivable() -> None:
    """Cash and UPI that add up to 97.14 approve a walk-in bill of 97.1376."""
    session, setup, cash = _counter()
    bill = _bill(
        setup,
        cash,
        received_now_tenders=[
            SalesInvoiceTenderWrite(mode="CASH", amount=Decimal("50.00")),
            SalesInvoiceTenderWrite(
                mode="UPI", amount=Decimal("47.14"), reference="UPI-1"
            ),
        ],
    )

    approved = _approve(setup, bill)

    assert approved.status == "APPROVED"
    session.refresh(cash)
    assert Decimal(str(cash.current_outstanding)) == Decimal("0")
    assert _owing(setup, cash) == []
    _books_balance(session)


def test_a_named_customer_who_pays_the_receivable_owes_nothing() -> None:
    """97.14 on a credit customer's bill of 97.1376 clears it at approval."""
    session, setup, _ = _counter()
    bill = _bill(
        setup,
        setup.customer,
        received_now_amount=_PAYABLE,
        received_now_method="CASH",
    )

    _approve(setup, bill)

    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")
    assert _owing(setup, setup.customer) == []
    _books_balance(session)


def test_a_receipt_of_the_receivable_clears_a_credit_bill() -> None:
    """Paid later through a receipt: 97.14 allocated leaves the bill at nothing."""
    session, setup, _ = _counter()
    bill = _approve(setup, _bill(setup, setup.customer))
    assert _owing(setup, setup.customer) == [_PAYABLE]

    ReceiptService(session).create(
        SettlementCreate(
            party_id=setup.customer.id,
            settlement_date=date(2026, 8, 5),
            amount=_PAYABLE,
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(invoice_id=bill.id, amount=_PAYABLE)
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    session.commit()

    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")
    assert _owing(setup, setup.customer) == []
    _books_balance(session)
