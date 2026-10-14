"""A firm may require a salesman on every order, delivery note and bill (P2).

``sales_workflow_settings.salesman_required`` is off unless a firm switches it
on (``docs/design/SALESMAN_LIST_DESIGN.md``, section 6). On, the order, the
note and the bill refuse a save that names no salesman once the server's own
fill has run -- in create, in update and in the chain a bare bill raises. The
quotation is not held to it.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.quotation.schemas.quotation import QuotationCreate, QuotationLineWrite
from app.quotation.services.quotation_service import QuotationService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesWorkflowSettings
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesWorkflowSettingsWrite,
)
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from app.salesmen.models import Salesman
from app.salesmen.services.required import SALESMAN_REQUIRED_MESSAGE
from tests.unit.test_sales_chain_synthesis import (
    _bill_of,
    _Firm,
    _persons_note,
    _session_factory,
)

REFUSAL = "This firm requires a salesman on every order, delivery note and bill."


def _setup(*, stages: bool = True) -> _Firm:
    """Build the firm; ``stages=False`` switches the first three stages off."""
    session: Session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=stages, sales_order=stages, delivery_note=stages)
    return setup


def _require(setup: _Firm, required: bool = True) -> None:
    """Switch the rule through the settings service, as the screen does."""
    row = setup.session.scalar(
        select(SalesWorkflowSettings).where(
            SalesWorkflowSettings.firm_id == setup.firm.id
        )
    )
    assert row is not None
    SalesWorkflowService(setup.session).update_settings(
        SalesWorkflowSettingsWrite(
            quotation_stage=row.quotation_stage,
            sales_order_stage=row.sales_order_stage,
            delivery_note_stage=row.delivery_note_stage,
            salesman_required=required,
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _salesman(setup: _Firm, name: str = "Mohan") -> UUID:
    """Put one active entry on the firm's list."""
    row = Salesman(firm_id=setup.firm.id, name=name)
    setup.session.add(row)
    setup.session.commit()
    return row.id


def _order(setup: _Firm, salesman_id: UUID | None = None) -> SalesOrderCreate:
    """Describe an order typed by hand."""
    return SalesOrderCreate(
        customer_id=setup.customer.id,
        salesman_id=salesman_id,
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
    )


def test_the_message_is_word_for_word() -> None:
    message = f"{REFUSAL} Choose one in the Salesman box."
    assert message == SALESMAN_REQUIRED_MESSAGE


def test_the_setting_is_off_until_chosen_and_read_back() -> None:
    setup = _setup()
    service = SalesWorkflowService(setup.session)
    assert service.settings_response(setup.firm.id).salesman_required is False
    assert service.requires_salesman(setup.firm.id) is False

    _require(setup)

    assert service.settings_response(setup.firm.id).salesman_required is True
    # Omitted on a later write is left as it is.
    service.update_settings(
        SalesWorkflowSettingsWrite(
            quotation_stage=True, sales_order_stage=True, delivery_note_stage=True
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    assert service.requires_salesman(setup.firm.id) is True


def test_off_a_bill_and_an_order_save_without_a_salesman() -> None:
    setup = _setup(stages=False)

    invoice = SalesInvoiceService(setup.session).create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
    )
    order = SalesOrderService(setup.session).create_order(
        _order(setup), firm_id=setup.firm.id, actor_id=uuid4()
    )

    assert invoice.salesman_id is None
    assert order.salesman_id is None


def test_on_an_order_naming_nobody_is_refused() -> None:
    setup = _setup()
    _require(setup)

    with pytest.raises(ValidationError, match=REFUSAL):
        SalesOrderService(setup.session).create_order(
            _order(setup), firm_id=setup.firm.id, actor_id=uuid4()
        )
    setup.session.rollback()
    named = _salesman(setup)
    order = SalesOrderService(setup.session).create_order(
        _order(setup, named), firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert order.salesman_id == named


def test_on_an_update_that_clears_the_salesman_is_refused() -> None:
    setup = _setup()
    _require(setup)
    named = _salesman(setup)
    service = SalesOrderService(setup.session)
    order = service.create_order(
        _order(setup, named), firm_id=setup.firm.id, actor_id=uuid4()
    )

    with pytest.raises(ValidationError, match=REFUSAL):
        service.update_order(
            order.id, _order(setup), firm_scope=setup.firm.id, actor_id=uuid4()
        )


def test_on_a_note_of_an_order_naming_nobody_is_refused() -> None:
    setup = _setup()
    actor = uuid4()
    orders = SalesOrderService(setup.session)
    # Raised before the firm switched the rule on: its next document is held.
    order = orders.create_order(_order(setup), firm_id=setup.firm.id, actor_id=actor)
    orders.approve_order(order.id, firm_scope=setup.firm.id, actor_id=actor)
    _require(setup)
    order_line = setup.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None

    with pytest.raises(ValidationError, match=REFUSAL):
        DeliveryNoteService(setup.session).create_note(
            DeliveryNoteCreate(
                sales_order_id=order.id,
                delivery_date=date(2026, 8, 3),
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=order_line.id,
                        line_number=1,
                        current_delivery_quantity=Decimal("4"),
                    )
                ],
            ),
            firm_id=setup.firm.id,
            actor_id=actor,
        )


def test_on_a_bill_of_a_note_naming_nobody_is_refused() -> None:
    setup = _setup()
    note = _persons_note(setup)
    DeliveryNoteService(setup.session).dispatch_note(
        note.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )
    _require(setup)

    with pytest.raises(ValidationError, match=REFUSAL):
        SalesInvoiceService(setup.session).create_invoice(
            _bill_of(setup, note), firm_id=setup.firm.id, actor_id=uuid4()
        )
    setup.session.rollback()
    # Naming one on the bill itself is enough.
    named = _salesman(setup)
    bill = _bill_of(setup, note)
    bill.salesman_id = named
    invoice = SalesInvoiceService(setup.session).create_invoice(
        bill, firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert invoice.salesman_id == named


def test_on_a_bare_bill_naming_nobody_is_refused_and_writes_nothing() -> None:
    setup = _setup(stages=False)
    _require(setup)

    with pytest.raises(ValidationError, match=REFUSAL):
        SalesInvoiceService(setup.session).create_invoice(
            setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
        )
    setup.session.rollback()
    assert setup.session.scalars(select(SalesOrder)).all() == []
    assert setup.session.scalars(select(SalesInvoice)).all() == []


def test_the_chain_keeps_the_bills_salesman_on_what_it_raises() -> None:
    setup = _setup(stages=False)
    _require(setup)
    named = _salesman(setup)
    bill = setup.bare_bill()
    bill.salesman_id = named

    invoice = SalesInvoiceService(setup.session).create_invoice(
        bill, firm_id=setup.firm.id, actor_id=uuid4()
    )

    order = setup.session.scalar(select(SalesOrder))
    note = setup.session.scalar(select(DeliveryNote))
    assert order is not None and note is not None
    assert (order.salesman_id, note.salesman_id, invoice.salesman_id) == (
        named,
        named,
        named,
    )


def test_a_quotation_is_not_held_to_it() -> None:
    setup = _setup()
    _require(setup)

    quotation = QuotationService(setup.session).create_quotation(
        QuotationCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            quotation_date=date(2026, 8, 3),
            valid_until=date(2026, 8, 31),
            lines=[
                QuotationLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    assert quotation.salesman_id is None
