"""The steps of each Settings subject, read from the firm's own records.

One subject is one function, ``(session, firm_id) -> list[SettingsStep]``, and
``SECTIONS`` is the registry of them: a new subject is a new function and a new
entry, never a new endpoint.

**Nothing here writes.** Several of the settings services create their row on
first read or answer defaults for a firm that never saved; this reads the
models directly so that opening a screen can never leave a row behind, and so
"never saved" stays distinguishable from "saved as the default".
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.finance.models.tds_194q import Tds194QSettings
from app.settings_sections.services.account_structure import (
    account_structure_section,
)
from app.settings_sections.services.business_profile import (
    business_profile_section,
)
from app.settings_sections.services.buying import buying_section
from app.settings_sections.services.firm import firm_section
from app.settings_sections.services.item_lists import item_lists_section
from app.settings_sections.services.locations import locations_section
from app.settings_sections.services.party_lists import party_lists_section
from app.settings_sections.services.pricing import pricing_section
from app.settings_sections.services.selling import selling_section
from app.settings_sections.services.steps import (
    DONE,
    NONE_YET,
    OPTIONAL,
    TODO,
    SectionReader,
    SettingsStep,
    counted,
    saved_step,
    switch_step,
)
from app.settings_sections.services.stock import stock_section
from app.settings_sections.services.territories import territories_section
from app.tax.models import GstComplianceSettings, TaxProfile, TaxRule, TaxSettings
from app.tax.services.gst_template import (
    TEMPLATE_RULE_CODES,
    template_profile_codes,
)

_FROM_TEMPLATE = ", from the GST template"


def _profiles_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm holds any live tax profile."""
    live = (TaxProfile.firm_id == firm_id, TaxProfile.is_deleted.is_(False))
    count = session.scalar(select(func.count()).select_from(TaxProfile).where(*live))
    if not count:
        return SettingsStep("rates-and-profiles", TODO, NONE_YET)
    # A profile is versioned under its group code, and a rate change mints a
    # new code beneath it, so the template's slabs are looked for by group.
    name = func.coalesce(TaxProfile.group_code, TaxProfile.code)
    wanted = template_profile_codes()
    held = session.scalar(
        select(func.count(func.distinct(name))).where(*live, name.in_(wanted))
    )
    detail = counted(count, "profile", "profiles")
    if held == len(wanted):
        detail += _FROM_TEMPLATE
    return SettingsStep("rates-and-profiles", DONE, detail)


def _rules_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm holds any live rule that is switched on."""
    active = (
        TaxRule.firm_id == firm_id,
        TaxRule.is_deleted.is_(False),
        TaxRule.status == "ACTIVE",
    )
    count = session.scalar(select(func.count()).select_from(TaxRule).where(*active))
    if not count:
        return SettingsStep("tax-rules", TODO, NONE_YET)
    held = session.scalar(
        select(func.count(func.distinct(TaxRule.code))).where(
            *active, TaxRule.code.in_(TEMPLATE_RULE_CODES)
        )
    )
    detail = counted(count, "active rule", "active rules")
    if held == len(TEMPLATE_RULE_CODES):
        detail += _FROM_TEMPLATE
    return SettingsStep("tax-rules", DONE, detail)


def _tax_settings_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm has saved tax settings of its own."""
    return saved_step(session, TaxSettings, firm_id, "tax-settings")


def _gst_documents_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say which GST documents the firm has switched on.

    ``gst_compliance_settings`` carries one switch of this kind: the date from
    which the firm must e-invoice, null where it does not have to. An e-way
    bill has no switch there -- only ``eway_bill_limit``, which applies to
    every firm, saved or not -- so it is never named as on or off.
    """
    einvoice_from = session.scalar(
        select(GstComplianceSettings.einvoice_applicable_from).where(
            GstComplianceSettings.firm_id == firm_id,
            GstComplianceSettings.is_deleted.is_(False),
        )
    )
    return SettingsStep(
        "gst-documents", OPTIONAL, "Off" if einvoice_from is None else "E-invoice on"
    )


def _tds_purchases_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether TDS on the purchase of goods (194Q) is switched on."""
    return switch_step(session, Tds194QSettings, firm_id, "tds-purchases")


def tax_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the five steps of the Tax subject, in set-up order."""
    return [
        _profiles_step(session, firm_id),
        _rules_step(session, firm_id),
        _tax_settings_step(session, firm_id),
        _gst_documents_step(session, firm_id),
        _tds_purchases_step(session, firm_id),
    ]


#: Every Settings subject that can say where a firm stands, by its code.
SECTIONS: dict[str, SectionReader] = {
    "tax": tax_section,
    "firm": firm_section,
    "selling": selling_section,
    "buying": buying_section,
    "stock": stock_section,
    "business-profile": business_profile_section,
    "pricing": pricing_section,
    "territories": territories_section,
    "account-structure": account_structure_section,
    "party-lists": party_lists_section,
    "item-lists": item_lists_section,
    "locations": locations_section,
}


def section_state(session: Session, firm_id: UUID, section: str) -> list[SettingsStep]:
    """Return the steps of one Settings subject for a firm.

    Raises:
        ResourceNotFoundError: If no subject has this code.

    """
    reader = SECTIONS.get(section)
    if reader is None:
        raise ResourceNotFoundError("Settings section not found.")
    return reader(session, firm_id)


__all__ = [
    "DONE",
    "OPTIONAL",
    "SECTIONS",
    "TODO",
    "SettingsStep",
    "account_structure_section",
    "business_profile_section",
    "buying_section",
    "firm_section",
    "item_lists_section",
    "locations_section",
    "party_lists_section",
    "pricing_section",
    "section_state",
    "selling_section",
    "stock_section",
    "tax_section",
    "territories_section",
]
