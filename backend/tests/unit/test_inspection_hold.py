"""Received goods wait for an inspection (BUY-9, decision A100).

Ten widgets marked for inspection arrive. They are owned and valued but sit
in quarantine, not stock, until somebody inspects them. Seven passed and
three written off leaves seven in stock and nothing held; four rejected for
return stay in quarantine for the purchase return. A decided inspection
cannot be undone by cancelling the receipt.
"""

# ruff: noqa: D103

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.services import GoodsReceiptService
from app.goods_receipt.services.inspection_service import GoodsInspectionService
from app.inventory.models import InventoryRecord
from app.products.models import ProductCategory
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
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="INSPC")
    built.stages(order=True, receipt=False)
    return built


def _receive_ten(firm: _Firm) -> None:
    order = _order(firm, lines=[(firm.product, "10", "100")])
    (line,) = _order_lines(firm, order)
    bills = firm.bills()
    bill = bills.create_invoice(
        _bill_of_order(firm, order, line, "10"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)


def _held(firm: _Firm) -> tuple[Decimal, Decimal]:
    row = firm.session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == firm.firm.id,
            InventoryRecord.product_id == firm.product.id,
        )
    )
    assert row is not None
    return row.current_quantity, row.quarantine_quantity


def test_goods_wait_then_pass_and_write_off(firm: _Firm) -> None:
    firm.product.inspection_required = True
    firm.session.commit()
    _receive_ten(firm)
    assert _held(firm) == (D("0"), D("10"))

    service = GoodsInspectionService(firm.session)
    (waiting,) = service.list_inspections(firm_id=firm.firm.id)
    assert waiting.quantity == D("10") and waiting.status == "PENDING"

    with pytest.raises(ValidationError, match="must come to that"):
        service.inspect(
            waiting.goods_receipt_id,
            waiting.line_id,
            passed_quantity=D("7"),
            rejected_quantity=D("2"),
            rejected_action="WRITE_OFF",
            remarks=None,
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    with pytest.raises(ValidationError, match="rejected goods"):
        service.inspect(
            waiting.goods_receipt_id,
            waiting.line_id,
            passed_quantity=D("7"),
            rejected_quantity=D("3"),
            rejected_action=None,
            remarks=None,
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    done = service.inspect(
        waiting.goods_receipt_id,
        waiting.line_id,
        passed_quantity=D("7"),
        rejected_quantity=D("3"),
        rejected_action="WRITE_OFF",
        remarks="Seals broken",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert done.status == "DONE"
    assert _held(firm) == (D("7"), D("0"))
    assert service.list_inspections(firm_id=firm.firm.id) == []
    assert len(service.list_inspections(firm_id=firm.firm.id, status="DONE")) == 1

    # Decided goods are history: the receipt is undone with a return.
    receipt = firm.session.scalar(select(GoodsReceipt))
    assert receipt is not None
    with pytest.raises(ValidationError, match="already inspected"):
        GoodsReceiptService(firm.session)._undo_inspection_holds(
            receipt, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason=None
        )


def test_a_category_flag_holds_and_rejects_for_return(firm: _Firm) -> None:
    category = ProductCategory(
        firm_id=firm.firm.id,
        code="FOOD",
        name="Food",
        level=0,
        path="FOOD",
        inspection_required=True,
    )
    firm.session.add(category)
    firm.session.flush()
    firm.product.category_id = category.id
    firm.session.commit()
    _receive_ten(firm)
    service = GoodsInspectionService(firm.session)
    (waiting,) = service.list_inspections(firm_id=firm.firm.id)
    service.inspect(
        waiting.goods_receipt_id,
        waiting.line_id,
        passed_quantity=D("6"),
        rejected_quantity=D("4"),
        rejected_action="RETURN",
        remarks=None,
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    # The rejected four stay held until a purchase return sends them back.
    assert _held(firm) == (D("6"), D("4"))


def test_goods_not_marked_go_straight_to_stock(firm: _Firm) -> None:
    _receive_ten(firm)
    assert _held(firm) == (D("10"), D("0"))
    assert (
        GoodsInspectionService(firm.session).list_inspections(firm_id=firm.firm.id)
        == []
    )
