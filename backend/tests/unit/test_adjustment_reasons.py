"""Adjustment reasons as the firm's own master (STK-7, decision A104).

Reading the list seeds the six system reasons. A firm adds BREAKAGE booked
to its staff welfare account: writing two units off as breakage costs that
account, not inventory adjustment; an adjustment naming it does the same. A
reason the firm does not keep, or has switched off, is refused; a system
reason keeps its code and cannot be deleted.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import FirmControlAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.schemas import InventoryAdjustmentCreate, StockWriteOffCreate
from app.inventory.services import InventoryService
from app.inventory.services.adjustment_reasons import (
    AdjustmentReasonService,
    AdjustmentReasonWrite,
)
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm holding ten widgets at 100."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="REASN")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    return built


def _welfare_account(firm: _Firm) -> object:
    account = firm.session.scalar(
        select(FirmControlAccount.ledger_account_id).where(
            FirmControlAccount.firm_id == firm.firm.id,
            FirmControlAccount.purpose == ControlAccountPurpose.STAFF_WELFARE.value,
        )
    )
    assert account is not None
    return account


def _write_off(firm: _Firm, reason: str, quantity: str = "2") -> None:
    InventoryService(firm.session).write_off_stock(
        StockWriteOffCreate(
            branch_id=firm.branch.id,
            warehouse_id=firm.warehouse.id,
            product_id=firm.product.id,
            reason=reason,
            quantity=D(quantity),
            transaction_date=date(2026, 8, 12),
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_system_reasons_are_seeded_and_kept(firm: _Firm) -> None:
    service = AdjustmentReasonService(firm.session)
    reasons = service.list_reasons(firm.firm.id)
    assert [r.code for r in reasons] == [
        "DAMAGE",
        "EXPIRY",
        "LOSS",
        "INTERNAL_USE",
        "STAFF",
        "DISPLAY",
    ]
    damage = reasons[0]
    with pytest.raises(ValidationError, match="cannot be deleted"):
        service.delete(damage.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    with pytest.raises(ValidationError, match="its code stays"):
        service.update(
            damage.id,
            AdjustmentReasonWrite(code="BROKEN", name="Broken"),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    # The system reasons still post where they always did.
    _write_off(firm, "damage")
    assert firm.balance(ControlAccountPurpose.INVENTORY_ADJUSTMENT) == D("200")


def test_a_reason_of_the_firms_own_costs_its_account(firm: _Firm) -> None:
    service = AdjustmentReasonService(firm.session)
    breakage = service.create(
        AdjustmentReasonWrite(
            code="breakage", name="Breakage", ledger_account_id=_welfare_account(firm)
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert breakage.code == "BREAKAGE"
    _write_off(firm, "BREAKAGE")
    assert firm.balance(ControlAccountPurpose.STAFF_WELFARE) == D("200")
    assert firm.balance(ControlAccountPurpose.INVENTORY_ADJUSTMENT) == 0

    InventoryService(firm.session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=firm.branch.id,
            warehouse_id=firm.warehouse.id,
            product_id=firm.product.id,
            quantity=D("-1"),
            reason_code="breakage",
            transaction_date=date(2026, 8, 12),
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert firm.balance(ControlAccountPurpose.STAFF_WELFARE) == D("300")

    service.update(
        breakage.id,
        AdjustmentReasonWrite(code="BREAKAGE", name="Breakage", is_active=False),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    with pytest.raises(ValidationError, match="not an active"):
        _write_off(firm, "BREAKAGE")
    firm.session.rollback()
    with pytest.raises(ValidationError, match="not an active"):
        _write_off(firm, "THEFT")
