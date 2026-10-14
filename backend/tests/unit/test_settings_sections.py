"""Where a firm stands on each step of a Settings subject."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.models.tds_194q import Tds194QSettings
from app.firms.models import Firm
from app.sales.models import GeoCountry
from app.settings_sections.api.router import settings_section_state
from app.settings_sections.schemas import SettingsSectionStateResponse
from app.settings_sections.services import SECTIONS
from app.tax.models import GstComplianceSettings, TaxProfile, TaxRule
from app.tax.schemas import TaxProfileWrite, TaxStatus, TaxSystemWrite
from app.tax.services import TaxFrameworkService, gst_template

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


def test_reading_the_state_writes_nothing(session: Session) -> None:
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
        _state(session, firm.id)
        # And a firm that has saved nothing: no row is made for it either.
        _state(session, uuid4())
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert statements
    assert all(statement.startswith("SELECT") for statement in statements)
    assert not session.new
    assert not session.dirty
