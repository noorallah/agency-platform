"""A firm administrator staffs the firms they administer, and only those.

`FIRM_ADMIN` holds `USER_CREATE`, `USER_VIEW`, `USER_UPDATE`, `ROLE_ASSIGN` and
`ROLE_VIEW` -- everything running a firm's people needs. It does not hold
`FIRM_VIEW`, which is a platform code and one of the set a firm administrator
may not even grant. Setting a user's firm memberships was gated on the platform
designation, so an administrator of two firms could not put a new hire in both:
the ordinary case, refused outright.

The reasoning on that gate was "which firms a person belongs to is a cross-firm
fact, so not a decision any single firm's administrator can make". The first
half is true and the second does not follow. What the cross-firm part actually
requires is **reach**, and two things follow from it, both tested here:

* they may name only firms they themselves may staff, judged on holding
  `USER_CREATE` **in that firm** rather than on mere membership; and
* the call **merges** rather than replaces, or a firm administrator saving a
  membership of their own firm would silently remove that person from every
  other firm on the platform -- the endpoint's own last loop soft-deletes
  everything the request did not name.
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
from app.core.exceptions import BusinessRuleError, ValidationError
from app.firms.models import Firm
from app.identity.models import PlatformAdmin, Role, User, UserFirm, UserRole
from app.identity.schemas.api import UserCreate, UserFirmAssignment, UserUpdate
from app.identity.services import IdentityService
from app.identity.system_seed import ROLE_PERMISSION_CODES, seed_system_rbac

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


def _member(session: Session, user: User, firm: Firm, primary: bool = False) -> None:
    """Put a user in a firm."""
    session.add(
        UserFirm(
            user_id=user.id,
            firm_id=firm.id,
            is_primary=primary,
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


def _codes_held(session: Session, user_id: UUID, firm_id: UUID | None) -> set[str]:
    """Return the role codes a user holds, in one firm's scope."""
    return set(
        session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.firm_id == firm_id,
                UserRole.is_deleted.is_(False),
            )
        )
    )


def _firms_of(session: Session, user: User) -> set[UUID]:
    """Return the firms a user is actively a member of."""
    return set(
        session.scalars(
            select(UserFirm.firm_id).where(
                UserFirm.user_id == user.id,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
            )
        )
    )


def _primary_of(session: Session, user: User) -> UUID | None:
    """Return the firm a user lands in when they sign in."""
    return session.scalar(
        select(UserFirm.firm_id).where(
            UserFirm.user_id == user.id,
            UserFirm.is_primary.is_(True),
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
        )
    )


def test_a_firm_admin_holds_everything_needed_to_create_a_user() -> None:
    """Except `FIRM_VIEW`, which is why the desktop button was hidden.

    The desktop's New-user gate asked for all five. Four are the role's own
    job; the fifth is a platform code it can never be given, so the single
    role whose whole purpose is running a firm's people had no way to create
    one.
    """
    granted = ROLE_PERMISSION_CODES["FIRM_ADMIN"]

    assert {
        "USER_CREATE",
        "USER_VIEW",
        "USER_UPDATE",
        "ROLE_ASSIGN",
        "ROLE_VIEW",
    } <= granted
    assert "FIRM_VIEW" not in granted


def test_a_multi_firm_admin_can_staff_both_of_their_firms() -> None:
    """The case that was refused outright."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    hire = _user(service, "hire@example.com")

    service.set_user_firms(
        hire.id,
        [
            UserFirmAssignment(firm_id=one.id, is_primary=True, is_active=True),
            UserFirmAssignment(firm_id=two.id, is_primary=False, is_active=True),
        ],
        ACTOR,
        frozenset({one.id, two.id}),
    )

    assert _firms_of(session, hire) == {one.id, two.id}


def test_a_firm_outside_the_callers_reach_is_refused_by_name() -> None:
    """Refused, not quietly dropped.

    A request that silently does less than it said is how somebody comes to
    believe a user was added to a firm they were not.
    """
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    hire = _user(service, "hire@example.com")

    with pytest.raises(BusinessRuleError):
        service.set_user_firms(
            hire.id,
            [UserFirmAssignment(firm_id=two.id, is_primary=True, is_active=True)],
            ACTOR,
            frozenset({one.id}),
        )

    assert _firms_of(session, hire) == set()


def test_saving_one_firm_does_not_remove_the_person_from_the_others() -> None:
    """The destructive half, and the reason this merges rather than replaces.

    `set_user_firms` soft-deletes every membership the request did not name.
    That is right when the caller can see them all and catastrophic when they
    cannot: a firm administrator correcting their own firm's membership would
    take the person out of every other firm on the platform.
    """
    service, session = _service()
    one, two, three = _firm(session, "F1"), _firm(session, "F2"), _firm(session, "F3")
    person = _user(service, "person@example.com")
    _member(session, person, one, primary=True)
    _member(session, person, two)
    _member(session, person, three)

    # An administrator of F1 alone, saving F1.
    service.set_user_firms(
        person.id,
        [UserFirmAssignment(firm_id=one.id, is_primary=True, is_active=True)],
        ACTOR,
        frozenset({one.id}),
    )

    assert _firms_of(session, person) == {one.id, two.id, three.id}


def test_a_scoped_caller_can_still_remove_from_their_own_firm() -> None:
    """Merging must not mean nothing can be taken away."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one, primary=True)
    _member(session, person, two)

    service.set_user_firms(person.id, [], ACTOR, frozenset({two.id}))

    assert _firms_of(session, person) == {one.id}


def test_a_scoped_caller_does_not_move_the_primary_firm() -> None:
    """One flag across every firm somebody belongs to.

    `UQ_user_firms_active_primary` allows one active primary per user, so a
    caller who can see only some of them setting it would either collide with
    a primary they cannot see or quietly demote it.
    """
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one, primary=True)
    _member(session, person, two)

    # An administrator of F2, trying to make F2 primary.
    service.set_user_firms(
        person.id,
        [UserFirmAssignment(firm_id=two.id, is_primary=True, is_active=True)],
        ACTOR,
        frozenset({two.id}),
    )

    assert _primary_of(session, person) == one.id


def test_a_new_hire_with_no_primary_lands_somewhere() -> None:
    """Otherwise they sign in with no firm selected and see nothing."""
    service, session = _service()
    one = _firm(session, "F1")
    hire = _user(service, "hire@example.com")

    service.set_user_firms(
        hire.id,
        [UserFirmAssignment(firm_id=one.id, is_primary=False, is_active=True)],
        ACTOR,
        frozenset({one.id}),
    )

    assert _primary_of(session, hire) == one.id


def test_a_platform_caller_still_replaces_the_whole_list() -> None:
    """None means every firm, which is what they have always had.

    The merge is a narrowing of a caller's reach, not a change to what the
    endpoint means.
    """
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "person@example.com")
    _member(session, person, one, primary=True)
    _member(session, person, two)

    service.set_user_firms(
        person.id,
        [UserFirmAssignment(firm_id=one.id, is_primary=True, is_active=True)],
        ACTOR,
        None,
    )

    assert _firms_of(session, person) == {one.id}


# --------------------------------------------------------------------------
# Finding somebody who already has an account
# --------------------------------------------------------------------------


def test_a_short_term_is_refused() -> None:
    """`"a"` must not return the platform.

    The lookup reaches across firms, so it is a lookup and not a directory.
    The minimum term is the first of the limits that makes that true.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    _user(service, "asha@example.com")

    with pytest.raises(ValidationError):
        service.lookup_users("as", firm.id)

    # Three is enough.
    assert service.lookup_users("ash", firm.id)


def test_a_lookup_finds_somebody_in_another_firm_by_name_and_by_email() -> None:
    """The gap this exists to close.

    `list_users` filters to the caller's own members and applies `search`
    *after* that filter, so a firm administrator could not find -- or even
    learn the existence of -- somebody who already has an account elsewhere.
    """
    service, session = _service()
    mine, theirs = _firm(session, "F1"), _firm(session, "F2")
    outsider = _user(service, "asha.rao@elsewhere.example")
    outsider.full_name = "Asha Rao"
    _member(session, outsider, theirs)
    session.commit()

    by_name = service.lookup_users("Asha", mine.id)
    by_email = service.lookup_users("elsewhere.example", mine.id)

    assert [row.id for row, _ in by_name] == [outsider.id]
    assert [row.id for row, _ in by_email] == [outsider.id]


def test_a_lookup_never_says_which_firms_somebody_is_in() -> None:
    """The one fact a firm must not learn about another.

    The service answers `(User, already_a_member)` and the response schema
    carries four fields. Neither can name a firm the caller cannot see, which
    is the whole reason `UserLookupResponse` is not `UserResponse`.
    """
    from app.identity.schemas.api import UserLookupResponse

    assert set(UserLookupResponse.model_fields) == {
        "id",
        "full_name",
        "email",
        "already_a_member",
    }


def test_a_lookup_marks_the_callers_own_people() -> None:
    """The caller's own people are marked rather than hidden.

    Otherwise somebody types a name, sees a row, and cannot tell why nothing
    happens when they add it.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    inside = _user(service, "inside@example.com")
    _member(session, inside, firm)
    outside = _user(service, "outside@example.com")
    session.commit()

    found = dict(
        (row.id, member) for row, member in service.lookup_users("example", firm.id)
    )

    assert found[inside.id] is True
    assert found[outside.id] is False


def test_a_lookup_never_returns_a_platform_administrator() -> None:
    """Mirroring `list_users`. Their accounts are not a firm's to hire."""
    service, session = _service()
    firm = _firm(session, "F1")
    boss = _user(service, "boss@example.com")
    session.add(PlatformAdmin(user_id=boss.id, created_by=ACTOR, updated_by=ACTOR))
    session.commit()

    assert service.lookup_users("boss", firm.id) == []


def test_a_lookup_is_capped_and_does_not_page() -> None:
    """A lookup answers "is this them?", not "who works here?".

    There is deliberately no page parameter, so the result is not a directory
    somebody can walk.
    """
    service, session = _service()
    firm = _firm(session, "F1")
    for index in range(service.LOOKUP_LIMIT + 5):
        _user(service, f"many{index:02d}@example.com")

    found = service.lookup_users("many", firm.id)

    assert len(found) == service.LOOKUP_LIMIT


# --------------------------------------------------------------------------
# What a firm administrator may see and do to a shared person
# --------------------------------------------------------------------------


def test_the_membership_list_shows_only_firms_the_caller_may_see() -> None:
    """It showed every one, on a route gated only by `ROLE_VIEW`.

    So a firm administrator holding any user id could read which firms that
    person belongs to -- for every user on the platform, not only shared ones.
    """
    service, session = _service()
    mine, theirs = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "shared@example.com")
    _member(session, person, mine, primary=True)
    _member(session, person, theirs)

    scoped = service.list_user_firms(person.id, frozenset({mine.id}))
    unscoped = service.list_user_firms(person.id)

    assert [row.firm_id for row in scoped] == [mine.id]
    # A platform caller passes None and still sees both.
    assert {row.firm_id for row in unscoped} == {mine.id, theirs.id}


def test_a_shared_person_is_flagged_on_the_row() -> None:
    """The grid can disable Edit rather than offer a form that cannot save.

    `_assert_exclusive_firm_user` refuses the save either way; the flag is
    what lets somebody find that out before they type.
    """
    service, session = _service()
    mine, theirs = _firm(session, "F1"), _firm(session, "F2")
    only_mine = _user(service, "mine@example.com")
    _member(session, only_mine, mine)
    shared = _user(service, "shared@example.com")
    _member(session, shared, mine)
    _member(session, shared, theirs)

    flagged = service.shared_user_ids([only_mine.id, shared.id], mine.id)

    assert flagged == {shared.id}
    # A platform caller sees every firm, so nothing is hidden from them.
    assert service.shared_user_ids([only_mine.id, shared.id], None) == set()


def test_a_shared_persons_profile_is_refused_and_says_why() -> None:
    """The rule is unchanged; the message now names the situation.

    So the screen can repeat it instead of showing a bare refusal.
    """
    service, session = _service()
    mine, theirs = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "shared@example.com")
    _member(session, person, mine)
    _member(session, person, theirs)

    with pytest.raises(BusinessRuleError) as refusal:
        service.update_user(person.id, UserUpdate(full_name="Renamed"), ACTOR, mine.id)

    assert "another firm" in str(refusal.value)


def test_a_shared_persons_roles_in_my_firm_are_still_mine_to_set() -> None:
    """The half that must keep working.

    Their profile is the platform's; the job they do in my firm is mine.
    """
    service, session = _service()
    mine, theirs = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "shared@example.com")
    _member(session, person, mine)
    _member(session, person, theirs)
    service.set_user_roles(
        person.id, [_role_id(session, "ACCOUNTANT")], ACTOR, theirs.id
    )

    service.set_user_roles(person.id, [_role_id(session, "CASHIER")], ACTOR, mine.id)

    assert _codes_held(session, person.id, mine.id) == {"CASHIER"}
    assert _codes_held(session, person.id, theirs.id) == {"ACCOUNTANT"}
