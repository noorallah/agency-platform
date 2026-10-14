"""The Party lists subject: the lists a firm sorts its customers and suppliers by.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: a customer needs no group, a supplier no category or type, and a firm
with no licence types has nothing for the licence check to ask about -- with
no saved policy it warns and never blocks. So each step is OPTIONAL.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.customers.models.customer import CustomerGroup
from app.settings_sections.services.steps import (
    SettingsStep,
    counted_step,
    saved_step,
)
from app.trade_licences.models.trade_licence import (
    TradeLicenceSettings,
    TradeLicenceType,
)
from app.vendors.models.vendor import VendorCategory, VendorType


def party_lists_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the five steps of the Party lists subject, in set-up order."""
    return [
        counted_step(
            session,
            CustomerGroup,
            firm_id,
            "customer-groups",
            ("group", "groups"),
            CustomerGroup.is_active.is_(True),
        ),
        counted_step(
            session,
            VendorCategory,
            firm_id,
            "vendor-categories",
            ("category", "categories"),
            VendorCategory.is_active.is_(True),
        ),
        counted_step(
            session,
            VendorType,
            firm_id,
            "vendor-types",
            ("type", "types"),
            VendorType.is_active.is_(True),
        ),
        counted_step(
            session,
            TradeLicenceType,
            firm_id,
            "licence-types",
            ("licence type", "licence types"),
            TradeLicenceType.is_active.is_(True),
        ),
        saved_step(session, TradeLicenceSettings, firm_id, "licence-check-settings"),
    ]


__all__ = ["party_lists_section"]
