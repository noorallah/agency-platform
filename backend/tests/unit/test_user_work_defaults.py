"""A person's usual branch and warehouse in a firm (backlog 44).

Where someone usually works -- never where they may work. Validated on save
(live, the warehouse the branch's) and on use (one retired since is dropped
and said so, never filled into a form).
"""

# ruff: noqa: D103

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.branches.services.user_work_defaults import UserWorkDefaultService
from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from tests.unit.test_opening_stock_import_file import _factory, _firm


def _setup() -> tuple[Session, Firm, Branch, Warehouse]:
    session = _factory()()
    firm = _firm(session)
    branch = session.scalar(select(Branch).where(Branch.firm_id == firm.id))
    main = session.scalar(
        select(Warehouse).where(Warehouse.firm_id == firm.id, Warehouse.code == "MAIN")
    )
    assert branch is not None and main is not None
    return session, firm, branch, main


def test_nothing_set_gives_nothing() -> None:
    session, firm, _, _ = _setup()
    value = UserWorkDefaultService(session).current(firm.id, uuid4())
    assert (value.branch_id, value.warehouse_id, value.ignored) == (None, None, ())


def test_a_person_sets_their_own_and_reads_it_back() -> None:
    session, firm, branch, main = _setup()
    user = uuid4()
    service = UserWorkDefaultService(session)
    service.set(firm.id, user, branch_id=branch.id, warehouse_id=main.id, actor_id=user)
    session.commit()

    value = service.current(firm.id, user)
    assert (value.branch_id, value.warehouse_id) == (branch.id, main.id)
    # Somebody else in the same firm is untouched.
    assert service.current(firm.id, uuid4()).branch_id is None


def test_a_warehouse_alone_brings_its_branch() -> None:
    session, firm, branch, main = _setup()
    user = uuid4()
    value = UserWorkDefaultService(session).set(
        firm.id, user, branch_id=None, warehouse_id=main.id, actor_id=user
    )
    assert value.branch_id == branch.id


def test_a_warehouse_of_another_branch_is_refused() -> None:
    session, firm, branch, main = _setup()
    other = Branch(
        firm_id=firm.id,
        code="BR2",
        name="Branch Two",
        display_name="Branch Two",
        working_hours={},
        status="ACTIVE",
    )
    session.add(other)
    session.commit()
    with pytest.raises(ValidationError, match="belongs to another branch"):
        UserWorkDefaultService(session).set(
            firm.id, uuid4(), branch_id=other.id, warehouse_id=main.id, actor_id=uuid4()
        )


def test_a_place_retired_since_is_dropped_and_said_so() -> None:
    session, firm, branch, main = _setup()
    user = uuid4()
    service = UserWorkDefaultService(session)
    service.set(firm.id, user, branch_id=branch.id, warehouse_id=main.id, actor_id=user)
    main.is_deleted = True
    session.commit()

    value = service.current(firm.id, user)
    assert value.branch_id == branch.id
    assert value.warehouse_id is None
    assert any("retired" in message for message in value.ignored)


def test_clearing_takes_both_back() -> None:
    session, firm, branch, main = _setup()
    user = uuid4()
    service = UserWorkDefaultService(session)
    service.set(firm.id, user, branch_id=branch.id, warehouse_id=main.id, actor_id=user)
    value = service.set(firm.id, user, branch_id=None, warehouse_id=None, actor_id=user)
    assert (value.branch_id, value.warehouse_id) == (None, None)


def test_the_routes_answer_for_the_caller_only() -> None:
    from app.branches.api.router import (
        WorkDefaultsWrite,
        my_work_defaults,
        set_my_work_defaults,
    )

    session, firm, branch, main = _setup()
    user = uuid4()
    scope = type("Scope", (), {"firm_id": firm.id, "actor_id": user})()
    set_my_work_defaults(
        data=WorkDefaultsWrite(branch_id=branch.id, warehouse_id=main.id),
        scope=scope,  # type: ignore[arg-type]
        db=session,
    )
    response = my_work_defaults(scope=scope, db=session)  # type: ignore[arg-type]
    assert response.data is not None
    assert response.data.warehouse_id == main.id


def _member(session: Session, firm: Firm, email: str, *, active: bool = True) -> UUID:
    """Add a user and their membership of the firm."""
    user = User(email=email, full_name="Clerk", password_hash="hash")
    session.add(user)
    session.flush()
    session.add(UserFirm(user_id=user.id, firm_id=firm.id, is_active=active))
    session.commit()
    return user.id


def test_an_administrator_sets_a_members_defaults_and_it_is_theirs() -> None:
    """The admin path writes the member's row, audited as the admin's act."""
    from app.branches.api.router import (
        WorkDefaultsWrite,
        member_work_defaults,
        set_member_work_defaults,
    )

    session, firm, branch, main = _setup()
    clerk = _member(session, firm, "clerk@example.local")
    admin = uuid4()
    scope = type("Scope", (), {"firm_id": firm.id, "actor_id": admin})()

    set_member_work_defaults(
        user_id=clerk,
        data=WorkDefaultsWrite(branch_id=branch.id, warehouse_id=main.id),
        scope=scope,  # type: ignore[arg-type]
        db=session,
    )

    # What the clerk's own forms will open with.
    mine = UserWorkDefaultService(session).current(firm.id, clerk)
    assert (mine.branch_id, mine.warehouse_id) == (branch.id, main.id)
    # The administrator's own defaults are untouched.
    assert UserWorkDefaultService(session).current(firm.id, admin).branch_id is None
    read = member_work_defaults(
        user_id=clerk, scope=scope, db=session  # type: ignore[arg-type]
    )
    assert read.data is not None and read.data.warehouse_id == main.id
    audit = session.scalars(
        select(AuditLog).where(AuditLog.action == "user_work_defaults.set")
    ).one()
    assert audit.actor_id == admin
    assert audit.after_data is not None
    assert audit.after_data["user_id"] == str(clerk)


def test_the_admin_path_is_held_to_the_firms_members() -> None:
    """A stranger, or a member who has left, is not found -- read or write."""
    from app.branches.api.router import (
        WorkDefaultsWrite,
        member_work_defaults,
        set_member_work_defaults,
    )

    session, firm, branch, _ = _setup()
    gone = _member(session, firm, "gone@example.local", active=False)
    scope = type("Scope", (), {"firm_id": firm.id, "actor_id": uuid4()})()
    for person in (uuid4(), gone):
        with pytest.raises(ResourceNotFoundError):
            member_work_defaults(
                user_id=person, scope=scope, db=session  # type: ignore[arg-type]
            )
        with pytest.raises(ResourceNotFoundError):
            set_member_work_defaults(
                user_id=person,
                data=WorkDefaultsWrite(branch_id=branch.id),
                scope=scope,  # type: ignore[arg-type]
                db=session,
            )


def test_the_admin_path_validates_like_the_own_one() -> None:
    """Another firm's warehouse is refused for a member just as for oneself."""
    from app.branches.api.router import WorkDefaultsWrite, set_member_work_defaults

    session, firm, _, _ = _setup()
    clerk = _member(session, firm, "clerk@example.local")
    scope = type("Scope", (), {"firm_id": firm.id, "actor_id": uuid4()})()
    with pytest.raises(ValidationError, match="working warehouses"):
        set_member_work_defaults(
            user_id=clerk,
            data=WorkDefaultsWrite(warehouse_id=uuid4()),
            scope=scope,  # type: ignore[arg-type]
            db=session,
        )
