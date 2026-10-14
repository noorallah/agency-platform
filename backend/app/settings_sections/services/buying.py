"""The Buying subject: how a firm's purchases are run and limited.

Every reader selects and nothing else, like the Tax subject's.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.purchase.models.purchase import (
    PurchaseBudget,
    PurchaseWorkflowSettings,
    RolePurchaseApprovalLimit,
)
from app.settings_sections.services.steps import (
    SettingsStep,
    counted_step,
    saved_step,
)


def buying_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the three steps of the Buying subject, in set-up order."""
    return [
        saved_step(session, PurchaseWorkflowSettings, firm_id, "purchase-settings"),
        counted_step(
            session,
            RolePurchaseApprovalLimit,
            firm_id,
            "approval-limits",
            ("role limit", "role limits"),
        ),
        counted_step(
            session,
            PurchaseBudget,
            firm_id,
            "purchase-budgets",
            ("budget", "budgets"),
        ),
    ]


__all__ = ["buying_section"]
