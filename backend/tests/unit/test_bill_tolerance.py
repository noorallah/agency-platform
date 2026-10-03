"""A supplier bill past tolerance over its order waits (BUY-10, decision A99).

Ten ordered at 100. The firm allows a bill's rate 2% over the order and the
whole bill 50 over. A bill at 101 passes. A bill at 110 -- 10% over, 100 more
on the bill -- is refused naming the line and the total, unless the approver
may approve over tolerance. With no tolerance set nothing is checked.
"""

# ruff: noqa: D103

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import AuthorizationError
from app.purchase.schemas import PurchaseWorkflowSettingsWrite
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.purchase_invoice.models import PurchaseInvoice
from tests.unit.test_purchase_chain_synthesis import _Firm
from tests.unit.test_purchase_header_discount import (
    _bill_of_order,
    _order,
    _order_lines,
)

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store that types no receipts."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="TOLER")
    built.stages(order=True, receipt=False)
    return built


def _tolerance(firm: _Firm) -> None:
    PurchaseWorkflowService(firm.session).update_settings(
        PurchaseWorkflowSettingsWrite(
            purchase_order_stage=True,
            goods_receipt_stage=False,
            bill_price_tolerance_percent=D("2"),
            bill_tolerance_amount=D("50"),
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _bill_at(firm: _Firm, price: str) -> PurchaseInvoice:
    order = _order(firm, lines=[(firm.product, "10", "100")])
    (line,) = _order_lines(firm, order)
    payload = _bill_of_order(firm, order, line, "10")
    payload.lines[0].unit_price = D(price)
    return firm.bills().create_invoice(
        payload, firm_id=firm.firm.id, actor_id=firm.actor_id
    )


def test_a_bill_inside_tolerance_is_approved(firm: _Firm) -> None:
    _tolerance(firm)
    bill = _bill_at(firm, "101")
    approved = firm.bills().approve_invoice(
        bill.id,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        may_exceed_tolerance=False,
    )
    assert approved.status == "APPROVED"


def test_a_bill_past_tolerance_waits_for_the_override(firm: _Firm) -> None:
    _tolerance(firm)
    bill = _bill_at(firm, "110")
    bills = firm.bills()
    breaches = bills.tolerance_breaches(bill, firm_id=firm.firm.id)
    assert len(breaches) == 2, breaches
    assert "line 1" in breaches[0] and "10.0% over" in breaches[0]
    with pytest.raises(AuthorizationError, match="PURCHASE_APPROVE_OVER_TOLERANCE"):
        bills.approve_invoice(
            bill.id,
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
            may_exceed_tolerance=False,
        )
    firm.session.rollback()
    approved = bills.approve_invoice(
        bill.id,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        may_exceed_tolerance=True,
    )
    assert approved.status == "APPROVED"


def test_with_no_tolerance_nothing_is_checked(firm: _Firm) -> None:
    bill = _bill_at(firm, "150")
    assert firm.bills().tolerance_breaches(bill, firm_id=firm.firm.id) == []
