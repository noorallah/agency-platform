"""The shared unit set catalogue.

Reference data every firm store holds its own copy of, as it does of the
units and the goods types: `20261008_0351` writes it into the stores that
exist, and `seed_unit_sets` into one built from the models. It names units
and goods types by code, so it runs after both are seeded, and a set whose
units a store lacks is left out rather than written half-filled.

A profile hands a firm no unit sets of its own: the goods types it starts the
firm with decide which of these the firm's products are offered first, and
the sets tied to no goods type are offered to every product (backlog 89).
"""

from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.products.models.goods_type import GoodsType
from app.uom.models import UnitSet, UnitSetGoodsType, Uom


class UnitSetSeed(TypedDict):
    """One shared unit set, its units and goods types named by code."""

    id: UUID
    name: str
    stock: str
    purchase: str
    factor: Decimal | None
    allow_decimal: bool
    goods_types: tuple[str, ...]


SHARED_UNIT_SETS: tuple[UnitSetSeed, ...] = (
    {
        "id": UUID("8a000000-0000-0000-0000-000000000001"),
        "name": "Strip, box of 10",
        "stock": "STRIP",
        "purchase": "BOX",
        "factor": Decimal("10"),
        "allow_decimal": False,
        "goods_types": ("MEDICINE",),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000002"),
        "name": "Strip, box of 15",
        "stock": "STRIP",
        "purchase": "BOX",
        "factor": Decimal("15"),
        "allow_decimal": False,
        "goods_types": ("MEDICINE",),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000003"),
        "name": "Bottle, carton of 24",
        "stock": "BOTTLE",
        "purchase": "CARTON",
        "factor": Decimal("24"),
        "allow_decimal": False,
        "goods_types": ("MEDICINE", "FOOD", "COSMETICS"),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000004"),
        "name": "Tube, box of 20",
        "stock": "TUBE",
        "purchase": "BOX",
        "factor": Decimal("20"),
        "allow_decimal": False,
        "goods_types": ("MEDICINE", "COSMETICS"),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000005"),
        "name": "Pack, carton of 12",
        "stock": "PACK",
        "purchase": "CARTON",
        "factor": Decimal("12"),
        "allow_decimal": False,
        "goods_types": ("FOOD",),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000006"),
        "name": "Litre, loose",
        "stock": "L",
        "purchase": "L",
        "factor": None,
        "allow_decimal": True,
        "goods_types": ("PAINT",),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000007"),
        "name": "Piece, loose",
        "stock": "PIECE",
        "purchase": "PIECE",
        "factor": None,
        "allow_decimal": False,
        "goods_types": (),
    },
    {
        "id": UUID("8a000000-0000-0000-0000-000000000008"),
        "name": "Unit, box of 10",
        "stock": "UNIT",
        "purchase": "BOX",
        "factor": Decimal("10"),
        "allow_decimal": False,
        "goods_types": (),
    },
)


def seed_unit_sets(session: Session) -> None:
    """Add the shared unit sets this store is missing; flush, no commit.

    A set is never rewritten once it exists, deleted or not: a replay must
    not undo what the platform has since changed or retired.
    """
    held = set(session.scalars(select(UnitSet.id).where(UnitSet.firm_id.is_(None))))
    names = set(
        session.scalars(
            select(UnitSet.name).where(
                UnitSet.firm_id.is_(None), UnitSet.is_deleted.is_(False)
            )
        )
    )
    units: dict[str, UUID] = {
        code: unit_id
        for code, unit_id in session.execute(
            select(Uom.code, Uom.id).where(Uom.is_deleted.is_(False))
        ).all()
    }
    types: dict[str, UUID] = {
        code: type_id
        for code, type_id in session.execute(
            select(GoodsType.code, GoodsType.id).where(
                GoodsType.firm_id.is_(None), GoodsType.is_deleted.is_(False)
            )
        ).all()
    }
    for seed in SHARED_UNIT_SETS:
        stock, purchase = units.get(seed["stock"]), units.get(seed["purchase"])
        if seed["id"] in held or seed["name"] in names:
            continue
        if stock is None or purchase is None:
            continue
        session.add(
            UnitSet(
                id=seed["id"],
                firm_id=None,
                name=seed["name"],
                base_uom_id=stock,
                inventory_uom_id=stock,
                purchase_uom_id=purchase,
                sales_uom_id=stock,
                allow_decimal=seed["allow_decimal"],
                conversion_factor=seed["factor"],
            )
        )
        session.flush()
        for code in seed["goods_types"]:
            if code in types:
                session.add(
                    UnitSetGoodsType(unit_set_id=seed["id"], goods_type_id=types[code])
                )
    session.flush()
