"""Repacking and bulk breaking (STK-4, decision A114).

Ten bags are held at 100. One bag is broken into 20 small packs and 5 large
ones with 5% wastage: the bag leaves at 100, 5 is written off, and the 95
left is split by what the packs are worth at their purchase price -- 10x5
against 5x10, so 47.50 each. Cancelling puts everything back.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.models import InventoryRecord
from app.inventory.services.repacking import RepackService, RepackWrite
from app.products.models import Product
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm holding ten bags at 100."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="REPAK")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    return built


def _pack(firm: _Firm, code: str, price: str) -> Product:
    row = Product(
        firm_id=firm.firm.id,
        code=code,
        name=code.title(),
        product_type="STOCK_ITEM",
        status="ACTIVE",
        purchase_price=D(price),
    )
    firm.session.add(row)
    firm.session.commit()
    return row


def _held(firm: _Firm, product: Product) -> Decimal:
    total = firm.session.scalar(
        select(InventoryRecord.current_quantity).where(
            InventoryRecord.product_id == product.id
        )
    )
    return D(str(total or 0))


def test_a_bag_breaks_into_packs_carrying_its_cost(firm: _Firm) -> None:
    small = _pack(firm, "PACK-S", "5")
    large = _pack(firm, "PACK-L", "10")
    service = RepackService(firm.session)
    repack = service.post(
        RepackWrite(
            repack_date=date(2026, 8, 12),
            branch_id=firm.branch.id,
            warehouse_id=firm.warehouse.id,
            wastage_percent=D("5"),
            lines=[
                {"kind": "CONSUME", "product_id": firm.product.id, "quantity": "1"},
                {"kind": "PRODUCE", "product_id": small.id, "quantity": "10"},
                {"kind": "PRODUCE", "product_id": large.id, "quantity": "5"},
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert (repack.consumed_value, repack.wastage_value) == (D("100"), D("5"))
    (response,) = service.responses([repack])
    assert [line.value for line in response.lines if line.kind == "PRODUCE"] == [
        D("47.5000"),
        D("47.5000"),
    ]
    assert (_held(firm, firm.product), _held(firm, small), _held(firm, large)) == (
        D("9"),
        D("10"),
        D("5"),
    )
    assert firm.balance(ControlAccountPurpose.INVENTORY_ADJUSTMENT) == D("5")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("995")

    service.cancel(repack.id, "Wrong bag", firm_id=firm.firm.id, actor_id=firm.actor_id)
    assert (_held(firm, firm.product), _held(firm, small), _held(firm, large)) == (
        D("10"),
        D("0"),
        D("0"),
    )
    assert firm.balance(ControlAccountPurpose.INVENTORY_ADJUSTMENT) == D("0")


def test_a_repack_needs_both_sides() -> None:
    with pytest.raises(SchemaError, match="consumes at least one"):
        RepackWrite.model_validate(
            {
                "repack_date": "2026-08-12",
                "branch_id": "00000000-0000-0000-0000-000000000001",
                "warehouse_id": "00000000-0000-0000-0000-000000000002",
                "lines": [
                    {
                        "kind": "CONSUME",
                        "product_id": "00000000-0000-0000-0000-000000000003",
                        "quantity": "1",
                    },
                    {
                        "kind": "CONSUME",
                        "product_id": "00000000-0000-0000-0000-000000000004",
                        "quantity": "1",
                    },
                ],
            }
        )
