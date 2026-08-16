"""Beat plans, route types, and the call order of a round.

Three resources that shipped with no unit test at all. Beat plans have had
complete CRUD since the module was written and nothing exercised it; route
types had no update or delete to exercise; and `visit_sequence` -- the order a
round is walked in -- was writable from the first migration and unreadable
through the API, so nothing could have noticed if it were being stored wrong.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.sales.api.router import delete_route_type, update_route_type
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryCreate,
)
from app.sales.schemas.territory import (
    BeatPlanCreate,
    BeatPlanType,
    BeatPlanUpdate,
    RouteProfileInput,
    RouteTypeWrite,
    TerritoryCustomerAssignmentInput,
    VisitFrequency,
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


def _route(
    service: SalesTerritoryService,
    firm_id: UUID,
    actor: UUID,
    code: str,
    *,
    is_route: bool = True,
) -> UUID:
    """Create a root-level node, optionally carrying a route profile."""
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code=code,
            name=f"{code} node",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=(
                RouteProfileInput(visit_frequency=VisitFrequency.WEEKLY)
                if is_route
                else None
            ),
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return node.id


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


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper."""
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


def test_route_type_can_be_renamed_and_retired() -> None:
    session = _session_factory()()
    firm = _firm(session, "RTY")
    actor = uuid4()
    service = SalesTerritoryService(session)

    created = service.create_route_type(
        RouteTypeWrite(code="SALES", name="Sales Route"),
        firm_scope=firm.id,
        actor_id=actor,
    )
    updated = service.update_route_type(
        created.id,
        RouteTypeWrite(code="SALES", name="Sales Beat", description="Renamed"),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert updated.name == "Sales Beat"
    assert updated.description == "Renamed"

    service.delete_route_type(created.id, firm_scope=firm.id, actor_id=actor)
    assert service.list_route_types(firm_scope=firm.id) == []


def test_route_types_can_be_edited_and_deleted_through_the_api() -> None:
    """The Route Types screen edits and deletes through the router, not the service.

    `update_route_type` and `delete_route_type` existed on the service with no
    endpoint declaring their paths, so the screen's Edit and Delete buttons
    reached a route FastAPI had never heard of. Call the route functions the
    way a request does, so a missing declaration fails here rather than on the
    first click.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "RTAPI")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()

    session = factory()
    principal = _principal(
        user_id, {"TERRITORY_VIEW", "TERRITORY_UPDATE", "TERRITORY_DELETE"}
    )
    scope = _firm_scope(principal, session, firm.id)
    service = SalesTerritoryService(session)
    created = service.create_route_type(
        RouteTypeWrite(code="COLL", name="Collection"),
        firm_scope=firm.id,
        actor_id=user_id,
    )

    renamed = update_route_type(
        created.id,
        RouteTypeWrite(code="COLL", name="Collection Round"),
        scope=scope,
        db=session,
    )
    assert renamed.data is not None
    assert renamed.data.name == "Collection Round"

    response = delete_route_type(created.id, scope=scope, db=session)
    assert response.status_code == 204
    assert service.list_route_types(firm_scope=firm.id) == []


def test_route_type_code_must_stay_unique() -> None:
    session = _session_factory()()
    firm = _firm(session, "RTU")
    actor = uuid4()
    service = SalesTerritoryService(session)
    service.create_route_type(
        RouteTypeWrite(code="SALES", name="Sales"), firm_scope=firm.id, actor_id=actor
    )
    second = service.create_route_type(
        RouteTypeWrite(code="COLLECT", name="Collection"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    # Create used to have no check at all and relied on the unique index, which
    # surfaces as a rollback rather than a message naming the clash.
    with pytest.raises(ConflictError):
        service.create_route_type(
            RouteTypeWrite(code="SALES", name="Another"),
            firm_scope=firm.id,
            actor_id=actor,
        )
    with pytest.raises(ConflictError):
        service.update_route_type(
            second.id,
            RouteTypeWrite(code="SALES", name="Collection"),
            firm_scope=firm.id,
            actor_id=actor,
        )
    # Renaming a type to its own code is not a clash.
    service.update_route_type(
        second.id,
        RouteTypeWrite(code="COLLECT", name="Collection Round"),
        firm_scope=firm.id,
        actor_id=actor,
    )


def test_a_route_type_in_use_cannot_be_deleted() -> None:
    """There is no FK guard, so deleting one would blank the column silently."""
    session = _session_factory()()
    firm = _firm(session, "RTD")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route_type = service.create_route_type(
        RouteTypeWrite(code="SALES", name="Sales Route"),
        firm_scope=firm.id,
        actor_id=actor,
    )
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    service.create_territory(
        TerritoryCreate(
            code="RT01",
            name="North Beat",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(
                route_type_id=route_type.id,
                visit_frequency=VisitFrequency.WEEKLY,
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    with pytest.raises(ConflictError) as caught:
        service.delete_route_type(route_type.id, firm_scope=firm.id, actor_id=actor)
    assert "1 route(s)" in str(caught.value)


def test_route_type_of_another_firm_is_not_found() -> None:
    session = _session_factory()()
    mine = _firm(session, "MINE")
    theirs = _firm(session, "THRS")
    actor = uuid4()
    service = SalesTerritoryService(session)
    row = service.create_route_type(
        RouteTypeWrite(code="SALES", name="Sales"), firm_scope=theirs.id, actor_id=actor
    )
    with pytest.raises(ResourceNotFoundError):
        service.update_route_type(
            row.id,
            RouteTypeWrite(code="SALES", name="Hijacked"),
            firm_scope=mine.id,
            actor_id=actor,
        )


def test_beat_plan_round_trips_with_its_stops() -> None:
    session = _session_factory()()
    firm = _firm(session, "BPC")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")

    created = service.create_beat_plan(
        BeatPlanCreate(
            code="MON-NORTH",
            name="Monday North",
            territory_id=route,
            plan_type=BeatPlanType.WEEKLY,
            weekday=1,
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
            notes="Every Monday",
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert created.code == "MON-NORTH"
    assert created.weekday == 1
    assert created.is_active is True

    fetched = service.get_beat_plan(created.id, firm_scope=firm.id)
    assert fetched.name == "Monday North"

    listed, total = service.list_beat_plans(firm_scope=firm.id, page=1, page_size=20)
    assert [row.code for row in listed] == ["MON-NORTH"]
    assert total == 1

    updated = service.update_beat_plan(
        created.id,
        BeatPlanUpdate(
            code="MON-NORTH",
            name="Monday North Round",
            territory_id=route,
            plan_type=BeatPlanType.WEEKLY,
            weekday=3,
            is_active=False,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert updated.name == "Monday North Round"
    assert updated.weekday == 3
    assert updated.is_active is False

    service.delete_beat_plan(created.id, firm_scope=firm.id, actor_id=actor)
    assert service.list_beat_plans(firm_scope=firm.id, page=1, page_size=20)[1] == 0


def test_beat_plan_must_target_a_route() -> None:
    """A plan on a region calls nobody, because assignments live on routes."""
    session = _session_factory()()
    firm = _firm(session, "BPR")
    actor = uuid4()
    service = SalesTerritoryService(session)
    not_a_route = _route(service, firm.id, actor, "RGN01", is_route=False)

    with pytest.raises(ValidationError) as caught:
        service.create_beat_plan(
            BeatPlanCreate(
                code="BAD",
                name="Region plan",
                territory_id=not_a_route,
                plan_type=BeatPlanType.WEEKLY,
                weekday=1,
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
    assert "is not a route" in str(caught.value)


def test_beat_plan_code_must_stay_unique_in_the_firm() -> None:
    session = _session_factory()()
    firm = _firm(session, "BPU")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    service.create_beat_plan(
        BeatPlanCreate(
            code="MON",
            name="Monday",
            territory_id=route,
            plan_type=BeatPlanType.WEEKLY,
            weekday=1,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    with pytest.raises(ConflictError):
        service.create_beat_plan(
            BeatPlanCreate(
                code="MON",
                name="Monday again",
                territory_id=route,
                plan_type=BeatPlanType.WEEKLY,
                weekday=2,
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )


def test_customers_come_back_in_call_order_with_the_unplaced_last() -> None:
    """The ordering rule this repo has been bitten by before.

    On ASC, SQLite sorts NULLs first and PostgreSQL sorts them last, so a bare
    `.asc()` leads the round with the customers nobody has placed here and
    trails with them in production. The two disagree, which is the whole
    problem: whichever one you test against, the other is wrong.
    """
    session = _session_factory()()
    firm = _firm(session, "SEQ")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    first = _customer(session, firm.id, "C1")
    second = _customer(session, firm.id, "C2")
    unplaced = _customer(session, firm.id, "C3")

    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(
                    customer_id=second.id, visit_sequence=2
                ),
                TerritoryCustomerAssignmentInput(customer_id=unplaced.id),
                TerritoryCustomerAssignmentInput(
                    customer_id=first.id, visit_sequence=1
                ),
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    on_round = service.customers(route, firm_scope=firm.id)
    assert [row.customer_id for row in on_round] == [
        first.id,
        second.id,
        unplaced.id,
    ]
    assert [row.visit_sequence for row in on_round] == [1, 2, None]
    assert on_round[0].is_potential is False


def test_a_customer_can_be_on_two_rounds_at_once() -> None:
    """A distributor calls the same shop to sell and again to collect.

    `set_customers` used to clear a customer's assignment to *every* territory,
    with no `territory_id` filter on the delete, so putting a shop on the
    collection round silently took it off the sales round -- and nothing said
    so.
    """
    session = _session_factory()()
    firm = _firm(session, "TWO")
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales_round = _route(service, firm.id, actor, "RT-SALES")
    collection_round = _route(service, firm.id, actor, "RT-COLL")
    shop = _customer(session, firm.id, "C1")

    service.set_customers(
        sales_round,
        TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    service.set_customers(
        collection_round,
        TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert [
        row.customer_id for row in service.customers(sales_round, firm_scope=firm.id)
    ] == [shop.id]
    assert [
        row.customer_id
        for row in service.customers(collection_round, firm_scope=firm.id)
    ] == [shop.id]


def test_dropping_a_customer_from_one_round_leaves_the_other_alone() -> None:
    session = _session_factory()()
    firm = _firm(session, "DROP")
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales_round = _route(service, firm.id, actor, "RT-SALES")
    collection_round = _route(service, firm.id, actor, "RT-COLL")
    shop = _customer(session, firm.id, "C1")
    other = _customer(session, firm.id, "C2")

    for round_id in (sales_round, collection_round):
        service.set_customers(
            round_id,
            TerritoryAssignCustomersRequest(customer_ids=[shop.id, other.id]),
            firm_scope=firm.id,
            actor_id=actor,
        )

    service.set_customers(
        sales_round,
        TerritoryAssignCustomersRequest(customer_ids=[other.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert [
        row.customer_id for row in service.customers(sales_round, firm_scope=firm.id)
    ] == [other.id]
    assert sorted(
        str(row.customer_id)
        for row in service.customers(collection_round, firm_scope=firm.id)
    ) == sorted([str(shop.id), str(other.id)])


def test_re_saving_a_round_keeps_the_call_order_it_was_not_told_about() -> None:
    """The picker sends bare ids; it must not flatten the sequence."""
    session = _session_factory()()
    firm = _firm(session, "KEEP")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    first = _customer(session, firm.id, "C1")
    second = _customer(session, firm.id, "C2")

    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(
                    customer_id=first.id, visit_sequence=1
                ),
                TerritoryCustomerAssignmentInput(
                    customer_id=second.id, visit_sequence=2
                ),
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[first.id, second.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert [
        row.visit_sequence for row in service.customers(route, firm_scope=firm.id)
    ] == [1, 2]


def test_a_second_round_does_not_take_the_primary_flag() -> None:
    """The flag has to settle which round a sale counts against.

    It used to be set unconditionally, so a shop on two rounds had two
    primaries and `resolve_sales_scope` -- which looks for exactly one --
    resolved to nothing. The sale then landed in no report at all, silently.
    """
    session = _session_factory()()
    firm = _firm(session, "PRIM1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales = _route(service, firm.id, actor, "SALES01")
    collection = _route(service, firm.id, actor, "COLL01")
    shop = _customer(session, firm.id, "C1")

    for route in (sales, collection):
        service.set_customers(
            route,
            TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
            firm_scope=firm.id,
            actor_id=actor,
        )

    first = service.customers(sales, firm_scope=firm.id)
    second = service.customers(collection, firm_scope=firm.id)
    assert [row.is_primary for row in first] == [True]
    assert [row.is_primary for row in second] == [False]


def test_a_caller_can_still_move_the_primary_flag() -> None:
    session = _session_factory()()
    firm = _firm(session, "PRIM2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales = _route(service, firm.id, actor, "SALES01")
    collection = _route(service, firm.id, actor, "COLL01")
    shop = _customer(session, firm.id, "C1")
    service.set_customers(
        sales,
        TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    service.set_customers(
        sales,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(customer_id=shop.id, is_primary=False)
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    service.set_customers(
        collection,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(customer_id=shop.id, is_primary=True)
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert [row.is_primary for row in service.customers(sales, firm_scope=firm.id)] == [
        False
    ]
    assert [
        row.is_primary for row in service.customers(collection, firm_scope=firm.id)
    ] == [True]


def test_two_shops_cannot_share_a_stop_number() -> None:
    """Named in the refusal, not surfaced as a rollback.

    The partial index refuses it as well, but as "the operation violates
    uniqueness constraints", which names neither the round nor the number.
    """
    session = _session_factory()()
    firm = _firm(session, "SEQ1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    first = _customer(session, firm.id, "C1")
    second = _customer(session, firm.id, "C2")

    with pytest.raises(ValueError, match="share a stop number"):
        service.set_customers(
            route,
            TerritoryAssignCustomersRequest(
                entries=[
                    TerritoryCustomerAssignmentInput(
                        customer_id=first.id, visit_sequence=1
                    ),
                    TerritoryCustomerAssignmentInput(
                        customer_id=second.id, visit_sequence=1
                    ),
                ]
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
