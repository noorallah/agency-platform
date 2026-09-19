"""Enterprise tax framework service and API-scope tests."""

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile, FirmBusinessProfile
from app.common.audit.models.audit_log import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_money
from app.customers.models import Customer, CustomerAddress
from app.firms.models import Firm
from app.products.schemas import ProductCreate
from app.products.services import ProductService
from app.sales.models import GeoCountry
from app.tax.models import (
    TaxComponent,
    TaxProfile,
    TaxRuleExecutionLog,
    TaxSettings,
    TaxSystem,
)
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleSimulationRequest,
    TaxRuleSimulationResponse,
    TaxRuleWrite,
    TaxSettingsWrite,
    TaxStatus,
    TaxSystemWrite,
)
from app.tax.services import TaxFrameworkService, TaxRetentionService, TaxRuleService
from app.tax.services.place_of_supply import gst_state_code


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
    """A product takes its tax profile from the firm's tax system."""
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
    """A component cannot belong to a system its profile does not use.

    Mixing them silently would compute a tax nobody has legislated.
    """
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
    """The first rule that matches decides, and evaluation stops there.

    Ordered by priority, then code, then version. Two rules both applying
    would tax the same line twice.
    """
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
    """An active rule is versioned rather than edited.

    Documents already taxed under it must keep computing the same way,
    which editing in place would silently change.
    """
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
    """A firm with no tax settings row gets one on its first change."""
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


def _rate_setup(session: Session) -> tuple[Firm, UUID, TaxSystem, TaxComponent]:
    """Create the firm, system and component a rate-version test needs."""
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
    return firm, actor_id, system, component


def _profile_write(
    system: TaxSystem,
    component: TaxComponent,
    code: str,
    percent: str,
    starts: date | None,
    ends: date | None,
) -> TaxProfileWrite:
    return TaxProfileWrite(
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
    )


def test_overlapping_rate_versions_are_rejected() -> None:
    """Two active versions covering one day would make the rate ambiguous."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)

    service.create_profile(
        _profile_write(
            system, component, "GST_5", "5", date(2020, 1, 1), date(2026, 3, 31)
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    with pytest.raises(ValidationError, match="overlap"):
        service.create_profile(
            _profile_write(system, component, "GST_8", "8", date(2026, 3, 1), None),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    # Starting the day after the previous one ends is fine.
    service.create_profile(
        _profile_write(system, component, "GST_8", "8", date(2026, 4, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )


def test_an_open_ended_version_blocks_any_later_one() -> None:
    """A version with no end date runs forever, so nothing may follow it."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)

    service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    with pytest.raises(ValidationError, match="overlap"):
        service.create_profile(
            _profile_write(system, component, "GST_8", "8", date(2030, 1, 1), None),
            firm_id=firm.id,
            actor_id=actor_id,
        )


def test_superseding_closes_the_previous_version_without_a_gap() -> None:
    """A rate change is two edits that must agree; doing it in one step is safe."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)

    old = service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    new = service.supersede_profile(
        old.id,
        _profile_write(system, component, "GST_8", "8", date(2026, 4, 1), None),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    session.refresh(old)
    assert old.effective_to == date(2026, 3, 31), "the day before the successor"
    assert old.is_historical is True
    assert new.effective_from == date(2026, 4, 1)
    assert new.group_code == old.group_code

    # No gap and no overlap: every date resolves to exactly one version.
    assert (
        service.resolve_active_profile(
            "GST_STANDARD", date(2026, 3, 31), firm_scope=firm.id
        ).id
        == old.id
    )
    assert (
        service.resolve_active_profile(
            "GST_STANDARD", date(2026, 4, 1), firm_scope=firm.id
        ).id
        == new.id
    )


def test_a_replacement_must_start_after_the_version_it_replaces() -> None:
    """Otherwise the closing date would land before the version even began."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)

    old = service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2026, 4, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    with pytest.raises(ValidationError, match="must start after"):
        service.supersede_profile(
            old.id,
            _profile_write(system, component, "GST_8", "8", date(2026, 1, 1), None),
            firm_scope=firm.id,
            actor_id=actor_id,
        )
    with pytest.raises(ValidationError, match="needs an effective_from"):
        service.supersede_profile(
            old.id,
            _profile_write(system, component, "GST_8", "8", None, None),
            firm_scope=firm.id,
            actor_id=actor_id,
        )


def test_a_rule_keeps_matching_after_the_rate_version_changes() -> None:
    """A rule written against a tax group must survive a rate change.

    Profiles are versioned, so a rate change creates a new row with a new id and
    the same group_code. A rule condition written against the id stops matching
    the moment that happens — silently, because a rule that does not match simply
    does not fire. For INTERSTATE_GST_18 that means an interstate sale is taxed
    as a local one with no error anywhere.
    """
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)
    rule_service = TaxRuleService(session)
    business_profile = session.query(BusinessProfile).first()
    country = session.query(GeoCountry).first()

    old = service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    rule_service.create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="INTERSTATE",
            name="Interstate swap",
            priority=1,
            status="ACTIVE",
            conditions=[
                {
                    "sequence": 1,
                    "field_key": "tax_profile_group_code",
                    "operator": "EQUALS",
                    "value_text": "GST_STANDARD",
                }
            ],
            actions=[{"sequence": 1, "action_type": "ZERO_RATED"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    def _fires(profile_id: UUID, when: date) -> bool:
        result = rule_service.simulate(
            TaxRuleSimulationRequest(
                transaction_type="SALES_INTERSTATE",
                transaction_date=when,
                country_id=country.id,
                business_profile_id=business_profile.id,
                tax_profile_id=profile_id,
                invoice_value="100",
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )
        # zero_rated is set by the rule's action, so it proves the rule fired.
        return result.matched_rule_id is not None and result.zero_rated

    assert _fires(old.id, date(2026, 1, 1)), "the rule should match the first version"

    # The rate changes: a new version, a new id, the same group.
    new = service.supersede_profile(
        old.id,
        _profile_write(system, component, "GST_8", "8", date(2026, 4, 1), None),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    assert new.id != old.id
    assert new.group_code == old.group_code
    assert _fires(new.id, date(2026, 6, 1)), (
        "the rule must still fire after a rate change; matching on the profile "
        "id instead of the group is what silently broke this"
    )


def _priced_profile(
    session: Session,
    firm: Firm,
    actor_id: UUID,
    system: TaxSystem,
    *,
    percent: str,
    included_in_price: bool,
    code: str = "PRICED",
) -> TaxProfile:
    """Create a single-component profile at the given rate and price treatment."""
    component = TaxFrameworkService(session).create_component(
        TaxComponentWrite(
            tax_system_id=system.id,
            code=f"C_{code}",
            name=code,
            label=code,
            percentage=percent,
            included_in_price=included_in_price,
            status="ACTIVE",
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    return TaxFrameworkService(session).create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            code=code,
            name=code,
            label=code,
            status="ACTIVE",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": percent,
                    "calculation_order": 1,
                    "included_in_price": included_in_price,
                    "recoverable": False,
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )


def _document_style_simulation(
    session: Session,
    firm: Firm,
    actor_id: UUID,
    profile_id: UUID,
    value: str = "100",
) -> TaxRuleSimulationResponse:
    """Simulate exactly the way a transactional document does.

    Documents send no country and, in two of the seven, no business profile,
    which is what made rule scope behave differently per document type.
    """
    return TaxRuleService(session).simulate(
        TaxRuleSimulationRequest(
            transaction_type="SALES_INVOICE",
            transaction_date=date(2026, 6, 1),
            tax_profile_id=profile_id,
            invoice_value=value,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )


def test_tax_amounts_round_half_up_like_every_other_amount() -> None:
    """Tax used Python's default banker's rounding; money is rounded half up.

    ``_quantize`` passed no rounding argument, so a component landing exactly on
    a half rounded to even while every amount the document computed around it
    rounded away from zero.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    profile = _priced_profile(
        session, firm, actor_id, system, percent="100", included_in_price=False
    )

    result = _document_style_simulation(
        session, firm, actor_id, profile.id, value="1.00025"
    )
    assert result.total_tax_amount == quantize_money(Decimal("1.00025"))
    assert result.total_tax_amount == Decimal("1.0003")


def test_simulate_does_not_commit_the_caller_transaction() -> None:
    """Every document computes tax per line on its own session, mid-write.

    Committing here published whatever the document had written so far and left
    the rest of the write in a separate transaction.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    profile = _priced_profile(
        session, firm, actor_id, system, percent="5", included_in_price=False
    )

    pending = TaxSystem(
        firm_id=firm.id,
        country_id=session.query(GeoCountry).first().id,
        code="HALF_WRITTEN",
        name="Half written",
        display_name="Half written",
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(pending)
    session.flush()

    _document_style_simulation(session, firm, actor_id, profile.id)
    session.rollback()

    assert (
        session.scalar(select(TaxSystem).where(TaxSystem.code == "HALF_WRITTEN"))
        is None
    ), "simulate committed work the caller had not finished"


def test_a_country_scoped_rule_fires_the_way_a_document_calls_it() -> None:
    """No document sends a country, so country-scoped rules never fired.

    The country is derivable: the applied profile belongs to a tax system, and
    that system names the country.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    country = session.query(GeoCountry).first()
    profile = _priced_profile(
        session, firm, actor_id, system, percent="5", included_in_price=False
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            code="COUNTRY_ZERO",
            name="Country scoped",
            priority=1,
            status="ACTIVE",
            actions=[{"sequence": 1, "action_type": "ZERO_RATED"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    result = _document_style_simulation(session, firm, actor_id, profile.id)
    assert result.matched_rule_id is not None
    assert result.zero_rated is True
    assert result.total_tax_amount == Decimal("0")


def test_a_profile_scoped_rule_fires_without_an_explicit_profile_id() -> None:
    """Two of the seven documents send no business profile; five do.

    The same rule set therefore taxed a purchase order and the invoice raised
    from it differently. The firm's assignment settles it for all of them.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    business_profile = session.query(BusinessProfile).first()
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=business_profile.id,
            is_active=True,
            effective_from=date(2026, 1, 1),
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.commit()
    profile = _priced_profile(
        session, firm, actor_id, system, percent="5", included_in_price=False
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            business_profile_id=business_profile.id,
            code="PROFILE_ZERO",
            name="Profile scoped",
            priority=1,
            status="ACTIVE",
            actions=[{"sequence": 1, "action_type": "ZERO_RATED"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    result = _document_style_simulation(session, firm, actor_id, profile.id)
    assert result.matched_rule_id is not None
    assert result.zero_rated is True


def test_an_unassigned_firm_matches_the_default_profile_rule() -> None:
    """A firm with no assignment is judged by the platform default profile.

    The tax engine read ``firm_business_profiles`` directly and answered None
    for an unassigned firm, so every profile-scoped rule skipped it -- while
    ``resolve_capabilities`` had already decided that firm operates under
    GENERIC. Two resolvers, two answers, and the tax one charged full rate.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    default_profile = session.query(BusinessProfile).first()
    assert default_profile.is_default is True
    assert session.query(FirmBusinessProfile).count() == 0
    profile = _priced_profile(
        session, firm, actor_id, system, percent="5", included_in_price=False
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            business_profile_id=default_profile.id,
            code="DEFAULT_ZERO",
            name="Default profile scoped",
            priority=1,
            status="ACTIVE",
            actions=[{"sequence": 1, "action_type": "ZERO_RATED"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    result = _document_style_simulation(session, firm, actor_id, profile.id)

    assert result.matched_rule_id is not None
    assert result.zero_rated is True


def test_tax_inside_the_price_is_extracted_not_added() -> None:
    """An inclusive component was computed as exclusive and billed on top.

    A 110 line carrying an inclusive 10% component was invoiced at 121: the
    customer paid the embedded tax once in the price and again as tax.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    profile = _priced_profile(
        session, firm, actor_id, system, percent="10", included_in_price=True
    )

    result = _document_style_simulation(session, firm, actor_id, profile.id, "110")

    assert result.applied_components[0].amount == Decimal("10.0000")
    assert result.inclusive_tax_amount == Decimal("10.0000")
    # What the document adds to its payable total.
    assert result.total_tax_amount == Decimal("0")


def test_reverse_charge_does_not_bill_the_counterparty() -> None:
    """The action set a flag that changed nothing; the tax was still charged.

    Under reverse charge the recipient accounts for the tax, so the supplier
    bills none of it. The amount is still reported for the ledger.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    country = session.query(GeoCountry).first()
    profile = _priced_profile(
        session, firm, actor_id, system, percent="5", included_in_price=False
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            code="RCM",
            name="Reverse charge",
            priority=1,
            status="ACTIVE",
            actions=[{"sequence": 1, "action_type": "REVERSE_CHARGE"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    result = _document_style_simulation(session, firm, actor_id, profile.id)

    assert result.reverse_charge is True
    assert result.total_tax_amount == Decimal("0")
    assert result.reverse_charge_tax_amount == Decimal("5.0000")


def test_execution_logs_are_prunable_beyond_the_retention_window() -> None:
    """The log grows by one row per document line and nothing removed any."""
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    profile = _priced_profile(
        session, firm, actor_id, system, percent="5", included_in_price=False
    )
    for _ in range(3):
        _document_style_simulation(session, firm, actor_id, profile.id)
    session.commit()

    logs = session.scalars(select(TaxRuleExecutionLog)).all()
    assert len(logs) == 3
    logs[0].created_at = utc_now() - timedelta(days=400)
    session.commit()

    service = TaxRetentionService(session)
    assert service.purge(dry_run=True).execution_logs == 1
    assert len(session.scalars(select(TaxRuleExecutionLog)).all()) == 3

    assert service.purge().execution_logs == 1
    assert len(session.scalars(select(TaxRuleExecutionLog)).all()) == 2

    with pytest.raises(ValueError):
        service.purge(execution_log_days=0)


def test_a_tax_system_refuses_a_write_aimed_at_an_older_version() -> None:
    """`tax` could take `If-Match` under its own name from the start.

    `version_number` here is a rule's published revision, so the concurrency
    counter never collided with it the way it did in `uom` -- the reason both
    modules had been left last-one-wins was the collision in one of them.
    """
    session = _session_factory()()
    firm, actor_id, system, _ = _rate_setup(session)
    service = TaxFrameworkService(session)
    read_at = system.version

    service.update_system(
        system.id,
        TaxSystemWrite(
            country_id=system.country_id,
            code="GST",
            name="GST revised",
            display_name="GST",
            status="ACTIVE",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
        expected_version=read_at,
    )

    with pytest.raises(ConflictError):
        service.update_system(
            system.id,
            TaxSystemWrite(
                country_id=system.country_id,
                code="GST",
                name="GST revised again",
                display_name="GST",
                status="ACTIVE",
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
            expected_version=read_at,
        )

    # Opt-in: a client that sends nothing still writes.
    service.update_system(
        system.id,
        TaxSystemWrite(
            country_id=system.country_id,
            code="GST",
            name="GST final",
            display_name="GST",
            status="ACTIVE",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    assert system.name == "GST final"


def test_a_condition_written_against_a_profile_id_matches_that_profile() -> None:
    """The seeded interstate rules are `tax_profile_id EQUALS <id>`, and none fired.

    The condition's value is stored as text and the context carries a UUID;
    the text was uppercased and the UUID rendered lowercase, so the two never
    compared equal. Every interstate sale on every seeded firm was charged
    CGST and SGST instead of IGST. Driving the GST template on 2026-09-08 is
    what found it -- the simulator said "tax_profile_id failed EQUALS" for a
    rule naming exactly the profile it had been given.
    """
    factory = _session_factory()
    session = factory()
    actor_id = uuid4()
    firm = _firm(session)
    country = _country(session, actor_id)
    business_profile = _profile(session, actor_id)

    framework_service = TaxFrameworkService(session)
    system = framework_service.create_system(
        TaxSystemWrite(country_id=country.id, code="GST", name="GST"),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    def component(code: str) -> object:
        return framework_service.create_component(
            TaxComponentWrite(
                tax_system_id=system.id, code=code, name=code, label=code
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    cgst, sgst, igst = component("CGST"), component("SGST"), component("IGST")

    def profile(code: str, rows: list[tuple[object, str]]) -> object:
        return framework_service.create_profile(
            TaxProfileWrite(
                tax_system_id=system.id,
                business_profile_id=business_profile.id,
                code=code,
                name=code,
                components=[
                    {
                        "tax_component_id": getattr(item, "id"),  # noqa: B009
                        "percentage": rate,
                        "calculation_order": index,
                    }
                    for index, (item, rate) in enumerate(rows, start=1)
                ],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    local = profile("GST_18_LOCAL", [(cgst, "9"), (sgst, "9")])
    interstate = profile("GST_18_INTERSTATE", [(igst, "18")])

    rule_service = TaxRuleService(session)
    rule_service.create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="INTERSTATE_GST_18",
            name="Interstate sale switches 18 percent GST to IGST",
            priority=12,
            status="ACTIVE",
            conditions=[
                {
                    "sequence": 1,
                    "field_key": "transaction_type",
                    "operator": "EQUALS",
                    "value_text": "SALES_INTERSTATE",
                },
                {
                    "sequence": 2,
                    "field_key": "tax_profile_id",
                    "operator": "EQUALS",
                    # As the seed writes it: the id rendered as text.
                    "value_text": str(getattr(local, "id")),  # noqa: B009
                },
            ],
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": getattr(interstate, "id"),  # noqa: B009
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    result = rule_service.simulate(
        TaxRuleSimulationRequest(
            transaction_type="SALES_INTERSTATE",
            transaction_date=date(2026, 6, 1),
            country_id=country.id,
            business_profile_id=business_profile.id,
            tax_profile_id=getattr(local, "id"),  # noqa: B009
            invoice_value="1000",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    assert result.matched_rule_id is not None, result.decisions
    assert result.applied_tax_profile_id == getattr(interstate, "id")  # noqa: B009
    assert {item.code for item in result.applied_components} == {"IGST"}
    assert result.total_tax_amount == Decimal("180")


def _audit_actions(session: Session) -> Counter[str]:
    """Count every audit action written so far.

    Counted rather than listed: one request's rows share ``created_at``, so
    their order is not something to assert on.
    """
    return Counter(session.scalars(select(AuditLog.action)).all())


def test_every_tax_change_leaves_an_audit_row() -> None:
    """Deletes, restores, bulk status and settings wrote nothing (D-CMP-9).

    Tax History reads the trail, so a change with no row there did not
    happen as far as anybody reviewing the configuration can tell.
    """
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)
    profile = service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    written = _audit_actions(session)

    service.bulk_profile_status(
        [profile.id], TaxStatus.INACTIVE, firm_scope=firm.id, actor_id=actor_id
    )
    service.delete_component(component.id, firm_scope=firm.id, actor_id=actor_id)
    service.restore_component(component.id, firm_scope=firm.id, actor_id=actor_id)
    service.bulk_delete_profiles([profile.id], firm_scope=firm.id, actor_id=actor_id)
    service.bulk_restore_profiles([profile.id], firm_scope=firm.id, actor_id=actor_id)
    service.update_settings(
        TaxSettingsWrite(
            primary_label="GST",
            component_label="Component",
            profile_label="Profile",
            report_label="GST",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    assert _audit_actions(session) - written == Counter(
        [
            "tax.profile.status_changed",
            "tax.component.deleted",
            "tax.component.restored",
            "tax.profile.deleted",
            "tax.profile.restored",
            "tax.settings.changed",
        ]
    )
    assert "tax_settings" in {
        row.entity_type for row in service.history(firm_scope=firm.id)
    }


def test_reading_the_settings_writes_nothing() -> None:
    """A firm with no settings row is answered with defaults, unsaved."""
    session = _session_factory()()
    firm = _firm(session)

    answer = TaxFrameworkService(session).get_settings(firm_scope=firm.id)
    session.commit()

    assert answer.primary_label == "Tax"
    assert session.scalars(select(TaxSettings)).all() == []


def _rule_applying(
    session: Session, firm: Firm, actor_id: UUID, profile: TaxProfile
) -> None:
    """Create an ACTIVE rule whose action applies ``profile``."""
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            code="SWITCH_TO_IT",
            name="Switch to it",
            priority=10,
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


def test_a_profile_an_active_rule_applies_cannot_be_deleted() -> None:
    """The rule would fire and apply nothing -- no tax at all (D-CMP-9)."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)
    profile = service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    _rule_applying(session, firm, actor_id, profile)

    with pytest.raises(ValidationError, match="SWITCH_TO_IT"):
        service.delete_profile(profile.id, firm_scope=firm.id, actor_id=actor_id)
    with pytest.raises(ValidationError, match="SWITCH_TO_IT"):
        service.bulk_delete_profiles(
            [profile.id], firm_scope=firm.id, actor_id=actor_id
        )


def test_a_profile_a_rule_tests_for_by_id_cannot_be_deleted() -> None:
    """The GST template's interstate rules name their local profile by id."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)
    profile = service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            code="WHEN_IT",
            name="When it",
            priority=10,
            status="ACTIVE",
            conditions=[
                {
                    "sequence": 1,
                    "field_key": "tax_profile_id",
                    "operator": "EQUALS",
                    "value_text": str(profile.id).upper(),
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    with pytest.raises(ValidationError, match="WHEN_IT"):
        service.delete_profile(profile.id, firm_scope=firm.id, actor_id=actor_id)


def test_bulk_activation_and_restore_run_the_overlap_check() -> None:
    """Two ACTIVE versions covering one day leave the rate to chance (D-CMP-9)."""
    session = _session_factory()()
    firm, actor_id, system, component = _rate_setup(session)
    service = TaxFrameworkService(session)
    service.create_profile(
        _profile_write(system, component, "GST_5", "5", date(2020, 1, 1), None),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    draft = _profile_write(system, component, "GST_8", "8", date(2026, 1, 1), None)
    draft.status = TaxStatus.INACTIVE
    other = service.create_profile(draft, firm_id=firm.id, actor_id=actor_id)

    with pytest.raises(ValidationError, match="overlap"):
        service.bulk_profile_status(
            [other.id], TaxStatus.ACTIVE, firm_scope=firm.id, actor_id=actor_id
        )
    session.rollback()

    # An ACTIVE version deleted while its group moved on cannot come back on
    # top of the version that replaced it.
    replaced = session.scalar(select(TaxProfile).where(TaxProfile.code == "GST_5"))
    assert replaced is not None
    replaced.is_deleted = True
    other.status = TaxStatus.ACTIVE.value
    session.commit()
    with pytest.raises(ValidationError, match="overlap"):
        service.bulk_restore_profiles(
            [replaced.id], firm_scope=firm.id, actor_id=actor_id
        )


class _RuleBook:
    """One firm with one ACTIVE rule, ``SWITCH``, matching every sale."""

    def __init__(self) -> None:
        """Seed the firm and the rule."""
        self.session = _session_factory()()
        self.actor_id = uuid4()
        self.firm = _firm(self.session)
        self.rules = TaxRuleService(self.session)
        self.original = self.rules.create_rule(
            self.write(), firm_id=self.firm.id, actor_id=self.actor_id
        )

    @staticmethod
    def write(
        *, status: str = "ACTIVE", effective_from: date | None = None
    ) -> TaxRuleWrite:
        """Return the rule as a form would send it."""
        return TaxRuleWrite(
            code="SWITCH",
            name="Switch",
            priority=10,
            status=status,
            effective_from=effective_from,
            conditions=[
                {
                    "sequence": 1,
                    "field_key": "transaction_type",
                    "operator": "EQUALS",
                    "value_text": "SALES_INVOICE",
                }
            ],
        )

    def edit(self, rule_id: UUID, data: TaxRuleWrite) -> object:
        """Save an edit the way the rule form does."""
        return self.rules.update_rule(
            rule_id, data, firm_scope=self.firm.id, actor_id=self.actor_id
        )

    def matched_on(self, when: date) -> UUID | None:
        """Return the rule a sale on this date is decided by."""
        return self.rules.simulate(
            TaxRuleSimulationRequest(
                transaction_type="SALES_INVOICE",
                transaction_date=when,
                invoice_value="100",
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        ).matched_rule_id

    def statuses(self) -> list[tuple[int, str, date | None]]:
        """Return every version of the rule, oldest first."""
        return [
            (row.version_number, row.status, row.effective_to)
            for row in self.rules.rule_history(firm_scope=self.firm.id, code="SWITCH")
        ]


def test_switching_a_rule_off_takes_every_version_out_of_force() -> None:
    """D-CMP-3: an edit to INACTIVE left version 1 ACTIVE and still deciding."""
    book = _RuleBook()

    book.edit(book.original.id, book.write(status="INACTIVE"))

    assert book.statuses() == [(1, "INACTIVE", None), (2, "INACTIVE", None)]
    assert book.matched_on(date(2026, 6, 1)) is None


def test_an_edit_leaves_exactly_one_version_deciding() -> None:
    """The new version decides; the one it replaced no longer matches at all."""
    book = _RuleBook()

    successor = book.edit(book.original.id, book.write())

    assert book.statuses() == [(1, "INACTIVE", None), (2, "ACTIVE", None)]
    assert book.matched_on(date(2026, 6, 1)) == successor.id


def test_a_later_start_closes_the_old_version_the_day_before() -> None:
    """Documents dated before the change are still decided by the old version.

    Closed rather than switched off, the way a rate change closes a profile:
    a September bill reprinted in December must still be taxed as it was.
    """
    book = _RuleBook()

    successor = book.edit(
        book.original.id, book.write(effective_from=date(2026, 10, 1))
    )

    assert book.statuses() == [
        (1, "ACTIVE", date(2026, 9, 30)),
        (2, "ACTIVE", None),
    ]
    assert book.matched_on(date(2026, 9, 15)) == book.original.id
    assert book.matched_on(date(2026, 10, 15)) == successor.id


def test_a_draft_successor_retires_nothing_until_it_is_put_in_force() -> None:
    """Preparing a change is not making it: the live version decides meanwhile."""
    book = _RuleBook()

    draft = book.edit(book.original.id, book.write(status="DRAFT"))

    assert book.statuses() == [(1, "ACTIVE", None), (2, "DRAFT", None)]
    assert book.matched_on(date(2026, 6, 1)) == book.original.id

    activated = book.edit(draft.id, book.write(status="ACTIVE"))

    assert book.statuses() == [(1, "INACTIVE", None), (2, "ACTIVE", None)]
    assert book.matched_on(date(2026, 6, 1)) == draft.id
    # Editing a draft that has a condition used to answer 409: assigning the
    # new list nulled the old conditions' NOT NULL rule id.
    assert [condition.value_text for condition in activated.conditions] == [
        "SALES_INVOICE"
    ]


@pytest.mark.parametrize(
    ("written", "code"),
    [
        ("33AABCU9603R1ZM", "33"),
        ("29", "29"),
        ("KA", "29"),
        ("tn", "33"),
        ("Tamil Nadu", "33"),
        ("  jammu &  kashmir ", "01"),
        ("Atlantis", None),
        ("", None),
        (None, None),
    ],
)
def test_a_state_is_read_as_its_gst_code_however_it_is_written(
    written: str | None, code: str | None
) -> None:
    """A GSTIN, a code, an abbreviation and a name all name the same state."""
    assert gst_state_code(written) == code


def _supplier_and_buyer(
    session: Session,
    *,
    firm_gstin: str | None,
    buyer_gstin: str | None = None,
    address: tuple[str, str] | None = None,
) -> tuple[Firm, Customer]:
    """Make a firm and one buyer, the buyer optionally with a billing address."""
    firm = _firm(session)
    firm.gst_number = firm_gstin
    buyer = Customer(
        firm_id=firm.id,
        code="B1",
        customer_type="BUSINESS",
        name="Buyer",
        display_name="Buyer",
        currency_code="INR",
        status="ACTIVE",
        gst_number=buyer_gstin,
    )
    session.add(buyer)
    session.flush()
    if address is not None:
        state, country = address
        session.add(
            CustomerAddress(
                customer_id=buyer.id,
                address_type="BILLING",
                address_line1="1 Main Road",
                city="Somewhere",
                state=state,
                country=country,
                postal_code="000000",
            )
        )
    session.commit()
    session.refresh(buyer)
    return firm, buyer


@pytest.mark.parametrize(
    ("firm_gstin", "buyer_gstin", "address", "priced_as"),
    [
        # The buyer's GSTIN names another state.
        ("33AABCU9603R1ZM", "29AAACR5055K1Z5", None, "SALES_INTERSTATE"),
        # The GSTIN wins over an address in the seller's own state.
        (
            "33AABCU9603R1ZM",
            "29AAACR5055K1Z5",
            ("Tamil Nadu", "IN"),
            "SALES_INTERSTATE",
        ),
        # Unregistered: the billing address decides.
        ("33AABCU9603R1ZM", None, ("Kerala", "IN"), "SALES_INTERSTATE"),
        ("33AABCU9603R1ZM", None, ("Tamil Nadu", "IN"), "SALES_INVOICE"),
        # A buyer abroad is an inter-state supply (IGST Act s.7(5)(a)).
        ("33AABCU9603R1ZM", None, ("Dubai", "AE"), "SALES_INTERSTATE"),
        # Either side unknown: nothing is guessed.
        ("33AABCU9603R1ZM", None, None, "SALES_INVOICE"),
        (None, "29AAACR5055K1Z5", None, "SALES_INVOICE"),
    ],
)
def test_an_outward_supply_is_priced_by_where_it_is_made(
    firm_gstin: str | None,
    buyer_gstin: str | None,
    address: tuple[str, str] | None,
    priced_as: str,
) -> None:
    """D-CMP-1: the border, not the document's name, decides IGST."""
    session = _session_factory()()
    firm, buyer = _supplier_and_buyer(
        session, firm_gstin=firm_gstin, buyer_gstin=buyer_gstin, address=address
    )

    assert (
        TaxRuleService(session).outward_transaction_type(
            "SALES_INVOICE", firm_id=firm.id, branch_id=None, customer_id=buyer.id
        )
        == priced_as
    )


def test_every_outward_document_asks_where_its_supply_is_made() -> None:
    """No outward module may name its own type to the engine again.

    Five modules each wrote ``transaction_type="SALES_..."`` into the request,
    which is how none of them ever sent ``SALES_INTERSTATE`` (D-CMP-1).
    """
    root = Path(__file__).resolve().parents[2] / "app"
    offenders: list[str] = []
    for module in (
        "sales_invoice",
        "sales_order",
        "quotation",
        "delivery_note",
        "sales_return",
    ):
        for path in (root / module / "services").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for chunk in source.split("TaxRuleSimulationRequest(")[1:]:
                if "outward_transaction_type(" not in chunk[:400]:
                    offenders.append(f"{module}/{path.name}")
    assert offenders == []
