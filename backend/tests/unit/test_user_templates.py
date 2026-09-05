"""A named bundle of roles for one job.

A firm administrator hiring a counter clerk should not have to reassemble a
permission set from twelve roles and remember which. A template is that
decision, made once, under a name the firm already uses.

It is deliberately a **role bundle and not a dormant user row**. Cloning a user
carries everything a user has -- an email, a password, memberships, an audit
trail, a login history -- and the clone quietly inherits whatever was edited
after the template was written. A bundle carries only what the job needs, and
applying one is a plain `set_user_roles` whose result the administrator is then
free to edit: a template is where you start, not somewhere you stay.

The test that matters most here is the escalation one. `PLATFORM_ADMIN` carries
every seeded permission code, so a firm template able to name it would hand a
firm administrator the whole catalogue in their own firm -- through a template
rather than through a role assignment, which is a second door onto the same
room.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
)
from app.firms.models import Firm
from app.identity.models import Role, User, UserFirm, UserRole
from app.identity.schemas.api import (
    RoleCreate,
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
    """Return one seeded role's id."""
    role = session.scalar(select(Role).where(Role.code == code))
    assert role is not None, code
    return role.id


def _user(service: IdentityService, session: Session, email: str, firm: Firm) -> User:
    """Create one user who is a member of the firm.

    The membership is not decoration: `set_user_roles` resolves the user
    *within* the firm scope, so a firm administrator can only give roles to
    their own people. Applying a template goes through that same path.
    """
    user = service.create_user(
        UserCreate(email=email, full_name="Person", password=PASSWORD), actor_id=ACTOR
    )
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
    return user


def _codes_held(session: Session, user_id: UUID, firm_id: UUID | None) -> set[str]:
    """Return the role codes a user holds, in one firm's scope."""
    rows = session.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.firm_id == firm_id,
            UserRole.is_deleted.is_(False),
        )
    )
    return set(rows)


# --------------------------------------------------------------------------
# What a firm is offered
# --------------------------------------------------------------------------


def test_the_platform_templates_are_offered_to_every_firm() -> None:
    """Eleven jobs, seeded, needing no setup from the firm at all."""
    service, session = _service()
    firm = _firm(session, "F1")

    rows, total = service.list_user_templates(1, 50, None, "code", False, firm.id)

    assert total == 11
    assert {"counter-sales", "warehouse", "accounts"} <= {row.code for row in rows}
    assert all(row.is_system and row.firm_id is None for row in rows)


def test_a_template_says_what_it_does() -> None:
    """Most jobs are one role, and the value is the name -- but not all are.

    "Counter Sales" is a job a firm has. `CASHIER` plus `BILLING_EXECUTIVE` is
    a permission decision somebody has to make correctly, once, rather than on
    every hire.
    """
    service, session = _service()
    rows, _ = service.list_user_templates(1, 50, "counter", "code", False, None)

    counter = next(row for row in rows if row.code == "counter-sales")
    codes = {row.role.code for row in counter.template_roles if not row.is_deleted}
    assert codes == {"CASHIER", "BILLING_EXECUTIVE"}


def test_a_firms_own_template_is_invisible_to_another_firm() -> None:
    """A firm's own templates are its own; the platform's are everyone's."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    service.create_user_template(
        UserTemplateCreate(
            code="night-shift",
            name="Night Shift",
            role_ids=[_role_id(session, "CASHIER")],
        ),
        ACTOR,
        one.id,
    )

    theirs = {
        row.code
        for row in service.list_user_templates(1, 50, None, "code", False, one.id)[0]
    }
    others = {
        row.code
        for row in service.list_user_templates(1, 50, None, "code", False, two.id)[0]
    }

    assert "night-shift" in theirs
    assert "night-shift" not in others
    # And the platform's are offered to both.
    assert "counter-sales" in theirs and "counter-sales" in others


def test_two_firms_may_use_the_same_code() -> None:
    """The code is unique per scope, not globally.

    Two firms both have a night shift, and neither should have to know about
    the other.
    """
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    payload = UserTemplateCreate(
        code="night-shift", name="Night Shift", role_ids=[_role_id(session, "CASHIER")]
    )

    service.create_user_template(payload, ACTOR, one.id)
    service.create_user_template(payload, ACTOR, two.id)

    with pytest.raises(ConflictError):
        service.create_user_template(payload, ACTOR, one.id)


# --------------------------------------------------------------------------
# The escalation guard
# --------------------------------------------------------------------------


def test_a_firm_template_cannot_bundle_a_platform_role() -> None:
    """The one that matters.

    `PLATFORM_ADMIN` carries every seeded permission code. A firm template able
    to name it would hand a firm administrator the whole catalogue in their own
    firm -- through a template rather than through a role assignment, which is
    a second door onto the same room. `set_user_roles` already refuses it at
    apply time; refusing at *creation* is what stops a template that fails on
    whoever tries to use it, weeks later, with nothing on screen to say the
    template was wrong rather than their permissions.
    """
    service, session = _service()
    firm = _firm(session, "F1")

    with pytest.raises(BusinessRuleError):
        service.create_user_template(
            UserTemplateCreate(
                code="backdoor",
                name="Not a job",
                role_ids=[_role_id(session, "PLATFORM_ADMIN")],
            ),
            ACTOR,
            firm.id,
        )


def test_a_firm_template_cannot_bundle_another_firms_role() -> None:
    """The same guard, in the direction that is easier to reach by accident."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    theirs = service.create_role(
        RoleCreate(code="two-only", name="Two only"),
        actor_id=ACTOR,
        firm_scope=two.id,
    )

    with pytest.raises(BusinessRuleError):
        service.create_user_template(
            UserTemplateCreate(code="borrowed", name="Borrowed", role_ids=[theirs.id]),
            ACTOR,
            one.id,
        )


def test_a_firm_cannot_edit_or_retire_a_platform_template() -> None:
    """A firm sees them and uses them; changing them is the platform's call."""
    service, session = _service()
    firm = _firm(session, "F1")
    rows, _ = service.list_user_templates(1, 50, "counter", "code", False, firm.id)
    counter = rows[0]

    with pytest.raises(BusinessRuleError):
        service.update_user_template(
            counter.id, UserTemplateUpdate(name="Ours now"), ACTOR, firm.id
        )
    with pytest.raises(BusinessRuleError):
        service.delete_user_template(counter.id, ACTOR, firm.id)


# --------------------------------------------------------------------------
# Applying one
# --------------------------------------------------------------------------


def test_applying_a_template_gives_the_user_its_roles() -> None:
    """The whole point of the feature, in one call."""
    service, session = _service()
    firm = _firm(session, "F1")
    person = _user(service, session, "clerk@example.com", firm)
    rows, _ = service.list_user_templates(1, 50, "counter", "code", False, firm.id)

    service.apply_user_template(person.id, rows[0].id, ACTOR, firm.id)

    assert _codes_held(session, person.id, firm.id) == {"CASHIER", "BILLING_EXECUTIVE"}


def test_a_template_is_where_you_start_not_where_you_stay() -> None:
    """The decision the owner made: a firm admin may edit freely afterwards.

    Nothing on the user records which template they came from, deliberately --
    a user who has since been edited is no longer described by it.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    person = _user(service, session, "clerk@example.com", firm)
    rows, _ = service.list_user_templates(1, 50, "counter", "code", False, firm.id)
    service.apply_user_template(person.id, rows[0].id, ACTOR, firm.id)

    # An ordinary role edit, on an ordinary user.
    service.set_user_roles(
        person.id,
        [_role_id(session, "CASHIER"), _role_id(session, "SALES_EXECUTIVE")],
        ACTOR,
        firm.id,
    )

    assert _codes_held(session, person.id, firm.id) == {"CASHIER", "SALES_EXECUTIVE"}


def test_an_inactive_template_is_not_applied() -> None:
    """Retiring is for future hires; switching off stops them immediately."""
    service, session = _service()
    firm = _firm(session, "F1")
    person = _user(service, session, "clerk@example.com", firm)
    template = service.create_user_template(
        UserTemplateCreate(
            code="night-shift",
            name="Night Shift",
            role_ids=[_role_id(session, "CASHIER")],
            is_active=False,
        ),
        ACTOR,
        firm.id,
    )

    with pytest.raises(BusinessRuleError):
        service.apply_user_template(person.id, template.id, ACTOR, firm.id)


def test_retiring_a_template_leaves_its_users_alone() -> None:
    """Nobody loses access because a template was retired.

    A template is where a user started; retiring one is a decision about future
    hires, not about the people already doing the job.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    person = _user(service, session, "clerk@example.com", firm)
    template = service.create_user_template(
        UserTemplateCreate(
            code="night-shift",
            name="Night Shift",
            role_ids=[_role_id(session, "CASHIER")],
        ),
        ACTOR,
        firm.id,
    )
    service.apply_user_template(person.id, template.id, ACTOR, firm.id)

    service.delete_user_template(template.id, ACTOR, firm.id)

    assert _codes_held(session, person.id, firm.id) == {"CASHIER"}
    with pytest.raises(ResourceNotFoundError):
        service.get_user_template(template.id, firm.id)


# --------------------------------------------------------------------------
# Editing one
# --------------------------------------------------------------------------


def test_an_update_that_says_nothing_about_the_bundle_leaves_it_alone() -> None:
    """The full-dump trap, which has shipped in this repo more than once.

    A write schema gives every optional field a default, so `model_dump()`
    returns a value for a field the caller never mentioned. Renaming a template
    must not empty its bundle.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    template = service.create_user_template(
        UserTemplateCreate(
            code="night-shift",
            name="Night Shift",
            description="Covers the late counter.",
            role_ids=[
                _role_id(session, "CASHIER"),
                _role_id(session, "BILLING_EXECUTIVE"),
            ],
        ),
        ACTOR,
        firm.id,
    )

    updated = service.update_user_template(
        template.id, UserTemplateUpdate(name="Late Shift"), ACTOR, firm.id
    )

    assert updated.name == "Late Shift"
    assert updated.description == "Covers the late counter."
    assert updated.is_active is True
    live = {row.role.code for row in updated.template_roles if not row.is_deleted}
    assert live == {"CASHIER", "BILLING_EXECUTIVE"}


def test_naming_the_bundle_replaces_it() -> None:
    """Absent means leave alone; stated means this is the whole bundle now."""
    service, session = _service()
    firm = _firm(session, "F1")
    template = service.create_user_template(
        UserTemplateCreate(
            code="night-shift",
            name="Night Shift",
            role_ids=[
                _role_id(session, "CASHIER"),
                _role_id(session, "BILLING_EXECUTIVE"),
            ],
        ),
        ACTOR,
        firm.id,
    )

    updated = service.update_user_template(
        template.id,
        UserTemplateUpdate(role_ids=[_role_id(session, "SALES_EXECUTIVE")]),
        ACTOR,
        firm.id,
    )

    live = {row.role.code for row in updated.template_roles if not row.is_deleted}
    assert live == {"SALES_EXECUTIVE"}


def test_a_role_returned_to_a_bundle_is_restored_not_duplicated() -> None:
    """A removed role has to be revived rather than re-inserted.

    The unique key is on `(template_id, role_id)` and ignores the soft delete,
    so inserting a second row for a role the template once held raises.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    cashier = _role_id(session, "CASHIER")
    template = service.create_user_template(
        UserTemplateCreate(code="night-shift", name="Night Shift", role_ids=[cashier]),
        ACTOR,
        firm.id,
    )
    service.update_user_template(
        template.id,
        UserTemplateUpdate(role_ids=[_role_id(session, "SALES_EXECUTIVE")]),
        ACTOR,
        firm.id,
    )

    updated = service.update_user_template(
        template.id, UserTemplateUpdate(role_ids=[cashier]), ACTOR, firm.id
    )

    assert len(updated.template_roles) == 2
    live = {row.role.code for row in updated.template_roles if not row.is_deleted}
    assert live == {"CASHIER"}


# --------------------------------------------------------------------------
# What a firm administrator can see to build one from
# --------------------------------------------------------------------------


def test_a_firm_admin_can_list_the_roles_a_template_may_bundle() -> None:
    """Found by driving the endpoint, not by reading the code.

    `GET /api/v1/roles` was gated on the platform *designation* while the other
    three role endpoints -- get, create and update -- all took `ROLE_VIEW`, and
    while `list_users` and `list_permissions`, the two lists beside it, took
    their own view codes. So a firm administrator holding `ROLE_VIEW` was
    refused the one screen they would start from, and the firm filtering in
    `list_roles` had been written for a caller who could never reach it.

    That mattered here: a firm cannot assemble its own template without seeing
    the roles. The list is scoped, so what they see is the twelve firm roles
    and their own -- never `PLATFORM_ADMIN`, which is what makes the bundle
    guard above a second lock rather than the only one.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    service.create_role(
        RoleCreate(code="night-desk", name="Night desk"), ACTOR, firm_scope=firm.id
    )

    rows, _ = service.list_roles(1, 100, None, "code", False, firm.id)
    codes = {row.code for row in rows}

    assert "night-desk" in codes
    assert {"CASHIER", "SALES_EXECUTIVE", "ACCOUNTANT"} <= codes
    assert not codes & {"PLATFORM_ADMIN", "SUPPORT_ADMIN", "LICENSE_ADMIN"}
