"""Approval for large stock adjustments (STK-8, decision A108).

Ten widgets are carried at 100 each. A storekeeper may move 250: writing two
off (200) posts; writing five off (500) is refused and can be submitted
instead. A storekeeper cannot approve it; a manager allowed 1,000 can, which
posts it as typed. A rejection keeps its reason. Without limits nothing
changes.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.identity.models import Role, User, UserRole
from app.inventory.schemas import StockWriteOffCreate
from app.inventory.services import InventoryService
from app.inventory.services.adjustment_approval import (
    StockAdjustmentApprovalService,
    StockAdjustmentLimitItem,
    StockAdjustmentRequestWrite,
)
from app.uom.models import ConversionRule, Uom
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm holding ten widgets at 100, with two limits set."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="ADJAP")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    StockAdjustmentApprovalService(built.session).replace_limits(
        [
            StockAdjustmentLimitItem(role_code="STOREKEEPER", max_value=D("250")),
            StockAdjustmentLimitItem(role_code="STORE_HEAD", max_value=D("1000")),
        ],
        firm_id=built.firm.id,
        actor_id=built.actor_id,
    )
    return built


def _person(firm: _Firm, code: str) -> UUID:
    user = User(
        email=f"{uuid4().hex[:8]}@stock.test", full_name=code, password_hash="x"
    )
    firm.session.add(user)
    firm.session.flush()
    role = firm.session.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=code.title())
        firm.session.add(role)
        firm.session.flush()
    firm.session.add(UserRole(user_id=user.id, role_id=role.id, firm_id=firm.firm.id))
    firm.session.commit()
    return user.id


def _write_off(firm: _Firm, quantity: str) -> StockWriteOffCreate:
    return StockWriteOffCreate(
        branch_id=firm.branch.id,
        warehouse_id=firm.warehouse.id,
        product_id=firm.product.id,
        reason="DAMAGE",
        quantity=D(quantity),
        transaction_date=date(2026, 8, 12),
    )


def test_within_the_limit_posts_and_above_it_waits(firm: _Firm) -> None:
    keeper = _person(firm, "STOREKEEPER")
    head = _person(firm, "STORE_HEAD")
    inventory = InventoryService(firm.session)
    inventory.write_off_stock(
        _write_off(firm, "2"), firm_scope=firm.firm.id, actor_id=keeper
    )
    with pytest.raises(ValidationError, match="Submit it for approval"):
        inventory.write_off_stock(
            _write_off(firm, "5"), firm_scope=firm.firm.id, actor_id=keeper
        )
    firm.session.rollback()

    approvals = StockAdjustmentApprovalService(firm.session)
    request = approvals.submit(
        StockAdjustmentRequestWrite(kind="WRITE_OFF", write_off=_write_off(firm, "5")),
        firm_id=firm.firm.id,
        actor_id=keeper,
    )
    assert request.estimated_value == D("500.00")
    assert [r.id for r in approvals.list_requests(firm.firm.id)] == [request.id]
    with pytest.raises(ValidationError, match="somebody allowed more"):
        approvals.approve(request.id, firm_id=firm.firm.id, actor_id=keeper)
    firm.session.rollback()
    approved = approvals.approve(request.id, firm_id=firm.firm.id, actor_id=head)
    assert approved.status == "APPROVED"
    assert approved.transaction_id is not None
    assert firm.stock() == D("3")


def test_a_rejection_keeps_why(firm: _Firm) -> None:
    keeper = _person(firm, "STOREKEEPER")
    approvals = StockAdjustmentApprovalService(firm.session)
    request = approvals.submit(
        StockAdjustmentRequestWrite(kind="WRITE_OFF", write_off=_write_off(firm, "5")),
        firm_id=firm.firm.id,
        actor_id=keeper,
    )
    rejected = approvals.reject(
        request.id, "Count again first", firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert (rejected.status, rejected.decision_remarks) == (
        "REJECTED",
        "Count again first",
    )
    assert firm.stock() == D("10")


def test_somebody_with_no_limited_role_is_not_limited(firm: _Firm) -> None:
    unlimited = _person(firm, "OWNER_ROLE")
    InventoryService(firm.session).write_off_stock(
        _write_off(firm, "9"), firm_scope=firm.firm.id, actor_id=unlimited
    )
    assert firm.stock() == D("1")


def _pairs(firm: _Firm) -> UUID:
    """Keep the widget in pieces, two to a pair; return the pair."""
    piece = Uom(code="PIECE", name="Piece", dimension="COUNT", status="ACTIVE")
    pair = Uom(code="PAIR", name="Pair", dimension="COUNT", status="ACTIVE")
    firm.session.add_all([piece, pair])
    firm.session.flush()
    firm.product.base_uom_id = piece.id
    firm.product.inventory_uom_id = piece.id
    firm.session.add(
        ConversionRule(
            firm_id=firm.firm.id,
            product_id=firm.product.id,
            from_uom_id=pair.id,
            to_uom_id=piece.id,
            conversion_factor=D("2"),
            rounding_mode="HALF_UP",
            precision_scale=4,
            effective_from=date(2026, 4, 1),
            version_number=1,
        )
    )
    firm.session.commit()
    return pair.id


def test_the_limit_judges_the_pieces_a_pack_moves(firm: _Firm) -> None:
    # Two pairs are four widgets, worth 400: above the storekeeper's 250,
    # though the number typed is 2 (D-STK-57).
    keeper = _person(firm, "STOREKEEPER")
    pair = _pairs(firm)
    two_pairs = _write_off(firm, "2").model_copy(update={"entered_uom_id": pair})
    with pytest.raises(ValidationError, match="worth 400.00"):
        InventoryService(firm.session).write_off_stock(
            two_pairs, firm_scope=firm.firm.id, actor_id=keeper
        )
    firm.session.rollback()
    assert firm.stock() == D("10")

    request = StockAdjustmentApprovalService(firm.session).submit(
        StockAdjustmentRequestWrite(kind="WRITE_OFF", write_off=two_pairs),
        firm_id=firm.firm.id,
        actor_id=keeper,
    )
    assert (request.quantity, request.estimated_value) == (D("4"), D("400.00"))
