"""Inventory round 4: the rules the owner agreed for the open batch rows.

D-STK-43: a batch number typed for a product that keeps no batches made a
batch. D-STK-48: a product that tracks expiry took a batch with no date.
D-STK-50: Add Serial numbered a unit without looking at the stock held.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.batch_serial.models.batch_serial import BatchRecord
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchUpdate,
    SerialCreate,
    SerialUpdate,
)
from app.batch_serial.services import BatchSerialService
from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import InventoryRecord
from tests.unit import test_batch_serial_expiry as registers
from tests.unit.test_goods_receipt import _Fixture, _session_factory
from tests.unit.test_inventory_round_1_b import _Register

pytestmark = pytest.mark.typed_document_numbers


def _receive(fixture: _Fixture, **line: object) -> object:
    """Create a receipt of two of the order line with these line fields."""
    data = fixture.receipt_payload("2").model_dump()
    data["lines"][0].update(line)
    return GoodsReceiptService(fixture.session).create_receipt(
        GoodsReceiptCreate.model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _complete(fixture: _Fixture, receipt: object) -> None:
    """Complete a receipt, which is what stocks it and makes its batch."""
    GoodsReceiptService(fixture.session).complete_receipt(
        receipt.id,  # type: ignore[attr-defined]
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _batches(fixture: _Fixture) -> list[BatchRecord]:
    """Return every batch the firm has registered."""
    return list(
        fixture.session.scalars(
            select(BatchRecord).where(BatchRecord.firm_id == fixture.firm.id)
        )
    )


# ── D-STK-43: a batch typed for a product that keeps none ───────────────────


def test_a_batch_typed_for_an_untracked_product_is_ignored() -> None:
    """The receipt goes through, onto the product's own row, with no batch."""
    fixture = _Fixture(_session_factory()(), "R4UNT")
    receipt = _receive(fixture, batch_number="TYPED-1")

    _complete(fixture, receipt)

    assert _batches(fixture) == []
    line = fixture.session.scalar(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.goods_receipt_id == receipt.id  # type: ignore[attr-defined]
        )
    )
    assert line is not None
    assert (line.batch_number, line.batch_id) == ("TYPED-1", None)
    rows = list(
        fixture.session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.product_id == fixture.product.id
            )
        )
    )
    assert [(row.batch_id, row.current_quantity) for row in rows] == [
        (None, Decimal("2"))
    ]


def test_a_batch_typed_for_a_tracked_product_is_still_registered() -> None:
    """The switch decides: the same line on a batch-tracked product."""
    fixture = _Fixture(_session_factory()(), "R4TRK")
    fixture.product.track_batch = True
    fixture.session.commit()

    _complete(fixture, _receive(fixture, batch_number="TYPED-2"))

    assert [row.batch_number for row in _batches(fixture)] == ["TYPED-2"]


# ── D-STK-48: an expiry date where the product tracks expiry ────────────────


def _dated_product(fixture: _Fixture) -> None:
    """Make the fixture's product one that tracks batch, expiry and make date."""
    for switch in ("track_batch", "track_expiry", "track_manufacturing_date"):
        setattr(fixture.product, switch, True)
    fixture.session.commit()


def test_a_receipt_refuses_a_batch_with_no_expiry_where_expiry_is_tracked() -> None:
    """Refused when it would be stocked, and nothing is stocked."""
    fixture = _Fixture(_session_factory()(), "R4EXP")
    _dated_product(fixture)
    receipt = _receive(fixture, batch_number="NO-DATE")

    with pytest.raises(ValidationError, match="batch NO-DATE needs an expiry date"):
        _complete(fixture, receipt)
    fixture.session.rollback()

    assert _batches(fixture) == []
    assert (
        fixture.session.scalar(
            select(InventoryRecord).where(
                InventoryRecord.product_id == fixture.product.id
            )
        )
        is None
    )


def test_a_receipt_with_a_shelf_life_needs_only_the_manufacturing_date() -> None:
    """The shelf life fills the expiry, so the batch is dated and taken."""
    fixture = _Fixture(_session_factory()(), "R4SHL")
    _dated_product(fixture)
    fixture.product.shelf_life_days = 30
    fixture.session.commit()

    _complete(
        fixture,
        _receive(fixture, batch_number="MADE", manufacturing_date=date(2026, 8, 1)),
    )

    assert [row.expiry_date for row in _batches(fixture)] == [date(2026, 8, 31)]


def test_a_later_delivery_dates_a_batch_registered_without_one() -> None:
    """An old undated batch takes the date typed, and is refused with none."""
    fixture = _Fixture(_session_factory()(), "R4OLD")
    _dated_product(fixture)
    old = BatchRecord(
        firm_id=fixture.firm.id,
        product_id=fixture.product.id,
        batch_number="OLD-1",
        status="AVAILABLE",
        created_by=fixture.actor_id,
        updated_by=fixture.actor_id,
    )
    fixture.session.add(old)
    fixture.session.commit()

    with pytest.raises(ValidationError, match="batch OLD-1 needs an expiry date"):
        _complete(fixture, _receive(fixture, batch_number="OLD-1"))
    fixture.session.rollback()

    _complete(
        fixture, _receive(fixture, batch_number="OLD-1", expiry_date=date(2027, 5, 1))
    )
    fixture.session.refresh(old)
    assert old.expiry_date == date(2027, 5, 1)


def test_the_batch_master_asks_for_the_expiry_of_a_dated_product() -> None:
    """On the way in, by shelf life where only the make date is typed, on edit."""
    books = _Register("R4BM")

    def create(number: str, **fields: object) -> BatchRecord:
        return books.service.create_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            data=BatchCreate.model_validate(
                {"product_id": books.product.id, "batch_number": number} | fields
            ),
        )

    with pytest.raises(ValidationError, match="batch BM-1 needs an expiry date"):
        create("BM-1")
    filled = create("BM-2", manufacturing_date="2026-08-01", shelf_life_days=10)
    assert filled.expiry_date == date(2026, 8, 11)

    with pytest.raises(ValidationError, match="batch BM-2 needs an expiry date"):
        books.service.update_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            batch_id=filled.id,
            data=BatchUpdate(expiry_date=None),
        )
    # A save that does not touch the date is not asked for it.
    filled.expiry_date = None
    books.session.commit()
    held = books.service.update_batch(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        batch_id=filled.id,
        data=BatchUpdate(remarks="held for a recall"),
    )
    assert held.remarks == "held for a recall"


def test_a_product_that_tracks_no_expiry_keeps_its_undated_batch() -> None:
    """The rule is the product's switch, not every batch's."""
    books = _Register("R4PNT")
    books.product.track_expiry = False
    books.session.commit()

    batch = books.service.create_batch(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        data=BatchCreate(product_id=books.product.id, batch_number="PAINT-1"),
    )

    assert batch.expiry_date is None


# ── D-STK-50: Add Serial stops at the stock held ────────────────────────────


def _two_on_the_shelf(code: str) -> _Register:
    """Build a register whose own warehouse holds two of the product."""
    books = _Register(code)
    registers._stock(books.session, books.warehouse, books.batch("SHELF"), "2")
    return books


def test_add_serial_is_refused_past_the_quantity_the_warehouse_holds() -> None:
    """Two held, two numbered, and the third is refused in words."""
    books = _two_on_the_shelf("R4SN")
    here = {"warehouse_id": books.warehouse.id}
    books.serial("U-1", **here)
    books.serial("U-2", **here)

    with pytest.raises(
        ValidationError, match="This warehouse holds 2 of .* and 2 are already"
    ):
        books.serial("U-3", **here)


def test_a_unit_that_has_left_is_not_counted_against_the_shelf() -> None:
    """A sold unit is a record of the past; it may not come back unseen."""
    books = _two_on_the_shelf("R4SO")
    here = {"warehouse_id": books.warehouse.id}
    books.serial("U-1", **here)
    gone = books.serial("U-OLD", status="SOLD", **here)
    books.serial("U-2", **here)

    with pytest.raises(ValidationError, match="another serial number cannot be added"):
        books.service.update_serial(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            serial_id=gone.id,
            data=SerialUpdate.model_validate({"status": "AVAILABLE"}),
        )
    # An edit that leaves the unit where it stands is not judged.
    kept = books.service.update_serial(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        serial_id=gone.id,
        data=SerialUpdate(remarks="invoice 14"),
    )
    assert kept.remarks == "invoice 14"


def test_a_unit_naming_no_warehouse_is_judged_against_the_firm() -> None:
    """Everything the firm holds of the product, then refused."""
    session = registers._session_factory()()
    firm = registers._firm(session, "R4FW")
    product = registers._product(session, firm.id)
    registers._held(session, product, "1")
    service = BatchSerialService(session)

    def add(number: str) -> None:
        service.create_serial(
            firm_scope=firm.id,
            actor_id=uuid4(),
            data=SerialCreate(product_id=product.id, serial_number=number),
        )

    add("ONLY-1")
    with pytest.raises(ValidationError, match="The firm holds 1 of"):
        add("ONLY-2")
