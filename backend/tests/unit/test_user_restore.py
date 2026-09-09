"""A deleted user can be brought back, by a platform administrator, as they were.

Deletion marks the row and revokes the sessions; it leaves the memberships,
the roles and the preferences in place. So a restore is one flag, and the
person signs in with their old password to their old firms and roles. Until
this existed the only way back was a hand-written UPDATE, while branches,
warehouses and customers each had a restore route.

The one thing a restore cannot do is coexist with a live account on the same
address: the email is unique among live accounts, so a re-onboarded person
blocks the restore of the old one. Refused by name rather than merged --
which of the two accounts should survive is a person's call.
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
        UserCreate(email=email, full_name="Leaver", password=PASSWORD), actor_id=ACTOR
    )


def _member(session: Session, user: User, firm: Firm) -> None:
    """Put a user in a firm, as its primary."""
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


def test_a_restored_user_has_everything_they_had() -> None:
    """The flag comes back; the memberships and roles never left."""
    service, session = _service()
    firm = _firm(session, "F1")
    person = _user(service, "leaver@example.com")
    _member(session, person, firm)
    service.set_user_firm_roles(
        person.id, firm.id, [_role_id(session, "SALES_MANAGER")], ACTOR
    )
    service.delete_user(person.id, actor_id=ACTOR)
    assert session.get(User, person.id).is_deleted is True

    restored = service.restore_user(person.id, ACTOR)

    assert restored.is_deleted is False
    assert restored.deleted_at is None
    firms = set(
        session.scalars(
            select(UserFirm.firm_id).where(
                UserFirm.user_id == person.id, UserFirm.is_deleted.is_(False)
            )
        )
    )
    assert firms == {firm.id}
    roles = set(
        session.scalars(
            select(UserRole.role_id).where(
                UserRole.user_id == person.id, UserRole.is_deleted.is_(False)
            )
        )
    )
    assert roles == {_role_id(session, "SALES_MANAGER")}
    # And they are back in the ordinary list, without asking for deleted rows.
    listed, total = service.list_users(1, 50, None, "email", False, None)
    assert person.id in {row.id for row in listed}


def test_a_live_user_cannot_be_restored() -> None:
    """Nothing to bring back, and saying so beats a silent no-op."""
    service, session = _service()
    person = _user(service, "leaver@example.com")

    with pytest.raises(BusinessRuleError, match="not deleted"):
        service.restore_user(person.id, ACTOR)


def test_a_reused_address_blocks_the_restore() -> None:
    """Two live accounts cannot share an address, so the old one stays deleted.

    Restore before re-onboarding, not after -- and the refusal says which
    account is in the way rather than merging or overwriting either.
    """
    service, session = _service()
    person = _user(service, "leaver@example.com")
    service.delete_user(person.id, actor_id=ACTOR)
    rehire = service.create_user(
        UserCreate(email="leaver@example.com", full_name="Rehire", password=PASSWORD),
        actor_id=ACTOR,
    )

    with pytest.raises(BusinessRuleError, match="Another live account"):
        service.restore_user(person.id, ACTOR)

    assert session.get(User, person.id).is_deleted is True
    assert session.get(User, rehire.id).is_deleted is False


def test_a_platform_caller_can_read_what_a_deleted_user_had() -> None:
    """The view dialog on a deleted row reads roles and firms as it opens.

    Reported from the running app: every one of those reads answered "User
    not found", so the dialog -- and the Restore in its footer -- never
    appeared. A platform caller reads them; a firm caller still gets 404.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    person = _user(service, "leaver@example.com")
    _member(session, person, firm)
    service.set_user_firm_roles(
        person.id, firm.id, [_role_id(session, "SALES_MANAGER")], ACTOR
    )
    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ACTOR, None)
    service.delete_user(person.id, actor_id=ACTOR)

    assert service.list_user_role_ids(person.id, None) == [_role_id(session, "VIEWER")]
    assert [row.firm_id for row in service.list_user_firms(person.id)] == [firm.id]
    assert service.list_user_firm_role_ids(person.id, firm.id, None) == [
        _role_id(session, "SALES_MANAGER")
    ]

    from app.core.exceptions import ResourceNotFoundError

    with pytest.raises(ResourceNotFoundError):
        service.list_user_role_ids(person.id, firm.id)
    with pytest.raises(ResourceNotFoundError):
        service.list_user_firms(person.id, frozenset({firm.id}))


def test_deleted_users_are_listed_instead_of_live_ones_when_asked_for() -> None:
    """The grid is the only place to find one, so the list has a switch.

    It answers the deleted rows **instead of** the live ones. The first cut
    mixed them in, and a platform administrator choosing "Deleted" saw every
    active user beside the one they were looking for.
    """
    service, session = _service()
    person = _user(service, "leaver@example.com")
    stayer = _user(service, "stayer@example.com")
    service.delete_user(person.id, actor_id=ACTOR)

    live, live_total = service.list_users(1, 50, None, "email", False, None)
    deleted, deleted_total = service.list_users(
        1, 50, None, "email", False, None, deleted_only=True
    )

    assert {row.id for row in live} >= {stayer.id}
    assert person.id not in {row.id for row in live}
    assert [row.id for row in deleted] == [person.id]
    assert deleted_total == 1
    assert live_total >= 1


def test_inactive_users_are_listed_on_their_own_when_asked_for() -> None:
    """The Firm filter's Inactive choice: who is switched off, and nobody else.

    A narrowing of the live rows rather than a second population the way
    `deleted_only` is -- an inactive person is still on the ordinary list,
    marked Inactive; this answers "just those".
    """
    service, session = _service()
    shut = _user(service, "shut@example.com")
    open_ = _user(service, "open@example.com")
    shut.is_active = False
    session.commit()

    inactive, total = service.list_users(
        1, 50, None, "email", False, None, inactive_only=True
    )
    live, _ = service.list_users(1, 50, None, "email", False, None)

    assert [row.id for row in inactive] == [shut.id]
    assert total == 1
    assert {shut.id, open_.id} <= {
        row.id for row in live
    }, "the ordinary list still shows them, marked Inactive"

    # Beside `deleted_only` the flag means nothing: a deleted row's Active
    # flag is whatever it was, and the question asked is "who is deleted".
    service.delete_user(open_.id, actor_id=ACTOR)
    deleted, _ = service.list_users(
        1, 50, None, "email", False, None, deleted_only=True, inactive_only=True
    )
    assert [row.id for row in deleted] == [open_.id]


def test_active_only_is_the_mirror_of_inactive() -> None:
    """The Status filter's Active choice: the switched-on live rows."""
    service, session = _service()
    shut = _user(service, "shut@example.com")
    open_ = _user(service, "open@example.com")
    shut.is_active = False
    session.commit()

    active, total = service.list_users(
        1, 50, None, "email", False, None, active_only=True
    )

    assert {row.id for row in active} == {open_.id}
    assert total == 1
    assert shut.id not in {row.id for row in active}


def test_a_status_narrowing_composes_with_a_firm() -> None:
    """Inactive members of one firm -- the query the overloaded filter could not ask.

    The status flag and the firm scope are independent WHERE clauses, so the
    two dropdowns combine. This is the whole reason status came off the Firm
    filter onto its own.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    other = _firm(session, "F2")
    shut_here = _user(service, "shut-here@example.com")
    open_here = _user(service, "open-here@example.com")
    shut_elsewhere = _user(service, "shut-elsewhere@example.com")
    _member(session, shut_here, firm)
    _member(session, open_here, firm)
    _member(session, shut_elsewhere, other)
    shut_here.is_active = False
    shut_elsewhere.is_active = False
    session.commit()

    inactive_in_firm, total = service.list_users(
        1, 50, None, "email", False, firm.id, inactive_only=True
    )

    assert [row.id for row in inactive_in_firm] == [shut_here.id]
    assert total == 1, "not the active member, and not the inactive one elsewhere"
