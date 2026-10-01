"""A person's usual branch and warehouse in a firm (backlog 44).

Where someone usually works -- never where they may work. Validated on save
(live, the warehouse the branch's) and on use (one retired since is dropped
and said so, never filled into a form).
"""

# ruff: noqa: D103

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.branches.services.user_work_defaults import UserWorkDefaultService
from app.core.exceptions import ValidationError
from app.firms.models import Firm
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
