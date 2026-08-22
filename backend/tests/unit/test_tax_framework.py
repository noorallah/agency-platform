"""Enterprise tax framework service and API-scope tests."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile, FirmBusinessProfile
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_money
from app.firms.models import Firm
from app.products.schemas import ProductCreate
from app.products.services import ProductService
from app.sales.models import GeoCountry
from app.tax.models import (
    TaxComponent,
    TaxProfile,
    TaxRuleExecutionLog,
    TaxSystem,
)
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleSimulationRequest,
    TaxRuleSimulationResponse,
    TaxRuleWrite,
    TaxSettingsWrite,
    TaxSystemWrite,
)
from app.tax.services import TaxFrameworkService, TaxRetentionService, TaxRuleService


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
