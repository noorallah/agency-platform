"""The Locations subject: the places, kinds of site and storage a firm uses.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: a branch or warehouse needs no type and no place from the masters, so
each step is OPTIONAL. A storage area sits inside a warehouse, which is set up
under Organisation rather than here, so the step says when there is none yet.

Places carry no firm column: the geography masters are the store's own, shared
by every firm in it, so they are counted for the store. The order is **decided
by the loop**: places first, because branch and warehouse addresses name them;
the two types before the branches and warehouses that name them; storage
areas last.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.branches.models.branch_warehouse import (
    BranchType,
    Warehouse,
    WarehouseStorageNode,
    WarehouseType,
)
from app.sales.models.territory import GeoCity, GeoCountry, GeoDistrict, GeoState
from app.settings_sections.services.steps import (
    NONE_YET,
    OPTIONAL,
    SettingsStep,
    counted,
    counted_step,
    live_count,
)

NEEDS_A_WAREHOUSE = "Needs a warehouse first"

_PLACE_LEVELS = (
    (GeoCountry, ("country", "countries")),
    (GeoState, ("state", "states")),
    (GeoDistrict, ("district", "districts")),
    (GeoCity, ("city", "cities")),
)


def _places_step(session: Session) -> SettingsStep:
    """Count the store's active places at each level that holds any."""
    parts = []
    for model, nouns in _PLACE_LEVELS:
        count = session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.is_deleted.is_(False), model.is_active.is_(True))
        )
        if count:
            parts.append(counted(count, *nouns))
    return SettingsStep("geography-masters", OPTIONAL, ", ".join(parts) or NONE_YET)


def _storage_areas_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the firm's storage areas, reached through its warehouses.

    ``warehouse_storage_nodes`` has no firm column; each node names its
    warehouse, which does.
    """
    if not live_count(session, Warehouse, firm_id):
        return SettingsStep("storage-areas", OPTIONAL, NEEDS_A_WAREHOUSE)
    areas = session.scalar(
        select(func.count())
        .select_from(WarehouseStorageNode)
        .join(Warehouse, Warehouse.id == WarehouseStorageNode.warehouse_id)
        .where(
            Warehouse.firm_id == firm_id,
            Warehouse.is_deleted.is_(False),
            WarehouseStorageNode.is_deleted.is_(False),
            WarehouseStorageNode.is_active.is_(True),
        )
    )
    detail = counted(areas, "area", "areas") if areas else NONE_YET
    return SettingsStep("storage-areas", OPTIONAL, detail)


def locations_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the four steps of the Locations subject, in set-up order."""
    return [
        _places_step(session),
        counted_step(
            session,
            BranchType,
            firm_id,
            "branch-types",
            ("type", "types"),
            BranchType.is_active.is_(True),
        ),
        counted_step(
            session,
            WarehouseType,
            firm_id,
            "warehouse-types",
            ("type", "types"),
            WarehouseType.is_active.is_(True),
        ),
        _storage_areas_step(session, firm_id),
    ]


__all__ = ["NEEDS_A_WAREHOUSE", "locations_section"]
