"""The steps of each Settings subject, read from the firm's own records.

One subject is one function, ``(session, firm_id) -> list[SettingsStep]``, and
``SECTIONS`` is the registry of them: a new subject is a new function and a new
entry, never a new endpoint.

**Nothing here writes.** Several of the settings services create their row on
first read or answer defaults for a firm that never saved; this reads the
models directly so that opening a screen can never leave a row behind, and so
"never saved" stays distinguishable from "saved as the default".
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.finance.models.tds_194q import Tds194QSettings
from app.tax.models import GstComplianceSettings, TaxProfile, TaxRule, TaxSettings
from app.tax.services.gst_template import (
    TEMPLATE_RULE_CODES,
    template_profile_codes,
)

DONE: Literal["DONE"] = "DONE"
TODO: Literal["TODO"] = "TODO"
OPTIONAL: Literal["OPTIONAL"] = "OPTIONAL"

_FROM_TEMPLATE = ", from the GST template"
_NONE_YET = "None yet"


@dataclass(frozen=True, slots=True)
class SettingsStep:
    """One set-up step and where the firm stands on it."""

    code: str
    state: Literal["DONE", "TODO", "OPTIONAL"]
    detail: str


SectionReader = Callable[[Session, UUID], list[SettingsStep]]


def _counted(count: int, singular: str, plural: str) -> str:
    """Return ``count`` with the noun that agrees with it."""
    return f"{count} {singular if count == 1 else plural}"


def _profiles_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm holds any live tax profile."""
    live = (TaxProfile.firm_id == firm_id, TaxProfile.is_deleted.is_(False))
    count = session.scalar(select(func.count()).select_from(TaxProfile).where(*live))
    if not count:
        return SettingsStep("rates-and-profiles", TODO, _NONE_YET)
    # A profile is versioned under its group code, and a rate change mints a
    # new code beneath it, so the template's slabs are looked for by group.
    name = func.coalesce(TaxProfile.group_code, TaxProfile.code)
    wanted = template_profile_codes()
    held = session.scalar(
        select(func.count(func.distinct(name))).where(*live, name.in_(wanted))
    )
    detail = _counted(count, "profile", "profiles")
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
        return SettingsStep("tax-rules", TODO, _NONE_YET)
    held = session.scalar(
        select(func.count(func.distinct(TaxRule.code))).where(
            *active, TaxRule.code.in_(TEMPLATE_RULE_CODES)
        )
    )
    detail = _counted(count, "active rule", "active rules")
    if held == len(TEMPLATE_RULE_CODES):
        detail += _FROM_TEMPLATE
    return SettingsStep("tax-rules", DONE, detail)


def _tax_settings_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say whether the firm has saved tax settings of its own."""
    saved = session.scalar(
        select(func.count())
        .select_from(TaxSettings)
        .where(TaxSettings.firm_id == firm_id, TaxSettings.is_deleted.is_(False))
    )
    return SettingsStep(
        "tax-settings",
        OPTIONAL,
        "Set for this firm" if saved else "Left as it comes",
    )


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
    enabled = session.scalar(
        select(Tds194QSettings.is_enabled).where(
            Tds194QSettings.firm_id == firm_id,
            Tds194QSettings.is_deleted.is_(False),
        )
    )
    return SettingsStep("tds-purchases", OPTIONAL, "On" if enabled else "Off")


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
SECTIONS: dict[str, SectionReader] = {"tax": tax_section}


def section_state(session: Session, firm_id: UUID, section: str) -> list[SettingsStep]:
    """Return the steps of one Settings subject for a firm.

    Raises:
        ResourceNotFoundError: If no subject has this code.

    """
    reader = SECTIONS.get(section)
    if reader is None:
        raise ResourceNotFoundError("Settings section not found.")
    return reader(session, firm_id)


__all__ = ["SECTIONS", "SettingsStep", "section_state", "tax_section"]
