"""A grant keeps the tier it was made in, and no firm's own role reaches every firm.

D-IDN-3. A platform administrator's **Hire like this person** with no firm
named copied every role the source held, in any tier, and wrote them all as
global rows -- so a role the source held in one firm applied to the clone in
every firm they were copied into (live: `t0919subq`, SALES_EXECUTIVE in TEST01
only, cloned into SALES_EXECUTIVE globally, in TEST01 and TEST02). The global
path of `set_user_roles` checked only that the role ids existed, so it took
another firm's own custom role; `apply_user_template` with no firm named
applied any firm's template to the global tier; and a platform-wide template
could bundle a firm's custom role.
"""

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.core.security.authorization import Principal
from app.firms.models import Firm
from app.identity.api.router import clone_user as clone_user_route
from app.identity.models import Role, User, UserFirm, UserRole
from app.identity.schemas.api import (
    UserCloneRequest,
    UserCreate,
    UserTemplateCreate,
    UserTemplateUpdate,
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


def _role_id(session: Session, code: str) -> UUID:
    """Return one role's id by code."""
    role = session.scalar(select(Role).where(Role.code == code))
    assert role is not None, code
    return role.id


def _firm_role(session: Session, code: str, firm: Firm) -> UUID:
    """Create a custom role one firm owns."""
    role = Role(
        code=code,
        name=code,
        is_system=False,
        firm_id=firm.id,
        created_by=ACTOR,
        updated_by=ACTOR,
    )
    session.add(role)
    session.commit()
    return role.id


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


def _codes_held(session: Session, user_id: UUID, firm: Firm | None) -> set[str]:
    """Return the role codes a user holds in one firm's tier, or the global one."""
    tier = UserRole.firm_id.is_(None) if firm is None else UserRole.firm_id == firm.id
    return set(
        session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, tier, UserRole.is_deleted.is_(False))
        )
    )


def _request(email: str) -> UserCloneRequest:
    """Build the new person's own details."""
    return UserCloneRequest(email=email, full_name="New Hire", password=PASSWORD)


# --------------------------------------------------------------------------
# Clone
# --------------------------------------------------------------------------


def test_a_platform_clone_keeps_each_role_in_its_own_tier() -> None:
    """The live case: a role held in one firm stays in that one firm."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    source = _person(service, session, "source@example.com", one, two)
    service.set_user_roles(source.id, [_role_id(session, "VIEWER")], ACTOR, None)
    service.set_user_firm_roles(
        source.id, one.id, [_role_id(session, "SALES_EXECUTIVE")], ACTOR
    )

    clone = service.clone_user(source.id, _request("clone@example.com"), ACTOR, None)

    assert _codes_held(session, clone.id, None) == {"VIEWER"}
    assert _codes_held(session, clone.id, one) == {"SALES_EXECUTIVE"}
    assert _codes_held(session, clone.id, two) == set()


def test_a_clone_is_refused_roles_in_firms_the_caller_cannot_administer() -> None:
    """Refused by name, before any account is opened -- not dropped, not widened."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    source = _person(service, session, "source@example.com", one, two)
    service.set_user_firm_roles(
        source.id, two.id, [_role_id(session, "ACCOUNTANT")], ACTOR
    )

    with pytest.raises(BusinessRuleError, match="T2"):
        service.clone_user(
            source.id,
            _request("clone@example.com"),
            ACTOR,
            None,
            allowed_firm_ids=frozenset({one.id}),
        )

    assert session.scalar(select(User).where(User.email == "clone@example.com")) is None


def test_the_route_holds_a_platform_operator_to_their_reach() -> None:
    """Hold a platform operator to their reach at the route.

    The router hands the service the caller's reach, which for an operator
    holding no firm's `USER_CREATE` is no firm at all.
    """
    service, session = _service()
    firm = _firm(session, "T1")
    source = _person(service, session, "source@example.com", firm)
    service.set_user_firm_roles(
        source.id, firm.id, [_role_id(session, "CASHIER")], ACTOR
    )
    operator = Principal(
        subject=uuid4(),
        roles=frozenset(),
        permissions=frozenset({"ROLE_ASSIGN"}),
        claims=SimpleNamespace(  # type: ignore[arg-type]
            model_extra={"platform_admin": True, "platform_admin_scope": "PLATFORM"}
        ),
    )

    with pytest.raises(BusinessRuleError, match="T1"):
        clone_user_route(
            user_id=source.id,
            data=_request("clone@example.com"),
            principal=operator,
            db=session,
            settings=Settings(),
        )


def test_a_firm_administrator_still_copies_what_applies_in_their_firm() -> None:
    """Unchanged: a firm caller writes their own firm's tier and nothing else."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    source = _person(service, session, "source@example.com", one, two)
    service.set_user_firm_roles(
        source.id, one.id, [_role_id(session, "CASHIER")], ACTOR
    )
    service.set_user_firm_roles(
        source.id, two.id, [_role_id(session, "ACCOUNTANT")], ACTOR
    )

    clone = service.clone_user(source.id, _request("clone@example.com"), ACTOR, one.id)

    assert _codes_held(session, clone.id, one) == {"CASHIER"}
    assert _codes_held(session, clone.id, None) == set()


# --------------------------------------------------------------------------
# The global tier and platform-wide templates
# --------------------------------------------------------------------------


def test_another_firms_custom_role_is_refused_in_the_global_tier() -> None:
    """A firm's own role is that firm's decision, not every firm's."""
    service, session = _service()
    firm = _firm(session, "T1")
    kitchen = _firm_role(session, "kitchen.staff", firm)
    person = _person(service, session, "person@example.com", firm)

    with pytest.raises(BusinessRuleError, match="kitchen.staff"):
        service.set_user_roles(person.id, [kitchen], ACTOR, None)

    assert _codes_held(session, person.id, None) == set()


def test_a_firms_template_is_not_applied_to_the_global_tier() -> None:
    """Naming no firm writes the global tier, so a firm's template is refused."""
    service, session = _service()
    firm = _firm(session, "T1")
    template = service.create_user_template(
        UserTemplateCreate(
            code="counter", name="Counter", role_ids=[_role_id(session, "CASHIER")]
        ),
        ACTOR,
        firm.id,
    )
    person = _person(service, session, "person@example.com", firm)

    with pytest.raises(BusinessRuleError, match="belongs to one firm"):
        service.apply_user_template(person.id, template.id, ACTOR, None)

    # Naming the firm it belongs to is the way to apply it.
    service.apply_user_template(person.id, template.id, ACTOR, None, firm.id)
    assert _codes_held(session, person.id, firm) == {"CASHIER"}
    assert _codes_held(session, person.id, None) == set()


def test_a_firms_template_is_not_applied_in_another_firm() -> None:
    """Named in the wrong firm, it is not there to be found."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    template = service.create_user_template(
        UserTemplateCreate(
            code="counter", name="Counter", role_ids=[_role_id(session, "CASHIER")]
        ),
        ACTOR,
        one.id,
    )
    person = _person(service, session, "person@example.com", two)

    with pytest.raises(ResourceNotFoundError):
        service.apply_user_template(person.id, template.id, ACTOR, None, two.id)


def test_a_platform_template_cannot_bundle_a_firms_custom_role() -> None:
    """Offered to every firm, so it may not carry one firm's own role."""
    service, session = _service()
    firm = _firm(session, "T1")
    kitchen = _firm_role(session, "kitchen.staff", firm)

    with pytest.raises(BusinessRuleError, match="kitchen.staff"):
        service.create_user_template(
            UserTemplateCreate(code="kitchen", name="Kitchen", role_ids=[kitchen]),
            ACTOR,
            None,
        )


def test_a_template_edit_is_validated_against_the_firm_that_owns_it() -> None:
    """A platform caller editing one firm's template cannot add another's role."""
    service, session = _service()
    one, two = _firm(session, "T1"), _firm(session, "T2")
    template = service.create_user_template(
        UserTemplateCreate(
            code="counter",
            name="Counter",
            role_ids=[_role_id(session, "CASHIER")],
            firm_id=one.id,
        ),
        ACTOR,
        None,
    )
    elsewhere = _firm_role(session, "two.only", two)

    with pytest.raises(BusinessRuleError, match="cross-firm"):
        service.update_user_template(
            template.id, UserTemplateUpdate(role_ids=[elsewhere]), ACTOR, None
        )
