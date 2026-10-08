"""A repack draws a batch-tracked product from its batches (D-STK-51, D-STK-52).

Soap is held in two batches. A gift pack is two soaps and a towel. Assembling
three packs takes six soaps, and before this they were looked for on the stock
row with no batch: the kit was refused with "free 0" while eight soaps stood
on the shelf. They now leave earliest expiry first, one repack line per
batch, so cancelling puts each back where it came from. A product tracked by
serial number is refused, because a repack names no units.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.core.exceptions import ValidationError
from app.inventory.models import InventoryRecord
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.inventory.services.repacking import RepackService, RepackWrite
from app.products.services.kits import KitComponentsWrite, KitService
from tests.unit.test_delivery_note_module import _session_factory
from tests.unit.test_kits import ON, _Shop

D = Decimal


class _BatchShop(_Shop):
    """The gift-pack shop with its soap held in two batches and no other."""

    def __init__(self) -> None:
        """Move the soap into an early batch of three and a late one of five."""
        super().__init__(_session_factory()())
        self.soap.track_batch = True
        self._adjust(None, "-20")
        self.early = self._batch("EARLY", date(2026, 12, 31), "3")
        self.late = self._batch("LATE", date(2027, 6, 30), "5")

    def _adjust(self, batch_id: object, quantity: str) -> None:
        InventoryService(self.session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                product_id=self.soap.id,
                batch_id=batch_id,
                quantity=D(quantity),
                reference_number=f"ADJ-SOAP-{batch_id or 'NONE'}"[:40],
                reference_type="ADJUSTMENT",
                transaction_date=ON,
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor,
        )

    def _batch(self, number: str, expiry: date, quantity: str) -> BatchRecord:
        row = BatchRecord(
            firm_id=self.firm.id,
            product_id=self.soap.id,
            warehouse_id=self.warehouse.id,
            branch_id=self.branch.id,
            batch_number=number,
            expiry_date=expiry,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.session.add(row)
        self.session.commit()
        self._adjust(row.id, quantity)
        return row

    def by_batch(self) -> dict[str | None, Decimal]:
        """Return the soap on hand per batch number, leaving out empty rows."""
        numbers = {self.early.id: "EARLY", self.late.id: "LATE", None: None}
        rows = self.session.scalars(
            select(InventoryRecord).where(InventoryRecord.product_id == self.soap.id)
        ).all()
        return {
            numbers[row.batch_id]: D(str(row.current_quantity))
            for row in rows
            if D(str(row.current_quantity)) != 0
        }


def test_a_kit_takes_a_batch_tracked_part_earliest_expiry_first() -> None:
    shop = _BatchShop()
    repack = KitService(shop.session).assemble(
        shop.pack.id, shop.assembly("2"), firm_id=shop.firm.id, actor_id=shop.actor
    )
    # Four soaps: the three expiring first, then one of the later batch.
    assert shop.by_batch() == {"LATE": D("4")}
    assert shop.held(shop.pack) == D("2")
    lines = RepackService(shop.session).lines(repack.id)  # type: ignore[attr-defined]
    soap = sorted(
        (D(str(line.quantity)), line.batch_id)
        for line in lines
        if line.product_id == shop.soap.id
    )
    assert soap == sorted([(D("3"), shop.early.id), (D("1"), shop.late.id)])
    assert sorted(line.line_number for line in lines) == [1, 2, 3, 4]

    RepackService(shop.session).cancel(
        repack.id,  # type: ignore[attr-defined]
        "made in error",
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    assert shop.by_batch() == {"EARLY": D("3"), "LATE": D("5")}
    assert shop.held(shop.pack) == D("0")


def test_a_kit_short_of_a_batch_tracked_part_is_refused_by_name() -> None:
    shop = _BatchShop()
    kits = KitService(shop.session)
    with pytest.raises(ValidationError, match="SOAP: 8.* available, 10.* needed"):
        kits.assemble(
            shop.pack.id, shop.assembly("5"), firm_id=shop.firm.id, actor_id=shop.actor
        )
    assert shop.by_batch() == {"EARLY": D("3"), "LATE": D("5")}


def test_a_repack_line_naming_its_batch_is_left_as_it_was_written() -> None:
    shop = _BatchShop()
    RepackService(shop.session).post(
        RepackWrite.model_validate(
            {
                "repack_date": ON,
                "branch_id": shop.branch.id,
                "warehouse_id": shop.warehouse.id,
                "lines": [
                    {
                        "kind": "CONSUME",
                        "product_id": shop.soap.id,
                        "batch_id": shop.late.id,
                        "quantity": "2",
                    },
                    {"kind": "PRODUCE", "product_id": shop.towel.id, "quantity": "1"},
                ],
            }
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    assert shop.by_batch() == {"EARLY": D("3"), "LATE": D("3")}


def test_an_expired_batch_is_not_made_into_a_kit() -> None:
    shop = _BatchShop()
    shop.early.expiry_date = date(2026, 7, 1)
    shop.session.commit()
    with pytest.raises(ValidationError, match="SOAP.*cannot be repacked.*EARLY"):
        KitService(shop.session).assemble(
            shop.pack.id, shop.assembly("3"), firm_id=shop.firm.id, actor_id=shop.actor
        )
    shop.session.rollback()
    assert shop.by_batch() == {"EARLY": D("3"), "LATE": D("5")}


def test_a_serial_tracked_product_is_refused_on_a_repack_and_in_a_kit() -> None:
    shop = _BatchShop()
    shop.towel.track_serial = True
    shop.session.commit()
    kits = KitService(shop.session)
    with pytest.raises(ValidationError, match="TOWEL is tracked by serial number"):
        kits.assemble(
            shop.pack.id, shop.assembly("1"), firm_id=shop.firm.id, actor_id=shop.actor
        )
    shop.session.rollback()
    assert (shop.held(shop.towel), shop.held(shop.pack)) == (D("10"), D("0"))
    with pytest.raises(ValidationError, match="cannot go into a kit.*TOWEL"):
        kits.replace(
            shop.pack.id,
            KitComponentsWrite.model_validate(
                {
                    "components": [
                        {"component_product_id": shop.towel.id, "quantity": "1"}
                    ]
                }
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )
