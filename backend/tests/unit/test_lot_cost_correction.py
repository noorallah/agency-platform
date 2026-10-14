"""A bill's rate and a landed cost onto the lot (L2 step 8).

`docs/design/LOT_COST_DESIGN.md`, sections 3.3 and 3.6, decision 3. Ten
units arrive in one lot at 100. When the supplier's bill charges another
rate, the share for the units still in the lot corrects the lot and the
share for units gone stays purchase price variance; a landed cost lands on
the lot's own units, not on the item's. After every step the Inventory
account equals the sum of the lots.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.batch_serial.models import BatchRecord
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.models import GoodsReceipt
from app.inventory.models import BatchValuation, InventoryTransaction
from app.inventory.schemas.inventory import StockWriteOffCreate
from app.inventory.services import InventoryService
from app.landed_costs.services import LandedCostService, LandedCostWrite
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.services.purchase_invoice_service import (
    PurchaseInvoiceService,
)
from tests.unit.test_goods_receipt import _bill, _control_balance, _Fixture
from tests.unit.test_lot_receiving import _receive, _shop

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal
INVENTORY = ControlAccountPurpose.INVENTORY.value
VARIANCE = ControlAccountPurpose.PURCHASE_PRICE_VARIANCE.value
SOLD = ControlAccountPurpose.COST_OF_GOODS_SOLD.value


def _lots(fixture: _Fixture) -> D:
    """Return what every lot of the firm is worth."""
    total = fixture.session.scalar(
        select(func.coalesce(func.sum(BatchValuation.total_value), 0)).where(
            BatchValuation.firm_id == fixture.firm.id,
            BatchValuation.is_deleted.is_(False),
        )
    )
    return D(str(total))


def _worth(fixture: _Fixture, receipt: GoodsReceipt) -> tuple[D, D]:
    """Return what the receipt's lot holds and is worth."""
    lot = fixture.session.scalars(
        select(BatchValuation)
        .join(BatchRecord, BatchRecord.id == BatchValuation.batch_id)
        .where(BatchRecord.source_document_id == receipt.id)
    ).one()
    return D(lot.quantity_on_hand), D(lot.total_value)


def _balance(fixture: _Fixture, purpose: str) -> D:
    """Return a control account's debit-less-credit balance."""
    return _control_balance(fixture.session, fixture.firm.id, purpose)


def _books_agree(fixture: _Fixture) -> None:
    """Assert the Inventory account is the sum of the lots, to the paisa."""
    fixture.session.expire_all()
    assert _balance(fixture, INVENTORY) == _lots(fixture).quantize(D("0.01"))


def _write_off(fixture: _Fixture, quantity: str) -> None:
    """Write units off; they leave the first lot that holds them all."""
    InventoryService(fixture.session).write_off_stock(
        StockWriteOffCreate(
            branch_id=fixture.branch.id,
            warehouse_id=fixture.warehouse.id,
            product_id=fixture.product.id,
            reason="DAMAGE",
            quantity=D(quantity),
            transaction_date=date(2026, 8, 6),
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    fixture.session.expire_all()


def _cancel(fixture: _Fixture, bill: PurchaseInvoice) -> None:
    """Cancel an approved bill."""
    PurchaseInvoiceService(fixture.session).cancel_invoice(
        bill.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="Wrong rate",
    )
    fixture.session.expire_all()


def test_a_dearer_bill_corrects_the_units_still_in_the_lot() -> None:
    """Billed 110 for ten at 100 with four gone: 60 onto the lot, 40 variance."""
    fixture = _shop("LOT8A", by_lot=True, track_batch=False)
    receipt = _receive(fixture, "10")
    _write_off(fixture, "4")

    _bill(
        fixture.session,
        fixture,
        receipt,
        quantity="10",
        unit_price="110",
        supplier_number="S-1",
    )

    fixture.session.expire_all()
    assert _worth(fixture, receipt) == (D("6"), D("660"))
    assert _balance(fixture, VARIANCE) == D("40")
    _books_agree(fixture)
    [moved] = fixture.session.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.transaction_type == "COST_CORRECTION"
        )
    ).all()
    assert moved.quantity == 0
    assert moved.transaction_date == date(2026, 8, 6)


def test_a_cheaper_bill_lowers_the_lot() -> None:
    """Billed 90 for ten at 100, none gone: the lot is worth 900, no variance."""
    fixture = _shop("LOT8B", by_lot=True, track_batch=False)
    receipt = _receive(fixture, "10")

    _bill(
        fixture.session,
        fixture,
        receipt,
        quantity="10",
        unit_price="90",
        supplier_number="S-1",
    )

    fixture.session.expire_all()
    assert _worth(fixture, receipt) == (D("10"), D("900"))
    assert _balance(fixture, VARIANCE) == D("0")
    _books_agree(fixture)


def test_cancelling_the_bill_takes_back_what_the_lot_still_holds() -> None:
    """Cancelled at once, the lot and the books are as they were."""
    fixture = _shop("LOT8C", by_lot=True, track_batch=False)
    receipt = _receive(fixture, "10")
    _write_off(fixture, "4")
    bill = _bill(
        fixture.session,
        fixture,
        receipt,
        quantity="10",
        unit_price="110",
        supplier_number="S-1",
    )

    _cancel(fixture, bill)

    assert _worth(fixture, receipt) == (D("6"), D("600"))
    assert _balance(fixture, VARIANCE) == D("0")
    _books_agree(fixture)


def test_units_gone_after_the_bill_keep_their_share_on_cancel() -> None:
    """Three more leave at 110; cancelling takes 30 off the lot, 30 to variance."""
    fixture = _shop("LOT8D", by_lot=True, track_batch=False)
    receipt = _receive(fixture, "10")
    _write_off(fixture, "4")
    bill = _bill(
        fixture.session,
        fixture,
        receipt,
        quantity="10",
        unit_price="110",
        supplier_number="S-1",
    )
    _write_off(fixture, "3")
    assert _worth(fixture, receipt) == (D("3"), D("330"))

    _cancel(fixture, bill)

    assert _worth(fixture, receipt) == (D("3"), D("300"))
    assert _balance(fixture, VARIANCE) == D("-30")
    _books_agree(fixture)


def test_a_firm_on_average_puts_the_whole_difference_to_variance() -> None:
    """Nothing about Average moves: no correction, all of it variance."""
    fixture = _shop("LOT8E", by_lot=False, track_batch=False)
    receipt = _receive(fixture, "10")

    _bill(
        fixture.session,
        fixture,
        receipt,
        quantity="10",
        unit_price="110",
        supplier_number="S-1",
    )

    fixture.session.expire_all()
    assert _balance(fixture, VARIANCE) == D("100")
    assert _balance(fixture, INVENTORY) == D("1000")
    assert (
        fixture.session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "COST_CORRECTION"
            )
        ).all()
        == []
    )


def _landed(fixture: _Fixture, receipt: GoodsReceipt, amount: str) -> LandedCostWrite:
    """Build a freight voucher on one receipt."""
    return LandedCostWrite.model_validate(
        {
            "voucher_date": date(2026, 8, 20),
            "basis": "VALUE",
            "goods_receipt_ids": [receipt.id],
            "charges": [
                {
                    "description": "Freight",
                    "amount": amount,
                    "vendor_id": fixture.vendor.id,
                }
            ],
        }
    )


def test_a_landed_cost_lands_on_its_own_lot_not_the_item() -> None:
    """The first lot is gone, so its freight is all cost of goods sold.

    On the item's figure the five still held of the second lot would have
    carried it; by lot they are not the units the freight came with.
    """
    fixture = _shop("LOT8F", by_lot=True, track_batch=False)
    first = _receive(fixture, "5")
    second = _receive(fixture, "5")
    _write_off(fixture, "5")
    assert _worth(fixture, first) == (D("0"), D("0"))
    service = LandedCostService(fixture.session)

    voucher = service.post(
        _landed(fixture, first, "100"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    assert (voucher.inventory_amount, voucher.cogs_amount) == (D("0"), D("100"))
    assert _worth(fixture, second) == (D("5"), D("500"))
    _books_agree(fixture)

    onto_second = service.post(
        _landed(fixture, second, "100"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert (onto_second.inventory_amount, onto_second.cogs_amount) == (
        D("100"),
        D("0"),
    )
    assert _worth(fixture, second) == (D("5"), D("600"))
    _books_agree(fixture)


def test_cancelling_a_landed_cost_takes_back_only_what_the_lot_holds() -> None:
    """Two of five gone at 120: 60 comes off the lot, 40 stays cost of sales."""
    fixture = _shop("LOT8G", by_lot=True, track_batch=False)
    receipt = _receive(fixture, "5")
    service = LandedCostService(fixture.session)
    voucher = service.post(
        _landed(fixture, receipt, "100"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    _write_off(fixture, "2")
    assert _worth(fixture, receipt) == (D("3"), D("360"))
    sold_before = _balance(fixture, SOLD)

    service.cancel(
        voucher.id, "Wrong bill", firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )

    fixture.session.expire_all()
    assert _worth(fixture, receipt) == (D("3"), D("300"))
    assert _balance(fixture, SOLD) - sold_before == D("-40")
    _books_agree(fixture)
