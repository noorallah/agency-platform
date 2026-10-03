"""A new outlet waits for the office before it is billed (SEL-15, decision A93).

With the firm's switch on, a shop added by somebody who cannot approve it
starts PENDING. It may still be quoted and take orders; a bill for it is
refused by name until somebody holding CUSTOMER_APPROVE approves it. The
office adding a shop is the approval, so theirs starts ACTIVE.
"""

# ruff: noqa: D103

from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.customers.schemas.customer import (
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    CustomerUpdate,
)
from app.customers.services import CustomerService
from app.customers.services.trading_status import (
    assert_customer_may_be_billed,
    assert_customer_takes_new_documents,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.schemas import SalesWorkflowSettingsWrite
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory


def _switch_on(setup: _Firm) -> None:
    SalesWorkflowService(setup.session).update_settings(
        SalesWorkflowSettingsWrite(
            quotation_stage=False,
            sales_order_stage=False,
            delivery_note_stage=False,
            new_outlets_need_approval=True,
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _new_shop(code: str) -> CustomerCreate:
    return CustomerCreate(
        code=code,
        customer_type=CustomerType.BUSINESS,
        name=f"Shop {code}",
        currency_code="INR",
    )


def test_a_salesmans_outlet_waits_and_the_offices_does_not() -> None:
    setup = _Firm(_session_factory()())
    _switch_on(setup)
    customers = CustomerService(setup.session)
    pending = customers.create(
        _new_shop("NEW-1"), firm_id=setup.firm.id, actor_id=uuid4(), may_approve=False
    )
    assert pending.status == CustomerStatus.PENDING.value
    office = customers.create(
        _new_shop("NEW-2"), firm_id=setup.firm.id, actor_id=uuid4(), may_approve=True
    )
    assert office.status == CustomerStatus.ACTIVE.value

    # Orders are taken; the bill waits.
    assert_customer_takes_new_documents(pending, document="sales order")
    with pytest.raises(ValidationError, match="waiting for approval"):
        assert_customer_may_be_billed(pending)

    # Somebody without the code cannot set it active by editing it.
    with pytest.raises(AuthorizationError, match="CUSTOMER_APPROVE"):
        customers.update(
            pending.id,
            CustomerUpdate(
                code="NEW-1",
                customer_type=CustomerType.BUSINESS,
                name="Shop NEW-1",
                currency_code="INR",
                status=CustomerStatus.ACTIVE,
            ),
            firm_scope=setup.firm.id,
            actor_id=uuid4(),
            may_approve=False,
        )
    approved = customers.approve(pending.id, firm_id=setup.firm.id, actor_id=uuid4())
    setup.session.commit()
    assert approved.status == CustomerStatus.ACTIVE.value
    with pytest.raises(ValidationError, match="not waiting for approval"):
        customers.approve(pending.id, firm_id=setup.firm.id, actor_id=uuid4())


def test_a_bill_for_a_pending_outlet_is_refused() -> None:
    setup = _Firm(_session_factory()())
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.customer.status = CustomerStatus.PENDING.value
    setup.session.commit()
    with pytest.raises(ValidationError, match="waiting for approval"):
        SalesInvoiceService(setup.session).create_invoice(
            setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
        )


def test_with_the_switch_off_every_new_customer_is_active() -> None:
    setup = _Firm(_session_factory()())
    created = CustomerService(setup.session).create(
        _new_shop("NEW-3"), firm_id=setup.firm.id, actor_id=uuid4(), may_approve=False
    )
    assert created.status == CustomerStatus.ACTIVE.value
