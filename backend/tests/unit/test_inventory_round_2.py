"""Inventory round 2: the small refusals that read in the wrong words.

D-STK-44: a second write-off under a reference already used was refused by
the ledger, about a journal entry. D-STK-49: a batch saved a selling price
above its own MRP while PTR and PTS were held under it.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.schemas.batch_serial import BatchCreate, BatchUpdate
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.inventory.schemas import StockWriteOffCreate
from app.inventory.services import InventoryService
from tests.unit.test_inventory_round_1_b import _Register
from tests.unit.test_purchase_chain_synthesis import _Firm


def _stocked() -> _Firm:
    """Build a firm with books and ten of its product on the shelf."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="INVR2")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    return built


def _write_off(firm: _Firm, reference: str | None) -> StockWriteOffCreate:
    """Return a write-off of one unit under ``reference``."""
    return StockWriteOffCreate(
        branch_id=firm.branch.id,
        warehouse_id=firm.warehouse.id,
        product_id=firm.product.id,
        reason="DAMAGE",
        quantity=Decimal("1"),
        transaction_date=date(2026, 8, 12),
        reference_number=reference,
    )


def test_a_second_write_off_under_one_reference_is_refused_in_stock_words() -> None:
    """The ledger said it first, about a journal entry nobody typed."""
    firm = _stocked()
    inventory = InventoryService(firm.session)
    inventory.write_off_stock(
        _write_off(firm, "WO-TWICE"), firm_scope=firm.firm.id, actor_id=firm.actor_id
    )

    with pytest.raises(ConflictError, match="A write-off with the reference WO-TWICE"):
        inventory.write_off_stock(
            _write_off(firm, "WO-TWICE"),
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_write_offs_with_no_reference_typed_are_each_numbered() -> None:
    """The guard is on a typed reference; the series never repeats itself."""
    firm = _stocked()
    inventory = InventoryService(firm.session)

    first = inventory.write_off_stock(
        _write_off(firm, None), firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    second = inventory.write_off_stock(
        _write_off(firm, None), firm_scope=firm.firm.id, actor_id=firm.actor_id
    )

    assert first.reference_number != second.reference_number


def test_a_batch_cannot_sell_above_its_own_mrp() -> None:
    """Ninety against an MRP of fifty is a typing mistake, on create and edit."""
    books = _Register("R2MRP")

    with pytest.raises(ValidationError, match="Selling price 90.00 cannot exceed"):
        books.service.create_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            data=BatchCreate(
                product_id=books.product.id,
                batch_number="MRP-1",
                expiry_date=date(2031, 12, 31),
                mrp=Decimal("50"),
                selling_price=Decimal("90"),
            ),
        )

    batch = books.service.create_batch(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        data=BatchCreate(
            product_id=books.product.id,
            batch_number="MRP-2",
            expiry_date=date(2031, 12, 31),
            mrp=Decimal("50"),
            selling_price=Decimal("50"),
        ),
    )
    with pytest.raises(ValidationError, match="Selling price 50.00 cannot exceed"):
        books.service.update_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            batch_id=batch.id,
            data=BatchUpdate(mrp=Decimal("40")),
        )
