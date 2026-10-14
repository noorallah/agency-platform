"""The Selling subject: how a firm's sales are run and limited.

Every reader selects and nothing else, like the Tax subject's.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customers.models.customer import CreditControlSettings
from app.loyalty.models.loyalty import LoyaltySettings
from app.sales_order.models.sales_order import (
    PriceFloorSettings,
    RoleDiscountLimit,
    SalesWorkflowSettings,
)
from app.salesmen.models.salesman import Salesman
from app.settings_sections.services.steps import (
    DONE,
    NONE_YET,
    OPTIONAL,
    SAVED,
    TODO,
    SettingsStep,
    counted,
    counted_step,
    live_count,
    saved_step,
    switch_step,
)
from app.tcs.models.tcs import TcsSettings


def _salesmen_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the firm's active salesmen; owed only where a bill must name one."""
    required = session.scalar(
        select(SalesWorkflowSettings.salesman_required).where(
            SalesWorkflowSettings.firm_id == firm_id,
            SalesWorkflowSettings.is_deleted.is_(False),
        )
    )
    count = live_count(session, Salesman, firm_id, Salesman.is_active.is_(True))
    detail = counted(count, "salesman", "salesmen") if count else NONE_YET
    if not required:
        return SettingsStep("salesmen", OPTIONAL, detail)
    if not count:
        return SettingsStep("salesmen", TODO, "None yet: every bill must name one")
    return SettingsStep("salesmen", DONE, detail)


def _credit_control_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm has its own credit policy or takes the default."""
    saved = live_count(session, CreditControlSettings, firm_id)
    return SettingsStep(
        "credit-control",
        OPTIONAL,
        SAVED if saved else "Left as it comes: warns at 80%",
    )


def selling_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the seven steps of the Selling subject, in set-up order."""
    return [
        saved_step(session, SalesWorkflowSettings, firm_id, "sales-stages"),
        _salesmen_step(session, firm_id),
        _credit_control_step(session, firm_id),
        saved_step(session, PriceFloorSettings, firm_id, "price-floor"),
        counted_step(
            session,
            RoleDiscountLimit,
            firm_id,
            "discount-limits",
            ("role limit", "role limits"),
        ),
        switch_step(session, LoyaltySettings, firm_id, "loyalty-scheme"),
        switch_step(session, TcsSettings, firm_id, "tcs"),
    ]


__all__ = ["selling_section"]
