"""The firm's own directory of people, and what gates it.

Three screens needed a list of a firm's people and no two could share one:
assigning a route read it behind ``TERRITORY_ASSIGN_SALESMEN``, agreeing a
commission rate behind ``COMMISSION_VIEW``, and the sales-order form -- which
records which salesman took a phone order -- held neither, so it offered no
salesman field at all and every phone order recorded nobody.

The gate is now membership of the firm, and that is the thing these tests
pin. A firm's own directory of names is not a privilege: everybody in the firm
already knows who their colleagues are. What needs a permission is *acting* on
a person -- putting them on a route, setting the rate they are paid -- and
those gates are unchanged.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.directory.api.router import list_firm_members
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import User, UserFirm


def _session_factory() -> sessionmaker[Session]:
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


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


def _scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


def _member(session: Session, firm: Firm, email: str, name: str) -> User:
    user = User(email=email, full_name=name, password_hash="hash")
    session.add(user)
    session.flush()
    session.add(UserFirm(user_id=user.id, firm_id=firm.id, is_active=True))
    session.commit()
    return user


def test_the_directory_holds_this_firm_s_live_members_and_nobody_else() -> None:
    session = _session_factory()()
    firm = _firm(session, "DIR")
    other = _firm(session, "OTHR")

    active = _member(session, firm, "ravi@example.local", "Ravi Kumar")
    inactive = User(
        email="old@example.local", full_name="Former Rep", password_hash="hash"
    )
    stranger = User(
        email="other@example.local", full_name="Other Firm", password_hash="hash"
    )
    removed = User(
        email="gone@example.local", full_name="Deleted User", password_hash="hash"
    )
    session.add_all([inactive, stranger, removed])
    session.flush()
    removed.is_deleted = True
    session.add_all(
        [
            UserFirm(user_id=inactive.id, firm_id=firm.id, is_active=False),
            UserFirm(user_id=stranger.id, firm_id=other.id, is_active=True),
            UserFirm(user_id=removed.id, firm_id=firm.id, is_active=True),
        ]
    )
    session.commit()

    scope = _scope(_principal(active.id, set()), session, firm.id)
    members = list_firm_members(scope=scope, db=session).data
    assert members is not None

    # A membership that was withdrawn, another firm's people, and a deleted
    # account are all absent. Only the first is obvious from the query.
    assert [row.user_id for row in members] == [active.id]
    assert members[0].full_name == "Ravi Kumar"
    assert members[0].email == "ravi@example.local"


def test_a_member_holding_no_permission_at_all_can_read_it() -> None:
    """The decision this endpoint exists to record.

    It replaced three copies behind three permissions, each of which locked
    out a role that legitimately needed the names. Seeing who you work with is
    not a privilege; doing something to them is.
    """
    session = _session_factory()()
    firm = _firm(session, "OPEN")
    user = _member(session, firm, "rep@example.local", "Rep")

    scope = _scope(_principal(user.id, set()), session, firm.id)
    members = list_firm_members(scope=scope, db=session).data

    assert members is not None
    assert [row.email for row in members] == ["rep@example.local"]


def test_somebody_outside_the_firm_cannot_read_it() -> None:
    """Membership is a real gate, not a formality.

    A directory readable by anybody holding a token would leak one firm's
    staff to another firm's user on a shared deployment.
    """
    session = _session_factory()()
    firm = _firm(session, "MINE")
    other = _firm(session, "YOURS")
    _member(session, firm, "inside@example.local", "Inside")
    outsider = _member(session, other, "outside@example.local", "Outside")

    with pytest.raises(AuthorizationError):
        _scope(_principal(outsider.id, set()), session, firm.id)


def test_a_request_naming_no_firm_is_refused() -> None:
    """There is no firm-less directory: the question needs a firm to answer."""
    session = _session_factory()()
    firm = _firm(session, "NOFIRM")
    user = _member(session, firm, "someone@example.local", "Someone")

    with pytest.raises(AuthorizationError):
        _scope(_principal(user.id, set()), session, None)


def test_the_directory_is_ordered_by_name() -> None:
    """A picker in insertion order makes somebody hunt for a colleague."""
    session = _session_factory()()
    firm = _firm(session, "SORT")
    _member(session, firm, "zoya@example.local", "Zoya Khan")
    reader = _member(session, firm, "asha@example.local", "Asha Nair")
    _member(session, firm, "meera@example.local", "Meera Raghavan")

    scope = _scope(_principal(reader.id, set()), session, firm.id)
    members = list_firm_members(scope=scope, db=session).data

    assert members is not None
    assert [row.full_name for row in members] == [
        "Asha Nair",
        "Meera Raghavan",
        "Zoya Khan",
    ]


def test_a_platform_administrator_may_read_any_firm_s_directory() -> None:
    """Consistent with every other firm-scoped read, and it has to be.

    Provisioning and support both administer a firm the administrator is not a
    member of; refusing here would make the directory the one firm-scoped
    resource they could not see.
    """
    session = _session_factory()()
    firm = _firm(session, "ADMIN")
    _member(session, firm, "staff@example.local", "Staff Member")

    admin = Principal(
        subject=uuid4(),
        roles=frozenset({"platform_admin"}),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(uuid4()),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=["platform_admin"],
        ),
    )
    scope = _scope(admin, session, firm.id)
    members = list_firm_members(scope=scope, db=session).data

    assert members is not None
    assert [row.email for row in members] == ["staff@example.local"]
