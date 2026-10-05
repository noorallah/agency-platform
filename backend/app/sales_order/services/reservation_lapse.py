"""Stock held for an order that never ships lapses (STK-12, decision A115).

A firm that sets ``reservation_lapse_days`` has the stock held by any
approved order older than that, with a hold still on it, released on the
server's timer -- the messaging worker's pass runs this too. The order is
flagged, not cancelled: it can still be dispatched from free stock, or
reserved again. Off by default.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_today
from app.sales_order.models import SalesOrder, SalesOrderLine

logger = logging.getLogger(__name__)

#: Orders that can hold stock.
_HOLDING = ("APPROVED", "PARTIALLY_DELIVERED")
#: Recorded as the actor of a lapse nobody performed.
SYSTEM_ACTOR = UUID("00000000-0000-0000-0000-000000000000")


@dataclass
class LapseReport:
    """What one pass released."""

    orders: int = 0
    errors: list[str] = field(default_factory=list)


def lapse_firm(session: Session, firm_id: UUID, *, on: date | None = None) -> int:
    """Release the firm's stale holds and commit; return how many orders."""
    from app.sales_order.services.sales_order_service import SalesOrderService
    from app.sales_order.services.workflow_settings_service import (
        SalesWorkflowService,
    )

    days = (
        SalesWorkflowService(session).settings_response(firm_id).reservation_lapse_days
    )
    if not days:
        return 0
    cutoff = (on or firm_today(session, firm_id)) - timedelta(days=days)
    orders = list(
        session.scalars(
            select(SalesOrder).where(
                SalesOrder.firm_id == firm_id,
                SalesOrder.status.in_(_HOLDING),
                SalesOrder.is_deleted.is_(False),
                SalesOrder.reservation_lapsed_at.is_(None),
                SalesOrder.order_date <= cutoff,
                exists().where(
                    SalesOrderLine.sales_order_id == SalesOrder.id,
                    SalesOrderLine.reserved_quantity > 0,
                ),
            )
        ).all()
    )
    service = SalesOrderService(session)
    for order in orders:
        service.lapse_reservation(order, actor_id=SYSTEM_ACTOR, days=days)
    session.commit()
    return len(orders)


def lapse_every_firm(
    firm_ids: Callable[[], list[UUID]],
    open_store: Callable[[UUID], object],
) -> LapseReport:
    """Run one lapse pass over every firm, reporting a store it could not read."""
    report = LapseReport()
    for firm_id in firm_ids():
        try:
            with open_store(firm_id) as session:  # type: ignore[attr-defined]
                report.orders += lapse_firm(session, firm_id)
        except Exception as error:  # noqa: BLE001 - one firm never stops the rest
            logger.warning("reservation lapse failed for firm %s: %s", firm_id, error)
            report.errors.append(f"{firm_id}: {type(error).__name__}: {error}")
    return report
