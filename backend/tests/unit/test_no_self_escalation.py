"""Nobody grants themselves access, and a `PLATFORM` operator grants none in firms.

D-IDN-1. A `PLATFORM` operator holds `ROLE_ASSIGN` -- setting up a firm's
people is their job -- and `PUT /users/{id}/roles` from any platform caller
wrote the **global** tier of any user, their own row included. `_issue_tokens`
then gave every global seeded firm role to each of the holder's memberships,
so an operator who assigned themselves `FIRM_ADMIN` became a firm
administrator in every firm they were a member of from their next sign-in --
exactly the books the `PLATFORM` reach exists to keep them out of. The three
narrowing points (`scope.py`, `has_permission`, the stuffed claim) were each
correct; nothing stopped the operator writing the rows they read.

Three locks, each tested on its own so that removing any one fails here:

* nobody may change their own roles or memberships, whoever they are;
* a `PLATFORM` operator may not grant, in the global tier, a role reaching
  past their own ceiling (`PLATFORM_OPERATOR_PERMISSION_CODES`);
* a `PLATFORM` operator's token carries firm permissions only from grants
  made **in** that firm, never from a global row.
"""

import base64
import json
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope
from app.core.exceptions import BusinessRuleError
from app.firms.models import Firm
from app.identity.models import (
    Permission,
    PlatformAdmin,
    Role,
    RolePermission,
    User,
    UserFirm,
    UserRole,
)
from app.identity.schemas.api import UserCreate, UserFirmAssignment
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


def _firm(session: Session, code: str = "F1") -> Firm:
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


def _user(
    service: IdentityService,
    session: Session,
    email: str,
    scope: PlatformAdminScope | None = None,
) -> User:
    """Create a signed-in-able user, designated at the given reach or not at all."""
    user = service.create_user(
        UserCreate(email=email, full_name="Person", password=PASSWORD),
        actor_id=ACTOR,
    )
    user.force_password_change = False
    session.commit()
    if scope is not None:
        session.add(
            PlatformAdmin(
                user_id=user.id, scope=scope.value, created_by=ACTOR, updated_by=ACTOR
            )
        )
        session.commit()
    return user


def _member(session: Session, user: User, firm: Firm) -> None:
    """Put a user in a firm."""
    session.add(
        UserFirm(
            user_id=user.id,
            firm_id=firm.id,
            is_primary=True,
            is_active=True,
            created_by=ACTOR,
            updated_by=ACTOR,
        )
    )
    session.commit()


def _role_id(session: Session, code: str) -> UUID:
    """Return one seeded role's id."""
    role = session.scalar(select(Role).where(Role.code == code))
    assert role is not None, code
    return role.id


def _grant(session: Session, user: User, code: str, firm: Firm | None) -> None:
    """Write a role row directly, as whoever wrote it before the fix could."""
    session.add(
        UserRole(
            user_id=user.id,
            role_id=_role_id(session, code),
            firm_id=firm.id if firm is not None else None,
            created_by=ACTOR,
            updated_by=ACTOR,
        )
    )
    session.commit()


def _custom_role(session: Session, code: str, permission_codes: list[str]) -> UUID:
    """Create a global custom role holding exactly these codes."""
    role = Role(
        code=code, name=code, is_system=False, created_by=ACTOR, updated_by=ACTOR
    )
    session.add(role)
    session.flush()
    for permission_code in permission_codes:
        permission = session.scalar(
            select(Permission).where(Permission.code == permission_code)
        )
        assert permission is not None, permission_code
        session.add(
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                created_by=ACTOR,
                updated_by=ACTOR,
            )
        )
    session.commit()
    return role.id


def _firm_codes(service: IdentityService, user: User, firm: Firm) -> set[str]:
    """Sign in and return the codes the token grants in one firm."""
    tokens = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    payload = tokens.access_token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return set(claims["firm_permissions"].get(str(firm.id), []))


# --------------------------------------------------------------------------
# Nobody changes their own access
# --------------------------------------------------------------------------


def test_a_platform_operator_cannot_grant_themselves_firm_admin() -> None:
    """The escalation itself, refused before anything is written."""
    service, session = _service()
    operator = _user(service, session, "op@example.com", PlatformAdminScope.PLATFORM)

    with pytest.raises(BusinessRuleError, match="your own roles"):
        service.set_user_roles(
            operator.id, [_role_id(session, "FIRM_ADMIN")], operator.id, None
        )

    assert (
        session.scalar(select(UserRole.id).where(UserRole.user_id == operator.id))
        is None
    )


def test_even_an_all_firms_administrator_cannot_change_their_own_roles() -> None:
    """Separation of duties is not a rule about one tier."""
    service, session = _service()
    admin = _user(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)

    with pytest.raises(BusinessRuleError, match="your own roles"):
        service.set_user_roles(admin.id, [_role_id(session, "VIEWER")], admin.id, None)


def test_a_firm_administrator_cannot_change_their_own_roles_in_the_firm() -> None:
    """Both firm-tier writers refuse the caller's own row."""
    service, session = _service()
    firm = _firm(session)
    admin = _user(service, session, "fa@example.com")
    _member(session, admin, firm)

    with pytest.raises(BusinessRuleError, match="your own roles"):
        service.set_user_roles(
            admin.id, [_role_id(session, "FIRM_ADMIN")], admin.id, firm.id
        )
    with pytest.raises(BusinessRuleError, match="your own roles"):
        service.set_user_firm_roles(
            admin.id,
            firm.id,
            [_role_id(session, "FIRM_ADMIN")],
            admin.id,
            frozenset({firm.id}),
        )


def test_nobody_changes_their_own_memberships() -> None:
    """A membership is what turns a global role into access in a firm."""
    service, session = _service()
    firm = _firm(session)
    admin = _user(service, session, "all2@example.com", PlatformAdminScope.ALL_FIRMS)

    with pytest.raises(BusinessRuleError, match="firm memberships"):
        service.set_user_firms(
            admin.id,
            [UserFirmAssignment(firm_id=firm.id, is_primary=True, is_active=True)],
            admin.id,
            None,
        )


# --------------------------------------------------------------------------
# What a `PLATFORM` operator may grant in the global tier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["FIRM_ADMIN", "VIEWER", "PLATFORM_ADMIN"])
def test_a_platform_operator_cannot_grant_firm_access_globally(code: str) -> None:
    """Not to themselves, and not to anybody else either.

    `FIRM_ADMIN` and `VIEWER` are seeded firm roles, which a global row turns
    into firm permissions in every membership. `PLATFORM_ADMIN` carries every
    seeded code in the global claim -- `VOID_INVOICE` included -- which is
    more than the operator holds, and nobody grants more than they hold.
    """
    service, session = _service()
    operator = _user(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    other = _user(service, session, "other@example.com")

    with pytest.raises(BusinessRuleError, match=code):
        service.set_user_roles(other.id, [_role_id(session, code)], operator.id, None)

    assert (
        session.scalar(select(UserRole.id).where(UserRole.user_id == other.id)) is None
    )


def test_a_platform_operator_may_grant_a_role_within_their_own_ceiling() -> None:
    """The tier stays usable: a platform helper role is theirs to hand out."""
    service, session = _service()
    operator = _user(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    other = _user(service, session, "helper@example.com")
    helper = _custom_role(session, "platform.helper", ["USER_VIEW", "FIRM_VIEW"])

    service.set_user_roles(other.id, [helper], operator.id, None)

    assert service.list_user_role_ids(other.id) == [helper]


def test_a_custom_role_reaching_a_firms_books_is_refused_too() -> None:
    """The ceiling is derived from the codes, not from a list of role names."""
    service, session = _service()
    operator = _user(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    other = _user(service, session, "clerk@example.com")
    sneaky = _custom_role(session, "platform.sneaky", ["USER_VIEW", "SALES_CREATE"])

    with pytest.raises(BusinessRuleError, match="platform.sneaky"):
        service.set_user_roles(other.id, [sneaky], operator.id, None)


def test_an_all_firms_administrator_still_grants_globally() -> None:
    """The wider reach keeps what it always had."""
    service, session = _service()
    admin = _user(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)
    other = _user(service, session, "boss@example.com")

    service.set_user_roles(other.id, [_role_id(session, "FIRM_ADMIN")], admin.id, None)

    assert service.list_user_role_ids(other.id) == [_role_id(session, "FIRM_ADMIN")]


# --------------------------------------------------------------------------
# What the token carries
# --------------------------------------------------------------------------


def test_a_global_firm_role_grants_a_platform_operator_nothing_in_a_firm() -> None:
    """The token's half, for a row written before the fix or by anybody else."""
    service, session = _service()
    firm = _firm(session)
    operator = _user(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    _member(session, operator, firm)
    _grant(session, operator, "FIRM_ADMIN", None)

    assert _firm_codes(service, operator, firm) == set()


def test_a_grant_made_in_the_firm_still_applies_to_a_platform_operator() -> None:
    """A designation is a ceiling, not a floor: a real firm grant still counts."""
    service, session = _service()
    firm = _firm(session)
    operator = _user(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    _member(session, operator, firm)
    _grant(session, operator, "SALES_EXECUTIVE", firm)

    assert "SALES_ORDER_CREATE" in _firm_codes(service, operator, firm)


def test_a_global_firm_role_still_applies_to_everybody_else() -> None:
    """Tier 2 is unchanged: a global seeded firm role reaches every membership."""
    service, session = _service()
    firm = _firm(session)
    person = _user(service, session, "person@example.com")
    _member(session, person, firm)
    _grant(session, person, "FIRM_ADMIN", None)

    assert "SALES_CREATE" in _firm_codes(service, person, firm)
