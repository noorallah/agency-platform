"""A firm decides, per sales document, whether approval is its own step.

Backlog 119. A firm run by one person has nobody to approve what that person
typed, so the order, the delivery note and the bill each have a switch in
`sales_workflow_settings`. Off, whoever raised the document approves it under
the code they raised it with, and the desktop's Save does both. What must
stay true:

- the answer is stamped on the document as it is raised, so switching the
  setting never changes a document already made;
- the stamp is the server's -- no request can carry it;
- only the author is let through, and only without an approver's code;
- every check approval runs still runs.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.delivery_note.api.router import approve_delivery_note
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.sales_invoice.api.router import approve_sales_invoice
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.api.router import approve_sales_order
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesWorkflowSettingsWrite,
)
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

_STAGES = {
    "quotation_stage": False,
    "sales_order_stage": False,
    "delivery_note_stage": False,
}
_WHOLE_CHAIN = {
    "quotation_stage": True,
    "sales_order_stage": True,
    "delivery_note_stage": True,
}


def _scope(setup: _Firm, user_id: UUID, *codes: str) -> ResolvedFirmScope:
    """Act in the firm as one user holding exactly these codes."""
    return ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset(codes),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=setup.firm.id,
    )


def _save(setup: _Firm, **values: object) -> None:
    """Save the firm's settings through the service a request reaches."""
    SalesWorkflowService(setup.session).update_settings(
        SalesWorkflowSettingsWrite.model_validate(values),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _bill(setup: _Firm, actor: UUID) -> SalesInvoice:
    """Raise a counter bill as one user."""
    return SalesInvoiceService(setup.session).create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )


def _order(setup: _Firm, actor: UUID) -> SalesOrder:
    """Raise a sales order as one user."""
    return SalesOrderService(setup.session).create_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )


def _note(setup: _Firm, order: SalesOrder, actor: UUID) -> DeliveryNote:
    """Raise a delivery note against an approved order as one user."""
    line = setup.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    return DeliveryNoteService(setup.session).create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 3),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )


def test_a_firm_that_never_chose_keeps_approval_on_every_document() -> None:
    session = _session_factory()()
    setup = _Firm(session)

    answer = SalesWorkflowService(session).settings_response(setup.firm.id)

    assert answer.sales_order_approval is True
    assert answer.delivery_note_approval is True
    assert answer.sales_invoice_approval is True


def test_the_switches_are_saved_and_an_omitted_one_is_left_alone() -> None:
    session = _session_factory()()
    setup = _Firm(session)

    _save(setup, **_STAGES, sales_invoice_approval=False)
    first = SalesWorkflowService(session).settings_response(setup.firm.id)
    assert first.sales_invoice_approval is False
    assert first.sales_order_approval is True
    assert first.delivery_note_approval is True

    # An editor that never showed the switches sends none of them.
    _save(setup, **_STAGES)
    second = SalesWorkflowService(session).settings_response(setup.firm.id)
    assert second.sales_invoice_approval is False

    _save(setup, **_STAGES, sales_invoice_approval=True, sales_order_approval=False)
    third = SalesWorkflowService(session).settings_response(setup.firm.id)
    assert third.sales_invoice_approval is True
    assert third.sales_order_approval is False

    trail = session.scalars(
        select(AuditLog).where(AuditLog.entity_type == "sales_workflow_settings")
    ).all()
    assert trail[-1].after_data is not None
    assert trail[-1].after_data["sales_order_approval"] is False


def test_no_request_can_carry_the_stamp() -> None:
    assert "approval_step" not in SalesInvoiceCreate.model_fields
    assert "approval_step" not in SalesOrderCreate.model_fields
    assert "approval_step" not in DeliveryNoteCreate.model_fields


def test_one_save_bills_where_no_step_is_switched_on() -> None:
    """A counter clerk raises and completes a bill with the create code alone."""
    session = _session_factory()()
    setup = _Firm(session)
    _save(setup, **_STAGES, sales_invoice_approval=False)
    clerk = uuid4()

    bill = _bill(setup, clerk)
    assert bill.approval_step is False
    assert bill.status == "DRAFT"

    answer = approve_sales_invoice(
        _scope(setup, clerk, "SALES_INVOICE_CREATE"), session, bill.id
    )

    assert answer.data is not None
    assert answer.data.status == "APPROVED"
    assert answer.data.approval_step is False
    # The goods left with it: the chain behind the bill is as real as ever.
    note = session.scalar(select(DeliveryNote))
    assert note is not None
    assert note.status == "DISPATCHED"


def test_a_firm_with_approval_on_is_stopped_at_it() -> None:
    session = _session_factory()()
    setup = _Firm(session)
    _save(setup, **_STAGES)
    clerk = uuid4()
    bill = _bill(setup, clerk)
    assert bill.approval_step is True

    with pytest.raises(AuthorizationError, match="waits for approval"):
        approve_sales_invoice(
            _scope(setup, clerk, "SALES_INVOICE_CREATE"), session, bill.id
        )
    session.refresh(bill)
    assert bill.status == "DRAFT"

    answer = approve_sales_invoice(
        _scope(setup, uuid4(), "SALES_APPROVE"), session, bill.id
    )
    assert answer.data is not None
    assert answer.data.status == "APPROVED"


def test_only_the_author_completes_a_bill_without_the_approve_code() -> None:
    session = _session_factory()()
    setup = _Firm(session)
    _save(setup, **_STAGES, sales_invoice_approval=False)
    bill = _bill(setup, uuid4())

    with pytest.raises(AuthorizationError, match="Only whoever raised"):
        approve_sales_invoice(
            _scope(setup, uuid4(), "SALES_INVOICE_CREATE"), session, bill.id
        )

    # An approver is still an approver, whoever raised it.
    answer = approve_sales_invoice(
        _scope(setup, uuid4(), "SALES_APPROVE"), session, bill.id
    )
    assert answer.data is not None
    assert answer.data.status == "APPROVED"


def test_a_document_keeps_the_steps_it_was_made_under() -> None:
    session = _session_factory()()
    setup = _Firm(session)
    clerk = uuid4()
    _save(setup, **_STAGES)
    made_under_approval = _bill(setup, clerk)

    _save(setup, **_STAGES, sales_invoice_approval=False)
    made_without = _bill(setup, clerk)
    _save(setup, **_STAGES, sales_invoice_approval=True)

    scope = _scope(setup, clerk, "SALES_INVOICE_CREATE")
    with pytest.raises(AuthorizationError, match="waits for approval"):
        approve_sales_invoice(scope, session, made_under_approval.id)
    answer = approve_sales_invoice(scope, session, made_without.id)
    assert answer.data is not None
    assert answer.data.status == "APPROVED"


def test_a_check_approval_makes_still_refuses_the_author() -> None:
    """Approval off removes the second person, never the checks."""
    session = _session_factory()()
    setup = _Firm(session)
    _save(setup, **_STAGES, sales_invoice_approval=False)
    clerk = uuid4()
    bill = SalesInvoiceService(session).create_invoice(
        setup.bare_bill(Decimal("500")), firm_id=setup.firm.id, actor_id=clerk
    )

    with pytest.raises(Exception, match=r"(?i)stock|available|insufficient"):
        approve_sales_invoice(
            _scope(setup, clerk, "SALES_INVOICE_CREATE"), session, bill.id
        )
    session.rollback()
    session.refresh(bill)
    assert bill.status == "DRAFT"


def test_an_order_and_a_note_each_follow_their_own_switch() -> None:
    session = _session_factory()()
    setup = _Firm(session)
    _save(setup, **_WHOLE_CHAIN, sales_order_approval=False)
    salesman = uuid4()
    storeman = uuid4()

    order = _order(setup, salesman)
    assert order.approval_step is False
    approved = approve_sales_order(
        order.id, _scope(setup, salesman, "SALES_ORDER_CREATE"), session
    )
    assert approved.data is not None
    assert approved.data.status == "APPROVED"
    assert approved.data.approval_step is False

    # The note's switch is still on, so its author is stopped at it.
    note = _note(setup, order, storeman)
    assert note.approval_step is True
    with pytest.raises(AuthorizationError, match="waits for approval"):
        approve_delivery_note(
            note.id, _scope(setup, storeman, "DELIVERY_NOTE_CREATE"), session
        )

    _save(setup, **_WHOLE_CHAIN, delivery_note_approval=False)
    session.refresh(note)
    assert note.approval_step is True, "a note already made keeps its step"
    note.status = "CANCELLED"
    session.commit()

    second = _note(setup, order, storeman)
    assert second.approval_step is False
    with pytest.raises(AuthorizationError, match="Only whoever raised"):
        approve_delivery_note(
            second.id, _scope(setup, uuid4(), "DELIVERY_NOTE_CREATE"), session
        )
    answer = approve_delivery_note(
        second.id, _scope(setup, storeman, "DELIVERY_NOTE_CREATE"), session
    )
    assert answer.data is not None
    assert answer.data.status == "APPROVED"
    assert answer.data.created_by == storeman
    assert answer.data.approval_step is False
