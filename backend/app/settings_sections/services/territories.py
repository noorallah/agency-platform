"""The Territories subject: the firm's map of areas, rounds and carriers.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: a sale with no territory, round or transporter is still taken, so each
step is OPTIONAL. The order is a hard one all the same -- a route type names a
round and the Route Builder puts shops on a territory, so neither is any use
before the territories exist -- and it stays OPTIONAL, as Attribute definitions
before Mandatory attributes does in Business profile.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.delivery_note.models.transporter import Transporter
from app.sales.models.territory import (
    RouteTypeMaster,
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
)
from app.settings_sections.services.steps import (
    NONE_YET,
    OPTIONAL,
    SettingsStep,
    counted,
    counted_step,
)


def _route_builder_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the shops the Route Builder has put on the firm's rounds.

    The screen saves through ``PUT /sales-territories/{id}/customers``, which
    writes ``territory_customer_assignments``. That table has no firm column,
    so it is reached through the firm's live territories.
    """
    placed = (
        select(
            func.count(),
            func.count(func.distinct(TerritoryCustomerAssignment.territory_id)),
        )
        .select_from(TerritoryCustomerAssignment)
        .join(
            SalesTerritoryNode,
            SalesTerritoryNode.id == TerritoryCustomerAssignment.territory_id,
        )
        .where(
            SalesTerritoryNode.firm_id == firm_id,
            SalesTerritoryNode.is_deleted.is_(False),
            TerritoryCustomerAssignment.is_deleted.is_(False),
        )
    )
    shops, rounds = session.execute(placed).one()
    if not shops:
        return SettingsStep("route-builder", OPTIONAL, NONE_YET)
    detail = (
        f"{counted(shops, 'shop', 'shops')} on {counted(rounds, 'round', 'rounds')}"
    )
    return SettingsStep("route-builder", OPTIONAL, detail)


def territories_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the four steps of the Territories subject, in set-up order."""
    return [
        counted_step(
            session,
            SalesTerritoryNode,
            firm_id,
            "territories",
            ("territory", "territories"),
            SalesTerritoryNode.status == "ACTIVE",
        ),
        counted_step(
            session,
            RouteTypeMaster,
            firm_id,
            "route-types",
            ("route type", "route types"),
            RouteTypeMaster.is_active.is_(True),
        ),
        _route_builder_step(session, firm_id),
        counted_step(
            session,
            Transporter,
            firm_id,
            "transporters",
            ("transporter", "transporters"),
            Transporter.is_active.is_(True),
        ),
    ]


__all__ = ["territories_section"]
