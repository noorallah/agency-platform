"""Where a firm stands on each step of a Settings subject."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.approvals.models import ApprovalRule
from app.batch_serial.models.batch_serial import BatchSaleSettings
from app.business.models.framework import (
    AttributeDefinition,
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    CategoryAttributeRule,
    FirmAttributeSwitch,
    FirmBusinessProfile,
    ProfileFeature,
    ProfileModule,
)
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models.customer import CreditControlSettings, CustomerGroup
from app.delivery_note.models.transporter import Transporter
from app.finance.models.finance import (
    AccountGroup,
    CostCenter,
    FinancialYear,
    FirmControlAccount,
    LedgerAccount,
    ProfitCenter,
)
from app.finance.models.tds_194q import Tds194QSettings
from app.firms.models import Firm
from app.firms.services.readiness import ALL_PURPOSES
from app.inventory.models.adjustment_approval import RoleStockAdjustmentLimit
from app.inventory.models.adjustment_reason import StockAdjustmentReason
from app.loyalty.models.loyalty import LoyaltyEntry, LoyaltySettings
from app.messaging.models.messaging import MessagingSettings
from app.pricing.models.price_level import PriceLevel
from app.pricing.models.price_list import PriceList
from app.promotions.models.promotion import Promotion
from app.purchase.models.purchase import (
    PurchaseBudget,
    PurchaseWorkflowSettings,
    RolePurchaseApprovalLimit,
)
from app.sales.models import GeoCountry
from app.sales.models.territory import (
    RouteTypeMaster,
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
)
from app.sales_order.models.sales_order import (
    PriceFloorSettings,
    RoleDiscountLimit,
    SalesWorkflowSettings,
)
from app.salesmen.models.salesman import Salesman
from app.settings_sections.api.router import settings_section_state
from app.settings_sections.schemas import SettingsSectionStateResponse
from app.settings_sections.services import SECTIONS
from app.tax.models import GstComplianceSettings, TaxProfile, TaxRule
from app.tax.schemas import TaxProfileWrite, TaxStatus, TaxSystemWrite
from app.tax.services import TaxFrameworkService, gst_template
from app.tcs.models.tcs import TcsSettings
from app.trade_licences.models.trade_licence import (
    TradeLicenceSettings,
    TradeLicenceType,
)
from app.uom.models.unit_set import UnitSet
from app.vendors.models.vendor import VendorCategory, VendorType

STEP_CODES = [
    "rates-and-profiles",
    "tax-rules",
    "tax-settings",
    "gst-documents",
    "tds-purchases",
]


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session() -> Session:
    """Return a session on a fresh in-memory store."""
    return _session_factory()()


def _firm(session: Session, code: str = "SET01") -> Firm:
    """Create a firm with nothing set up."""
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _scope(firm_id: UUID) -> ResolvedFirmScope:
    """Return a member's scope on the firm, holding no permission at all."""
    user_id = uuid4()
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=[],
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


def _state(
    session: Session, firm_id: UUID, section: str = "tax"
) -> SettingsSectionStateResponse:
    """Call the route function as a member of the firm."""
    response = settings_section_state(section, _scope(firm_id), session)
    assert response.data is not None
    return response.data


def _details(state: SettingsSectionStateResponse) -> dict[str, tuple[str, str]]:
    """Return each step's state and detail, keyed by its code."""
    return {step.code: (step.state, step.detail) for step in state.steps}


def _profile_by_hand(session: Session, firm_id: UUID, code: str = "VAT_5") -> None:
    """Give the firm one tax system and one profile, without the template."""
    actor_id = uuid4()
    country = GeoCountry(
        code="AE",
        name="United Arab Emirates",
        iso2="AE",
        iso3="ARE",
        phone_code="+971",
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(country)
    session.flush()
    framework = TaxFrameworkService(session)
    system = framework.create_system(
        TaxSystemWrite(
            country_id=country.id,
            business_profile_id=None,
            code="VAT",
            name="Value Added Tax",
            display_name="VAT",
            description=None,
            status=TaxStatus.ACTIVE,
            display_order=10,
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    framework.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            business_profile_id=None,
            code=code,
            name="VAT 5%",
            label="VAT 5%",
            description=None,
            status=TaxStatus.ACTIVE,
            display_order=1,
            is_historical=False,
            effective_from=date(2018, 1, 1),
            effective_to=None,
            components=[],
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    session.commit()


def test_an_empty_firm_has_two_steps_to_do(session: Session) -> None:
    """Profiles and rules are owed; the rest is the firm's choice."""
    firm = _firm(session)

    state = _state(session, firm.id)

    assert state.section == "tax"
    assert state.todo_count == 2
    assert [step.code for step in state.steps] == STEP_CODES
    assert _details(state) == {
        "rates-and-profiles": ("TODO", "None yet"),
        "tax-rules": ("TODO", "None yet"),
        "tax-settings": ("OPTIONAL", "Left as it comes"),
        "gst-documents": ("OPTIONAL", "Off"),
        "tds-purchases": ("OPTIONAL", "Off"),
    }


def test_the_gst_template_finishes_both_steps_and_is_named(session: Session) -> None:
    """A firm on the template is told so, with what it holds counted."""
    firm = _firm(session)
    gst_template.apply_india_gst_template(session, firm_id=firm.id, actor_id=uuid4())
    session.commit()

    state = _state(session, firm.id)

    # Eight slabs and the two reverse-charge profiles.
    assert state.todo_count == 0
    assert _details(state) == {
        "rates-and-profiles": ("DONE", "10 profiles, from the GST template"),
        "tax-rules": ("DONE", "9 active rules, from the GST template"),
        "tax-settings": ("OPTIONAL", "Set for this firm"),
        "gst-documents": ("OPTIONAL", "Off"),
        "tds-purchases": ("OPTIONAL", "Off"),
    }


def test_the_template_rule_codes_are_the_rules_the_template_switches_on(
    session: Session,
) -> None:
    """The list the check reads is the list the template writes."""
    firm = _firm(session)
    gst_template.apply_india_gst_template(session, firm_id=firm.id, actor_id=uuid4())
    session.commit()

    active = session.scalars(
        select(TaxRule.code).where(
            TaxRule.firm_id == firm.id, TaxRule.status == "ACTIVE"
        )
    ).all()

    assert sorted(active) == sorted(gst_template.TEMPLATE_RULE_CODES)


def test_a_template_firm_missing_a_slab_is_not_called_a_template_firm(
    session: Session,
) -> None:
    """Deleting one of the template's profiles drops the template words."""
    firm = _firm(session)
    gst_template.apply_india_gst_template(session, firm_id=firm.id, actor_id=uuid4())
    row = session.scalar(select(TaxProfile).where(TaxProfile.code == "GST_12_LOCAL"))
    assert row is not None
    row.is_deleted = True
    session.commit()

    state, detail = _details(_state(session, firm.id))["rates-and-profiles"]

    assert state == "DONE"
    assert "template" not in detail


def test_a_profile_made_by_hand_is_done_without_the_template_words(
    session: Session,
) -> None:
    """One profile is one profile, and no rule is still a step to do."""
    firm = _firm(session)
    _profile_by_hand(session, firm.id)

    state = _state(session, firm.id)

    assert state.todo_count == 1
    assert _details(state)["rates-and-profiles"] == ("DONE", "1 profile")
    assert _details(state)["tax-rules"] == ("TODO", "None yet")


def test_another_firms_setup_is_not_counted(session: Session) -> None:
    """Every count is the asking firm's own."""
    firm = _firm(session)
    other = _firm(session, "SET02")
    gst_template.apply_india_gst_template(session, firm_id=other.id, actor_id=uuid4())
    session.commit()

    assert _state(session, firm.id).todo_count == 2


def test_the_optional_steps_say_what_is_switched_on(session: Session) -> None:
    """E-invoicing from a date and 194Q switched on are both named."""
    firm = _firm(session)
    session.add(
        GstComplianceSettings(
            firm_id=firm.id, einvoice_applicable_from=date(2026, 4, 1)
        )
    )
    session.add(Tds194QSettings(firm_id=firm.id, is_enabled=True))
    session.commit()

    details = _details(_state(session, firm.id))

    assert details["gst-documents"] == ("OPTIONAL", "E-invoice on")
    assert details["tds-purchases"] == ("OPTIONAL", "On")


def test_an_unknown_section_is_refused(session: Session) -> None:
    """A subject nobody registered is not found, rather than empty."""
    firm = _firm(session)

    with pytest.raises(ResourceNotFoundError):
        _state(session, firm.id, "no-such-section")
    assert "no-such-section" not in SECTIONS


@pytest.mark.parametrize(
    "section",
    [
        "tax",
        "firm",
        "selling",
        "buying",
        "stock",
        "business-profile",
        "pricing",
        "territories",
        "account-structure",
        "party-lists",
    ],
)
def test_reading_the_state_writes_nothing(session: Session, section: str) -> None:
    """Opening a Settings subject issues selects and nothing else."""
    firm = _firm(session)
    gst_template.apply_india_gst_template(session, firm_id=firm.id, actor_id=uuid4())
    session.commit()
    statements: list[str] = []

    def record(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        """Keep every statement the read sends."""
        statements.append(statement.lstrip().upper())

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        _state(session, firm.id, section)
        # And a firm that has saved nothing: no row is made for it either.
        _state(session, uuid4(), section)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert statements
    assert all(statement.startswith("SELECT") for statement in statements)
    assert not session.new
    assert not session.dirty


FIRM_CODES = [
    "firm-profile",
    "financial-years",
    "numbering-series",
    "goods-types",
    "custom-fields",
    "custom-field-rules",
    "messaging",
    "approval-levels",
]
SELLING_CODES = [
    "sales-stages",
    "salesmen",
    "credit-control",
    "price-floor",
    "discount-limits",
    "loyalty-scheme",
    "tcs",
]
BUYING_CODES = ["purchase-settings", "approval-limits", "purchase-budgets"]


def _year(session: Session, firm_id: UUID, code: str, **values: object) -> None:
    """Give the firm one financial year."""
    start = int(code[:4])
    session.add(
        FinancialYear(
            firm_id=firm_id,
            code=code,
            name=f"FY {code}",
            starts_on=date(start, 4, 1),
            ends_on=date(start + 1, 3, 31),
            **values,
        )
    )
    session.commit()


def test_a_bare_firm_has_one_firm_step_to_do(session: Session) -> None:
    """Only an open year is owed; everything else is the firm's choice."""
    firm = _firm(session)

    state = _state(session, firm.id, "firm")

    assert state.section == "firm"
    assert [step.code for step in state.steps] == FIRM_CODES
    assert state.todo_count == 1
    assert _details(state) == {
        "firm-profile": ("OPTIONAL", "Not chosen: the firm runs as General"),
        "financial-years": ("TODO", "None open: nothing can be posted"),
        "numbering-series": ("OPTIONAL", "As each document comes"),
        "goods-types": ("OPTIONAL", "None yet"),
        "custom-fields": ("OPTIONAL", "None yet"),
        "custom-field-rules": ("OPTIONAL", "None yet"),
        "messaging": ("OPTIONAL", "Off"),
        "approval-levels": ("OPTIONAL", "None yet"),
    }


def test_a_year_is_done_while_open_and_owed_once_locked(session: Session) -> None:
    """A locked year is a closed one and does not count as open."""
    firm = _firm(session)
    _year(session, firm.id, "2025-26", is_locked=True)

    assert _details(_state(session, firm.id, "firm"))["financial-years"] == (
        "TODO",
        "None open: nothing can be posted",
    )

    _year(session, firm.id, "2026-27")
    assert _details(_state(session, firm.id, "firm"))["financial-years"] == (
        "DONE",
        "2026-27 open",
    )

    _year(session, firm.id, "2027-28")
    assert _details(_state(session, firm.id, "firm"))["financial-years"] == (
        "DONE",
        "2 years open",
    )


def test_a_firm_holding_things_is_told_what_it_holds(session: Session) -> None:
    """The profile is named, lists are counted and the switch reads On."""
    firm = _firm(session)
    other = _firm(session, "SET02")
    profile = BusinessProfile(code="PHARMA", name="Pharmacy", industry_type="PHARMA")
    session.add(profile)
    session.flush()
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            effective_from=datetime(2026, 4, 1, tzinfo=UTC),
        )
    )
    mine = AttributeDefinition(
        firm_id=firm.id, code="SHADE", name="Shade", data_type="TEXT"
    )
    session.add_all(
        [
            mine,
            # The platform's own definition and another firm's are not counted.
            AttributeDefinition(
                firm_id=None, code="IMEI", name="IMEI", data_type="TEXT"
            ),
            AttributeDefinition(
                firm_id=other.id, code="SIZE", name="Size", data_type="TEXT"
            ),
            MessagingSettings(firm_id=firm.id, is_enabled=True),
        ]
    )
    session.flush()
    session.add(CategoryAttributeRule(firm_id=firm.id, attribute_definition_id=mine.id))
    for level in (1, 2):
        session.add(
            ApprovalRule(
                firm_id=firm.id,
                document_type="PURCHASE_ORDER",
                level=level,
                min_amount=Decimal("1000"),
                role_code="FIRM_ADMIN",
            )
        )
    session.commit()
    _year(session, firm.id, "2026-27")

    state = _state(session, firm.id, "firm")

    assert state.todo_count == 0
    details = _details(state)
    assert details["firm-profile"] == ("OPTIONAL", "Pharmacy")
    assert details["custom-fields"] == ("OPTIONAL", "1 field")
    assert details["custom-field-rules"] == ("OPTIONAL", "1 rule")
    assert details["messaging"] == ("OPTIONAL", "On")
    assert details["approval-levels"] == ("OPTIONAL", "2 levels")


def test_a_bare_firm_owes_nothing_in_selling(session: Session) -> None:
    """Every selling step is optional and reads as it comes."""
    firm = _firm(session)

    state = _state(session, firm.id, "selling")

    assert [step.code for step in state.steps] == SELLING_CODES
    assert state.todo_count == 0
    assert _details(state) == {
        "sales-stages": ("OPTIONAL", "Left as it comes"),
        "salesmen": ("OPTIONAL", "None yet"),
        "credit-control": ("OPTIONAL", "Left as it comes: warns at 80%"),
        "price-floor": ("OPTIONAL", "Left as it comes"),
        "discount-limits": ("OPTIONAL", "None yet"),
        "loyalty-scheme": ("OPTIONAL", "Off"),
        "tcs": ("OPTIONAL", "Off"),
    }


def test_a_firm_that_needs_a_salesman_owes_one_until_it_has_one(
    session: Session,
) -> None:
    """Required salesmen turn the step TODO, then DONE once one is active."""
    firm = _firm(session)
    session.add(SalesWorkflowSettings(firm_id=firm.id, salesman_required=True))
    session.add(Salesman(firm_id=firm.id, name="Gone", is_active=False))
    session.commit()

    state = _state(session, firm.id, "selling")
    assert state.todo_count == 1
    assert _details(state)["salesmen"] == ("TODO", "None yet: every bill must name one")

    session.add(Salesman(firm_id=firm.id, name="Ravi"))
    session.commit()
    assert _details(_state(session, firm.id, "selling"))["salesmen"] == (
        "DONE",
        "1 salesman",
    )


def test_a_firm_that_has_set_up_selling_is_told_so(session: Session) -> None:
    """Saved rows, counted limits and switches on are all named."""
    firm = _firm(session)
    session.add_all(
        [
            SalesWorkflowSettings(firm_id=firm.id),
            Salesman(firm_id=firm.id, name="Ravi"),
            Salesman(firm_id=firm.id, name="Sunil"),
            CreditControlSettings(firm_id=firm.id),
            PriceFloorSettings(firm_id=firm.id),
            RoleDiscountLimit(
                firm_id=firm.id,
                role_code="SALES_EXECUTIVE",
                max_discount_percent=Decimal("5"),
            ),
            LoyaltySettings(firm_id=firm.id, is_enabled=True),
            TcsSettings(firm_id=firm.id, is_enabled=True),
        ]
    )
    session.commit()

    assert _details(_state(session, firm.id, "selling")) == {
        "sales-stages": ("OPTIONAL", "Set for this firm"),
        "salesmen": ("OPTIONAL", "2 salesmen"),
        "credit-control": ("OPTIONAL", "Set for this firm"),
        "price-floor": ("OPTIONAL", "Set for this firm"),
        "discount-limits": ("OPTIONAL", "1 role limit"),
        "loyalty-scheme": ("OPTIONAL", "On"),
        "tcs": ("OPTIONAL", "On"),
    }


def test_buying_reads_as_it_comes_then_what_was_set(session: Session) -> None:
    """A bare firm owes nothing; a set-up one is told what it holds."""
    firm = _firm(session)

    bare = _state(session, firm.id, "buying")
    assert [step.code for step in bare.steps] == BUYING_CODES
    assert bare.todo_count == 0
    assert _details(bare) == {
        "purchase-settings": ("OPTIONAL", "Left as it comes"),
        "approval-limits": ("OPTIONAL", "None yet"),
        "purchase-budgets": ("OPTIONAL", "None yet"),
    }

    session.add_all(
        [
            PurchaseWorkflowSettings(firm_id=firm.id),
            RolePurchaseApprovalLimit(
                firm_id=firm.id,
                role_code="PURCHASE_MANAGER",
                max_order_amount=Decimal("50000"),
            ),
            PurchaseBudget(
                firm_id=firm.id, budget_month=date(2026, 4, 1), amount=Decimal("1")
            ),
            PurchaseBudget(
                firm_id=firm.id, budget_month=date(2026, 5, 1), amount=Decimal("1")
            ),
        ]
    )
    session.commit()

    assert _details(_state(session, firm.id, "buying")) == {
        "purchase-settings": ("OPTIONAL", "Set for this firm"),
        "approval-limits": ("OPTIONAL", "1 role limit"),
        "purchase-budgets": ("OPTIONAL", "2 budgets"),
    }


@pytest.mark.parametrize(
    "section",
    [
        "firm",
        "selling",
        "buying",
        "stock",
        "business-profile",
        "pricing",
        "territories",
        "account-structure",
        "party-lists",
    ],
)
def test_the_route_serves_each_new_section(session: Session, section: str) -> None:
    """Each subject is registered and answered by the one endpoint."""
    firm = _firm(session)

    state = _state(session, firm.id, section)

    assert section in SECTIONS
    assert state.section == section
    assert state.steps


STOCK_CODES = [
    "adjustment-reasons",
    "adjustment-limits",
    "batch-rules",
]
BUSINESS_PROFILE_CODES = [
    "profile-assignment",
    "feature-management",
    "module-configuration",
    "attribute-definitions",
    "mandatory-attributes",
    "unit-sets",
]
PRICING_CODES = ["price-lists", "price-levels", "promotions", "loyalty"]


def test_stock_reads_as_it_comes_then_what_was_set(session: Session) -> None:
    """A bare firm owes nothing; a set-up one is told what it holds."""
    firm = _firm(session)

    bare = _state(session, firm.id, "stock")
    assert bare.section == "stock"
    assert [step.code for step in bare.steps] == STOCK_CODES
    assert bare.todo_count == 0
    assert _details(bare) == {
        "adjustment-reasons": ("OPTIONAL", "8 built in"),
        "adjustment-limits": ("OPTIONAL", "None yet"),
        "batch-rules": ("OPTIONAL", "Left as it comes"),
    }

    other = _firm(session, "SET02")
    session.add_all(
        [
            # A built-in reason the list wrote is not the firm's own.
            StockAdjustmentReason(
                firm_id=firm.id, code="DAMAGE", name="Damage", is_system=True
            ),
            StockAdjustmentReason(firm_id=firm.id, code="RATS", name="Rats"),
            StockAdjustmentReason(
                firm_id=firm.id, code="OLD", name="Old", is_active=False
            ),
            StockAdjustmentReason(firm_id=other.id, code="MINE", name="Mine"),
            RoleStockAdjustmentLimit(
                firm_id=firm.id, role_code="STORE_KEEPER", max_value=Decimal("500")
            ),
            BatchSaleSettings(firm_id=firm.id),
        ]
    )
    session.commit()

    assert _details(_state(session, firm.id, "stock")) == {
        "adjustment-reasons": ("OPTIONAL", "8 built in, 1 own"),
        "adjustment-limits": ("OPTIONAL", "1 role limit"),
        "batch-rules": ("OPTIONAL", "Set for this firm"),
    }


def test_a_bare_firm_owes_nothing_in_business_profile(session: Session) -> None:
    """No profile gates nothing, and no field leaves a rule nothing to name."""
    firm = _firm(session)

    state = _state(session, firm.id, "business-profile")

    assert state.section == "business-profile"
    assert [step.code for step in state.steps] == BUSINESS_PROFILE_CODES
    assert state.todo_count == 0
    assert _details(state) == {
        "profile-assignment": ("OPTIONAL", "Not chosen: the firm runs as General"),
        "feature-management": ("OPTIONAL", "No profile: nothing is switched off"),
        "module-configuration": ("OPTIONAL", "No profile: nothing is switched off"),
        "attribute-definitions": ("OPTIONAL", "None yet"),
        "mandatory-attributes": ("OPTIONAL", "None yet: add a field first"),
        "unit-sets": ("OPTIONAL", "None yet"),
    }


def test_a_profiled_firm_is_told_what_its_profile_switches_on(
    session: Session,
) -> None:
    """The profile is named, its switches counted, own and shared told apart."""
    firm = _firm(session)
    other = _firm(session, "SET02")
    profile = BusinessProfile(code="PHARMA", name="Pharmacy", industry_type="PHARMA")
    batch = BusinessFeature(code="BATCH", name="Batch", default_enabled=False)
    expiry = BusinessFeature(code="EXPIRY", name="Expiry", default_enabled=True)
    serial = BusinessFeature(code="SERIAL", name="Serial", default_enabled=True)
    sales = BusinessModule(code="SALES", name="Sales")
    hr = BusinessModule(code="HR", name="HR")
    session.add_all([profile, batch, expiry, serial, sales, hr])
    session.flush()
    hidden = AttributeDefinition(
        firm_id=None, code="IMEI", name="IMEI", data_type="TEXT"
    )
    shared = AttributeDefinition(
        firm_id=None, code="BRAND", name="Brand", data_type="TEXT"
    )
    mine = AttributeDefinition(
        firm_id=firm.id, code="SHADE", name="Shade", data_type="TEXT"
    )
    session.add_all(
        [
            FirmBusinessProfile(
                firm_id=firm.id,
                business_profile_id=profile.id,
                effective_from=datetime(2026, 4, 1, tzinfo=UTC),
            ),
            # Batch is switched on against its default, Serial off against it.
            ProfileFeature(business_profile_id=profile.id, feature_id=batch.id),
            ProfileFeature(
                business_profile_id=profile.id, feature_id=serial.id, is_enabled=False
            ),
            ProfileModule(
                business_profile_id=profile.id, module_id=hr.id, is_enabled=False
            ),
            hidden,
            shared,
            mine,
            AttributeDefinition(
                firm_id=other.id, code="SIZE", name="Size", data_type="TEXT"
            ),
            UnitSet(firm_id=None, name="Strip of 10", base_uom_id=uuid4()),
            UnitSet(firm_id=firm.id, name="Box of 6", base_uom_id=uuid4()),
            UnitSet(firm_id=other.id, name="Crate", base_uom_id=uuid4()),
        ]
    )
    session.flush()
    session.add_all(
        [
            # A shared field this firm switched off is not offered to it.
            FirmAttributeSwitch(
                firm_id=firm.id, attribute_definition_id=hidden.id, is_enabled=False
            ),
            CategoryAttributeRule(
                firm_id=None,
                category_code="TABLETS",
                attribute_definition_id=shared.id,
            ),
            CategoryAttributeRule(
                firm_id=firm.id,
                category_code="TABLETS",
                attribute_definition_id=mine.id,
            ),
            # A rule that ties a field without requiring it is not counted.
            CategoryAttributeRule(
                firm_id=firm.id,
                category_code="SYRUPS",
                attribute_definition_id=mine.id,
                is_mandatory=False,
            ),
            CategoryAttributeRule(
                firm_id=other.id,
                category_code="TABLETS",
                attribute_definition_id=shared.id,
            ),
        ]
    )
    session.commit()

    state = _state(session, firm.id, "business-profile")

    assert state.todo_count == 0
    assert _details(state) == {
        "profile-assignment": ("OPTIONAL", "Pharmacy"),
        "feature-management": ("OPTIONAL", "2 of 3 features on"),
        "module-configuration": ("OPTIONAL", "1 of 2 modules on"),
        "attribute-definitions": ("OPTIONAL", "1 own, 1 shared"),
        "mandatory-attributes": ("OPTIONAL", "1 own, 1 shared"),
        "unit-sets": ("OPTIONAL", "1 own, 1 shared"),
    }


def test_a_firm_with_a_field_but_no_rule_is_simply_none_yet(
    session: Session,
) -> None:
    """Once a field exists, no compulsory rule is just an empty list."""
    firm = _firm(session)
    session.add(
        AttributeDefinition(firm_id=None, code="IMEI", name="IMEI", data_type="TEXT")
    )
    session.commit()

    details = _details(_state(session, firm.id, "business-profile"))

    assert details["attribute-definitions"] == ("OPTIONAL", "1 shared")
    assert details["mandatory-attributes"] == ("OPTIONAL", "None yet")


def test_pricing_reads_as_it_comes_then_what_was_set(session: Session) -> None:
    """A bare firm owes nothing; a set-up one is told what it holds."""
    firm = _firm(session)

    bare = _state(session, firm.id, "pricing")
    assert bare.section == "pricing"
    assert [step.code for step in bare.steps] == PRICING_CODES
    assert bare.todo_count == 0
    assert _details(bare) == {
        "price-lists": ("OPTIONAL", "None yet"),
        "price-levels": ("OPTIONAL", "None yet"),
        "promotions": ("OPTIONAL", "None yet"),
        "loyalty": ("OPTIONAL", "Scheme off: none yet"),
    }

    other = _firm(session, "SET02")
    diwali = uuid4()
    customer = uuid4()
    session.add_all(
        [
            PriceList(
                firm_id=firm.id,
                code="STD",
                name="Standard",
                effective_from=date(2026, 4, 1),
            ),
            PriceList(
                firm_id=other.id,
                code="STD",
                name="Standard",
                effective_from=date(2026, 4, 1),
            ),
            PriceLevel(firm_id=firm.id, code="A", name="Retail"),
            PriceLevel(firm_id=firm.id, code="B", name="Wholesale"),
            PriceLevel(firm_id=firm.id, code="C", name="Old", is_active=False),
            # One offer in two revisions is one offer.
            Promotion(
                firm_id=firm.id,
                code="DIWALI",
                name="Diwali",
                status="INACTIVE",
                version_group_id=diwali,
                version_number=1,
            ),
            Promotion(
                firm_id=firm.id,
                code="DIWALI",
                name="Diwali",
                status="ACTIVE",
                version_group_id=diwali,
                version_number=2,
            ),
            Promotion(
                firm_id=firm.id,
                code="SUMMER",
                name="Summer",
                status="DRAFT",
                version_group_id=uuid4(),
            ),
            LoyaltySettings(firm_id=firm.id, is_enabled=True),
            LoyaltyEntry(
                firm_id=firm.id,
                customer_id=customer,
                kind="EARNED",
                points=Decimal("10"),
                earned_on=date(2026, 4, 1),
            ),
            LoyaltyEntry(
                firm_id=firm.id,
                customer_id=customer,
                kind="EARNED",
                points=Decimal("5"),
                earned_on=date(2026, 4, 2),
            ),
        ]
    )
    session.commit()

    assert _details(_state(session, firm.id, "pricing")) == {
        "price-lists": ("OPTIONAL", "1 list"),
        "price-levels": ("OPTIONAL", "2 levels"),
        "promotions": ("OPTIONAL", "2 offers, 1 running"),
        "loyalty": ("OPTIONAL", "1 customer"),
    }


TERRITORIES_CODES = ["territories", "route-types", "route-builder", "transporters"]
ACCOUNT_STRUCTURE_CODES = ["control-accounts", "cost-centers", "profit-centers"]
PARTY_LISTS_CODES = [
    "customer-groups",
    "vendor-categories",
    "vendor-types",
    "licence-types",
    "licence-check-settings",
]


def _territory(session: Session, firm_id: UUID, code: str, **values: object) -> UUID:
    """Create one territory node of the firm and return its id."""
    node = SalesTerritoryNode(
        firm_id=firm_id,
        hierarchy_level_id=uuid4(),
        code=code,
        name=code.title(),
        path=f"/{code}",
        **values,
    )
    session.add(node)
    session.flush()
    return node.id


def test_territories_read_as_they_come_then_what_was_set(session: Session) -> None:
    """A bare firm owes nothing; a set-up one is told what it holds."""
    firm = _firm(session)

    bare = _state(session, firm.id, "territories")
    assert bare.section == "territories"
    assert [step.code for step in bare.steps] == TERRITORIES_CODES
    assert bare.todo_count == 0
    assert _details(bare) == {
        "territories": ("OPTIONAL", "None yet"),
        "route-types": ("OPTIONAL", "None yet"),
        "route-builder": ("OPTIONAL", "None yet"),
        "transporters": ("OPTIONAL", "None yet"),
    }

    other = _firm(session, "SET02")
    north = _territory(session, firm.id, "NORTH")
    south = _territory(session, firm.id, "SOUTH")
    _territory(session, firm.id, "OLD", status="INACTIVE")
    theirs = _territory(session, other.id, "NORTH")
    session.add_all(
        [
            RouteTypeMaster(firm_id=firm.id, code="SALES", name="Sales round"),
            RouteTypeMaster(firm_id=firm.id, code="GONE", name="Gone", is_active=False),
            TerritoryCustomerAssignment(
                territory_id=north, customer_id=uuid4(), is_primary=False
            ),
            TerritoryCustomerAssignment(
                territory_id=north, customer_id=uuid4(), is_primary=False
            ),
            TerritoryCustomerAssignment(
                territory_id=south, customer_id=uuid4(), is_primary=False
            ),
            # Another firm's round, and a shop taken off one, are not counted.
            TerritoryCustomerAssignment(territory_id=theirs, customer_id=uuid4()),
            TerritoryCustomerAssignment(
                territory_id=south,
                customer_id=uuid4(),
                is_primary=False,
                is_deleted=True,
            ),
            Transporter(firm_id=firm.id, name="Swift Roadways"),
            Transporter(firm_id=other.id, name="Elsewhere Cargo"),
        ]
    )
    session.commit()

    assert _details(_state(session, firm.id, "territories")) == {
        "territories": ("OPTIONAL", "2 territories"),
        "route-types": ("OPTIONAL", "1 route type"),
        "route-builder": ("OPTIONAL", "3 shops on 2 rounds"),
        "transporters": ("OPTIONAL", "1 transporter"),
    }


def _ledger_account(session: Session, firm_id: UUID, code: str, **flags: bool) -> UUID:
    """Create one ledger account of the firm, under a group of its own."""
    group = AccountGroup(
        firm_id=firm_id, code=f"G{code}", name=f"Group {code}", account_type="ASSET"
    )
    session.add(group)
    session.flush()
    account = LedgerAccount(
        firm_id=firm_id,
        account_group_id=group.id,
        code=code,
        name=f"Account {code}",
        account_type="ASSET",
        **flags,
    )
    session.add(account)
    session.flush()
    return account.id


def test_a_bare_firm_owes_its_control_accounts(session: Session) -> None:
    """Posting refuses an unmapped purpose, so every one of them is owed."""
    firm = _firm(session)
    total = len(ALL_PURPOSES)

    bare = _state(session, firm.id, "account-structure")
    assert bare.section == "account-structure"
    assert [step.code for step in bare.steps] == ACCOUNT_STRUCTURE_CODES
    assert bare.todo_count == 1
    assert _details(bare) == {
        "control-accounts": ("TODO", f"{total} of {total} unmapped"),
        "cost-centers": ("OPTIONAL", "None yet"),
        "profit-centers": ("OPTIONAL", "None yet"),
    }

    account = _ledger_account(session, firm.id, "1000")
    session.add(
        FirmControlAccount(
            firm_id=firm.id, purpose=ALL_PURPOSES[0].value, ledger_account_id=account
        )
    )
    session.commit()
    details = _details(_state(session, firm.id, "account-structure"))
    assert details["control-accounts"] == ("TODO", f"{total - 1} of {total} unmapped")


def test_a_mapped_firm_is_done_and_told_its_centres(session: Session) -> None:
    """Every purpose mapped is done; centres are counted, another firm's not."""
    firm = _firm(session)
    other = _firm(session, "SET02")
    account = _ledger_account(session, firm.id, "1000")
    session.add_all(
        [
            *(
                FirmControlAccount(
                    firm_id=firm.id, purpose=purpose.value, ledger_account_id=account
                )
                for purpose in ALL_PURPOSES
            ),
            CostCenter(firm_id=firm.id, code="SHOP", name="Shop"),
            CostCenter(firm_id=firm.id, code="VAN", name="Van"),
            CostCenter(firm_id=firm.id, code="OLD", name="Old", is_active=False),
            ProfitCenter(firm_id=other.id, code="NORTH", name="North"),
        ]
    )
    session.commit()

    state = _state(session, firm.id, "account-structure")
    assert state.todo_count == 0
    assert _details(state) == {
        "control-accounts": ("DONE", f"All {len(ALL_PURPOSES)} mapped"),
        "cost-centers": ("OPTIONAL", "2 centres"),
        "profit-centers": ("OPTIONAL", "None yet"),
    }


def test_an_account_needing_a_centre_owes_one_until_there_is_one(
    session: Session,
) -> None:
    """A line on such an account is refused without a centre, so one is owed."""
    firm = _firm(session)
    _ledger_account(session, firm.id, "4000", requires_profit_center=True)
    _ledger_account(session, firm.id, "4100", requires_profit_center=True)
    session.commit()

    details = _details(_state(session, firm.id, "account-structure"))
    assert details["cost-centers"] == ("OPTIONAL", "None yet")
    assert details["profit-centers"] == ("TODO", "None yet: 2 accounts need one")

    session.add(ProfitCenter(firm_id=firm.id, code="NORTH", name="North"))
    session.commit()
    details = _details(_state(session, firm.id, "account-structure"))
    assert details["profit-centers"] == ("OPTIONAL", "1 centre")


def test_party_lists_read_as_they_come_then_what_was_set(session: Session) -> None:
    """A bare firm owes nothing; a set-up one is told what it holds."""
    firm = _firm(session)

    bare = _state(session, firm.id, "party-lists")
    assert bare.section == "party-lists"
    assert [step.code for step in bare.steps] == PARTY_LISTS_CODES
    assert bare.todo_count == 0
    assert _details(bare) == {
        "customer-groups": ("OPTIONAL", "None yet"),
        "vendor-categories": ("OPTIONAL", "None yet"),
        "vendor-types": ("OPTIONAL", "None yet"),
        "licence-types": ("OPTIONAL", "None yet"),
        "licence-check-settings": ("OPTIONAL", "Left as it comes"),
    }

    other = _firm(session, "SET02")
    session.add_all(
        [
            CustomerGroup(firm_id=firm.id, code="RET", name="Retailer"),
            CustomerGroup(firm_id=firm.id, code="WHL", name="Wholesaler"),
            CustomerGroup(firm_id=other.id, code="RET", name="Retailer"),
            VendorCategory(firm_id=firm.id, code="PHARMA", name="Pharma"),
            VendorCategory(firm_id=firm.id, code="OLD", name="Old", is_active=False),
            VendorType(firm_id=firm.id, code="MFR", name="Manufacturer"),
            VendorType(firm_id=firm.id, code="DIST", name="Distributor"),
            TradeLicenceType(firm_id=firm.id, code="DL", name="Drug licence"),
            TradeLicenceSettings(firm_id=firm.id, sale_enforcement="BLOCK"),
        ]
    )
    session.commit()

    assert _details(_state(session, firm.id, "party-lists")) == {
        "customer-groups": ("OPTIONAL", "2 groups"),
        "vendor-categories": ("OPTIONAL", "1 category"),
        "vendor-types": ("OPTIONAL", "2 types"),
        "licence-types": ("OPTIONAL", "1 licence type"),
        "licence-check-settings": ("OPTIONAL", "Set for this firm"),
    }
