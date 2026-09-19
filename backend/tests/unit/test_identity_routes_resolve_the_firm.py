"""Identity routes take their firm from the shared resolver, never the raw header.

D-IDN-7. `_firm_scope` returned `principal.firm_id` -- the `X-Firm-ID` header,
checked against nothing -- a private firm-scope resolver on the one router
that manages memberships. A firm administrator was held back only because
their codes sit in one firm's `firm_permissions`; anybody holding a code in
the **global** claim (a global custom role, a platform role such as
`SYSTEM_AUDITOR`) could list a firm's people, create users into it and set its
roles merely by naming it, with no membership. And with no header at all it
returned None, which the service reads as platform-wide -- every user on the
platform. Firm-owned routes check the membership in `app/common/scope.py`;
the identity routes now compose the same dependency.
"""

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.common.scope import FirmScope, optional_firm_scope
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal
from app.firms.models import Firm
from app.identity.api.router import create_user, list_roles, list_users
from app.identity.api.router import router as identity_router
from app.identity.models import User, UserFirm
from app.identity.schemas.api import UserCreate
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Str0ng-Passw0rd!"
ACTOR = uuid4()


def _service() -> tuple[IdentityService, Session]:
    """Build the service over a seeded in-memory schema."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_system_rbac(session)
    session.commit()
    return IdentityService(session, Settings()), session


def _firm(session: Session, code: str) -> Firm:
    """Create one active firm."""
    firm = Firm(
        code=code,
        name=f"Firm {code}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=True,
        created_by=ACTOR,
        updated_by=ACTOR,
    )
    session.add(firm)
    session.commit()
    return firm


def _staff(service: IdentityService, session: Session, firm: Firm) -> User:
    """Create one person working in the firm."""
    user = service.create_user(
        UserCreate(email="staff@example.com", full_name="Staff", password=PASSWORD),
        actor_id=ACTOR,
        firm_scope=firm.id,
    )
    session.commit()
    return user


def _global_claim_holder(named_firm: UUID | None) -> Principal:
    """Build a caller holding identity codes in the global claim, and no membership.

    What a global custom role or a platform role such as `SYSTEM_AUDITOR`
    yields -- no platform designation, so no exemption from anything.
    """
    return Principal(
        subject=uuid4(),
        roles=frozenset(),
        permissions=frozenset({"USER_VIEW", "USER_CREATE", "ROLE_VIEW"}),
        claims=SimpleNamespace(model_extra={}),  # type: ignore[arg-type]
        firm_id=named_firm,
    )


def test_every_identity_route_that_reads_a_firm_composes_the_shared_resolver() -> None:
    """The routes that act in a firm resolve it through `app/common/scope.py`."""
    wanted = {
        ("GET", "/api/v1/users"),
        ("POST", "/api/v1/users"),
        ("GET", "/api/v1/users/lookup"),
        ("PATCH", "/api/v1/users/{user_id}"),
        ("PUT", "/api/v1/users/{user_id}/roles"),
        ("GET", "/api/v1/roles"),
        ("POST", "/api/v1/roles"),
        ("POST", "/api/v1/users/{user_id}/clone"),
        ("POST", "/api/v1/users/{user_id}/apply-template"),
        ("GET", "/api/v1/permissions"),
    }
    found = set()
    for route in identity_router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if (method, route.path) in wanted:
                calls = [dependency.call for dependency in route.dependant.dependencies]
                assert optional_firm_scope in calls, (method, route.path)
                found.add((method, route.path))
    assert found == wanted


def test_the_resolver_refuses_a_global_claim_holder_naming_a_firm() -> None:
    """What a real request now meets: no membership, no firm."""
    _, session = _service()
    firm = _firm(session, "T1")

    with pytest.raises(AuthorizationError, match="not authorized"):
        optional_firm_scope(_global_claim_holder(firm.id), session, firm.id)


def test_naming_a_firm_in_the_header_no_longer_lists_its_people() -> None:
    """The raw header used to be the scope: T1's staff, to a stranger."""
    service, session = _service()
    firm = _firm(session, "T1")
    _staff(service, session, firm)

    with pytest.raises(AuthorizationError):
        list_users(_global_claim_holder(firm.id), db=session, settings=Settings())


def test_naming_a_firm_in_the_header_no_longer_creates_users_in_it() -> None:
    """And no account is opened in the firm the caller does not belong to."""
    _, session = _service()
    firm = _firm(session, "T1")

    with pytest.raises(AuthorizationError):
        create_user(
            UserCreate(email="plant@example.com", full_name="Plant", password=PASSWORD),
            _global_claim_holder(firm.id),
            db=session,
            settings=Settings(),
        )

    assert session.scalar(select(User).where(User.email == "plant@example.com")) is None
    assert (
        session.scalar(select(UserFirm.id).where(UserFirm.firm_id == firm.id)) is None
    )


def test_no_header_is_not_platform_wide_for_anybody_without_the_designation() -> None:
    """None used to mean every user and every role on the platform."""
    service, session = _service()
    _staff(service, session, _firm(session, "T1"))

    with pytest.raises(AuthorizationError, match="X-Firm-ID is required"):
        list_users(_global_claim_holder(None), db=session, settings=Settings())
    with pytest.raises(AuthorizationError, match="X-Firm-ID is required"):
        list_roles(_global_claim_holder(None), db=session, settings=Settings())


def test_a_resolved_membership_still_lists_that_firms_people() -> None:
    """The ordinary firm caller, admitted by the resolver, is unchanged."""
    service, session = _service()
    firm = _firm(session, "T1")
    _staff(service, session, firm)
    caller = _global_claim_holder(firm.id)

    page = list_users(
        caller,
        caller_scope=FirmScope(principal=caller, firm_id=firm.id),
        db=session,
        settings=Settings(),
    )

    assert [row.email for row in page.data] == ["staff@example.com"]
