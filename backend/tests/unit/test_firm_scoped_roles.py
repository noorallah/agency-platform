"""Two administrators, two sets of role grants, and neither undoes the other.

A **platform** administrator writes the *global* set (`user_roles.firm_id`
NULL), which applies in every firm the person belongs to, and may also grant a
role in one named firm. A **firm** administrator writes only their own firm's
set: they may add to it and remove from it, and they can neither edit nor
delete a global grant -- but they can see one, because it applies in their
firm and hiding it under-reports what the person can do there.

The defect this file pins is the one that made the split unsafe:
`_replace_associations` keyed on `role_id` alone, so a platform administrator
who opened a user and pressed Save -- changing nothing -- soft-deleted every
firm-scoped row and re-created the survivors unscoped. Two firms' separate
grants collapsed into one global grant, silently, from a no-op.
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
from app.core.exceptions import BusinessRuleError
from app.firms.models import Firm
from app.identity.models import Role, User, UserFirm, UserRole
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


def _user(service: IdentityService, email: str) -> User:
    """Create one user, in no firm."""
    return service.create_user(
        UserCreate(email=email, full_name="Person", password=PASSWORD), actor_id=ACTOR
    )


def _member(session: Session, user: User, firm: Firm) -> None:
    """Put a user in a firm."""
    session.add(
        UserFirm(
            user_id=user.id,
            firm_id=firm.id,
            is_primary=False,
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


def _codes_in(session: Session, user_id: UUID, firm_id: UUID | None) -> set[str]:
    """Return the role codes a user holds in one firm, or globally."""
    scope = (
        UserRole.firm_id.is_(None) if firm_id is None else UserRole.firm_id == firm_id
    )
    return set(
        session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                scope,
                UserRole.is_deleted.is_(False),
            )
        )
    )


def test_a_platform_save_no_longer_flattens_each_firms_roles() -> None:
    """The defect, reproduced and closed.

    Two firms with different jobs, then a platform administrator saves the
    global set without touching either. Before this, both firm rows were
    soft-deleted and re-created unscoped, so the person became a sales manager
    *and* a sales executive in both firms.
    """
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one)
    _member(session, person, two)
    service.set_user_firm_roles(
        person.id, one.id, [_role_id(session, "SALES_MANAGER")], ACTOR
    )
    service.set_user_firm_roles(
        person.id, two.id, [_role_id(session, "SALES_EXECUTIVE")], ACTOR
    )

    # The platform administrator sets the global set. Nothing about the firms.
    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ACTOR, None)

    assert _codes_in(session, person.id, one.id) == {"SALES_MANAGER"}
    assert _codes_in(session, person.id, two.id) == {"SALES_EXECUTIVE"}
    assert _codes_in(session, person.id, None) == {"VIEWER"}


def test_a_platform_administrator_may_grant_globally_or_in_one_firm() -> None:
    """Both are theirs, and they are separate sets."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one)
    _member(session, person, two)

    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ACTOR, None)
    service.set_user_firm_roles(
        person.id, one.id, [_role_id(session, "FIRM_ADMIN")], ACTOR
    )

    assert _codes_in(session, person.id, None) == {"VIEWER"}
    assert _codes_in(session, person.id, one.id) == {"FIRM_ADMIN"}
    # Granted where it was named, and nowhere else.
    assert _codes_in(session, person.id, two.id) == set()


def test_a_firm_administrator_cannot_remove_a_global_role() -> None:
    """The rule the split rests on.

    A firm administrator replaces their own firm's set. The global grant is a
    platform decision and survives -- so in their firm the person keeps it.
    """
    service, session = _service()
    one = _firm(session, "F1")
    person = _user(service, "person@example.com")
    _member(session, person, one)
    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ACTOR, None)

    service.set_user_firm_roles(
        person.id, one.id, [_role_id(session, "CASHIER")], ACTOR, frozenset({one.id})
    )

    assert _codes_in(session, person.id, None) == {"VIEWER"}
    assert _codes_in(session, person.id, one.id) == {"CASHIER"}


def test_a_firm_administrator_owns_their_own_firms_set() -> None:
    """Add and remove, in their firm, without reaching another."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one)
    _member(session, person, two)
    admin = _role_id(session, "FIRM_ADMIN")
    service.set_user_firm_roles(person.id, one.id, [admin], ACTOR)
    service.set_user_firm_roles(person.id, two.id, [admin], ACTOR)

    service.set_user_firm_roles(
        person.id, two.id, [_role_id(session, "CASHIER")], ACTOR, frozenset({two.id})
    )

    assert _codes_in(session, person.id, one.id) == {"FIRM_ADMIN"}
    assert _codes_in(session, person.id, two.id) == {"CASHIER"}


def test_a_firm_caller_cannot_reach_another_firm() -> None:
    """Refused by name rather than silently applied to their own firm."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one)
    _member(session, person, two)

    with pytest.raises(BusinessRuleError) as refusal:
        service.set_user_firm_roles(
            person.id,
            two.id,
            [_role_id(session, "CASHIER")],
            ACTOR,
            frozenset({one.id}),
        )

    assert "firms you administer" in str(refusal.value)
    assert _codes_in(session, person.id, two.id) == set()


def test_a_role_needs_a_membership_first() -> None:
    """A role in a firm somebody does not belong to is not reachable access.

    It would sit in the table and stay out of the token, which is built per
    membership -- so the grant would look done and do nothing.
    """
    service, session = _service()
    one = _firm(session, "F1")
    person = _user(service, "person@example.com")

    with pytest.raises(BusinessRuleError) as refusal:
        service.set_user_firm_roles(
            person.id, one.id, [_role_id(session, "CASHIER")], ACTOR
        )

    assert "Add the user to this firm" in str(refusal.value)


def test_each_caller_reads_back_what_they_manage() -> None:
    """What the screens render, and why they no longer mislead.

    The platform read used to return every row from every firm merged into one
    list, which read as "holds all of these, everywhere" -- and then a save
    made it true. It answers with the global set now, which is exactly what
    that save replaces.
    """
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one)
    _member(session, person, two)
    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ACTOR, None)
    service.set_user_firm_roles(
        person.id, one.id, [_role_id(session, "SALES_MANAGER")], ACTOR
    )
    service.set_user_firm_roles(
        person.id, two.id, [_role_id(session, "SALES_EXECUTIVE")], ACTOR
    )

    assert service.list_user_role_ids(person.id, None) == [_role_id(session, "VIEWER")]
    assert service.list_user_firm_role_ids(person.id, one.id) == [
        _role_id(session, "SALES_MANAGER")
    ]
    # A firm administrator sees the global set too -- read-only, because it
    # applies in their firm and hiding it would under-report the person.
    assert service.list_user_global_role_ids(person.id) == [_role_id(session, "VIEWER")]
