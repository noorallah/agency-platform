"""Seed sample GST tax data for one or more firms."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies.settings import get_settings
from app.core.database.engine import DatabaseManager
from app.core.exceptions import ResourceNotFoundError
from app.core.tenancy import (
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.firms.models import Firm
from app.identity.models import User
from app.sales.models.territory import GeoCountry
from app.sales.schemas import GeoCountryWrite
from app.sales.services.territory_service import SalesTerritoryService
from app.tax.models import TaxSystem
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


@dataclass(frozen=True)
class TaxSeedContext:
    actor_id: UUID


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed sample GST tax data.")
    parser.add_argument(
        "--firm-code",
        action="append",
        dest="firm_codes",
        help="Seed one specific firm code. Repeat for multiple firms. Defaults to all firms.",
    )
    args = parser.parse_args()

    settings = get_settings()
    platform = DatabaseManager.from_settings(settings)
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    try:
        with platform.sessions(schema=platform.config.default_schema).session() as session:
            context = _resolve_seed_context(session)
            firms = _resolve_firms(session, args.firm_codes)
            for firm in firms:
                tenant = _tenant_context_for_firm(settings, firm)
                database = provider.manager_for(tenant)
                schema = provider.schema_for(tenant)
                with database.sessions(schema=schema).session() as tenant_session:
                    existing_system = tenant_session.scalar(
                        select(TaxSystem).where(
                            TaxSystem.firm_id == firm.id,
                            TaxSystem.is_deleted.is_(False),
                        )
                    )
                    if existing_system is not None:
                        print(
                            f"Skipped: firm={firm.code} schema={schema} "
                            "reason=tax_system_exists"
                        )
                        continue
                    _seed_firm_tax_data(tenant_session, firm, context)
                    print(
                        f"Seeded: firm={firm.code} schema={schema} "
                        "system=GST profiles=8 rules=6"
                    )
    finally:
        provider.dispose()
        platform.dispose()
    return 0


def _resolve_seed_context(session) -> TaxSeedContext:
    actor = session.scalar(
        select(User).where(User.email == "platform-admin@agency.local")
    ) or session.scalar(select(User).order_by(User.email.asc()))
    if actor is None:
        raise ResourceNotFoundError("No user is available to own seeded tax records.")
    return TaxSeedContext(actor_id=actor.id)


def _resolve_firms(session, requested_codes: list[str] | None) -> list[Firm]:
    statement = select(Firm).options(selectinload(Firm.storage_mappings))
    if not requested_codes:
        return list(session.scalars(statement.order_by(Firm.code.asc())).all())
    normalized = [code.strip().upper() for code in requested_codes]
    firms = list(
        session.scalars(
            statement.where(Firm.code.in_(normalized)).order_by(Firm.code.asc())
        ).all()
    )
    found_codes = {firm.code for firm in firms}
    missing = [code for code in normalized if code not in found_codes]
    if missing:
        raise ResourceNotFoundError(f"Firm not found: {', '.join(missing)}")
    return firms


def _tenant_context_for_firm(settings, firm: Firm) -> TenantContext:
    mapping = next(
        (
            item
            for item in firm.storage_mappings
            if item.is_active and not item.is_deleted
        ),
        None,
    )
    mode = (
        DeploymentMode.SHARED
        if mapping is None
        else DeploymentMode(mapping.deployment_mode)
    )
    if mode is DeploymentMode.SHARED:
        return TenantContext(
            firm_id=firm.id,
            deployment_mode=DeploymentMode.SHARED,
            database_name=settings.tenancy.shared_database_name,
            schema_name=settings.tenancy.shared_schema_name,
            database_type=settings.tenancy.platform_database_type.value,
        )
    if mapping is None or mapping.database_name is None or mapping.schema_name is None:
        raise ResourceNotFoundError(
            f"Firm {firm.code} does not have a complete storage mapping."
        )
    return TenantContext(
        firm_id=firm.id,
        deployment_mode=mode,
        database_name=mapping.database_name,
        schema_name=mapping.schema_name,
        database_type=mapping.database_type,
    )


def _seed_firm_tax_data(session, firm: Firm, context: TaxSeedContext) -> None:
    country = session.scalar(select(GeoCountry).where(GeoCountry.code == "IN"))
    if country is None:
        country = session.scalar(select(GeoCountry).where(GeoCountry.name == "India"))
    if country is None:
        country = SalesTerritoryService(session).create_country(
            GeoCountryWrite(
                code="IN",
                name="India",
                iso2="IN",
                iso3="IND",
                phone_code="91",
                is_active=True,
            ),
            actor_id=context.actor_id,
        )
    framework = TaxFrameworkService(session)
    rules = TaxRuleService(session)
    framework.update_settings(
        TaxSettingsWrite(
            primary_label="GST",
            component_label="Component",
            profile_label="Tax Profile",
            report_label="GST Report",
            allow_mixed_historical=True,
            additional_settings={"seeded": True, "default_country_code": "IN"},
        ),
        firm_scope=firm.id,
        actor_id=context.actor_id,
    )
    gst_system = framework.create_system(
        TaxSystemWrite(
            country_id=country.id,
            business_profile_id=None,
            code="GST",
            name="Goods and Services Tax",
            display_name="GST",
            description="Sample GST configuration for B2B distribution flows.",
            status=TaxStatus.ACTIVE,
            display_order=10,
            effective_from=date(2017, 7, 1),
            effective_to=None,
        ),
        firm_id=firm.id,
        actor_id=context.actor_id,
    )
    components = {
        "CGST": framework.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="CGST",
                name="Central GST",
                label="CGST",
                short_label="CGST",
                display_order=1,
                calculation_order=1,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=True,
                status=TaxStatus.ACTIVE,
                effective_from=date(2017, 7, 1),
                effective_to=None,
            ),
            firm_id=firm.id,
            actor_id=context.actor_id,
        ),
        "SGST": framework.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="SGST",
                name="State GST",
                label="SGST",
                short_label="SGST",
                display_order=2,
                calculation_order=2,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=True,
                status=TaxStatus.ACTIVE,
                effective_from=date(2017, 7, 1),
                effective_to=None,
            ),
            firm_id=firm.id,
            actor_id=context.actor_id,
        ),
        "IGST": framework.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="IGST",
                name="Integrated GST",
                label="IGST",
                short_label="IGST",
                display_order=3,
                calculation_order=3,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=True,
                status=TaxStatus.ACTIVE,
                effective_from=date(2017, 7, 1),
                effective_to=None,
            ),
            firm_id=firm.id,
            actor_id=context.actor_id,
        ),
        "CESS": framework.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="CESS",
                name="Compensation Cess",
                label="CESS",
                short_label="CESS",
                display_order=4,
                calculation_order=4,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=False,
                status=TaxStatus.ACTIVE,
                effective_from=date(2017, 7, 1),
                effective_to=None,
            ),
            firm_id=firm.id,
            actor_id=context.actor_id,
        ),
    }
    framework.create_country_mapping(
        TaxCountryMappingWrite(
            country_id=country.id,
            business_profile_id=None,
            tax_system_id=gst_system.id,
            status=TaxStatus.ACTIVE,
            is_default=True,
            effective_from=date(2017, 7, 1),
            effective_to=None,
        ),
        firm_id=firm.id,
        actor_id=context.actor_id,
    )
    profiles = _create_profiles(
        framework, firm.id, context.actor_id, gst_system.id, components
    )
    _create_rules(rules, firm.id, context.actor_id, country.id, profiles)


def _create_profiles(
    framework: TaxFrameworkService,
    firm_id: UUID,
    actor_id: UUID,
    tax_system_id: UUID,
    components: dict[str, object],
) -> dict[str, object]:
    profile_definitions = (
        ("GST_0", "GST 0%", [("IGST", Decimal("0"))]),
        ("GST_5_LOCAL", "GST 5% Local", [("CGST", Decimal("2.5")), ("SGST", Decimal("2.5"))]),
        ("GST_5_INTERSTATE", "GST 5% Interstate", [("IGST", Decimal("5"))]),
        ("GST_12_LOCAL", "GST 12% Local", [("CGST", Decimal("6")), ("SGST", Decimal("6"))]),
        ("GST_12_INTERSTATE", "GST 12% Interstate", [("IGST", Decimal("12"))]),
        ("GST_18_LOCAL", "GST 18% Local", [("CGST", Decimal("9")), ("SGST", Decimal("9"))]),
        ("GST_18_INTERSTATE", "GST 18% Interstate", [("IGST", Decimal("18"))]),
        ("EXEMPT", "Exempt", []),
    )
    created: dict[str, object] = {}
    for display_order, (code, name, component_rows) in enumerate(profile_definitions, start=1):
        created[code] = framework.create_profile(
            TaxProfileWrite(
                tax_system_id=tax_system_id,
                business_profile_id=None,
                code=code,
                name=name,
                label=name,
                description=f"Sample {name} profile.",
                status=TaxStatus.ACTIVE,
                display_order=display_order,
                is_historical=False,
                effective_from=date(2017, 7, 1),
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
                    for index, (component_code, percentage) in enumerate(component_rows, start=1)
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
    return created


def _create_rules(
    rules: TaxRuleService,
    firm_id: UUID,
    actor_id: UUID,
    country_id: UUID,
    profiles: dict[str, object],
) -> None:
    rule_definitions = (
        (
            "EXPORT_ZERO",
            "Export supplies are zero rated",
            1,
            [("transaction_type", TaxRuleConditionOperator.EQUALS, "EXPORT", None)],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_0"].id,
                ),
                TaxRuleActionWrite(sequence=2, action_type=TaxRuleActionType.ZERO_RATED),
            ],
        ),
        (
            "INTERSTATE_GST_5",
            "Interstate sale switches 5 percent GST to IGST",
            10,
            [
                ("transaction_type", TaxRuleConditionOperator.EQUALS, "SALES_INTERSTATE", None),
                ("tax_profile_id", TaxRuleConditionOperator.EQUALS, str(profiles["GST_5_LOCAL"].id), None),
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_5_INTERSTATE"].id,
                )
            ],
        ),
        (
            "INTERSTATE_GST_12",
            "Interstate sale switches 12 percent GST to IGST",
            11,
            [
                ("transaction_type", TaxRuleConditionOperator.EQUALS, "SALES_INTERSTATE", None),
                ("tax_profile_id", TaxRuleConditionOperator.EQUALS, str(profiles["GST_12_LOCAL"].id), None),
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_12_INTERSTATE"].id,
                )
            ],
        ),
        (
            "INTERSTATE_GST_18",
            "Interstate sale switches 18 percent GST to IGST",
            12,
            [
                ("transaction_type", TaxRuleConditionOperator.EQUALS, "SALES_INTERSTATE", None),
                ("tax_profile_id", TaxRuleConditionOperator.EQUALS, str(profiles["GST_18_LOCAL"].id), None),
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_18_INTERSTATE"].id,
                )
            ],
        ),
        (
            "EXEMPT_PROFILE",
            "Exempt products remain exempt",
            20,
            [("tax_profile_id", TaxRuleConditionOperator.EQUALS, str(profiles["EXEMPT"].id), None)],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.EXEMPT_TAX)],
        ),
        (
            "PURCHASE_INPUT_CREDIT",
            "Purchase transactions allow input credit",
            30,
            [("transaction_type", TaxRuleConditionOperator.EQUALS, "PURCHASE", None)],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.INPUT_CREDIT_ALLOWED)],
        ),
    )
    for code, name, priority, conditions, actions in rule_definitions:
        rules.create_rule(
            TaxRuleWrite(
                country_id=country_id,
                business_profile_id=None,
                tax_profile_id=None,
                code=code,
                name=name,
                description=f"Sample rule: {name}.",
                priority=priority,
                status=TaxStatus.ACTIVE,
                effective_from=date(2017, 7, 1),
                effective_to=None,
                conditions=[
                    TaxRuleConditionWrite(
                        sequence=index,
                        field_key=field_key,
                        operator=operator,
                        value_text=value_text,
                        value_number=value_number,
                        value_date=None,
                        value_boolean=None,
                        value_json=None,
                    )
                    for index, (field_key, operator, value_text, value_number) in enumerate(
                        conditions, start=1
                    )
                ],
                actions=actions,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )


if __name__ == "__main__":
    raise SystemExit(main())
