"""A customer who is not ACTIVE takes no new sales document.

D-MST-6: nothing on the sales side read ``customers.status``. With a customer
INACTIVE an order was raised and approved, though the delete refusal tells the
user to "set the customer inactive to stop trading with them" and the purchase
side has always checked its counterparty. New documents are refused by name;
what is already in flight carries on.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.quotation.models import SalesQuotation
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceStatus
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_quotation_module import _session_factory as _quotation_db
from tests.unit.test_quotation_module import _Setup
from tests.unit.test_sales_chain_synthesis import _Firm
from tests.unit.test_sales_chain_synthesis import _session_factory as _chain_db


def _set_status(setup: _Setup | _Firm, customer: Customer, status: str) -> None:
    """Move a customer to a status, as the customer form would."""
    customer.status = status
    setup.session.commit()


def _order(setup: _Setup, customer: Customer) -> SalesOrderCreate:
    """Build a one-line sales order for the given customer."""
    return SalesOrderCreate(
        customer_id=customer.id,
        branch_id=setup.branch.id,
        warehouse_id=setup.warehouse.id,
        order_date=utc_now().date(),
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=setup.product.id,
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
            )
        ],
    )


@pytest.mark.parametrize(
    ("status", "words"), [("INACTIVE", "is inactive"), ("ON_HOLD", "is on hold")]
)
def test_no_new_order_or_quotation_for_a_customer_who_is_not_active(
    status: str, words: str
) -> None:
    """Both refuse by the customer's code and name, and write nothing."""
    setup = _Setup(_quotation_db()())
    _set_status(setup, setup.customer, status)

    with pytest.raises(ValidationError) as order_refused:
        SalesOrderService(setup.session).create_order(
            _order(setup, setup.customer),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    setup.session.rollback()
    with pytest.raises(ValidationError) as quote_refused:
        setup.service.create_quotation(
            setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
        )
    setup.session.rollback()

    assert setup.customer.code in str(order_refused.value)
    assert words in str(order_refused.value)
    assert "new sales order" in str(order_refused.value)
    assert "new quotation" in str(quote_refused.value)
    assert setup.session.scalar(select(SalesOrder.id)) is None
    assert setup.session.scalar(select(SalesQuotation.id)) is None


def test_an_active_customer_is_sold_to_as_before() -> None:
    """The check is about the status and nothing else."""
    setup = _Setup(_quotation_db()())

    order = SalesOrderService(setup.session).create_order(
        _order(setup, setup.customer), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    assert order.status == "DRAFT"


def test_an_accepted_offer_does_not_become_an_order_once_they_are_inactive() -> None:
    """Converting raises a new order, which is where a sale commits stock."""
    setup = _Setup(_quotation_db()())
    accepted = setup.accepted()
    _set_status(setup, setup.customer, "INACTIVE")

    with pytest.raises(ValidationError, match="is inactive"):
        setup.service.convert_quotation(
            accepted.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )
    setup.session.rollback()

    setup.session.refresh(accepted)
    assert accepted.status == "ACCEPTED"
    assert setup.session.scalar(select(SalesOrder.id)) is None


def test_a_draft_already_raised_carries_on_but_cannot_move_to_them() -> None:
    """An edit that keeps the customer saves; one that moves to them does not."""
    setup = _Setup(_quotation_db()())
    orders = SalesOrderService(setup.session)
    draft = orders.create_order(
        _order(setup, setup.customer), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    quotation = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    _set_status(setup, setup.customer, "INACTIVE")

    kept = orders.update_order(
        draft.id,
        _order(setup, setup.customer),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert kept.customer_id == setup.customer.id
    setup.service.update_quotation(
        quotation.id, setup.payload(), firm_scope=setup.firm.id, actor_id=uuid4()
    )

    # A second, active customer's draft cannot be pointed at the inactive one.
    other = Customer(
        firm_id=setup.firm.id,
        code="CUST-OTHER",
        customer_type="RETAIL",
        name="Other",
        display_name="Other",
        currency_code="INR",
        status="ACTIVE",
    )
    setup.session.add(other)
    setup.session.commit()
    theirs = orders.create_order(
        _order(setup, other), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    with pytest.raises(ValidationError, match="is inactive"):
        orders.update_order(
            theirs.id,
            _order(setup, setup.customer),
            firm_scope=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_bill_without_an_order_is_refused_as_a_bill_and_leaves_nothing() -> None:
    """The counter sale says what the person was raising."""
    setup = _Firm(_chain_db()())
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _set_status(setup, setup.customer, "INACTIVE")

    with pytest.raises(ValidationError) as refused:
        SalesInvoiceService(setup.session).create_invoice(
            setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
        )
    setup.session.rollback()

    assert "new bill cannot be raised" in str(refused.value)
    assert setup.session.scalar(select(SalesOrder.id)) is None
    assert setup.session.scalar(select(SalesInvoice.id)) is None


def test_a_bill_already_in_flight_is_still_approved() -> None:
    """Going inactive stops new business, not what is already owed."""
    setup = _Firm(_chain_db()())
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(setup.session)
    actor = uuid4()
    draft = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )
    _set_status(setup, setup.customer, "INACTIVE")

    approved = service.approve_invoice(
        draft.id, firm_scope=setup.firm.id, actor_id=actor
    )

    assert approved.status == SalesInvoiceStatus.APPROVED.value
