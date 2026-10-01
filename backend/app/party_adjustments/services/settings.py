"""A firm's limits on clearing a balance without money.

Read by the party adjustment service (its approval threshold) and by receipts
and payments (the rounding limit), so it imports only this module's models.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.party_adjustments.models import (
    DEFAULT_APPROVAL_THRESHOLD,
    DEFAULT_ROUNDING_LIMIT,
    PartyAdjustmentSettings,
)


@dataclass(frozen=True, slots=True)
class AdjustmentLimits:
    """The two limits, with the firm's row or the defaults behind them."""

    approval_threshold: Decimal
    rounding_limit: Decimal
    is_default: bool


def adjustment_limits(session: Session, firm_id: UUID) -> AdjustmentLimits:
    """Return the firm's limits, or the defaults where it has set none."""
    row = _settings_row(session, firm_id)
    if row is None:
        return AdjustmentLimits(
            approval_threshold=DEFAULT_APPROVAL_THRESHOLD,
            rounding_limit=DEFAULT_ROUNDING_LIMIT,
            is_default=True,
        )
    return AdjustmentLimits(
        approval_threshold=Decimal(str(row.approval_threshold)),
        rounding_limit=Decimal(str(row.rounding_limit)),
        is_default=False,
    )


def stage_adjustment_limits(
    session: Session,
    firm_id: UUID,
    *,
    approval_threshold: Decimal,
    rounding_limit: Decimal,
    actor_id: UUID,
) -> AdjustmentLimits:
    """Write the firm's limits and audit the change; the caller commits."""
    row = _settings_row(session, firm_id)
    before: dict[str, object] | None = None
    if row is None:
        row = PartyAdjustmentSettings(firm_id=firm_id, created_by=actor_id)
        session.add(row)
    else:
        before = {
            "approval_threshold": str(row.approval_threshold),
            "rounding_limit": str(row.rounding_limit),
        }
    row.approval_threshold = approval_threshold
    row.rounding_limit = rounding_limit
    row.updated_by = actor_id
    session.flush()
    record_audit(
        session,
        action="party_adjustment.settings_updated",
        entity_type="party_adjustment_settings",
        entity_id=row.id,
        actor_id=actor_id,
        firm_id=firm_id,
        before_data=before,
        after_data={
            "approval_threshold": str(approval_threshold),
            "rounding_limit": str(rounding_limit),
        },
    )
    return adjustment_limits(session, firm_id)


def _settings_row(session: Session, firm_id: UUID) -> PartyAdjustmentSettings | None:
    """Return the firm's live settings row, if it has one."""
    return session.scalar(
        select(PartyAdjustmentSettings).where(
            PartyAdjustmentSettings.firm_id == firm_id,
            PartyAdjustmentSettings.is_deleted.is_(False),
        )
    )
