"""The shared goods type catalogue, and what each profile starts a firm with.

The catalogue is reference data every firm store holds its own copy of, as
it does of the units: `20261008_0350` writes it into the stores that exist,
and `seed_goods_types` into one built from the models. A profile's starting
set is applied once, the first time a firm is given a profile; after that the
firm's administrator adds and drops types and the profile has no say
(backlog 89, *Business profiles stay, smaller*).
"""

from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.products.models.goods_type import FirmGoodsType, GoodsType


class GoodsTypeSeed(TypedDict):
    """One shared goods type."""

    id: UUID
    code: str
    name: str
    description: str
    switches: tuple[str, ...]


SHARED_GOODS_TYPES: tuple[GoodsTypeSeed, ...] = (
    {
        "id": UUID("89000000-0000-0000-0000-000000000001"),
        "code": "MEDICINE",
        "name": "Medicine",
        "description": "Medicines and healthcare goods: batch and expiry on all.",
        "switches": ("track_batch", "track_expiry", "track_manufacturing_date"),
    },
    {
        "id": UUID("89000000-0000-0000-0000-000000000002"),
        "code": "FOOD",
        "name": "Food",
        "description": "Food, grocery and packaged goods with a shelf life.",
        "switches": ("track_batch", "track_expiry", "track_manufacturing_date"),
    },
    {
        "id": UUID("89000000-0000-0000-0000-000000000003"),
        "code": "COSMETICS",
        "name": "Cosmetics and personal care",
        "description": "Personal care goods sold by batch with a use-by date.",
        "switches": ("track_batch", "track_expiry", "track_manufacturing_date"),
    },
    {
        "id": UUID("89000000-0000-0000-0000-000000000004"),
        "code": "PAINT",
        "name": "Paint",
        "description": "Paints and coatings: a batch for the shade, no expiry.",
        "switches": ("track_batch",),
    },
    {
        "id": UUID("89000000-0000-0000-0000-000000000005"),
        "code": "ELECTRONICS",
        "name": "Electronics",
        "description": "Electronic goods sold by serial number under warranty.",
        "switches": ("track_serial", "track_warranty"),
    },
)

#: The goods types a firm starts with, by its profile's code. A profile not
#: named here starts with none: every product is General until the firm's
#: administrator adds a type.
PROFILE_STARTING_GOODS_TYPES: dict[str, tuple[str, ...]] = {
    "PHARMACY": ("MEDICINE",),
    "FOOD": ("FOOD",),
    "RESTAURANT": ("FOOD",),
    "ELECTRONICS": ("ELECTRONICS",),
}


def seed_goods_types(session: Session) -> None:
    """Add the shared goods types this store is missing; flush, no commit."""
    held = set(
        session.scalars(select(GoodsType.code).where(GoodsType.firm_id.is_(None)))
    )
    for seed in SHARED_GOODS_TYPES:
        if seed["code"] in held:
            continue
        session.add(
            GoodsType(
                id=seed["id"],
                code=seed["code"],
                name=seed["name"],
                description=seed["description"],
                **dict.fromkeys(seed["switches"], True),
            )
        )
    session.flush()


def start_firm_goods_types(
    session: Session, *, firm_id: UUID, profile_code: str, actor_id: UUID | None
) -> list[str]:
    """Give a firm its profile's starting goods types; flush, no commit.

    Only for a firm that holds none: a firm that has chosen its types, or
    dropped them all, is not handed the profile's again.

    Returns:
        The codes put in use.

    """
    wanted = PROFILE_STARTING_GOODS_TYPES.get(profile_code, ())
    if not wanted:
        return []
    # Soft-deleted rows count: a type the firm dropped stays dropped.
    if session.scalar(
        select(FirmGoodsType.id).where(FirmGoodsType.firm_id == firm_id).limit(1)
    ):
        return []
    rows = session.execute(
        select(GoodsType.id, GoodsType.code).where(
            GoodsType.firm_id.is_(None),
            GoodsType.code.in_(wanted),
            GoodsType.is_deleted.is_(False),
        )
    ).all()
    for goods_type_id, _code in rows:
        session.add(
            FirmGoodsType(
                firm_id=firm_id,
                goods_type_id=goods_type_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
    session.flush()
    codes = sorted(code for _id, code in rows)
    if codes:
        record_audit(
            session,
            action="goods_type.starting_set",
            entity_type="firm",
            entity_id=firm_id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"profile": profile_code, "goods_types": codes},
        )
    return codes
