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
the nine rules that switch a local slab to its interstate twin -- for a sale
to another state and for a purchase from one (D-CMP-14) -- zero-rate an
export, keep exempt goods exempt and allow input credit on purchases. The
country India is created in the store if the store has none, because a tax
system belongs to a country and a new dedicated store has no geography at all.

Idempotent: a firm that already holds a GST system gets nothing, which is what
lets the same action be the repair -- except the **reverse-charge set** (A29),
which is added by code to any firm whose GST system lacks it, so a firm set up
before it gets it from the same button.

**Reverse charge, ready-made and switched off (decision A29).** Two service
profiles -- *GTA under reverse charge* (5%) and *Legal services under reverse
charge* (18%) -- and four rules, a local and an interstate one for each, that
mark an inward document as reverse charge with its input credit allowed. The
rules are created **INACTIVE**: whether a firm buys from a goods transport
agency or an advocate, and at which rate the GTA charges, is the firm's to say,
so it assigns the profile to its freight or legal-fees item and activates the
rules. They outrank the interstate and input-credit rules, because evaluation
stops at the first match.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sales.models.territory import GeoCountry
from app.tax.models import TaxComponent, TaxProfile, TaxRule, TaxSystem
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
from app.tax.services.place_of_supply import (
    FOREIGN_STATE_CODE,
    PURCHASE_INTERSTATE,
    SALES_INTERSTATE,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService

#: The one template offered today. A key rather than a bare boolean so a
#: second country's template is a new entry and not a new endpoint.
INDIA_GST = "IN_GST"

#: The transaction types an inward document prices a local line as -- what
#: ``inward_transaction_type`` returns for a supplier in the firm's own state.
INWARD_DOCUMENT_TYPES: tuple[str, ...] = (
    "PURCHASE",
    "GOODS_RECEIPT",
    "PURCHASE_INVOICE",
    "PURCHASE_RETURN",
)

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

#: Service profiles bought under reverse charge (A29): (code, name, local
#: rows, the interstate twin's code).
_RCM_PROFILES: tuple[tuple[str, str, list[tuple[str, Decimal]], str], ...] = (
    (
        "RCM_GTA_5",
        "GTA under reverse charge 5%",
        [("CGST", Decimal("2.5")), ("SGST", Decimal("2.5"))],
        "GST_5_INTERSTATE",
    ),
    (
        "RCM_LEGAL_18",
        "Legal services under reverse charge 18%",
        [("CGST", Decimal("9")), ("SGST", Decimal("9"))],
        "GST_18_INTERSTATE",
    ),
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
        # Only the reverse-charge set, where it is missing (A29).
        framework = TaxFrameworkService(session)
        rules = TaxRuleService(session)
        with framework.staged(), rules.staged():
            profiles_added, rules_added = _ensure_reverse_charge(
                session, framework, rules, firm_id=firm_id, actor_id=actor_id
            )
            session.flush()
        created["profiles"] += profiles_added
        created["rules"] += rules_added
        return created

    framework = TaxFrameworkService(session)
    rules = TaxRuleService(session)
    # One transaction, committed by the caller. Every record used to commit on
    # its own, so a template refused part-way left a half-built tax system --
    # and the next press was a no-op, because the firm "already has a tax
    # system" (D-CMP-8). Staged, a failure takes all of it back, the country
    # included.
    with framework.staged(), rules.staged():
        country_id = session.scalar(
            select(GeoCountry.id).where(GeoCountry.code == "IN")
        ) or session.scalar(select(GeoCountry.id).where(GeoCountry.name == "India"))
        if country_id is None:
            country = GeoCountry(
                code="IN",
                name="India",
                iso2="IN",
                iso3="IND",
                phone_code="91",
                is_active=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(country)
            session.flush()
            country_id = country.id
            created["countries"] += 1

        framework.update_settings(
            TaxSettingsWrite(
                primary_label="GST",
                component_label="Component",
                profile_label="Tax Profile",
                report_label="GST Report",
                allow_mixed_historical=True,
                additional_settings={
                    "template": INDIA_GST,
                    "default_country_code": "IN",
                },
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
                        for index, (component_code, percentage) in enumerate(
                            rows, start=1
                        )
                    ],
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            created["profiles"] += 1

        created["rules"] = _create_rules(rules, firm_id, actor_id, country_id, profiles)
        session.flush()
        profiles_added, rules_added = _ensure_reverse_charge(
            session, framework, rules, firm_id=firm_id, actor_id=actor_id
        )
        created["profiles"] += profiles_added
        created["rules"] += rules_added
        session.flush()
    return created


def _ensure_reverse_charge(
    session: Session,
    framework: TaxFrameworkService,
    rules: TaxRuleService,
    *,
    firm_id: UUID,
    actor_id: UUID,
) -> tuple[int, int]:
    """Add the reverse-charge profiles and inactive rules a firm lacks (A29).

    Looked up by code, so it adds only what is missing and never touches a
    profile or rule the firm has since edited. Nothing where the firm has no
    template GST system to hang them on.

    Returns:
        How many profiles and rules were created.

    """
    system = session.scalar(
        select(TaxSystem).where(
            TaxSystem.firm_id == firm_id,
            TaxSystem.code == "GST",
            TaxSystem.is_deleted.is_(False),
        )
    )
    if system is None:
        return 0, 0
    components = {
        row.code: row
        for row in session.scalars(
            select(TaxComponent).where(
                TaxComponent.tax_system_id == system.id,
                TaxComponent.is_deleted.is_(False),
            )
        )
    }
    if not {"CGST", "SGST"} <= set(components):
        return 0, 0

    def profile(code: str) -> TaxProfile | None:
        """Return the firm's live profile with this code, its newest version."""
        return session.scalar(
            select(TaxProfile)
            .where(
                TaxProfile.firm_id == firm_id,
                TaxProfile.tax_system_id == system.id,
                TaxProfile.code == code,
                TaxProfile.is_deleted.is_(False),
            )
            .order_by(TaxProfile.created_at.desc())
        )

    profiles_added = rules_added = 0
    for order, (code, name, rows, interstate_code) in enumerate(
        _RCM_PROFILES, start=len(_PROFILES) + 1
    ):
        local = profile(code)
        if local is None and session.scalar(
            select(TaxProfile.id).where(
                TaxProfile.firm_id == firm_id,
                TaxProfile.code == code,
                TaxProfile.is_deleted.is_(True),
            )
        ):
            # The firm deleted it: it decided against buying this way.
            continue
        if local is None:
            local = framework.create_profile(
                TaxProfileWrite(
                    tax_system_id=system.id,
                    business_profile_id=None,
                    code=code,
                    name=name,
                    label=name,
                    description=(
                        f"{name}: assign it to the service bought this way, "
                        "and activate its rules. From the platform template."
                    ),
                    status=TaxStatus.ACTIVE,
                    display_order=order,
                    is_historical=False,
                    effective_from=_GST_EFFECTIVE_FROM,
                    effective_to=None,
                    components=[
                        TaxProfileComponentInput(
                            tax_component_id=components[component].id,
                            label=component,
                            short_label=component,
                            calculation_order=index,
                            percentage=percentage,
                            included_in_price=False,
                            recoverable=True,
                        )
                        for index, (component, percentage) in enumerate(rows, start=1)
                    ],
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            profiles_added += 1
        interstate = profile(interstate_code)
        group = _group_code(local)
        for suffix, priority, transaction, twin in (
            ("INTERSTATE", 2, PURCHASE_INTERSTATE, interstate),
            ("LOCAL", 3, None, None),
        ):
            rule_code = f"{code}_{suffix}"
            exists = session.scalar(
                # Deleted ones count: a firm that removed the rule decided
                # against it, and its code is still taken.
                select(TaxRule.id).where(
                    TaxRule.firm_id == firm_id,
                    TaxRule.code == rule_code,
                )
            )
            if exists is not None or (suffix == "INTERSTATE" and twin is None):
                continue
            actions: list[TaxRuleActionWrite] = []
            if twin is not None:
                actions.append(
                    TaxRuleActionWrite(
                        sequence=1,
                        action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                        target_tax_profile_id=twin.id,
                    )
                )
            actions += [
                TaxRuleActionWrite(
                    sequence=len(actions) + 1,
                    action_type=TaxRuleActionType.REVERSE_CHARGE,
                ),
                TaxRuleActionWrite(
                    sequence=len(actions) + 2,
                    action_type=TaxRuleActionType.INPUT_CREDIT_ALLOWED,
                ),
            ]
            conditions = [
                TaxRuleConditionWrite(
                    sequence=1,
                    field_key="transaction_type",
                    operator=(
                        TaxRuleConditionOperator.EQUALS
                        if transaction
                        else TaxRuleConditionOperator.IN
                    ),
                    value_text=transaction,
                    value_number=None,
                    value_date=None,
                    value_boolean=None,
                    value_json=(
                        None if transaction else {"values": list(INWARD_DOCUMENT_TYPES)}
                    ),
                ),
                TaxRuleConditionWrite(
                    sequence=2,
                    field_key="tax_profile_group_code",
                    operator=TaxRuleConditionOperator.EQUALS,
                    value_text=group,
                    value_number=None,
                    value_date=None,
                    value_boolean=None,
                    value_json=None,
                ),
            ]
            where = "interstate" if twin is not None else "local"
            rules.create_rule(
                TaxRuleWrite(
                    country_id=system.country_id,
                    business_profile_id=None,
                    tax_profile_id=None,
                    code=rule_code,
                    name=f"{name}, {where} purchase",
                    description=(
                        f"{name}, {where} purchase: the buyer pays the tax. "
                        "Inactive until the firm switches it on; from the "
                        "platform template."
                    ),
                    # After EXPORT_ZERO (1), ahead of every interstate and
                    # input-credit rule: the first match is the only one.
                    priority=priority,
                    status=TaxStatus.INACTIVE,
                    effective_from=_GST_EFFECTIVE_FROM,
                    effective_to=None,
                    conditions=conditions,
                    actions=actions,
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            rules_added += 1
    return profiles_added, rules_added


def _interstate_rule(
    code: str,
    slab: int,
    priority: int,
    profiles: dict[str, TaxProfile],
    *,
    inward: bool = False,
) -> tuple[
    str,
    str,
    int,
    list[tuple[str, TaxRuleConditionOperator, str | list[str]]],
    list[TaxRuleActionWrite],
]:
    """One rule switching a local slab to its interstate twin.

    ``inward`` makes the purchase-side twin: conditioned on
    ``PURCHASE_INTERSTATE`` and also allowing input credit, because it outranks
    ``PURCHASE_INPUT_CREDIT`` and evaluation stops at the first match -- without
    the second action an interstate purchase would lose the credit a local one
    is given (D-CMP-14).
    """
    actions = [
        TaxRuleActionWrite(
            sequence=1,
            action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
            target_tax_profile_id=profiles[f"GST_{slab}_INTERSTATE"].id,
        )
    ]
    if inward:
        actions.append(
            TaxRuleActionWrite(
                sequence=2, action_type=TaxRuleActionType.INPUT_CREDIT_ALLOWED
            )
        )
    return (
        code,
        f"Interstate {'purchase' if inward else 'sale'} switches {slab} percent "
        "GST to IGST",
        priority,
        [
            (
                "transaction_type",
                TaxRuleConditionOperator.EQUALS,
                PURCHASE_INTERSTATE if inward else SALES_INTERSTATE,
            ),
            # The group, never the profile's id: a profile is versioned and a
            # rate change mints a new id under the same group, so a rule
            # written against the id stops matching the moment a rate
            # changes -- silently. `20260809_0049` rewrote the rules seeded
            # before it; this template went on writing ids (D-CMP-19).
            (
                "tax_profile_group_code",
                TaxRuleConditionOperator.EQUALS,
                _group_code(profiles[f"GST_{slab}_LOCAL"]),
            ),
        ],
        actions,
    )


def _group_code(profile: TaxProfile) -> str:
    """Return the version-stable name of a profile, its group code."""
    return profile.group_code or profile.code


def _create_rules(
    rules: TaxRuleService,
    firm_id: UUID,
    actor_id: UUID,
    country_id: UUID,
    profiles: dict[str, TaxProfile],
) -> int:
    """Create the nine rules and return how many."""
    definitions = (
        (
            "EXPORT_ZERO",
            "Export supplies are zero rated",
            1,
            # A buyer outside India, which is what a document can say; no
            # document sends a transaction type EXPORT (D-CMP-13). Zero rated
            # under LUT, IGST Act s.16(3)(a) -- a firm exporting on payment of
            # IGST edits or retires this rule.
            [("destination", TaxRuleConditionOperator.EQUALS, FOREIGN_STATE_CODE)],
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
        _interstate_rule("PURCHASE_INTERSTATE_GST_5", 5, 13, profiles, inward=True),
        _interstate_rule("PURCHASE_INTERSTATE_GST_12", 12, 14, profiles, inward=True),
        _interstate_rule("PURCHASE_INTERSTATE_GST_18", 18, 15, profiles, inward=True),
        (
            "EXEMPT_PROFILE",
            "Exempt products remain exempt",
            20,
            [
                (
                    "tax_profile_group_code",
                    TaxRuleConditionOperator.EQUALS,
                    _group_code(profiles["EXEMPT"]),
                )
            ],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.EXEMPT_TAX)],
        ),
        (
            "PURCHASE_INPUT_CREDIT",
            "Purchase transactions allow input credit",
            30,
            # Every inward document, not just the order: ``PURCHASE`` alone
            # left a receipt, a bill and a return without the credit its own
            # order was given (D-CMP-13).
            [
                (
                    "transaction_type",
                    TaxRuleConditionOperator.IN,
                    list(INWARD_DOCUMENT_TYPES),
                )
            ],
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
                        value_text=value if isinstance(value, str) else None,
                        value_number=None,
                        value_date=None,
                        value_boolean=None,
                        value_json=(
                            None if isinstance(value, str) else {"values": value}
                        ),
                    )
                    for index, (field_key, operator, value) in enumerate(
                        conditions, start=1
                    )
                ],
                actions=actions,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
    return len(definitions)
