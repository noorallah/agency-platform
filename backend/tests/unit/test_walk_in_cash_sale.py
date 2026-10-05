"""A walk-in cash sale: a counter bill for a buyer with no record (§87 #2).

One built-in *Cash sale* customer per firm, made on the first ask. Its bills
carry the buyer typed at the counter, are paid in full when approved, earn no
loyalty, and are B2C in GSTR-1 because the customer is unregistered.
"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.customers.services import CustomerService
from app.customers.services.cash_customer import (
    assert_cash_customer_stays,
    stage_cash_customer,
)
from app.loyalty.services import LoyaltyService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_invoice.services.invoice_pdf import PartyBlock
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
    _as_typed_at_the_counter,
)
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory


def _counter() -> tuple[Session, _Firm, Customer]:
    """Return a firm that types only the bill, and its cash customer."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    cash = stage_cash_customer(session, setup.firm.id, actor_id=uuid4())
    session.commit()
    return session, setup, cash


def _walk_in_bill(setup: _Firm, cash: Customer, **fields: object) -> SalesInvoiceCreate:
    """Describe a counter bill to the cash customer."""
    return setup.bare_bill().model_copy(
        update={"customer_id": cash.id, "buyer_name": "Ravi", **fields}
    )


def _draft(session: Session, setup: _Firm, data: SalesInvoiceCreate) -> SalesInvoice:
    """Save a bill as a draft."""
    return SalesInvoiceService(session).create_invoice(
        data, firm_id=setup.firm.id, actor_id=uuid4()
    )


def test_the_cash_customer_is_made_once_per_firm() -> None:
    """A second ask returns the same record; it is unregistered and active."""
    session, setup, cash = _counter()

    again = stage_cash_customer(session, setup.firm.id, actor_id=uuid4())

    assert again.id == cash.id
    assert (cash.name, cash.status, cash.gst_number) == ("Cash sale", "ACTIVE", None)
    assert (
        session.scalar(
            select(func.count(Customer.id)).where(Customer.is_cash_sale.is_(True))
        )
        == 1
    )


def test_a_code_already_taken_does_not_stop_it_being_made() -> None:
    """A firm that already has a customer coded CASH gets the next code."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.customer.code = "CASH"
    session.commit()

    cash = stage_cash_customer(session, setup.firm.id, actor_id=uuid4())

    assert cash.code == "CASH-2"


def test_the_route_returns_the_cash_customer() -> None:
    """The counter asks under the permission that raises a bill."""
    from app.sales_invoice.api.router import walk_in_customer

    session = _session_factory()()
    setup = _Firm(session)
    scope = SimpleNamespace(firm_id=setup.firm.id, actor_id=uuid4())

    first = walk_in_customer(scope=scope, db=session)  # type: ignore[arg-type]
    second = walk_in_customer(scope=scope, db=session)  # type: ignore[arg-type]

    assert first.data is not None and second.data is not None
    assert first.data.id == second.data.id
    assert first.data.name == "Cash sale"


def test_the_cash_customer_cannot_be_deleted_or_given_credit() -> None:
    """Every walk-in bill names it, and nothing may be left owing on it."""
    session, setup, cash = _counter()

    with pytest.raises(ValidationError, match="cannot be deleted"):
        CustomerService(session).delete(
            cash.id, firm_scope=setup.firm.id, actor_id=uuid4()
        )
    with pytest.raises(ValidationError, match="takes no credit"):
        assert_cash_customer_stays(cash, {"credit_limit": Decimal("5000")})
    with pytest.raises(ValidationError, match="unregistered"):
        assert_cash_customer_stays(cash, {"gst_number": "29AAACR5055K1Z5"})
    with pytest.raises(ValidationError, match="stays active"):
        assert_cash_customer_stays(cash, {"status": "INACTIVE"})
    assert_cash_customer_stays(cash, {"notes": "counter"})
    assert_cash_customer_stays(setup.customer, {"credit_limit": Decimal("5000")})


def test_a_walk_in_bill_keeps_the_buyer_typed_at_the_counter() -> None:
    """The name and phone are stored, answered and survive an edit."""
    session, setup, cash = _counter()
    service = SalesInvoiceService(session)
    draft = _draft(
        session, setup, _walk_in_bill(setup, cash, buyer_phone=" 9876543210 ")
    )

    assert (draft.buyer_name, draft.buyer_phone) == ("Ravi", "9876543210")
    assert service.invoice_response(draft).buyer_name == "Ravi"

    # An editor that never showed the buyer leaves it alone.
    [line] = service.invoice_response(draft).lines
    silent = SalesInvoiceCreate(
        customer_id=cash.id,
        invoice_date=draft.invoice_date,
        lines=[
            SalesInvoiceLineWrite(
                source_document_type=line.source_document_type,
                source_document_id=line.source_document_id,
                source_document_line_id=line.source_document_line_id,
                line_number=1,
                current_invoice_quantity=Decimal("4"),
            )
        ],
    )
    edited = service.update_invoice(
        draft.id, silent, firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert (edited.buyer_name, edited.buyer_phone) == ("Ravi", "9876543210")


def test_a_buyer_is_refused_on_a_bill_to_a_customer_with_a_record() -> None:
    """A second name would print a buyer the books do not know."""
    session, setup, _ = _counter()

    with pytest.raises(ValidationError, match="only on a walk-in bill"):
        _draft(
            session, setup, setup.bare_bill().model_copy(update={"buyer_name": "Ravi"})
        )


def test_a_walk_in_bill_is_paid_in_full_when_approved() -> None:
    """Nothing may be left owing by nobody in particular."""
    session, setup, cash = _counter()
    service = SalesInvoiceService(session)
    unpaid = _draft(session, setup, _walk_in_bill(setup, cash))
    total = Decimal(str(unpaid.grand_total)).quantize(Decimal("0.01"))

    with pytest.raises(ValidationError, match="paid in full at the counter"):
        service.approve_invoice(unpaid.id, firm_scope=setup.firm.id, actor_id=uuid4())
    session.rollback()

    unpaid.received_now_amount = total
    unpaid.received_now_method = "CASH"
    session.commit()
    approved = service.approve_invoice(
        unpaid.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )

    assert approved.status == "APPROVED"
    assert approved.received_now_settlement_id is not None
    session.refresh(cash)
    assert Decimal(str(cash.current_outstanding)) == Decimal("0")


def test_a_credit_customers_bill_still_approves_unpaid() -> None:
    """The rule is the cash customer's, not the counter's."""
    session, setup, _ = _counter()
    draft = _draft(session, setup, setup.bare_bill())

    approved = SalesInvoiceService(session).approve_invoice(
        draft.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )

    assert approved.status == "APPROVED"


def test_a_walk_in_bill_earns_no_loyalty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Points would pool on an account that belongs to nobody."""
    session, setup, cash = _counter()
    earned: list[object] = []
    monkeypatch.setattr(
        LoyaltyService,
        "stage_earning",
        lambda self, invoice, **_: earned.append(invoice.customer_id),
    )
    service = SalesInvoiceService(session)
    for customer_id in (cash.id, setup.customer.id):
        draft = _draft(
            session,
            setup,
            setup.bare_bill().model_copy(update={"customer_id": customer_id}),
        )
        total = Decimal(str(draft.grand_total)).quantize(Decimal("0.01"))
        draft.received_now_amount = total
        draft.received_now_method = "CASH"
        session.commit()
        service.approve_invoice(draft.id, firm_scope=setup.firm.id, actor_id=uuid4())

    assert earned == [setup.customer.id]


def test_the_print_names_the_buyer_typed_at_the_counter() -> None:
    """The cash customer's own name gives way to the one on the bill."""
    block = PartyBlock(name="Cash sale", address_lines=[], contact=None)

    typed = _as_typed_at_the_counter(
        block,
        SimpleNamespace(buyer_name="Ravi", buyer_phone="98765"),  # type: ignore[arg-type]
    )
    untyped = _as_typed_at_the_counter(
        block,
        SimpleNamespace(buyer_name=None, buyer_phone=None),  # type: ignore[arg-type]
    )

    assert (typed.name, typed.contact) == ("Ravi", "98765")
    assert untyped is block


def test_the_print_ships_to_the_buyer_typed_at_the_counter() -> None:
    """D-SELL-65: SHIPPED TO read "Cash sale" beside a BILLED TO naming Ravi."""
    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash, buyer_phone="98765"))

    document = SalesInvoicePrintService(session)._document(
        bill, firm_scope=setup.firm.id
    )

    assert document.buyer.name == "Ravi"
    assert document.ship_to is not None
    assert (document.ship_to.name, document.ship_to.contact) == ("Ravi", "98765")


def test_more_than_a_walk_in_bill_comes_to_is_change_not_a_shortfall() -> None:
    """D-SELL-66: 200 tendered on a bill of 118 was told to "Take the rest"."""
    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    total = Decimal(str(bill.grand_total)).quantize(Decimal("0.01"))
    bill.received_now_amount = total + 82
    bill.received_now_method = "CASH"
    session.commit()

    with pytest.raises(ValidationError) as refused:
        SalesInvoiceService(session).approve_invoice(
            bill.id, firm_scope=setup.firm.id, actor_id=uuid4()
        )

    assert "change is handed back" in str(refused.value)
    assert "Take the rest" not in str(refused.value)
