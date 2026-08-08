"""Enterprise tax framework service and API-scope tests."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile
from app.tax.models import TaxProfile
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.products.schemas import ProductCreate
from app.products.services import ProductService
from app.sales.models import GeoCountry
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleSimulationRequest,
    TaxRuleWrite,
    TaxSettingsWrite,
    TaxSystemWrite,
)
from app.tax.services import TaxFrameworkService, TaxRuleService


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Tax Firm",
        code="TAX01",
        country="AE",
        currency_code="AED",
        financial_year_start=date(2026, 1, 1),
    )
    session.add(row)
    session.commit()
    return row


def _country(session: Session, actor_id: UUID) -> GeoCountry:
    row = GeoCountry(
        code="AE",
        name="United Arab Emirates",
        iso2="AE",
        iso3="ARE",
        phone_code="+971",
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(row)
    session.commit()
    return row


def _profile(session: Session, actor_id: UUID) -> BusinessProfile:
    row = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
        created_by=actor_id,
        updated_by=actor_id,
        default_settings={},
    )
    session.add(row)
    session.commit()
    return row


def test_tax_framework_profile_drives_product_assignment() -> None:
    factory = _session_factory()
    session = factory()
    actor_id = uuid4()
    firm = _firm(session)
    country = _country(session, actor_id)
    _profile(session, actor_id)

    tax_service = TaxFrameworkService(session)
    system = tax_service.create_system(
        TaxSystemWrite(
            country_id=country.id,
            code="VAT",
            name="Value Added Tax",
            display_name="VAT",
            status="ACTIVE",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    component = tax_service.create_component(
        TaxComponentWrite(
            tax_system_id=system.id,
            code="VAT_STD",
            name="Standard VAT",
            label="VAT",
            percentage="5",
            status="ACTIVE",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    profile = tax_service.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            code="VAT_5",
            name="VAT 5%",
            label="VAT 5%",
            status="ACTIVE",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": "5",
                    "calculation_order": 1,
                    "included_in_price": False,
                    "recoverable": False,
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    product = ProductService(session).create_product(
        ProductCreate.model_validate(
            {
                "code": "SKU-TAX-1",
                "name": "Taxable Item",
                "product_type": "STOCK_ITEM",
                "status": "ACTIVE",
                "tax_profile_group_code": profile.group_code,
                "selling_price": "10",
                "attributes": [],
                "media": [],
            }
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    assert product.tax_profile_group_code == profile.group_code

    with pytest.raises(
        ValidationError,
        match="Tax profile group assigned to active products cannot be deleted.",
    ):
        tax_service.delete_profile(profile.id, firm_scope=firm.id, actor_id=actor_id)


def test_tax_framework_validates_component_system_alignment() -> None:
    factory = _session_factory()
    session = factory()
    actor_id = uuid4()
    firm = _firm(session)
    country = _country(session, actor_id)
    _profile(session, actor_id)

    service = TaxFrameworkService(session)
    system_a = service.create_system(
        TaxSystemWrite(country_id=country.id, code="SYS_A", name="System A"),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    system_b = service.create_system(
        TaxSystemWrite(country_id=country.id, code="SYS_B", name="System B"),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    component_b = service.create_component(
        TaxComponentWrite(
            tax_system_id=system_b.id,
            code="COMP_B",
            name="Component B",
            percentage="7",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    with pytest.raises(
        ValidationError,
        match="Profile components must belong to the selected tax system.",
    ):
        service.create_profile(
            TaxProfileWrite(
                tax_system_id=system_a.id,
                code="PROFILE_A",
                name="Profile A",
                components=[{"tax_component_id": component_b.id, "percentage": "7"}],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )


def test_tax_rule_engine_applies_highest_priority_matching_rule() -> None:
    factory = _session_factory()
    session = factory()
    actor_id = uuid4()
    firm = _firm(session)
    country = _country(session, actor_id)
    business_profile = _profile(session, actor_id)

    framework_service = TaxFrameworkService(session)
    system = framework_service.create_system(
        TaxSystemWrite(country_id=country.id, code="GEN_TAX", name="Generic Tax"),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    component = framework_service.create_component(
        TaxComponentWrite(
            tax_system_id=system.id,
            code="GEN_5",
            name="Generic 5",
            label="Generic 5",
            percentage="5",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    profile = framework_service.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            business_profile_id=business_profile.id,
            code="GEN_5",
            name="Generic 5",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": "5",
                    "calculation_order": 1,
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    rule_service = TaxRuleService(session)
    rule_service.create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="DEFAULT_RULE",
            name="Default Rule",
            priority=50,
            status="ACTIVE",
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": profile.id,
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    rule_service.create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="EXPORT_RULE",
            name="Export Rule",
            priority=1,
            status="ACTIVE",
            conditions=[
                {
                    "sequence": 1,
                    "field_key": "transaction_type",
                    "operator": "EQUALS",
                    "value_text": "EXPORT",
                }
            ],
            actions=[{"sequence": 1, "action_type": "ZERO_RATED"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    result = rule_service.simulate(
        TaxRuleSimulationRequest(
            transaction_type="EXPORT",
            transaction_date=date(2026, 8, 1),
            country_id=country.id,
            business_profile_id=business_profile.id,
            tax_profile_id=profile.id,
            invoice_value="100",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    assert result.matched_rule_id is not None
    assert result.zero_rated is True
    assert result.total_tax_amount == 0
    assert result.applied_tax_profile_id == profile.id
    assert result.decisions[0].priority == 1


def test_tax_rule_updates_create_new_version_after_activation() -> None:
    factory = _session_factory()
    session = factory()
    actor_id = uuid4()
    firm = _firm(session)
    country = _country(session, actor_id)
    business_profile = _profile(session, actor_id)

    rule_service = TaxRuleService(session)
    created = rule_service.create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="VERSION_RULE",
            name="Version Rule",
            priority=10,
            status="ACTIVE",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    versioned = rule_service.update_rule(
        created.id,
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="VERSION_RULE",
            name="Version Rule Updated",
            priority=5,
            status="ACTIVE",
            conditions=[
                {
                    "sequence": 1,
                    "field_key": "transaction_type",
                    "operator": "EQUALS",
                    "value_text": "SALES",
                }
            ],
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    assert versioned.id != created.id
    assert versioned.version_number == 2
    assert versioned.supersedes_rule_id == created.id
    assert created.version_number == 1


def test_tax_framework_settings_can_be_created_on_first_update() -> None:
    factory = _session_factory()
    session = factory()
    actor_id = uuid4()
    firm = _firm(session)

    settings = TaxFrameworkService(session).update_settings(
        TaxSettingsWrite(
            primary_label="Tax",
            component_label="Component",
            profile_label="Profile",
            report_label="Tax Report",
            allow_mixed_historical=True,
            additional_settings={"country_independent": True},
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    assert settings.firm_id == firm.id
    assert settings.report_label == "Tax Report"
    assert settings.additional_settings["country_independent"] is True


def test_profile_version_is_resolved_from_the_document_date() -> None:
    """A product names a tax group; the document's date picks the rate version.

    This is what makes "the rate changed on 1 April" expressible: a back-dated
    document keeps the rate that applied when it was supplied, and a rate change
    takes effect without touching any product.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    _profile(session, actor_id)
    service = TaxFrameworkService(session)
    country = _country(session, actor_id)
    system = service.create_system(
        TaxSystemWrite(
            country_id=country.id,
            code="GST",
            name="GST",
            display_name="GST",
            status="ACTIVE",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    component = service.create_component(
        TaxComponentWrite(
            tax_system_id=system.id,
            code="GST_STD",
            name="GST standard",
            label="GST",
            percentage="5",
            status="ACTIVE",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    def _version(
        code: str, percent: str, starts: date | None, ends: date | None
    ) -> TaxProfile:
        return service.create_profile(
            TaxProfileWrite(
                tax_system_id=system.id,
                code=code,
                name=code,
                label=code,
                status="ACTIVE",
                group_code="GST_STANDARD",
                effective_from=starts,
                effective_to=ends,
                components=[
                    {
                        "tax_component_id": component.id,
                        "percentage": percent,
                        "calculation_order": 1,
                        "included_in_price": False,
                        "recoverable": False,
                    }
                ],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    old = _version("GST_5", "5", date(2020, 1, 1), date(2026, 3, 31))
    new = _version("GST_8", "8", date(2026, 4, 1), None)

    product = ProductService(session).create_product(
        ProductCreate.model_validate(
            {
                "code": "SKU-RATE",
                "name": "Rated item",
                "product_type": "STOCK_ITEM",
                "status": "ACTIVE",
                "tax_profile_group_code": "GST_STANDARD",
                "selling_price": "100",
                "attributes": [],
                "media": [],
            }
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    before = service.resolve_profile_for_product(
        product, date(2026, 3, 15), firm_scope=firm.id
    )
    after = service.resolve_profile_for_product(
        product, date(2026, 6, 1), firm_scope=firm.id
    )
    assert before is not None and before.id == old.id
    assert after is not None and after.id == new.id

    # A profile named explicitly must have been in force on that date.
    service.assert_profile_effective_on(old.id, date(2026, 3, 15), firm_scope=firm.id)
    with pytest.raises(ValidationError, match="was not in effect"):
        service.assert_profile_effective_on(
            new.id, date(2026, 3, 15), firm_scope=firm.id
        )
    with pytest.raises(ValidationError, match="was not in effect"):
        service.assert_profile_effective_on(
            old.id, date(2026, 6, 1), firm_scope=firm.id
        )


def test_a_product_without_a_tax_group_resolves_to_nothing() -> None:
    """No tax group means no profile, rather than an arbitrary one."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    _profile(session, actor_id)
    product = ProductService(session).create_product(
        ProductCreate.model_validate(
            {
                "code": "SKU-NOTAX",
                "name": "Untaxed item",
                "product_type": "STOCK_ITEM",
                "status": "ACTIVE",
                "selling_price": "10",
                "attributes": [],
                "media": [],
            }
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    resolved = TaxFrameworkService(session).resolve_profile_for_product(
        product, date(2026, 6, 1), firm_scope=firm.id
    )
    assert resolved is None
