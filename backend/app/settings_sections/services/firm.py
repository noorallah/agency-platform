"""The Firm subject: the steps that shape how the whole firm works.

Every reader selects and nothing else, like the Tax subject's.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approvals.models import ApprovalRule
from app.business.models.framework import (
    AttributeDefinition,
    BusinessProfile,
    CategoryAttributeRule,
    FirmBusinessProfile,
)
from app.document_framework.models.document_framework import DocumentNumberingRule
from app.finance.models.finance import FinancialYear
from app.messaging.models.messaging import MessagingSettings
from app.products.models.goods_type import FirmGoodsType
from app.settings_sections.services.steps import (
    DONE,
    OPTIONAL,
    TODO,
    SettingsStep,
    counted,
    counted_step,
    live_count,
    switch_step,
)


def profile_step(
    session: Session, firm_id: UUID, code: str = "firm-profile"
) -> SettingsStep:
    """Name the business profile assigned to the firm, if one is.

    Shared with the Business profile subject, whose first step asks the same
    question under its own code.
    """
    name = session.scalar(
        select(func.coalesce(BusinessProfile.name, BusinessProfile.code))
        .join(
            FirmBusinessProfile,
            FirmBusinessProfile.business_profile_id == BusinessProfile.id,
        )
        .where(
            FirmBusinessProfile.firm_id == firm_id,
            FirmBusinessProfile.is_deleted.is_(False),
            FirmBusinessProfile.is_active.is_(True),
        )
    )
    return SettingsStep(
        code,
        OPTIONAL,
        name if name else "Not chosen: the firm runs as General",
    )


def _financial_years_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm has a year open to post into.

    A year is closed by locking it, so an open year is a live, active one
    that is not locked.
    """
    open_codes = session.scalars(
        select(FinancialYear.code)
        .where(
            FinancialYear.firm_id == firm_id,
            FinancialYear.is_deleted.is_(False),
            FinancialYear.is_active.is_(True),
            FinancialYear.is_locked.is_(False),
        )
        .order_by(FinancialYear.starts_on)
    ).all()
    if not open_codes:
        return SettingsStep("financial-years", TODO, "None open: nothing can be posted")
    if len(open_codes) == 1:
        return SettingsStep("financial-years", DONE, f"{open_codes[0]} open")
    return SettingsStep(
        "financial-years", DONE, counted(len(open_codes), "year open", "years open")
    )


def _numbering_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the firm's own numbering rules; without one a type numbers itself."""
    count = live_count(session, DocumentNumberingRule, firm_id)
    return SettingsStep(
        "numbering-series",
        OPTIONAL,
        counted(count, "series", "series") if count else "As each document comes",
    )


def firm_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the eight steps of the Firm subject, in set-up order."""
    return [
        profile_step(session, firm_id),
        _financial_years_step(session, firm_id),
        _numbering_step(session, firm_id),
        counted_step(
            session, FirmGoodsType, firm_id, "goods-types", ("in use", "in use")
        ),
        # Only the firm's own: a definition with no firm is the platform's.
        counted_step(
            session,
            AttributeDefinition,
            firm_id,
            "custom-fields",
            ("field", "fields"),
            AttributeDefinition.is_active.is_(True),
        ),
        counted_step(
            session,
            CategoryAttributeRule,
            firm_id,
            "custom-field-rules",
            ("rule", "rules"),
        ),
        switch_step(session, MessagingSettings, firm_id, "messaging"),
        counted_step(
            session,
            ApprovalRule,
            firm_id,
            "approval-levels",
            ("level", "levels"),
            ApprovalRule.is_active.is_(True),
        ),
    ]


__all__ = ["firm_section", "profile_step"]
