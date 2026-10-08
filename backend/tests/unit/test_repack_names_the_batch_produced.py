"""What a repack produces names its batch (D-STK-53).

Soap is kept in batches. A repack that produced soap and named no batch put
it on the stock row with no batch: goods on hand with no expiry, sold last
and never short-dated. A produce line now names the batch, by id or by a
number that is found or opened the way a goods receipt opens one. Breaking a
gift pack gives its soap back to the batch the pack's last assembly took it
from, unless the caller names another.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.core.exceptions import ValidationError
from app.inventory.models import InventoryRecord
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.inventory.services.repacking import (
    RepackLineWrite,
    RepackService,
    RepackWrite,
)
from app.products.models import Product
from app.products.services.kits import KitAssemblyWrite, KitService
from tests.unit.test_kits import ON
from tests.unit.test_repack_draws_from_batches import _BatchShop

D = Decimal


def _towel_into_soap(shop: _BatchShop, **batch: object) -> RepackWrite:
    return RepackWrite.model_validate(
        {
            "repack_date": ON,
            "branch_id": shop.branch.id,
            "warehouse_id": shop.warehouse.id,
            "lines": [
                {"kind": "CONSUME", "product_id": shop.towel.id, "quantity": "1"},
                {
                    "kind": "PRODUCE",
                    "product_id": shop.soap.id,
                    "quantity": "4",
                    **batch,
                },
            ],
        }
    )


def _soap_by_number(shop: _BatchShop) -> dict[str | None, Decimal]:
    numbers: dict[object, str | None] = {
        row.id: row.batch_number
        for row in shop.session.scalars(
            select(BatchRecord).where(BatchRecord.product_id == shop.soap.id)
        ).all()
    }
    numbers[None] = None
    rows = shop.session.scalars(
        select(InventoryRecord).where(InventoryRecord.product_id == shop.soap.id)
    ).all()
    return {
        numbers[row.batch_id]: D(str(row.current_quantity))
        for row in rows
        if D(str(row.current_quantity)) != 0
    }


def _post(shop: _BatchShop, data: RepackWrite) -> object:
    return RepackService(shop.session).post(
        data, firm_id=shop.firm.id, actor_id=shop.actor
    )


def _stock(shop: _BatchShop, product: Product, quantity: str) -> None:
    InventoryService(shop.session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            product_id=product.id,
            quantity=D(quantity),
            reference_number=f"ADJ-IN-{product.code}",
            reference_type="ADJUSTMENT",
            transaction_date=ON,
        ),
        firm_scope=shop.firm.id,
        actor_id=shop.actor,
    )


def test_a_batch_tracked_product_is_not_produced_into_no_batch() -> None:
    shop = _BatchShop()
    with pytest.raises(ValidationError, match="SOAP - Soap is kept in batches"):
        _post(shop, _towel_into_soap(shop))
    shop.session.rollback()
    assert _soap_by_number(shop) == {"EARLY": D("3"), "LATE": D("5")}
    assert shop.held(shop.towel) == D("10")


def test_a_new_batch_number_opens_the_batch_with_its_dates() -> None:
    shop = _BatchShop()
    shop.soap.track_expiry = True
    shop.session.commit()
    repack = _post(
        shop, _towel_into_soap(shop, batch_number="RPK-1", expiry_date="2027-03-31")
    )
    assert _soap_by_number(shop) == {
        "EARLY": D("3"),
        "LATE": D("5"),
        "RPK-1": D("4"),
    }
    batch = shop.session.scalar(
        select(BatchRecord).where(BatchRecord.batch_number == "RPK-1")
    )
    assert batch is not None and batch.expiry_date == date(2027, 3, 31)
    produced = [
        line
        for line in RepackService(shop.session).lines(repack.id)  # type: ignore[attr-defined]
        if line.kind == "PRODUCE"
    ]
    assert [line.batch_id for line in produced] == [batch.id]

    RepackService(shop.session).cancel(
        repack.id,  # type: ignore[attr-defined]
        "made in error",
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    assert _soap_by_number(shop) == {"EARLY": D("3"), "LATE": D("5")}


def test_a_dated_product_is_refused_a_new_batch_with_no_expiry() -> None:
    shop = _BatchShop()
    shop.soap.track_expiry = True
    shop.session.commit()
    with pytest.raises(ValidationError, match="expiry"):
        _post(shop, _towel_into_soap(shop, batch_number="RPK-2"))
    shop.session.rollback()
    assert _soap_by_number(shop) == {"EARLY": D("3"), "LATE": D("5")}


def test_a_number_the_product_already_has_goes_into_that_batch() -> None:
    shop = _BatchShop()
    _post(shop, _towel_into_soap(shop, batch_number="LATE"))
    assert _soap_by_number(shop) == {"EARLY": D("3"), "LATE": D("9")}


def test_a_batch_named_by_id_is_taken_as_written() -> None:
    shop = _BatchShop()
    _post(shop, _towel_into_soap(shop, batch_id=shop.early.id))
    assert _soap_by_number(shop) == {"EARLY": D("7"), "LATE": D("5")}


def test_a_product_not_kept_in_batches_is_refused_one() -> None:
    shop = _BatchShop()
    data = RepackWrite.model_validate(
        {
            "repack_date": ON,
            "branch_id": shop.branch.id,
            "warehouse_id": shop.warehouse.id,
            "lines": [
                {"kind": "CONSUME", "product_id": shop.soap.id, "quantity": "2"},
                {
                    "kind": "PRODUCE",
                    "product_id": shop.towel.id,
                    "quantity": "1",
                    "batch_number": "T-1",
                },
            ],
        }
    )
    with pytest.raises(ValidationError, match="TOWEL - Towel is not kept in batches"):
        _post(shop, data)
    shop.session.rollback()
    assert _soap_by_number(shop) == {"EARLY": D("3"), "LATE": D("5")}


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ({"kind": "CONSUME", "batch_number": "X"}, "only a produce line"),
        (
            {"kind": "PRODUCE", "batch_number": "X", "batch_id": "0" * 32},
            "not both",
        ),
        ({"kind": "PRODUCE", "expiry_date": "2027-01-01"}, "need its number"),
    ],
)
def test_a_line_names_its_batch_one_way(line: dict[str, str], message: str) -> None:
    with pytest.raises(SchemaError, match=message):
        RepackLineWrite.model_validate(
            {"product_id": "1" * 32, "quantity": "1", **line}
        )


def test_breaking_a_kit_gives_the_part_back_to_the_batch_it_came_from() -> None:
    shop = _BatchShop()
    kits = KitService(shop.session)
    # Two packs take four soaps: all three of EARLY, then one of LATE.
    kits.assemble(
        shop.pack.id, shop.assembly("2"), firm_id=shop.firm.id, actor_id=shop.actor
    )
    assert _soap_by_number(shop) == {"LATE": D("4")}
    kits.assemble(
        shop.pack.id,
        shop.assembly("1"),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
        disassemble=True,
    )
    assert _soap_by_number(shop) == {"LATE": D("6")}
    assert shop.held(shop.pack) == D("1")


def test_a_kit_never_assembled_here_asks_where_its_part_goes() -> None:
    shop = _BatchShop()
    _stock(shop, shop.pack, "2")
    kits = KitService(shop.session)
    with pytest.raises(
        ValidationError, match="SOAP - Soap is kept in batches, and no assembly"
    ):
        kits.assemble(
            shop.pack.id,
            shop.assembly("1"),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
            disassemble=True,
        )
    shop.session.rollback()
    kits.assemble(
        shop.pack.id,
        KitAssemblyWrite.model_validate(
            {
                **shop.assembly("1").model_dump(),
                "part_batches": [{"product_id": shop.soap.id, "batch_number": "EARLY"}],
            }
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
        disassemble=True,
    )
    assert _soap_by_number(shop) == {"EARLY": D("5"), "LATE": D("5")}
    assert shop.held(shop.pack) == D("1")


def test_a_kit_kept_in_batches_is_assembled_into_a_named_batch() -> None:
    shop = _BatchShop()
    shop.pack.track_batch = True
    shop.session.commit()
    kits = KitService(shop.session)
    with pytest.raises(ValidationError, match="GIFT - Gift is kept in batches"):
        kits.assemble(
            shop.pack.id, shop.assembly("1"), firm_id=shop.firm.id, actor_id=shop.actor
        )
    shop.session.rollback()
    # A note cannot name the batch, so it does not assemble such a kit.
    assert not kits.assemble_for_dispatch(
        firm_id=shop.firm.id,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        product_id=shop.pack.id,
        shortfall=D("1"),
        on=ON,
        reference="DN-1",
        actor_id=shop.actor,
    )
    named = KitAssemblyWrite.model_validate(
        {**shop.assembly("1").model_dump(), "batch_number": "GIFT-OCT"}
    )
    kits.assemble(shop.pack.id, named, firm_id=shop.firm.id, actor_id=shop.actor)
    row = shop.session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.product_id == shop.pack.id,
            InventoryRecord.current_quantity > 0,
        )
    )
    batch = shop.session.scalar(
        select(BatchRecord).where(BatchRecord.batch_number == "GIFT-OCT")
    )
    assert row is not None and batch is not None and row.batch_id == batch.id
    with pytest.raises(ValidationError, match="name a batch only for the parts"):
        kits.assemble(
            shop.pack.id,
            named,
            firm_id=shop.firm.id,
            actor_id=shop.actor,
            disassemble=True,
        )
