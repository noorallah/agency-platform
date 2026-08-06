"""Business profile framework service and authorization tests."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile
from app.business.api.router import _resolve_firm_scope
from app.business.schemas import (
    BusinessFeatureCreate,
    BusinessModuleCreate,
    BusinessProfileCreate,
    FirmBusinessProfileAssign,
)
from app.business.services import BusinessProfileFrameworkService
from app.business.system_seed import seed_business_profiles
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal, require_platform_admin
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm


def _session_factory() -> sessionmaker[Session]:
    """Create one in-memory database for service and API helper tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
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


def _principal(
    user_id: UUID,
    *,
    roles: set[str] | None = None,
    firm_id: UUID | None = None,
) -> Principal:
    role_values = roles or set()
    return Principal(
        subject=user_id,
        roles=frozenset(role_values),
        permissions=frozenset({"PLATFORM_VIEW"}),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=sorted(role_values),
        ),
        firm_id=firm_id,
    )


def test_business_profile_crud_and_default_switching() -> None:
    """Support profile CRUD while preserving exactly one chosen default profile."""
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()

    first = service.create_profile(
        BusinessProfileCreate(
            code="GENERIC",
            name="Generic",
            industry_type="GENERIC",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    second = service.create_profile(
        BusinessProfileCreate(
            code="PHARMACY",
            name="Pharmacy",
            industry_type="PHARMACY",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )

    session.refresh(first)
    assert first.is_default is False
    assert second.is_default is True
    rows, total = service.list_profiles(1, 20, "PHAR", "code", False)
    assert total == 1
    assert rows[0].code == "PHARMACY"


def test_profile_feature_module_assignment_and_runtime_resolution() -> None:
    """Resolve active features/modules from profile defaults and explicit toggles."""
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()
    profile = service.create_profile(
        BusinessProfileCreate(
            code="SERVICE",
            name="Service",
            industry_type="SERVICE",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    feature = service.create_feature(
        BusinessFeatureCreate(
            code="PROJECT_MANAGEMENT",
            name="Project Management",
            default_enabled=False,
        ),
        actor,
    )
    module = service.create_module(
        BusinessModuleCreate(
            code="PROJECTS",
            name="Projects",
            ui_route="projects",
            default_enabled=False,
        ),
        actor,
    )
    service.set_profile_features(profile.id, [feature.id], actor)
    service.set_profile_modules(profile.id, [module.id], actor)

    active_features = service.active_features(None)
    active_modules = service.active_modules(None)
    assert any(item[0].code == "PROJECT_MANAGEMENT" for item in active_features)
    assert any(item[0].code == "PROJECTS" for item in active_modules)


def test_firm_assignment_and_scope_authorization() -> None:
    """Assign profile to firm and enforce selected-firm membership checks."""
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()
    profile = service.create_profile(
        BusinessProfileCreate(
            code="RETAIL",
            name="Retail",
            industry_type="RETAIL",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    firm = _firm(session, "RET")
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    assignment = service.assign_profile_to_firm(
        firm.id,
        FirmBusinessProfileAssign(business_profile_id=profile.id),
        actor,
    )
    assert assignment.business_profile_id == profile.id
    assert service.get_firm_assignment(firm.id) is not None

    principal = _principal(user_id, firm_id=firm.id)
    assert _resolve_firm_scope(principal, session, firm.id, None) == firm.id
    with pytest.raises(AuthorizationError):
        _resolve_firm_scope(principal, session, uuid4(), None)


def test_platform_admin_dependency_rejects_non_admin_claim() -> None:
    """Keep business profile management restricted to platform administrators."""
    user_id = uuid4()
    non_admin = _principal(user_id, roles={"FIRM_ADMIN"})
    with pytest.raises(AuthorizationError):
        require_platform_admin()(non_admin)


def test_seed_business_profiles_prefills_distribution_profiles() -> None:
    """Seed baseline distributor profiles with stable defaults and no duplicates."""
    session = _session_factory()()

    seed_business_profiles(session)
    seed_business_profiles(session)
    session.commit()

    profiles = {
        profile.code: profile
        for profile in session.scalars(select(BusinessProfile)).all()
    }
    assert profiles["GENERIC"].is_default is True
    assert profiles["AGENCY"].default_settings["business_model"] == "distributor"
    assert profiles["AGENCY"].default_settings["route_management"] is True
    assert profiles["PHARMACY"].default_settings["expiry_required"] is True
    assert profiles["FOOD"].default_settings["near_expiry_alert_days"] == 30
    assert profiles["WHOLESALE"].default_settings["bulk_pricing"] is True
