"""The Stock subject: how a firm's stock is costed, adjusted and sold by batch.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: every step has a default the server works with, so each is OPTIONAL.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchSaleSettings
from app.inventory.models.adjustment_approval import RoleStockAdjustmentLimit
from app.inventory.models.adjustment_reason import StockAdjustmentReason
from app.inventory.models.inventory import StockLotSettings
from app.inventory.services.adjustment_reasons import SYSTEM_REASONS
from app.settings_sections.services.steps import (
    OPTIONAL,
    SettingsStep,
    counted,
    counted_step,
    live_count,
    saved_step,
)


def _inventory_settings_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Name the firm's costing method; a firm that never chose is on Average."""
    method = session.scalar(
        select(StockLotSettings.costing_method).where(
            StockLotSettings.firm_id == firm_id,
            StockLotSettings.is_deleted.is_(False),
        )
    )
    if method is None:
        return SettingsStep(
            "inventory-settings", OPTIONAL, "Left as it comes: average cost"
        )
    return SettingsStep(
        "inventory-settings",
        OPTIONAL,
        "Costed by lot" if method == "BY_LOT" else "Average cost",
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
    """Return the four steps of the Stock subject, in set-up order."""
    return [
        _inventory_settings_step(session, firm_id),
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
