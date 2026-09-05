"""How far a platform administrator's designation reaches.

The platform had exactly one kind of administrator. They pass every permission
check by short-circuit (`Principal.has_permission`) and every firm-membership
check by exemption (`optional_firm_scope`), and their token is stuffed with
every permission code the platform seeds. That is three separate grants of the
same thing, and together they conflate two jobs a real deployment separates:

* **running the platform** -- creating firms, creating their people,
  provisioning storage, setting a firm up until it works; and
* **acting inside a firm's books**, which is the firm's own business.

`platform_admins.scope` separates them. These tests are about all three grants,
because narrowing two and leaving the third is not a narrowing at all: the
stuffed `permissions` claim in particular is checked *directly* by
`has_permission`, so a `PLATFORM` administrator holding operational codes would
pass every firm permission check the moment they held a genuine membership --
the whole of tier 2 through a claim rather than through a bypass.
"""

import base64
import json
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import optional_firm_scope
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal, require_platform_admin
from app.firms.models import Firm
from app.identity.models import PlatformAdmin, User, UserFirm
from app.identity.schemas.api import UserCreate
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Str0ng-Passw0rd!"


def _service() -> tuple[IdentityService, Session]:
    """Build the service over an in-memory schema, as the suite does."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    # The real permission catalogue. A platform administrator holds no role
    # rows -- the codes are stuffed in from this table -- so an unseeded
    # schema would answer an empty claim for every tier and prove nothing.
    seed_system_rbac(session)
    session.commit()
    return IdentityService(session, Settings()), session


def _admin(
    service: IdentityService,
    session: Session,
    scope: PlatformAdminScope | None,
    email: str = "operator@example.com",
) -> User:
    """Create a user, designated at the given reach, or not designated at all."""
    user = service.create_user(
        UserCreate(email=email, full_name="Operator", password=PASSWORD),
        actor_id=uuid4(),
    )
    # `create_user` forces a password change and every platform gate refuses
    # such a token -- correctly, and it is `test_authentication_chain.py` that
    # covers it. These tests are about reach.
    user.force_password_change = False
    session.commit()
    if scope is not None:
        actor = uuid4()
        session.add(
            PlatformAdmin(
                user_id=user.id, scope=scope.value, created_by=actor, updated_by=actor
            )
        )
        session.commit()
    return user


def _claims(service: IdentityService, user: User) -> dict[str, object]:
    """Sign in and decode the access token this build actually mints."""
    tokens = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    payload = tokens.access_token.split(".")[1]
    decoded: dict[str, object] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return decoded


def _principal(claims: dict[str, object], subject: UUID) -> Principal:
    """Build a principal from decoded claims, the way the request path does."""
    roles: list[str] = list(claims.get("roles") or [])  # type: ignore[arg-type]
    codes: list[str] = list(claims.get("permissions") or [])  # type: ignore[arg-type]
    return Principal(
        subject=subject,
        roles=frozenset(roles),
        permissions=frozenset(codes),
        claims=SimpleNamespace(model_extra=claims),  # type: ignore[arg-type]
    )


def _firm(session: Session, code: str = "F1") -> Firm:
    """Create one active firm to be scoped to."""
    actor = uuid4()
    firm = Firm(
        code=code,
        name="A firm",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=True,
        created_by=actor,
        updated_by=actor,
    )
    session.add(firm)
    session.commit()
    return firm


def _granted(claims: dict[str, object]) -> set[str]:
    """Return the global permission codes the token carries."""
    codes: list[str] = list(claims.get("permissions") or [])  # type: ignore[arg-type]
    return set(codes)


# --------------------------------------------------------------------------
# What the token carries
# --------------------------------------------------------------------------


def test_an_all_firms_administrator_is_unchanged() -> None:
    """The designation as it has always behaved. Nothing here is new."""
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.ALL_FIRMS)
    claims = _claims(service, user)
    principal = _principal(claims, user.id)

    assert claims["platform_admin"] is True
    assert claims["platform_admin_scope"] == "ALL_FIRMS"
    assert principal.may_act_in_any_firm
    assert principal.has_permission("VOID_INVOICE")
    assert principal.has_permission("ANYTHING_AT_ALL")


def test_a_platform_operator_holds_no_operational_permission() -> None:
    """The third grant, and the easiest one to leave behind.

    `has_permission` reads the global `permissions` claim directly, so codes
    stuffed into the token are not covered by narrowing the short-circuit.
    """
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.PLATFORM)
    granted = _granted(_claims(service, user))

    # Their job: run the platform, and set a firm up until it works.
    assert {"FIRM_CREATE", "USER_CREATE", "ROLE_ASSIGN", "PLATFORM_SETTINGS"} <= granted
    # Not their job: a firm's own books, and the high-risk verbs over them.
    assert not granted & {
        "VOID_INVOICE",
        "EDIT_POSTED_TRANSACTION",
        "DELETE_TRANSACTION",
        "CUSTOMER_CREATE",
        "SALES_CREATE",
        "ACCOUNT_VIEW",
    }


def test_a_platform_operator_still_administers_the_platform() -> None:
    """The tier exists to be usable, not only to be refused."""
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.PLATFORM)
    principal = _principal(_claims(service, user), user.id)

    assert principal.is_platform_admin
    assert require_platform_admin()(principal) is principal
    assert principal.has_permission("FIRM_CREATE")


def test_a_platform_operator_does_not_short_circuit_permissions() -> None:
    """The first grant: a code they were never given is a code they lack."""
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.PLATFORM)
    principal = _principal(_claims(service, user), user.id)

    assert not principal.may_act_in_any_firm
    assert not principal.has_permission("SALES_CREATE")


# --------------------------------------------------------------------------
# The firm gate
# --------------------------------------------------------------------------


def test_an_all_firms_administrator_needs_no_membership() -> None:
    """The exemption, kept for the tier it belongs to."""
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.ALL_FIRMS)
    firm = _firm(session)
    principal = _principal(_claims(service, user), user.id)

    assert optional_firm_scope(principal, session, firm.id).firm_id == firm.id


def test_a_platform_operator_is_refused_a_firm_they_do_not_belong_to() -> None:
    """The heart of it, and note the shape: not refused by a rule of its own.

    They are simply not exempted, so they meet the ordinary membership check
    and fail it. Every firm-owned router composes `required_firm_scope`, so
    this one gate decides the whole firm-owned surface and nothing outside it.
    """
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.PLATFORM)
    firm = _firm(session)
    principal = _principal(_claims(service, user), user.id)

    with pytest.raises(AuthorizationError):
        optional_firm_scope(principal, session, firm.id)


def test_a_platform_operator_who_is_a_member_acts_as_that_member() -> None:
    """A designation is a ceiling, not a floor.

    Nothing forbids whoever runs the platform from also being a real user of a
    firm. Where they are, they are that user: admitted by their `UserFirm` row
    and limited to what their roles in that firm actually grant.
    """
    service, session = _service()
    user = _admin(service, session, PlatformAdminScope.PLATFORM)
    firm = _firm(session)
    actor = uuid4()
    session.add(
        UserFirm(
            user_id=user.id,
            firm_id=firm.id,
            is_primary=True,
            is_active=True,
            created_by=actor,
            updated_by=actor,
        )
    )
    session.commit()

    claims = _claims(service, user)
    principal = _principal(claims, user.id)

    assert optional_firm_scope(principal, session, firm.id).firm_id == firm.id
    # The map is computed for them, which it is not for an `ALL_FIRMS` admin:
    # the desktop needs it to know which modules to offer.
    assert str(firm.id) in claims["firm_permissions"]  # type: ignore[operator]
    # Admitted, and holding nothing -- they were given no role in this firm.
    # The membership is what let them in; it is not what decides what they do.
    assert not principal.has_permission("SALES_CREATE")


# --------------------------------------------------------------------------
# Reading the claim
# --------------------------------------------------------------------------


def test_an_older_token_without_the_claim_keeps_every_firm() -> None:
    """The only principal that can lack the claim already had everything.

    A token minted before the scope existed belongs to somebody who was, by
    definition, an `ALL_FIRMS` administrator. Reading its absence as the narrow
    value would demote every live administrator mid-session -- a worse failure
    than an unchanged one for the few minutes an access token lives.
    """
    principal = _principal({"platform_admin": True}, uuid4())

    assert principal.platform_admin_scope is PlatformAdminScope.ALL_FIRMS
    assert principal.may_act_in_any_firm


def test_an_unrecognised_reach_grants_the_narrow_one() -> None:
    """A value nobody recognises is a reason to grant less, never more."""
    principal = _principal(
        {"platform_admin": True, "platform_admin_scope": "EVERYTHING"}, uuid4()
    )

    assert principal.platform_admin_scope is PlatformAdminScope.PLATFORM
    assert not principal.may_act_in_any_firm


def test_someone_with_no_designation_has_no_reach() -> None:
    """An ordinary user is untouched by any of this."""
    service, session = _service()
    user = _admin(service, session, None, email="ordinary@example.com")
    principal = _principal(_claims(service, user), user.id)

    assert principal.platform_admin_scope is None
    assert not principal.is_platform_admin
    assert not principal.may_act_in_any_firm
    with pytest.raises(AuthorizationError):
        require_platform_admin()(principal)


def test_a_new_designation_defaults_to_the_narrow_reach() -> None:
    """A row written without stating a reach gets the safe answer.

    The column carries no server default for the same reason: a default is one
    migration away from silently handing somebody every firm's books.
    """
    service, session = _service()
    user = service.create_user(
        UserCreate(email="fresh@example.com", full_name="Fresh", password=PASSWORD),
        actor_id=uuid4(),
    )
    user.force_password_change = False
    actor = uuid4()
    session.add(PlatformAdmin(user_id=user.id, created_by=actor, updated_by=actor))
    session.commit()

    assert _claims(service, user)["platform_admin_scope"] == "PLATFORM"
