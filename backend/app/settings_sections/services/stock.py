"""The Stock subject: how a firm's stock is adjusted and sold by batch.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: every step has a default the server works with, so each is OPTIONAL.
Inventory Settings is no step: that screen holds the signed-in person's own
preferences, not the firm's, so the desktop shows it apart as theirs.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchSaleSettings
from app.inventory.models.adjustment_approval import RoleStockAdjustmentLimit
from app.inventory.models.adjustment_reason import StockAdjustmentReason
from app.inventory.services.adjustment_reasons import SYSTEM_REASONS
from app.settings_sections.services.steps import (
    OPTIONAL,
    SettingsStep,
    counted,
    counted_step,
    live_count,
    saved_step,
)


def _adjustment_reasons_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the firm's own reasons beside the built-in ones.

    The built-in reasons are written the first time the list is read, so a
    firm that never opened it holds none yet and still has every one of them:
    they are counted from the code, not from the store.
    """
    own = live_count(
        session,
        StockAdjustmentReason,
        firm_id,
        StockAdjustmentReason.is_system.is_(False),
        StockAdjustmentReason.is_active.is_(True),
    )
    built_in = f"{len(SYSTEM_REASONS)} built in"
    detail = f"{built_in}, {counted(own, 'own', 'own')}" if own else built_in
    return SettingsStep("adjustment-reasons", OPTIONAL, detail)


def stock_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the three steps of the Stock subject, in set-up order."""
    return [
        _adjustment_reasons_step(session, firm_id),
        counted_step(
            session,
            RoleStockAdjustmentLimit,
            firm_id,
            "adjustment-limits",
            ("role limit", "role limits"),
        ),
        saved_step(session, BatchSaleSettings, firm_id, "batch-rules"),
    ]


__all__ = ["stock_section"]
