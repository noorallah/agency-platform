"""The sales-stage defaults are kept, checked, and followed (D-CFG-14).

`sales_workflow_settings` names the branch and warehouse a bill raised without
an order or a note ships from. Four things went wrong with them, each failing
at bill time rather than where the mistake was made:

- an omitted default was written as null, so a client that never showed them
  wiped them;
- nothing checked them: an unknown id, another firm's branch, a deleted or
  inactive one, or a warehouse outside the branch were all saved;
- deleting the branch or warehouse they named was never refused;
- a bill naming a second branch took the first branch's default warehouse,
  which the order then refused as outside its branch.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.branches.services import BranchWarehouseService
from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesWorkflowSettingsWrite
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

_OFF = {"quotation_stage": False, "sales_order_stage": False}


def _write(**values: object) -> SalesWorkflowSettingsWrite:
    """Build a settings write from exactly the keys given, as a request would."""
    return SalesWorkflowSettingsWrite.model_validate(
        {**_OFF, "delivery_note_stage": False, **values}
    )


def _save(setup: _Firm, **values: object) -> None:
    """Save the firm's settings through the service a request reaches."""
    SalesWorkflowService(setup.session).update_settings(
        _write(**values), firm_id=setup.firm.id, actor_id=uuid4()
    )


def _branch(setup: _Firm, code: str, *, status: str = "ACTIVE") -> Branch:
    """Add a second branch to the firm."""
    row = Branch(
        firm_id=setup.firm.id,
        code=code,
        name=code,
        display_name=code,
        currency_code="INR",
        working_hours={},
        status=status,
    )
    setup.session.add(row)
    setup.session.commit()
    return row


def _warehouse(setup: _Firm, branch: Branch, code: str, **extra: object) -> Warehouse:
    """Add a warehouse under a branch."""
    row = Warehouse(
        firm_id=setup.firm.id,
        branch_id=branch.id,
        code=code,
        name=code,
        display_name=code,
        status="ACTIVE",
        **extra,
    )
    setup.session.add(row)
    setup.session.commit()
    return row


def _setup() -> _Firm:
    """Build a counter-selling firm."""
    session: Session = _session_factory()()
    return _Firm(session)


def test_an_omitted_default_is_left_alone_and_a_null_clears_it() -> None:
    setup = _setup()
    _save(
        setup,
        default_branch_id=str(setup.branch.id),
        default_warehouse_id=str(setup.warehouse.id),
    )

    # The Stages dialog sends the three switches; the defaults must survive.
    _save(setup)
    stored = SalesWorkflowService(setup.session).settings_for(setup.firm.id)
    assert stored.default_branch_id == setup.branch.id
    assert stored.default_warehouse_id == setup.warehouse.id

    _save(setup, default_warehouse_id=None)
    stored = SalesWorkflowService(setup.session).settings_for(setup.firm.id)
    assert stored.default_branch_id == setup.branch.id
    assert stored.default_warehouse_id is None


def test_a_default_the_firm_cannot_ship_from_is_refused_by_name() -> None:
    setup = _setup()
    other_firm = Firm(
        name="Other",
        code="OTHER",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    setup.session.add(other_firm)
    setup.session.commit()
    foreign = Branch(
        firm_id=other_firm.id,
        code="FX",
        name="FX",
        display_name="FX",
        currency_code="INR",
        working_hours={},
        status="ACTIVE",
    )
    setup.session.add(foreign)
    setup.session.commit()
    closed = _branch(setup, "SHUT", status="INACTIVE")
    second = _branch(setup, "B2")
    elsewhere = _warehouse(setup, second, "W2")

    for branch_id, message in (
        (uuid4(), "not one of this firm's branches"),
        (foreign.id, "not one of this firm's branches"),
        (closed.id, "Branch SHUT is inactive"),
    ):
        with pytest.raises(ValidationError, match=message):
            _save(setup, default_branch_id=str(branch_id))

    with pytest.raises(ValidationError, match="Warehouse W2 is not in branch BR-001"):
        _save(
            setup,
            default_branch_id=str(setup.branch.id),
            default_warehouse_id=str(elsewhere.id),
        )
    with pytest.raises(ValidationError, match="not one of this firm's warehouses"):
        _save(setup, default_warehouse_id=str(uuid4()))
    # Nothing was written by any refusal.
    stored = SalesWorkflowService(setup.session).settings_for(setup.firm.id)
    assert stored.default_branch_id is None


def test_a_bill_from_a_second_branch_ships_from_that_branchs_warehouse() -> None:
    setup = _setup()
    second = _branch(setup, "B2")
    second_store = _warehouse(setup, second, "W2", is_default=True)
    InventoryService(setup.session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=second.id,
            warehouse_id=second_store.id,
            product_id=setup.product.id,
            quantity=Decimal("10"),
            reference_number="ADJ-W2",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 1),
        ),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    _save(
        setup,
        default_branch_id=str(setup.branch.id),
        default_warehouse_id=str(setup.warehouse.id),
    )
    bill = setup.bare_bill().model_copy(update={"branch_id": second.id})

    SalesInvoiceService(setup.session).create_invoice(
        bill, firm_id=setup.firm.id, actor_id=uuid4()
    )

    order = setup.session.scalar(select(SalesOrder))
    assert order is not None
    assert order.branch_id == second.id
    assert order.warehouse_id == second_store.id


def test_the_default_branch_and_warehouse_cannot_be_deleted() -> None:
    setup = _setup()
    spare = _branch(setup, "SPARE")
    _save(
        setup,
        default_branch_id=str(setup.branch.id),
        default_warehouse_id=str(setup.warehouse.id),
    )
    service = BranchWarehouseService(setup.session)
    # WH-001 holds the opening stock, which refuses its delete first; an
    # empty warehouse reaches the check this is about.
    empty = _warehouse(setup, setup.branch, "EMPTY")
    _save(setup, default_warehouse_id=str(empty.id))

    with pytest.raises(ValidationError, match="Warehouse EMPTY is the default"):
        service.delete_warehouse(empty.id, firm_scope=setup.firm.id, actor_id=uuid4())

    _save(setup, default_branch_id=str(spare.id), default_warehouse_id=None)
    with pytest.raises(ValidationError, match="Branch SPARE is the default"):
        service.delete_branch(spare.id, firm_scope=setup.firm.id, actor_id=uuid4())


def test_the_stages_are_audited_by_name() -> None:
    """D-SELL-24: the stages were audited as bare CREATE / UPDATE."""
    setup = _setup()
    _save(setup)
    _save(setup, delivery_note_stage=True)

    actions = setup.session.scalars(
        select(AuditLog.action).where(AuditLog.entity_type == "sales_workflow_settings")
    ).all()
    assert actions
    assert set(actions) <= {
        "sales_workflow_settings.created",
        "sales_workflow_settings.updated",
    }
    assert actions[-1] == "sales_workflow_settings.updated"
