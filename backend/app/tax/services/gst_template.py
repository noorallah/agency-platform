"""The Indian GST template: a firm's whole tax setup in one call.

Every tax table is per firm, so a firm that has just been created has no tax
system, no components, no profiles and no rules, and every line it prices is
priced with no tax. Building that by hand is five screens before a sale can be
billed. This is what the demo firms are built with, moved out of
``scripts/seed_tax_sample_data.py`` on 2026-09-08 so the product can offer it
-- ``POST /api/v1/firms/{id}/apply-tax-template`` and the Firms setup panel --
and the script now calls it.

It is a **starting point**, editable afterwards on the tax screens like
anything else: one GST system with CGST, SGST, IGST and CESS; the 0, 5, 12
and 18 percent slabs as local and interstate profiles plus an exempt one; and
the six rules that switch a local slab to its interstate twin, zero-rate an
export, keep exempt goods exempt and allow input credit on purchases. The
country India is created in the store if the store has none, because a tax
system belongs to a country and a new dedicated store has no geography at all.

Idempotent: a firm that already holds a GST system gets nothing, which is what
lets the same action be the repair.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sales.models.territory import GeoCountry
from app.sales.schemas import GeoCountryWrite
from app.sales.services.territory_service import SalesTerritoryService
from app.tax.models import TaxComponent, TaxProfile, TaxSystem
from app.tax.schemas import (
    TaxComponentWrite,
    TaxCountryMappingWrite,
    TaxProfileComponentInput,
    TaxProfileWrite,
    TaxRuleActionType,
    TaxRuleActionWrite,
    TaxRuleConditionOperator,
    TaxRuleConditionWrite,
    TaxRuleWrite,
    TaxSettingsWrite,
    TaxStatus,
    TaxSystemWrite,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService

#: The one template offered today. A key rather than a bare boolean so a
#: second country's template is a new entry and not a new endpoint.
INDIA_GST = "IN_GST"

#: When GST came into force; every seeded row is effective from here.
_GST_EFFECTIVE_FROM = date(2017, 7, 1)

_COMPONENTS: tuple[tuple[str, str, bool], ...] = (
    ("CGST", "Central GST", True),
    ("SGST", "State GST", True),
    ("IGST", "Integrated GST", True),
    ("CESS", "Compensation Cess", False),
)

_PROFILES: tuple[tuple[str, str, list[tuple[str, Decimal]]], ...] = (
    ("GST_0", "GST 0%", [("IGST", Decimal("0"))]),
    (
        "GST_5_LOCAL",
        "GST 5% Local",
        [("CGST", Decimal("2.5")), ("SGST", Decimal("2.5"))],
    ),
    ("GST_5_INTERSTATE", "GST 5% Interstate", [("IGST", Decimal("5"))]),
    ("GST_12_LOCAL", "GST 12% Local", [("CGST", Decimal("6")), ("SGST", Decimal("6"))]),
    ("GST_12_INTERSTATE", "GST 12% Interstate", [("IGST", Decimal("12"))]),
    ("GST_18_LOCAL", "GST 18% Local", [("CGST", Decimal("9")), ("SGST", Decimal("9"))]),
    ("GST_18_INTERSTATE", "GST 18% Interstate", [("IGST", Decimal("18"))]),
    ("EXEMPT", "Exempt", []),
)


def firm_has_tax_system(session: Session, firm_id: UUID) -> bool:
    """Whether the firm already holds any live tax system."""
    return (
        session.scalar(
            select(TaxSystem.id).where(
                TaxSystem.firm_id == firm_id, TaxSystem.is_deleted.is_(False)
            )
        )
        is not None
    )


def apply_india_gst_template(
    session: Session, *, firm_id: UUID, actor_id: UUID
) -> dict[str, int]:
    """Give the firm the Indian GST setup, and return what was created.

    Args:
        session: A session bound to the firm's store.
        firm_id: The firm.
        actor_id: Who the rows are attributed to.

    Returns:
        Counts of ``countries``, ``systems``, ``components``, ``profiles`` and
        ``rules`` created -- all zero when the firm already had a tax system,
        so a caller can report a no-op honestly.

    """
    created = {"countries": 0, "systems": 0, "components": 0, "profiles": 0, "rules": 0}
    if firm_has_tax_system(session, firm_id):
        return created

    country_id = session.scalar(
        select(GeoCountry.id).where(GeoCountry.code == "IN")
    ) or session.scalar(select(GeoCountry.id).where(GeoCountry.name == "India"))
    if country_id is None:
        country_id = (
            SalesTerritoryService(session)
            .create_country(
                GeoCountryWrite(
                    code="IN",
                    name="India",
                    iso2="IN",
                    iso3="IND",
                    phone_code="91",
                    is_active=True,
                ),
                actor_id=actor_id,
            )
            .id
        )
        created["countries"] += 1

    framework = TaxFrameworkService(session)
    rules = TaxRuleService(session)
    framework.update_settings(
        TaxSettingsWrite(
            primary_label="GST",
            component_label="Component",
            profile_label="Tax Profile",
            report_label="GST Report",
            allow_mixed_historical=True,
            additional_settings={"template": INDIA_GST, "default_country_code": "IN"},
        ),
        firm_scope=firm_id,
        actor_id=actor_id,
    )
    system = framework.create_system(
        TaxSystemWrite(
            country_id=country_id,
            business_profile_id=None,
            code="GST",
            name="Goods and Services Tax",
            display_name="GST",
            description="Indian GST, from the platform template.",
            status=TaxStatus.ACTIVE,
            display_order=10,
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    created["systems"] += 1

    components: dict[str, TaxComponent] = {}
    for order, (code, name, recoverable) in enumerate(_COMPONENTS, start=1):
        components[code] = framework.create_component(
            TaxComponentWrite(
                tax_system_id=system.id,
                code=code,
                name=name,
                label=code,
                short_label=code,
                display_order=order,
                calculation_order=order,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=recoverable,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        created["components"] += 1

    framework.create_country_mapping(
        TaxCountryMappingWrite(
            country_id=country_id,
            business_profile_id=None,
            tax_system_id=system.id,
            status=TaxStatus.ACTIVE,
            is_default=True,
            effective_from=_GST_EFFECTIVE_FROM,
            effective_to=None,
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )

    profiles: dict[str, TaxProfile] = {}
    for order, (code, name, rows) in enumerate(_PROFILES, start=1):
        profiles[code] = framework.create_profile(
            TaxProfileWrite(
                tax_system_id=system.id,
                business_profile_id=None,
                code=code,
                name=name,
                label=name,
                description=f"{name}, from the platform template.",
                status=TaxStatus.ACTIVE,
                display_order=order,
                is_historical=False,
                effective_from=_GST_EFFECTIVE_FROM,
                effective_to=None,
                components=[
                    TaxProfileComponentInput(
                        tax_component_id=components[component_code].id,
                        label=component_code,
                        short_label=component_code,
                        calculation_order=index,
                        percentage=percentage,
                        included_in_price=False,
                        recoverable=True,
                    )
                    for index, (component_code, percentage) in enumerate(rows, start=1)
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        created["profiles"] += 1

    created["rules"] = _create_rules(rules, firm_id, actor_id, country_id, profiles)
    session.flush()
    return created


def _interstate_rule(
    code: str, slab: int, priority: int, profiles: dict[str, TaxProfile]
) -> tuple[
    str,
    str,
    int,
    list[tuple[str, TaxRuleConditionOperator, str]],
    list[TaxRuleActionWrite],
]:
    """One rule switching a local slab to its interstate twin."""
    return (
        code,
        f"Interstate sale switches {slab} percent GST to IGST",
        priority,
        [
            ("transaction_type", TaxRuleConditionOperator.EQUALS, "SALES_INTERSTATE"),
            (
                "tax_profile_id",
                TaxRuleConditionOperator.EQUALS,
                str(profiles[f"GST_{slab}_LOCAL"].id),
            ),
        ],
        [
            TaxRuleActionWrite(
                sequence=1,
                action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                target_tax_profile_id=profiles[f"GST_{slab}_INTERSTATE"].id,
            )
        ],
    )


def _create_rules(
    rules: TaxRuleService,
    firm_id: UUID,
    actor_id: UUID,
    country_id: UUID,
    profiles: dict[str, TaxProfile],
) -> int:
    """Create the six rules and return how many."""
    definitions = (
        (
            "EXPORT_ZERO",
            "Export supplies are zero rated",
            1,
            [("transaction_type", TaxRuleConditionOperator.EQUALS, "EXPORT")],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_0"].id,
                ),
                TaxRuleActionWrite(
                    sequence=2, action_type=TaxRuleActionType.ZERO_RATED
                ),
            ],
        ),
        _interstate_rule("INTERSTATE_GST_5", 5, 10, profiles),
        _interstate_rule("INTERSTATE_GST_12", 12, 11, profiles),
        _interstate_rule("INTERSTATE_GST_18", 18, 12, profiles),
        (
            "EXEMPT_PROFILE",
            "Exempt products remain exempt",
            20,
            [
                (
                    "tax_profile_id",
                    TaxRuleConditionOperator.EQUALS,
                    str(profiles["EXEMPT"].id),
                )
            ],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.EXEMPT_TAX)],
        ),
        (
            "PURCHASE_INPUT_CREDIT",
            "Purchase transactions allow input credit",
            30,
            [("transaction_type", TaxRuleConditionOperator.EQUALS, "PURCHASE")],
            [
                TaxRuleActionWrite(
                    sequence=1, action_type=TaxRuleActionType.INPUT_CREDIT_ALLOWED
                )
            ],
        ),
    )
    for code, name, priority, conditions, actions in definitions:
        rules.create_rule(
            TaxRuleWrite(
                country_id=country_id,
                business_profile_id=None,
                tax_profile_id=None,
                code=code,
                name=name,
                description=f"{name}, from the platform template.",
                priority=priority,
                status=TaxStatus.ACTIVE,
                effective_from=_GST_EFFECTIVE_FROM,
                effective_to=None,
                conditions=[
                    TaxRuleConditionWrite(
                        sequence=index,
                        field_key=field_key,
                        operator=operator,
                        value_text=value_text,
                        value_number=None,
                        value_date=None,
                        value_boolean=None,
                        value_json=None,
                    )
                    for index, (field_key, operator, value_text) in enumerate(
                        conditions, start=1
                    )
                ],
                actions=actions,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
    return len(definitions)
