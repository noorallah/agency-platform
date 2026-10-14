"""The two reserved price levels of a firm costing by lot (row L3, step 3).

`docs/design/LOT_MARGINS_DESIGN.md` section 3.5. A firm costing by lot has
two reserved levels, **Retail** and **Wholesale**, each naming the customer's
kind it stands for in ``price_levels.trade_class``. They are the bill's one
switch: the document's level decides which of the lot's two prices a line
takes (Retail its PTR, Wholesale its PTS), and a customer with no level of his
own or his group's starts on the level of his kind.

They may be renamed and reordered, never deleted, made inactive or given
another class. A firm on Average has neither, and prices exactly as before.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.pricing.models import PriceLevel


@dataclass(frozen=True, slots=True)
class TradeLevelSpec:
    """One reserved level: its code, its name and the class it stands for."""

    code: str
    name: str
    trade_class: str
    sort_order: int


#: Retail takes the lot's PTR, Wholesale its PTS (design section 3.1).
TRADE_LEVELS = (
    TradeLevelSpec(code="RETAIL", name="Retail", trade_class="RETAILER", sort_order=1),
    TradeLevelSpec(
        code="WHOLESALE", name="Wholesale", trade_class="STOCKIST", sort_order=2
    ),
)


def ensure_trade_levels(session: Session, firm_id: UUID, actor_id: UUID) -> bool:
    """Make the firm's two reserved levels where they are missing; flush only.

    A level already carrying the class is the reserved one, whatever it was
    renamed to. Otherwise a live level of the reserved code is adopted --
    a firm that kept a level coded RETAIL kept it for this -- and made active;
    else a new one is made. Returns whether anything was written, so a read
    that called this knows to commit.
    """
    live = list(
        session.scalars(
            select(PriceLevel).where(
                PriceLevel.firm_id == firm_id, PriceLevel.is_deleted.is_(False)
            )
        ).all()
    )
    classed = {row.trade_class for row in live if row.trade_class}
    wrote = False
    for spec in TRADE_LEVELS:
        if spec.trade_class in classed:
            continue
        row = next((level for level in live if level.code == spec.code), None)
        if row is None:
            row = PriceLevel(
                firm_id=firm_id,
                code=spec.code,
                name=spec.name,
                sort_order=spec.sort_order,
                is_active=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(row)
        row.trade_class = spec.trade_class
        row.is_active = True
        row.updated_by = actor_id
        session.flush()
        record_audit(
            session,
            action="price_level.reserved",
            entity_type="price_level",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "code": row.code,
                "name": row.name,
                "trade_class": row.trade_class,
            },
        )
        wrote = True
    return wrote


def trade_level_for(
    session: Session, firm_id: UUID, trade_class: str | None
) -> UUID | None:
    """Return the reserved level standing for this kind of customer, if any."""
    if trade_class not in ("RETAILER", "STOCKIST"):
        return None
    level_id: UUID | None = session.scalar(
        select(PriceLevel.id).where(
            PriceLevel.firm_id == firm_id,
            PriceLevel.trade_class == trade_class,
            PriceLevel.is_deleted.is_(False),
            PriceLevel.is_active.is_(True),
        )
    )
    return level_id


__all__ = ["TRADE_LEVELS", "TradeLevelSpec", "ensure_trade_levels", "trade_level_for"]
