"""A clone puts somebody in firms, so it is held to the reach a membership write is.

D-IDN-6. `_firms_the_caller_may_staff` is the firms where the caller holds
`USER_CREATE` in `firm_permissions`, which a `PLATFORM` operator never does --
so `PUT /users/{id}/firms` refuses them every firm ("You can only assign firms
you administer."). `clone_user` with no firm named copied the source's
memberships with no reach check at all, so the same operator could staff any
firm by copying somebody who worked there (live: `t0919tkcy` could not re-save
the clone's two memberships it had just created).
"""

from datetime import date
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import BusinessRuleError
from app.core.security.authorization import Principal
from app.firms.models import Firm
from app.identity.api.router import clone_user as clone_user_route
from app.identity.api.router import set_user_firms as set_user_firms_route
from app.identity.models import User, UserFirm
from app.identity.schemas.api import (
    UserCloneRequest,
    UserCreate,
    UserFirmAssignment,
    UserFirmAssignments,
)
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


def _person(
    service: IdentityService, session: Session, email: str, *firms: Firm
) -> User:
    """Create one user, a member of each firm given."""
    user = service.create_user(
        UserCreate(email=email, full_name="Person", password=PASSWORD), actor_id=ACTOR
    )
    for index, firm in enumerate(firms):
        session.add(
            UserFirm(
                user_id=user.id,
                firm_id=firm.id,
                is_primary=index == 0,
                is_active=True,
                created_by=ACTOR,
                updated_by=ACTOR,
            )
        )
    session.commit()
    return user


def _principal(scope: str | None, firm_codes: dict[UUID, list[str]]) -> Principal:
    """Build a caller: a platform designation of this reach, or none."""
    extra: dict[str, object] = {}
    if scope is not None:
        extra = {"platform_admin": True, "platform_admin_scope": scope}
    return Principal(
        subject=uuid4(),
        roles=frozenset(),
        permissions=frozenset({"ROLE_ASSIGN", "USER_UPDATE"}),
        claims=SimpleNamespace(model_extra=extra),  # type: ignore[arg-type]
        firm_permissions={
            firm_id: frozenset(codes) for firm_id, codes in firm_codes.items()
        },
    )


def _request(email: str, firm_id: UUID | None = None) -> UserCloneRequest:
    """Build the new person's own details."""
    return UserCloneRequest(
        email=email, full_name="New Hire", password=PASSWORD, firm_id=firm_id
    )


def test_a_direct_membership_write_refuses_a_platform_operator() -> None:
    """The baseline the clone must match -- unchanged by this fix."""
    service, session = _service()
    firm = _firm(session, "T1")
    person = _person(service, session, "person@example.com")

    with pytest.raises(BusinessRuleError, match="firms you administer"):
        set_user_firms_route(
            user_id=person.id,
            data=UserFirmAssignments(
                assignments=[
                    UserFirmAssignment(firm_id=firm.id, is_primary=True, is_active=True)
                ]
            ),
            # The handler needs the live request to open a departed firm's own
            # store and retire the person's rounds there (D-TER-17). Nothing
            # departs here -- the call is refused before it writes -- so a
            # stand-in with no tenancy services is enough.
            request=cast(Request, SimpleNamespace()),
            principal=_principal("PLATFORM", {}),
            db=session,
            settings=Settings(),
        )


def test_a_platform_operator_cannot_staff_a_firm_by_cloning() -> None:
    """The defect: the copy put the clone in T1 and T2 all the same."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    source = _person(service, session, "source@example.com", one, two)

    with pytest.raises(BusinessRuleError, match="T1, T2"):
        clone_user_route(
            user_id=source.id,
            data=_request("clone@example.com"),
            principal=_principal("PLATFORM", {}),
            db=session,
            settings=Settings(),
        )

    assert session.scalar(select(User).where(User.email == "clone@example.com")) is None


def test_naming_a_firm_out_of_reach_is_refused_too() -> None:
    """A platform caller naming a firm puts the clone in it: the same check."""
    service, session = _service()
    firm = _firm(session, "T1")
    source = _person(service, session, "source@example.com", firm)

    with pytest.raises(BusinessRuleError, match="T1"):
        clone_user_route(
            user_id=source.id,
            data=_request("clone@example.com", firm.id),
            principal=_principal("PLATFORM", {}),
            db=session,
            settings=Settings(),
        )


def test_an_all_firms_administrator_still_clones_into_every_firm() -> None:
    """Reach None is every firm, as for a direct write."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    source = _person(service, session, "source@example.com", one, two)

    response = clone_user_route(
        user_id=source.id,
        data=_request("clone@example.com"),
        principal=_principal("ALL_FIRMS", {}),
        db=session,
        settings=Settings(),
    )

    assert response.data is not None
    joined = set(
        session.scalars(
            select(UserFirm.firm_id).where(UserFirm.user_id == response.data.id)
        )
    )
    assert joined == {one.id, two.id}


def test_a_caller_who_staffs_every_firm_the_source_is_in_may_clone() -> None:
    """Reach, not the designation, decides: a member administrator of both firms."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    source = _person(service, session, "source@example.com", one, two)
    staffing = {one.id: ["USER_CREATE"], two.id: ["USER_CREATE"]}

    response = clone_user_route(
        user_id=source.id,
        data=_request("clone@example.com"),
        principal=_principal("PLATFORM", staffing),
        db=session,
        settings=Settings(),
    )

    assert response.data is not None
