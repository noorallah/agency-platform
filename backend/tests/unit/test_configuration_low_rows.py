"""The configuration module's Low rows, D-CFG-18 to D-CFG-23.

Each test writes the way a person or a client would and then reads back what
the defect row said went wrong: a counter a PUT could move, three answers to
one question about a firm's profile, a query per row of a list, writes that
recorded nothing or reset what they did not mention, and seeded series that
the modules then numbered from under one another's prefix.
"""

# ruff: noqa: D103

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.gating import resolve_profile_id
from app.business.models import (
    AttributeDefinition,
    BusinessFeature,
    BusinessProfile,
    FirmBusinessProfile,
)
from app.business.schemas import BusinessProfileCreate, FirmBusinessProfileAssign
from app.business.services import AttributeService, BusinessProfileFrameworkService
from app.common.audit.models import AuditLog
from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.api.router import _responses as customer_responses
from app.customers.models import Customer, CustomerAttributeValue
from app.document_framework.models import DocumentLine
from app.document_framework.schemas import (
    DocumentNumberingRuleCreate,
    DocumentNumberingRuleUpdate,
    DocumentPrintTemplateWrite,
    DocumentStateCreate,
    DocumentStateUpdate,
    DocumentTypeCreate,
)
from app.document_framework.services import DocumentFrameworkService
from app.document_framework.services.print_support import PRINTABLE_DOCUMENT_TYPES
from app.document_framework.services.print_template_service import (
    DocumentPrintTemplateService,
)
from app.firms.models import Firm
from app.firms.services.readiness import FirmReadinessService, store_steps
from app.identity.models import User, UserFirm, UserPreferences
from app.identity.schemas.api import UserPreferencesUpdate
from app.identity.services.identity_service import IdentityService
from app.loyalty.schemas.loyalty import LoyaltySettingsWrite
from app.loyalty.services.loyalty_service import LoyaltyService
from app.sales.schemas.territory import (
    GeoCountryWrite,
    GeoStateWrite,
    HierarchyLevelInput,
    HierarchyUpdateRequest,
)
from app.sales.services import SalesTerritoryService
from app.uom.models import BusinessProfileUomDefault, Uom
from app.uom.schemas.uom import (
    BusinessProfileUomDefaultUpsert,
    ConversionRuleUpdate,
    IndustryTemplateCreate,
    IndustryTemplateUpdate,
    UomCreate,
    UomUpdate,
)
from app.uom.services.uom_service import UomService

ACTOR = uuid4()

#: The module, not the `APIRouter` the package re-exports under the same name.
uom_router = importlib.import_module("app.uom.api.router")


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str = "LOW01") -> Firm:
    row = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _rows(session: Session, action: str) -> list[AuditLog]:
    return list(session.scalars(select(AuditLog).where(AuditLog.action == action)))


def _type(
    service: DocumentFrameworkService,
    firm: Firm,
    code: str,
    configuration: dict[str, object] | None = None,
) -> UUID:
    row = service.create_type(
        firm.id,
        DocumentTypeCreate(code=code, name=code.title(), configuration=configuration),
        ACTOR,
    )
    return row.id


# ---------------------------------------------------------------------------
# D-CFG-18 -- numbering and the document framework
# ---------------------------------------------------------------------------


def test_an_edit_cannot_state_the_counter() -> None:
    for owned in ("next_sequence", "last_scope_signature"):
        with pytest.raises(PydanticValidationError):
            DocumentNumberingRuleUpdate.model_validate(
                {
                    "document_type_id": str(uuid4()),
                    "code": "RC",
                    "name": "Receipts",
                    owned: 3 if owned == "next_sequence" else "X",
                }
            )


def test_a_series_cannot_move_under_another_type_or_another_firms() -> None:
    session = _session()
    firm = _firm(session)
    other = _firm(session, "LOW02")
    service = DocumentFrameworkService(session)
    receipts = _type(service, firm, "RECEIPT")
    payments = _type(service, firm, "PAYMENT")
    theirs = _type(service, other, "THEIRS")
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=receipts,
            code="RC",
            name="Receipts",
            prefix="RC",
            include_financial_year=True,
        ),
        ACTOR,
    )

    with pytest.raises(ValidationError, match="another document type"):
        service.update_numbering_rule(
            firm.id,
            rule.id,
            DocumentNumberingRuleUpdate(
                document_type_id=payments, code="RC", name="Receipts"
            ),
            ACTOR,
        )
    with pytest.raises(ResourceNotFoundError):
        service.create_numbering_rule(
            firm.id,
            DocumentNumberingRuleCreate(
                document_type_id=theirs,
                code="XX",
                name="X",
                prefix="XX",
                include_financial_year=True,
            ),
            ACTOR,
        )


def test_a_module_type_keeps_its_lifecycle_its_code_and_its_existence() -> None:
    session = _session()
    firm = _firm(session)
    service = DocumentFrameworkService(session)
    type_id = _type(service, firm, "SALES_ORDER", {"module": "SALES_ORDER"})
    state = service.create_state(
        firm.id,
        DocumentStateCreate(document_type_id=type_id, code="DRAFT", name="Draft"),
        ACTOR,
        module_bootstrap=True,
    )

    renamed = service.update_state(
        firm.id,
        state.id,
        DocumentStateUpdate(document_type_id=type_id, code="DRAFT", name="Open"),
        ACTOR,
    )
    assert renamed.name == "Open"
    with pytest.raises(ValidationError, match="allows_edit"):
        service.update_state(
            firm.id,
            state.id,
            DocumentStateUpdate(
                document_type_id=type_id, code="DRAFT", name="Open", allows_edit=False
            ),
            ACTOR,
        )
    with pytest.raises(ValidationError, match="cannot be added"):
        service.create_state(
            firm.id,
            DocumentStateCreate(document_type_id=type_id, code="HELD", name="Held"),
            ACTOR,
        )
    with pytest.raises(ValidationError, match="cannot be deleted"):
        service.delete_type(firm.id, type_id, ACTOR)


def test_a_switched_off_type_issues_no_number() -> None:
    session = _session()
    firm = _firm(session)
    service = DocumentFrameworkService(session)
    type_id = _type(service, firm, "RECEIPT")
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=type_id,
            code="RC",
            name="Receipts",
            prefix="RC",
            include_financial_year=True,
        ),
        ACTOR,
    )
    service.get_type(firm.id, type_id).is_active = False
    session.flush()

    with pytest.raises(ValidationError, match="switched off"):
        service.reserve_number(rule.id, firm_id=firm.id)


def test_a_print_template_names_a_printable_type_and_keeps_what_was_not_sent() -> None:
    session = _session()
    firm = _firm(session)
    service = DocumentPrintTemplateService(session)
    with pytest.raises(ValidationError, match="not a document that prints"):
        service.set(
            "SALES_INVOCE",
            DocumentPrintTemplateWrite(),
            firm_scope=firm.id,
            actor_id=ACTOR,
        )

    service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite(header_note="Wholesale only"),
        firm_scope=firm.id,
        actor_id=ACTOR,
    )
    # The desktop's Print settings sends no header_note.
    saved = service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite.model_validate({"terms": "30 days"}),
        firm_scope=firm.id,
        actor_id=ACTOR,
    )
    assert saved.header_note == "Wholesale only"
    assert saved.terms == "30 days"


def test_every_print_service_reads_a_printable_type() -> None:
    from app.delivery_note.services import challan_print_service
    from app.purchase.services import purchase_print_service
    from app.quotation.services import quotation_print_service
    from app.sales_invoice.services import invoice_print_service
    from app.sales_return.services import credit_note_print_service

    printed = {
        module.DOCUMENT_TYPE
        for module in (
            challan_print_service,
            purchase_print_service,
            quotation_print_service,
            invoice_print_service,
            credit_note_print_service,
        )
    }
    assert printed == PRINTABLE_DOCUMENT_TYPES


# ---------------------------------------------------------------------------
# D-CFG-19 -- one answer to "which profile is this firm on"
# ---------------------------------------------------------------------------


def test_no_resolvable_profile_is_ungated_not_some_other_profile() -> None:
    session = _session()
    firm = _firm(session)
    framework = BusinessProfileFrameworkService(session)
    # An ACTIVE profile that is not the default and not assigned.
    framework.create_profile(
        BusinessProfileCreate(
            code="PHARMA", name="Pharma", industry_type="PHARMACY", status="ACTIVE"
        ),
        ACTOR,
    )
    session.add(BusinessFeature(code="BARCODE", name="Barcode", default_enabled=False))
    session.commit()

    assert resolve_profile_id(session, firm.id) is None
    # The gate refuses nothing, so the list offers everything -- it used to
    # answer PHARMA's list, a profile the firm is not on.
    codes = {feature.code for feature, _ in framework.active_features(firm.id)}
    assert "BARCODE" in codes
    assert AttributeService(session)._profile_id(firm.id) is None


def test_the_three_callers_agree_on_an_assigned_profile() -> None:
    session = _session()
    firm = _firm(session)
    framework = BusinessProfileFrameworkService(session)
    profile = framework.create_profile(
        BusinessProfileCreate(
            code="FOOD", name="Food", industry_type="FOOD", status="ACTIVE"
        ),
        ACTOR,
    )
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=utc_now(),
        )
    )
    session.commit()

    assert resolve_profile_id(session, firm.id) == profile.id
    assert AttributeService(session)._profile_id(firm.id) == profile.id


# ---------------------------------------------------------------------------
# D-CFG-20 -- one custom-field read per page
# ---------------------------------------------------------------------------


def test_a_page_of_customers_reads_its_custom_fields_once() -> None:
    session = _session()
    firm = _firm(session)
    definition = AttributeDefinition(
        code="ROUTE_NOTE", name="Route note", entity_type="CUSTOMER", data_type="TEXT"
    )
    session.add(definition)
    customers = []
    for index in range(5):
        customer = Customer(
            firm_id=firm.id,
            code=f"C{index}",
            customer_type="BUSINESS",
            name=f"Customer {index}",
            display_name=f"Customer {index}",
            currency_code="INR",
            status="ACTIVE",
        )
        session.add(customer)
        customers.append(customer)
    session.flush()
    session.add(
        CustomerAttributeValue(
            firm_id=firm.id,
            customer_id=customers[2].id,
            attribute_definition_id=definition.id,
            value_text="Behind the temple",
        )
    )
    session.commit()

    statements: list[str] = []

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        responses = customer_responses(customers, session)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    reads = [text for text in statements if "customer_attribute_values" in text]
    assert len(reads) == 1
    by_code = {row.code: row.attributes for row in responses}
    assert [value.value_text for value in by_code["C2"]] == ["Behind the temple"]
    assert by_code["C0"] == []


# ---------------------------------------------------------------------------
# D-CFG-21 -- settings, units and places
# ---------------------------------------------------------------------------


def _identity(session: Session) -> IdentityService:
    return IdentityService(
        session,
        Settings(
            environment=Environment.TESTING,
            bootstrap_admin_password="Test-Bootstrap-Only1!",
        ),
    )


def test_preferences_read_writes_nothing_and_a_change_names_its_firm() -> None:
    session = _session()
    firm = _firm(session)
    user = User(email="low@example.com", full_name="Low", password_hash="x")
    session.add(user)
    session.flush()
    session.add(UserFirm(user_id=user.id, firm_id=firm.id, is_active=True))
    session.commit()
    service = _identity(session)

    service.get_user_preferences(user.id)
    assert session.query(UserPreferences).count() == 0
    # Stating a default changes nothing, so nothing is written at all.
    service.update_user_preferences(user.id, UserPreferencesUpdate(rows_per_page=20))
    assert session.query(UserPreferences).count() == 0
    assert _rows(session, "user_preferences.updated") == []

    service.update_user_preferences(
        user.id, UserPreferencesUpdate(default_firm_id=firm.id, rows_per_page=50)
    )
    [row] = _rows(session, "user_preferences.updated")
    assert row.firm_id == firm.id
    assert (row.after_data or {})["rows_per_page"] == 50
    assert (row.before_data or {})["rows_per_page"] == 20


def test_an_explicit_null_on_a_required_field_is_refused_by_name() -> None:
    for model, field in (
        (UomUpdate, "name"),
        (ConversionRuleUpdate, "conversion_factor"),
        (LoyaltySettingsWrite, "is_enabled"),
        (UserPreferencesUpdate, "language"),
    ):
        with pytest.raises(PydanticValidationError, match=field):
            model.model_validate({field: None})
    # Where null is a real value it still clears.
    assert UomUpdate.model_validate({"symbol": None}).symbol is None
    assert LoyaltySettingsWrite.model_validate({"expiry_months": None})
    assert ConversionRuleUpdate.model_validate({"effective_to": None})
    assert UserPreferencesUpdate.model_validate({"default_firm_id": None})


def test_the_hierarchy_read_is_audited_and_a_put_keeps_unstated_flags() -> None:
    session = _session()
    firm = _firm(session)
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=ACTOR)
    assert len(_rows(session, "sales_territory.hierarchy.created")) == 1
    service.get_hierarchy(firm_scope=firm.id, actor_id=ACTOR)
    assert len(_rows(session, "sales_territory.hierarchy.created")) == 1

    levels = [
        HierarchyLevelInput(
            level_order=level.level_order,
            level_code=level.level_code,
            display_name=level.display_name,
        )
        for level in hierarchy.levels
    ]
    service.update_hierarchy(
        firm_scope=firm.id,
        actor_id=ACTOR,
        payload=HierarchyUpdateRequest(
            max_levels=6, enforce_customer_leaf_assignment=True, levels=levels
        ),
    )
    # A second save that does not mention the flag or the levels' own flags.
    after = service.update_hierarchy(
        firm_scope=firm.id,
        actor_id=ACTOR,
        payload=HierarchyUpdateRequest(max_levels=6, levels=levels),
    )
    assert after.enforce_customer_leaf_assignment is True
    # REGION and TERRITORY were created mandatory; a rename kept it.
    assert [level.is_mandatory for level in after.levels][:2] == [True, True]
    assert after.levels[2].is_mandatory is False


def test_readiness_counts_a_live_profile_and_live_people_only() -> None:
    session = _session()
    firm = _firm(session)
    profile = BusinessProfile(
        code="FOOD", name="Food", industry_type="FOOD", status="ACTIVE"
    )
    session.add(profile)
    session.flush()
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            is_active=False,
            effective_from=utc_now(),
        )
    )
    gone = User(
        email="gone@example.com", full_name="Gone", password_hash="x", is_deleted=True
    )
    session.add(gone)
    session.flush()
    session.add(UserFirm(user_id=gone.id, firm_id=firm.id, is_active=True))
    session.commit()

    steps = {step.key: step for step in store_steps(session, firm.id, utc_now().date())}
    assert steps["business_profile"].status.value == "MISSING"
    readiness = FirmReadinessService(session).readiness(firm, session)
    members = next(step for step in readiness.steps if step.key == "members")
    assert members.status.value == "MISSING"


def test_assigning_a_profile_without_notes_keeps_the_notes() -> None:
    session = _session()
    firm = _firm(session)
    framework = BusinessProfileFrameworkService(session)
    profile = framework.create_profile(
        BusinessProfileCreate(
            code="FOOD", name="Food", industry_type="FOOD", status="ACTIVE"
        ),
        ACTOR,
    )
    framework.assign_profile_to_firm(
        firm.id,
        FirmBusinessProfileAssign(
            business_profile_id=profile.id, notes="Agreed with the owner"
        ),
        ACTOR,
    )
    row = framework.assign_profile_to_firm(
        firm.id,
        FirmBusinessProfileAssign.model_validate(
            {"business_profile_id": str(profile.id)}
        ),
        ACTOR,
    )
    assert row.notes == "Agreed with the owner"


def test_a_unit_on_a_document_line_cannot_be_deleted_and_a_deleted_code_returns() -> (
    None
):
    session = _session()
    firm = _firm(session)
    service = UomService(session)
    used = service.create_uom(UomCreate(code="DOZ", name="Dozen"), actor_id=ACTOR)
    session.add(
        DocumentLine(
            firm_id=firm.id,
            document_header_id=uuid4(),
            line_number=1,
            uom_id=used.id,
        )
    )
    session.commit()
    with pytest.raises(ValidationError, match="documents or stock movements"):
        service.delete_uom(used.id, actor_id=ACTOR)

    spare = service.create_uom(UomCreate(code="GROSS", name="Gross"), actor_id=ACTOR)
    service.delete_uom(spare.id, actor_id=ACTOR)
    again = service.create_uom(UomCreate(code="GROSS", name="Gross"), actor_id=ACTOR)
    assert again.id != spare.id


def test_the_loyalty_seeder_restating_the_scheme_writes_nothing() -> None:
    session = _session()
    firm = _firm(session)
    service = LoyaltyService(session)
    scheme = LoyaltySettingsWrite(
        is_enabled=True,
        points_per_amount=Decimal("1"),
        amount_per_point=Decimal("1"),
    )
    service.write_settings(firm.id, scheme, actor_id=ACTOR)
    service.write_settings(firm.id, scheme, actor_id=ACTOR)
    assert len(_rows(session, "loyalty.settings_changed")) == 1


def test_a_place_code_is_unique_per_parent_and_an_edit_keeps_what_it_omits() -> None:
    session = _session()
    service = SalesTerritoryService(session)
    india = service.create_country(
        GeoCountryWrite(code="IN", name="India", iso2="IN"), actor_id=ACTOR
    )
    nepal = service.create_country(
        GeoCountryWrite(code="NP", name="Nepal"), actor_id=ACTOR
    )
    service.create_state(
        GeoStateWrite(country_id=nepal.id, code="KA", name="Karnali"),
        actor_id=ACTOR,
    )
    karnataka = service.create_state(
        GeoStateWrite(country_id=india.id, code="KT", name="Karnataka"),
        actor_id=ACTOR,
    )
    renamed = service.update_state(
        karnataka.id,
        GeoStateWrite(country_id=india.id, code="KA", name="Karnataka"),
        actor_id=ACTOR,
    )
    assert renamed.code == "KA"

    service.update_country(
        india.id,
        GeoCountryWrite(code="IN", name="India", iso2="IN", is_active=False),
        actor_id=ACTOR,
    )
    kept = service.update_country(
        india.id,
        GeoCountryWrite.model_validate({"code": "IN", "name": "Bharat"}),
        actor_id=ACTOR,
    )
    assert kept.is_active is False
    assert kept.iso2 == "IN"


def test_a_profile_wide_default_reaches_every_firms_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller_store = _session()
    other_store = _session()
    platform = _session()
    caller = _firm(platform, "HOME")
    elsewhere = _firm(platform, "AWAY")
    for store in (caller_store, other_store):
        store.add(
            BusinessProfile(
                code="FOOD", name="Food", industry_type="FOOD", status="ACTIVE"
            )
        )
        store.commit()
    home_profile = caller_store.scalar(select(BusinessProfile))
    assert home_profile is not None

    @contextmanager
    def stores(request: object, firm_id: UUID) -> Iterator[Session]:
        assert firm_id == elsewhere.id
        yield other_store

    monkeypatch.setattr(uom_router, "firm_store_session", stores)
    unreached = uom_router._write_profile_default_in_every_store(
        request=None,  # type: ignore[arg-type]
        db=caller_store,
        platform_db=platform,
        caller_firm_id=caller.id,
        profile_id=home_profile.id,
        data=BusinessProfileUomDefaultUpsert(allow_fraction=True),
        actor_id=ACTOR,
    )

    assert unreached == []
    row = other_store.scalar(select(BusinessProfileUomDefault))
    assert row is not None
    assert row.firm_id is None
    assert row.allow_fraction is True


# ---------------------------------------------------------------------------
# D-CFG-22 -- the demo seeder's series
# ---------------------------------------------------------------------------


def test_the_seeded_series_pass_the_check_a_persons_would() -> None:
    from scripts.generate_sample_data import _seed_document_framework

    session = _session()
    firm = _firm(session)

    class _Context:
        pass

    context = _Context()
    context.firm = firm  # type: ignore[attr-defined]
    _seed_document_framework(
        session=session,
        context=context,  # type: ignore[arg-type]
        actor_id=ACTOR,
        docs=(),
        sample_product=None,  # type: ignore[arg-type]
        sample_uom=None,  # type: ignore[arg-type]
        sample_tax_profile=None,  # type: ignore[arg-type]
        branch_id=uuid4(),
        warehouse_id=uuid4(),
    )
    rules = DocumentFrameworkService(session).list_numbering_rules(
        firm.id, 1, 50, None, None, "code", False
    )[0]
    prefixes = [rule.prefix for rule in rules]
    assert len(prefixes) == 7
    assert len(set(prefixes)) == 7
    assert "PURCHASE" not in prefixes and "SALES" not in prefixes


# ---------------------------------------------------------------------------
# D-CFG-23 -- industry templates and profile defaults are audited
# ---------------------------------------------------------------------------


def test_industry_templates_and_profile_defaults_write_the_change() -> None:
    session = _session()
    firm = _firm(session)
    service = UomService(session)
    template = service.create_industry_template(
        IndustryTemplateCreate(code="FOOD", name="Food", industry_type="FOOD"),
        actor_id=ACTOR,
    )
    service.update_industry_template(
        template.id, IndustryTemplateUpdate(name="Food and grocery"), actor_id=ACTOR
    )
    service.delete_industry_template(template.id, actor_id=ACTOR)
    assert len(_rows(session, "uom.industry_template.created")) == 1
    [updated] = _rows(session, "uom.industry_template.updated")
    assert (updated.after_data or {})["name"] == "Food and grocery"
    assert len(_rows(session, "uom.industry_template.deleted")) == 1

    unit = session.scalar(select(Uom)) or service.create_uom(
        UomCreate(code="KG", name="Kilogram"), actor_id=ACTOR
    )
    profile = BusinessProfile(
        code="FOOD", name="Food", industry_type="FOOD", status="ACTIVE"
    )
    session.add(profile)
    session.commit()
    for _ in range(2):
        service.upsert_profile_default(
            firm_scope=firm.id,
            profile_id=profile.id,
            data=BusinessProfileUomDefaultUpsert(base_uom_id=unit.id),
            actor_id=ACTOR,
        )
    assert len(_rows(session, "uom.profile_default.created")) == 1
    # The same units again moved nothing, so no second row.
    assert _rows(session, "uom.profile_default.updated") == []
    service.upsert_profile_default(
        firm_scope=firm.id,
        profile_id=profile.id,
        data=BusinessProfileUomDefaultUpsert(base_uom_id=unit.id, allow_fraction=True),
        actor_id=ACTOR,
    )
    [changed] = _rows(session, "uom.profile_default.updated")
    assert (changed.after_data or {})["allow_fraction"] is True
    assert changed.firm_id == firm.id
