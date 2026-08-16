"""The four bulk territory operations, and the transaction they run in.

Bulk endpoints on this platform are a second implementation of something the
single-row path already does, and they have a history of being the weaker copy:
the branch and warehouse bulk operations wrote no audit rows and skipped the
delete guards their twins enforced, and the two import endpoints looped over a
service call that commits, so a batch failing on its fifth row returned an
error with the first four already written.

These bulk assignment methods had exactly that second defect. They are now one
transaction, and the test that matters is the refusal: a batch that fails
partway must leave nothing behind.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError
from app.customers.models import Customer
from app.firms.models import Firm
from app.sales.models import SalesTerritoryNode, TerritoryCustomerAssignment
from app.sales.schemas import (
    TerritoryBulkCustomerAssignment,
    TerritoryBulkMoveRequest,
    TerritoryBulkStatusRequest,
    TerritoryCreate,
)
from app.sales.schemas.territory import (
    TerritoryCustomerAssignmentInput,
    TerritoryStatus,
)
from app.sales.services import SalesTerritoryService


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


def _customer(session: Session, firm_id: UUID, code: str) -> Customer:
    row = Customer(
        firm_id=firm_id,
        code=code,
        customer_type="BUSINESS",
        name=f"{code} Stores",
        display_name=f"{code} Stores",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _node(
    service: SalesTerritoryService,
    firm_id: UUID,
    actor: UUID,
    code: str,
    *,
    level: int = 0,
    parent_id: UUID | None = None,
) -> UUID:
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    created = service.create_territory(
        TerritoryCreate(
            code=code,
            name=f"{code} node",
            hierarchy_level_id=hierarchy.levels[level].id,
            parent_id=parent_id,
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return created.id


def test_a_bulk_assignment_that_fails_partway_writes_nothing() -> None:
    """The defect this file exists for.

    `set_customers` commits, so looping over it applied each territory as it
    went. A batch naming a territory that does not exist wrote every territory
    before it and then raised -- the caller saw only the error and had no way
    to know half of it had landed.
    """
    session = _session_factory()()
    firm = _firm(session, "BULK1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    first = _node(service, firm.id, actor, "RT01")
    customer = _customer(session, firm.id, "C1")

    with pytest.raises(ResourceNotFoundError):
        service.bulk_set_customers(
            [
                TerritoryBulkCustomerAssignment(
                    territory_id=first, customer_ids=[customer.id]
                ),
                # No such territory: the batch must be refused whole.
                TerritoryBulkCustomerAssignment(
                    territory_id=uuid4(), customer_ids=[customer.id]
                ),
            ],
            firm_scope=firm.id,
            actor_id=actor,
        )

    session.rollback()
    assert service.customers(first, firm_scope=firm.id) == []


def test_a_bulk_assignment_that_succeeds_applies_every_territory() -> None:
    session = _session_factory()()
    firm = _firm(session, "BULK2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    first = _node(service, firm.id, actor, "RT01")
    second = _node(service, firm.id, actor, "RT02")
    one = _customer(session, firm.id, "C1")
    two = _customer(session, firm.id, "C2")

    result = service.bulk_set_customers(
        [
            TerritoryBulkCustomerAssignment(
                territory_id=first, customer_ids=[one.id, two.id]
            ),
            TerritoryBulkCustomerAssignment(territory_id=second, customer_ids=[two.id]),
        ],
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert result.affected == 2
    assert len(service.customers(first, firm_scope=firm.id)) == 2
    assert len(service.customers(second, firm_scope=firm.id)) == 1


def test_a_bulk_assignment_can_carry_the_call_order() -> None:
    """The bulk path forwarded only ids, making it weaker than its twin."""
    session = _session_factory()()
    firm = _firm(session, "BULK3")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _node(service, firm.id, actor, "RT01")
    one = _customer(session, firm.id, "C1")
    two = _customer(session, firm.id, "C2")

    service.bulk_set_customers(
        [
            TerritoryBulkCustomerAssignment(
                territory_id=route,
                entries=[
                    TerritoryCustomerAssignmentInput(
                        customer_id=two.id, visit_sequence=1
                    ),
                    TerritoryCustomerAssignmentInput(
                        customer_id=one.id, visit_sequence=2
                    ),
                ],
            )
        ],
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert [
        row.customer_id for row in service.customers(route, firm_scope=firm.id)
    ] == [two.id, one.id]


def test_a_bulk_status_change_records_one_audit_row_per_territory() -> None:
    """Not one summary row: a trail that says "5 changed" names none of them."""
    session = _session_factory()()
    firm = _firm(session, "BULK4")
    actor = uuid4()
    service = SalesTerritoryService(session)
    first = _node(service, firm.id, actor, "RT01")
    second = _node(service, firm.id, actor, "RT02")

    result = service.bulk_status_change(
        TerritoryBulkStatusRequest(
            territory_ids=[first, second], status=TerritoryStatus.INACTIVE
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert result.affected == 2
    rows = list(
        session.scalars(
            select(SalesTerritoryNode).where(
                SalesTerritoryNode.id.in_([first, second])
            )
        )
    )
    assert {row.status for row in rows} == {"INACTIVE"}
    changed = list(
        session.scalars(
            select(AuditLog).where(AuditLog.action == "sales_territory.status_changed")
        )
    )
    assert {row.entity_id for row in changed} == {first, second}


def test_a_bulk_move_reparents_and_repaths_every_territory() -> None:
    session = _session_factory()()
    firm = _firm(session, "BULK5")
    actor = uuid4()
    service = SalesTerritoryService(session)
    origin = _node(service, firm.id, actor, "NORTH")
    destination = _node(service, firm.id, actor, "SOUTH")
    child = _node(service, firm.id, actor, "RT01", level=1, parent_id=origin)

    result = service.bulk_move(
        TerritoryBulkMoveRequest(territory_ids=[child], new_parent_id=destination),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert result.affected == 1
    moved = session.scalar(
        select(SalesTerritoryNode).where(SalesTerritoryNode.id == child)
    )
    assert moved is not None
    assert moved.parent_id == destination
    assert moved.path.startswith("SOUTH/")


def test_a_bulk_move_under_a_missing_parent_moves_nobody() -> None:
    session = _session_factory()()
    firm = _firm(session, "BULK6")
    actor = uuid4()
    service = SalesTerritoryService(session)
    origin = _node(service, firm.id, actor, "NORTH")
    child = _node(service, firm.id, actor, "RT01", level=1, parent_id=origin)

    with pytest.raises(ResourceNotFoundError):
        service.bulk_move(
            TerritoryBulkMoveRequest(territory_ids=[child], new_parent_id=uuid4()),
            firm_scope=firm.id,
            actor_id=actor,
        )

    session.rollback()
    moved = session.scalar(
        select(SalesTerritoryNode).where(SalesTerritoryNode.id == child)
    )
    assert moved is not None
    assert moved.parent_id == origin


def test_a_bulk_assignment_refuses_a_customer_from_another_firm() -> None:
    """The guard the single-row path enforces, checked on the bulk path too."""
    session = _session_factory()()
    firm = _firm(session, "BULK7")
    other = _firm(session, "BULK8")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _node(service, firm.id, actor, "RT01")
    outsider = _customer(session, other.id, "X1")

    with pytest.raises(Exception):
        service.bulk_set_customers(
            [
                TerritoryBulkCustomerAssignment(
                    territory_id=route, customer_ids=[outsider.id]
                )
            ],
            firm_scope=firm.id,
            actor_id=actor,
        )

    session.rollback()
    assert (
        session.scalar(
            select(TerritoryCustomerAssignment).where(
                TerritoryCustomerAssignment.territory_id == route
            )
        )
        is None
    )
