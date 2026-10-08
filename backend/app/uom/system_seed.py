"""Baseline UOM and packaging seed data."""

from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.uom.models import (
    PackagingType,
    Uom,
    UomGroup,
    UomGroupUnit,
)


# The seed rows are heterogeneous records, so an untyped literal collapses to
# dict[str, object] and every read of one has to be narrowed at the call site.
# Declaring their shape once keeps the seed readable and type-checked.
class UomSeed(TypedDict):
    """One catalogue unit to seed."""

    id: UUID
    code: str
    name: str
    symbol: str
    dimension: str
    is_decimal_allowed: bool


class UomGroupSeed(TypedDict):
    """One unit group to seed, with its member units."""

    id: UUID
    code: str
    name: str
    description: str
    units: tuple[tuple[str, bool, int], ...]


SEED_UOMS: tuple[UomSeed, ...] = (
    {
        "id": UUID("81000000-0000-0000-0000-000000000001"),
        "code": "UNIT",
        "name": "Unit",
        "symbol": "unit",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000002"),
        "code": "PIECE",
        "name": "Piece",
        "symbol": "pc",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000003"),
        "code": "PACK",
        "name": "Pack",
        "symbol": "pk",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000015"),
        "code": "TABLET",
        "name": "Tablet",
        "symbol": "tab",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000004"),
        "code": "STRIP",
        "name": "Strip",
        "symbol": "strip",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000005"),
        "code": "BOX",
        "name": "Box",
        "symbol": "box",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000006"),
        "code": "CARTON",
        "name": "Carton",
        "symbol": "ctn",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000007"),
        "code": "CASE",
        "name": "Case",
        "symbol": "cs",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000008"),
        "code": "BAG",
        "name": "Bag",
        "symbol": "bag",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000009"),
        "code": "BOTTLE",
        "name": "Bottle",
        "symbol": "btl",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-00000000000A"),
        "code": "JAR",
        "name": "Jar",
        "symbol": "jar",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-00000000000B"),
        "code": "TUBE",
        "name": "Tube",
        "symbol": "tube",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-00000000000C"),
        "code": "SACHET",
        "name": "Sachet",
        "symbol": "scht",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-00000000000D"),
        "code": "CRATE",
        "name": "Crate",
        "symbol": "crate",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-00000000000E"),
        "code": "PALLET",
        "name": "Pallet",
        "symbol": "plt",
        "dimension": "COUNT",
        "is_decimal_allowed": False,
    },
    {
        "id": UUID("81000000-0000-0000-0000-00000000000F"),
        "code": "G",
        "name": "Gram",
        "symbol": "g",
        "dimension": "WEIGHT",
        "is_decimal_allowed": True,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000010"),
        "code": "KG",
        "name": "Kilogram",
        "symbol": "kg",
        "dimension": "WEIGHT",
        "is_decimal_allowed": True,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000011"),
        "code": "ML",
        "name": "Millilitre",
        "symbol": "ml",
        "dimension": "VOLUME",
        "is_decimal_allowed": True,
    },
    {
        "id": UUID("81000000-0000-0000-0000-000000000012"),
        "code": "L",
        "name": "Litre",
        "symbol": "l",
        "dimension": "VOLUME",
        "is_decimal_allowed": True,
    },
)

SEED_UOM_GROUPS: tuple[UomGroupSeed, ...] = (
    {
        "id": UUID("82000000-0000-0000-0000-000000000001"),
        "code": "DIST_COUNT",
        "name": "Distribution Count",
        "description": "General B2B distribution pack hierarchy.",
        "units": (
            ("UNIT", True, 1),
            ("BOX", False, 2),
            ("CARTON", False, 3),
            ("CASE", False, 4),
        ),
    },
    {
        "id": UUID("82000000-0000-0000-0000-000000000002"),
        "code": "PHARMA_PACK",
        "name": "Pharma Pack",
        "description": "Pharma-focused strip to carton packaging hierarchy.",
        "units": (
            ("TABLET", True, 1),
            ("STRIP", False, 2),
            ("BOX", False, 3),
            ("CARTON", False, 4),
        ),
    },
    {
        "id": UUID("82000000-0000-0000-0000-000000000003"),
        "code": "FOOD_PACK",
        "name": "Food Pack",
        "description": "Packaged food distribution hierarchy.",
        "units": (
            ("PACK", True, 1),
            ("BOX", False, 2),
            ("CARTON", False, 3),
            ("BAG", False, 4),
            ("BOTTLE", False, 5),
            ("SACHET", False, 6),
        ),
    },
    {
        "id": UUID("82000000-0000-0000-0000-000000000004"),
        "code": "WEIGHT_METRIC",
        "name": "Weight Metric",
        "description": "Metric units for weight-based items.",
        "units": (
            ("G", True, 1),
            ("KG", False, 2),
        ),
    },
    {
        "id": UUID("82000000-0000-0000-0000-000000000005"),
        "code": "VOLUME_METRIC",
        "name": "Volume Metric",
        "description": "Metric units for liquid products.",
        "units": (
            ("ML", True, 1),
            ("L", False, 2),
        ),
    },
)

SEED_PACKAGING_TYPES: tuple[tuple[UUID, str, str, str], ...] = (
    (
        UUID("83000000-0000-0000-0000-000000000001"),
        "UNIT",
        "Unit",
        "Single saleable unit.",
    ),
    (
        UUID("83000000-0000-0000-0000-000000000002"),
        "STRIP",
        "Strip",
        "Strip packing used in pharma products.",
    ),
    (
        UUID("83000000-0000-0000-0000-000000000003"),
        "PACK",
        "Pack",
        "Flexible consumer pack.",
    ),
    (UUID("83000000-0000-0000-0000-000000000004"), "BOX", "Box", "Retail inner box."),
    (
        UUID("83000000-0000-0000-0000-000000000005"),
        "CARTON",
        "Carton",
        "Outer shipping carton.",
    ),
    (
        UUID("83000000-0000-0000-0000-000000000006"),
        "CASE",
        "Case",
        "Wholesale case packaging.",
    ),
    (
        UUID("83000000-0000-0000-0000-000000000007"),
        "BAG",
        "Bag",
        "Bag or sack packaging.",
    ),
    (
        UUID("83000000-0000-0000-0000-000000000008"),
        "BOTTLE",
        "Bottle",
        "Bottle container.",
    ),
    (UUID("83000000-0000-0000-0000-000000000009"), "JAR", "Jar", "Jar container."),
    (UUID("83000000-0000-0000-0000-00000000000A"), "TUBE", "Tube", "Tube packaging."),
    (
        UUID("83000000-0000-0000-0000-00000000000B"),
        "SACHET",
        "Sachet",
        "Sachet or pouch pack.",
    ),
    (
        UUID("83000000-0000-0000-0000-00000000000C"),
        "CRATE",
        "Crate",
        "Reusable crate or tray.",
    ),
    (
        UUID("83000000-0000-0000-0000-00000000000D"),
        "PALLET",
        "Pallet",
        "Palletized transport unit.",
    ),
)


def seed_uom_reference_data(session: Session) -> None:
    """Create or restore baseline UOM catalog data without touching custom rows."""
    uoms = _seed_uoms(session)
    groups = _seed_uom_groups(session)
    session.flush()
    _seed_group_units(session, groups, uoms)
    _seed_packaging_types(session)


def _seed_uoms(session: Session) -> dict[str, Uom]:
    existing = {row.code: row for row in session.scalars(select(Uom))}
    seeded: dict[str, Uom] = {}
    for seed in SEED_UOMS:
        row = existing.get(seed["code"])
        if row is None:
            row = Uom(
                id=seed["id"],
                code=seed["code"],
                name=seed["name"],
                symbol=seed["symbol"],
                dimension=seed["dimension"],
                status="ACTIVE",
                is_decimal_allowed=seed["is_decimal_allowed"],
            )
            session.add(row)
        else:
            row.name = seed["name"]
            row.symbol = seed["symbol"]
            row.dimension = seed["dimension"]
            row.status = "ACTIVE"
            row.is_decimal_allowed = seed["is_decimal_allowed"]
            row.is_deleted = False
            row.deleted_at = None
            row.deleted_by = None
        seeded[seed["code"]] = row
    return seeded


def _seed_uom_groups(session: Session) -> dict[str, UomGroup]:
    existing = {row.code: row for row in session.scalars(select(UomGroup))}
    seeded: dict[str, UomGroup] = {}
    for seed in SEED_UOM_GROUPS:
        row = existing.get(seed["code"])
        if row is None:
            row = UomGroup(
                id=seed["id"],
                code=seed["code"],
                name=seed["name"],
                description=seed["description"],
                status="ACTIVE",
            )
            session.add(row)
        else:
            row.name = seed["name"]
            row.description = seed["description"]
            row.status = "ACTIVE"
            row.is_deleted = False
            row.deleted_at = None
            row.deleted_by = None
        seeded[seed["code"]] = row
    return seeded


def _seed_group_units(
    session: Session, groups: dict[str, UomGroup], uoms: dict[str, Uom]
) -> None:
    existing = {
        (row.uom_group_id, row.uom_id): row
        for row in session.scalars(select(UomGroupUnit))
    }
    for seed in SEED_UOM_GROUPS:
        group = groups[seed["code"]]
        for uom_code, is_base, display_order in seed["units"]:
            uom = uoms[uom_code]
            row = existing.get((group.id, uom.id))
            if row is None:
                row = UomGroupUnit(
                    uom_group_id=group.id,
                    uom_id=uom.id,
                    is_base=is_base,
                    display_order=display_order,
                )
                session.add(row)
                continue
            row.is_base = is_base
            row.display_order = display_order
            row.is_deleted = False
            row.deleted_at = None
            row.deleted_by = None


def _seed_packaging_types(session: Session) -> None:
    existing = {row.code: row for row in session.scalars(select(PackagingType))}
    for row_id, code, name, description in SEED_PACKAGING_TYPES:
        row = existing.get(code)
        if row is None:
            session.add(
                PackagingType(
                    id=row_id,
                    code=code,
                    name=name,
                    description=description,
                    status="ACTIVE",
                )
            )
            continue
        row.name = name
        row.description = description
        row.status = "ACTIVE"
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
