"""Run the loyalty expiry sweep over every firm, each in its own store.

Points past their date are worth nothing at the counter whether or not the
sweep has run -- the balance and a redemption leave them out (D-PRC-3) -- but
their cost stays in Loyalty Payable until a lapse releases it, and the only
thing that wrote a lapse was a route somebody had to remember to call. This is
the same sweep for an installed copy, which has no interpreter to hand a
script to: ``agency-server loyalty-expire``, for the operator or for whatever
schedules it.

Each firm is reached through its own store, as the messaging pass reaches it,
because a firm's ledger lives there; a store that cannot be read is reported
and never stops the rest.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.loyalty.services.loyalty_service import LoyaltyService

logger = logging.getLogger(__name__)

#: Who a lapse written by the sweep is attributed to when nobody ran it by
#: hand: the same nil actor an unattended reservation lapse carries.
SYSTEM_ACTOR = UUID("00000000-0000-0000-0000-000000000000")

StoreOpener = Callable[[UUID], AbstractContextManager[Session]]


@dataclass(slots=True)
class SweepReport:
    """What one pass lapsed, firm by firm, and the stores it could not read."""

    lapsed: dict[UUID, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def sweep_every_firm(
    firm_ids: Callable[[], list[UUID]], open_store: StoreOpener
) -> SweepReport:
    """Lapse what has run out of time in every firm; report each firm.

    Safe to run twice: each lapse names the batch it takes, so a second pass
    finds nothing left of it. A firm that runs no scheme has no batches and
    reports zero.
    """
    report = SweepReport()
    for firm_id in firm_ids():
        try:
            with open_store(firm_id) as session:
                report.lapsed[firm_id] = LoyaltyService(session).expire(
                    firm_scope=firm_id, actor_id=SYSTEM_ACTOR
                )
        except Exception as error:  # noqa: BLE001 - one firm never stops the rest
            logger.warning("loyalty sweep failed for firm %s: %s", firm_id, error)
            report.errors.append(f"{firm_id}: {type(error).__name__}: {error}")
    return report
