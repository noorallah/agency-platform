"""Landed cost vouchers (BUY-16, decision A129).

Ten units arrive at 100 on one receipt; four are written off, so six are on
hand. A freight bill of 200 is spread over the receipt: the six still held
carry 120 -- the average rises from 100 to 120 -- and the four gone carry 80
to cost of goods sold. The journal is Dr inventory 120, Dr cost of goods sold
80, Cr expenses included in valuation 200. Cancelling puts both books back.
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
from app.finance.models import JournalEntry
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.models import GoodsReceipt
from app.inventory.schemas.inventory import StockWriteOffCreate
from app.inventory.services.inventory_service import InventoryService
from app.landed_costs.services import LandedCostService, LandedCostWrite
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
ON = date(2026, 8, 20)


@pytest.fixture
def firm() -> _Firm:
    """Receive ten at 100, then write four off."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="LCV")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    InventoryService(built.session).write_off_stock(
        StockWriteOffCreate(
            branch_id=built.branch.id,
            warehouse_id=built.warehouse.id,
            product_id=built.product.id,
            reason="DAMAGE",
            quantity=D("4"),
            transaction_date=date(2026, 8, 15),
        ),
        firm_scope=built.firm.id,
        actor_id=built.actor_id,
    )
    return built


def _receipt(firm: _Firm) -> GoodsReceipt:
    row = firm.session.scalar(
        select(GoodsReceipt).where(GoodsReceipt.firm_id == firm.firm.id)
    )
    assert row is not None
    return row


def _write(firm: _Firm, basis: str = "VALUE") -> LandedCostWrite:
    return LandedCostWrite.model_validate(
        {
            "voucher_date": ON,
            "basis": basis,
            "goods_receipt_ids": [_receipt(firm).id],
            "charges": [
                {
                    "description": "Freight to the godown",
                    "amount": "200",
                    "vendor_id": firm.vendor.id,
                    "bill_reference": "TR-881",
                }
            ],
        }
    )


def _average(firm: _Firm) -> Decimal:
    return D(
        str(
            InventoryService(firm.session)
            .valuation_for(firm_scope=firm.firm.id, product_id=firm.product.id)
            .average_cost
        )
    ).quantize(D("0.01"))


def test_the_held_share_revalues_stock_and_the_sold_share_goes_to_cost(
    firm: _Firm,
) -> None:
    assert _average(firm) == D("100.00")
    inventory_before = firm.balance(ControlAccountPurpose.INVENTORY)
    service = LandedCostService(firm.session)
    voucher = service.post(_write(firm), firm_id=firm.firm.id, actor_id=firm.actor_id)

    assert (voucher.inventory_amount, voucher.cogs_amount) == (D("120"), D("80"))
    assert _average(firm) == D("120.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) - inventory_before == D("120")
    assert firm.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD) == D("80")
    assert firm.balance(ControlAccountPurpose.LANDED_COST_CLEARING) == D("-200")
    # Referenced by the voucher's own number, once: not LCV-LCV-... (D-BUY-47).
    posted = firm.session.get(JournalEntry, voucher.journal_entry_id)
    assert posted is not None
    assert voucher.voucher_number.startswith("LCV-")
    assert posted.reference_number == voucher.voucher_number
    (view,) = service.responses([voucher])
    assert view.charges[0].bill_reference == "TR-881"
    assert view.allocations[0].amount == D("200.00")

    service.cancel(
        voucher.id, "Wrong bill", firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert _average(firm) == D("100.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == inventory_before
    assert firm.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD) == D("0")
    assert firm.balance(ControlAccountPurpose.LANDED_COST_CLEARING) == D("0")
    mirror = firm.session.scalars(
        select(JournalEntry).where(JournalEntry.reversal_of_id == posted.id)
    ).one()
    assert mirror.reference_number == f"{voucher.voucher_number}-REV"


def test_a_basis_nothing_measures_is_refused(firm: _Firm) -> None:
    with pytest.raises(ValidationError, match="has a weight to spread"):
        LandedCostService(firm.session).post(
            _write(firm, basis="WEIGHT"), firm_id=firm.firm.id, actor_id=firm.actor_id
        )


def test_quantity_basis_spreads_the_same_on_one_line(firm: _Firm) -> None:
    voucher = LandedCostService(firm.session).post(
        _write(firm, basis="QUANTITY"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert voucher.total_amount == D("200")
    assert voucher.inventory_amount + voucher.cogs_amount == D("200")
