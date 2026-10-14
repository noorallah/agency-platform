"""The Stock subject: how a firm's stock is adjusted and sold by batch.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: every step has a default the server works with, so each is OPTIONAL.
Inventory Settings is no step: that screen holds the signed-in person's own
preferences, not the firm's, so the desktop shows it apart as theirs.
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


def _costing_method_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say how the firm costs its stock: Average, or by lot since a day.

    A firm with no ``stock_lot_settings`` row is on Average (L2 step 9).
    """
    row = session.execute(
        select(StockLotSettings.costing_method, StockLotSettings.switched_on).where(
            StockLotSettings.firm_id == firm_id,
            StockLotSettings.is_deleted.is_(False),
        )
    ).first()
    if row is None or row[0] != "BY_LOT":
        return SettingsStep("costing-method", OPTIONAL, "Average")
    since = f" since {row[1].isoformat()}" if row[1] is not None else ""
    return SettingsStep("costing-method", OPTIONAL, f"By lot{since}")


def stock_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the four steps of the Stock subject, in set-up order."""
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
        _costing_method_step(session, firm_id),
    ]


__all__ = ["stock_section"]
