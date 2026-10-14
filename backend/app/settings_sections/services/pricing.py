"""The Pricing subject: the firm's price lists, levels, offers and loyalty.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: a line with no list, level or offer is priced at the product's own rate,
so each step is OPTIONAL.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.loyalty.models.loyalty import LoyaltyEntry, LoyaltySettings
from app.pricing.models.price_level import PriceLevel
from app.pricing.models.price_list import PriceList
from app.promotions.models.promotion import Promotion
from app.settings_sections.services.steps import (
    NONE_YET,
    OPTIONAL,
    SettingsStep,
    counted,
    counted_step,
)


def _promotions_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the firm's offers, and how many of them are running.

    An offer is its ``version_group_id``: editing a running offer writes a new
    row under the same group, so rows would count one offer once per revision.
    """
    live = (Promotion.firm_id == firm_id, Promotion.is_deleted.is_(False))
    offers = (
        session.scalar(
            select(func.count(func.distinct(Promotion.version_group_id))).where(*live)
        )
        or 0
    )
    if not offers:
        return SettingsStep("promotions", OPTIONAL, NONE_YET)
    running = (
        session.scalar(
            select(func.count(func.distinct(Promotion.version_group_id))).where(
                *live, Promotion.status == "ACTIVE"
            )
        )
        or 0
    )
    detail = counted(offers, "offer", "offers")
    detail += f", {running} running" if running else ", none running"
    return SettingsStep("promotions", OPTIONAL, detail)


def _loyalty_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the customers holding a loyalty account, and say if the scheme is off.

    The Loyalty list is each customer's ledger of points, so what it holds is
    the customers with an entry. The scheme's switch itself is Selling's.
    """
    enabled = session.scalar(
        select(LoyaltySettings.is_enabled).where(
            LoyaltySettings.firm_id == firm_id,
            LoyaltySettings.is_deleted.is_(False),
        )
    )
    customers = (
        session.scalar(
            select(func.count(func.distinct(LoyaltyEntry.customer_id))).where(
                LoyaltyEntry.firm_id == firm_id,
                LoyaltyEntry.is_deleted.is_(False),
            )
        )
        or 0
    )
    detail = counted(customers, "customer", "customers") if customers else NONE_YET
    if not enabled:
        detail = f"Scheme off: {detail[0].lower()}{detail[1:]}"
    return SettingsStep("loyalty", OPTIONAL, detail)


def pricing_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the four steps of the Pricing subject, in set-up order."""
    return [
        counted_step(session, PriceList, firm_id, "price-lists", ("list", "lists")),
        counted_step(
            session,
            PriceLevel,
            firm_id,
            "price-levels",
            ("level", "levels"),
            PriceLevel.is_active.is_(True),
        ),
        _promotions_step(session, firm_id),
        _loyalty_step(session, firm_id),
    ]


__all__ = ["pricing_section"]
