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
from app.business.models.framework import (
    AttributeDefinition,
    BusinessProfile,
    CategoryAttributeRule,
    FirmBusinessProfile,
)
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models.customer import CreditControlSettings
from app.finance.models.finance import FinancialYear
from app.finance.models.tds_194q import Tds194QSettings
from app.firms.models import Firm
from app.loyalty.models.loyalty import LoyaltySettings
from app.messaging.models.messaging import MessagingSettings
from app.purchase.models.purchase import (
    PurchaseBudget,
    PurchaseWorkflowSettings,
    RolePurchaseApprovalLimit,
)
from app.sales.models import GeoCountry
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


@pytest.mark.parametrize("section", ["tax", "firm", "selling", "buying"])
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


@pytest.mark.parametrize("section", ["firm", "selling", "buying"])
def test_the_route_serves_each_new_section(session: Session, section: str) -> None:
    """Each subject is registered and answered by the one endpoint."""
    firm = _firm(session)

    state = _state(session, firm.id, section)

    assert section in SECTIONS
    assert state.section == section
    assert state.steps
