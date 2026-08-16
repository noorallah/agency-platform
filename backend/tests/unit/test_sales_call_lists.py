"""Who a beat plan says to call, on a given date.

The call list is computed from the recurrence rule and the assignment tables,
never stored: materialising occurrences would need a regeneration story every
time a plan, a route or a customer assignment changed, and a stale list is one
that sends someone to the wrong shop.

Two rules carry most of the weight here. A plan that cannot be computed says so
instead of returning an empty list -- "nobody to call today" and "this system
cannot tell you" are different answers. And a fortnightly plan with no anchor
date refuses rather than guessing, because guessing puts half of those rounds
on the wrong week.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCreate,
)
from app.sales.schemas.territory import (
    BeatPlanCreate,
    BeatPlanCustomerStopInput,
    BeatPlanType,
    BeatPlanUpdate,
    RouteProfileInput,
    SalesmanAssignmentInput,
    TerritoryCustomerAssignmentInput,
    VisitFrequency,
)
from app.sales.services import SalesTerritoryService

#: 2026-08-17 is a Monday, and every weekday assertion below counts from it.
MONDAY = date(2026, 8, 17)


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
    service: SalesTerritoryService, firm_id: UUID, actor: UUID, code: str
) -> UUID:
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code=code,
            name=f"{code} node",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(visit_frequency=VisitFrequency.WEEKLY),
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return node.id


def _plan(
    service: SalesTerritoryService,
    firm_id: UUID,
    actor: UUID,
    route: UUID,
    code: str,
    *,
    weekday: int = 1,
    plan_type: BeatPlanType = BeatPlanType.WEEKLY,
    week_of_month: int | None = None,
    starts_on: date | None = None,
    ends_on: date | None = None,
    customer_stops: list[BeatPlanCustomerStopInput] | None = None,
) -> UUID:
    created = service.create_beat_plan(
        BeatPlanCreate(
            code=code,
            name=f"{code} plan",
            territory_id=route,
            plan_type=plan_type,
            weekday=weekday,
            week_of_month=week_of_month,
            starts_on=starts_on,
            ends_on=ends_on,
            customer_stops=customer_stops or [],
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return created.id


def test_a_call_list_walks_the_round_in_its_own_order() -> None:
    """The end this stage exists for: who is called today, in what order."""
    session = _session_factory()()
    firm = _firm(session, "CALL1")
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
                    customer_id=second.id, visit_sequence=1
                ),
                TerritoryCustomerAssignmentInput(
                    customer_id=first.id, visit_sequence=2
                ),
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _plan(service, firm.id, actor, route, "MON")

    listed = service.call_list(firm_scope=firm.id, on_date=MONDAY)

    assert len(listed.entries) == 1
    entry = listed.entries[0]
    assert entry.occurs is True
    assert [stop.customer_code for stop in entry.stops] == ["C2", "C1"]
    assert [stop.stop_order for stop in entry.stops] == [1, 2]


def test_a_plan_that_does_not_run_today_lists_nobody() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    customer = _customer(session, firm.id, "C1")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[customer.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _plan(service, firm.id, actor, route, "MON")

    listed = service.call_list(firm_scope=firm.id, on_date=date(2026, 8, 18))

    assert listed.entries[0].occurs is False
    assert listed.entries[0].stops == []


def test_a_fortnightly_plan_with_no_anchor_refuses_to_guess() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL3")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    _plan(service, firm.id, actor, route, "FORT", plan_type=BeatPlanType.FORTNIGHTLY)

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert entry.occurs is False
    assert entry.reason is not None
    assert "start date" in entry.reason


def test_a_fortnightly_plan_runs_every_second_week_from_its_anchor() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL4")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    _plan(
        service,
        firm.id,
        actor,
        route,
        "FORT",
        plan_type=BeatPlanType.FORTNIGHTLY,
        starts_on=MONDAY,
    )

    def occurs(on_date: date) -> bool:
        return service.call_list(firm_scope=firm.id, on_date=on_date).entries[0].occurs

    assert occurs(MONDAY) is True
    assert occurs(date(2026, 8, 24)) is False
    assert occurs(date(2026, 8, 31)) is True


def test_a_custom_plan_says_it_is_not_computed() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL5")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    _plan(service, firm.id, actor, route, "CUST", plan_type=BeatPlanType.CUSTOM)

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert entry.occurs is False
    assert entry.reason == "A custom plan's dates are not computed."


def test_a_monthly_plan_runs_on_its_nth_weekday() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL6")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    _plan(
        service,
        firm.id,
        actor,
        route,
        "MONTH",
        plan_type=BeatPlanType.MONTHLY,
        week_of_month=3,
    )

    def occurs(on_date: date) -> bool:
        return service.call_list(firm_scope=firm.id, on_date=on_date).entries[0].occurs

    # Mondays in August 2026 fall on the 3rd, 10th, 17th, 24th and 31st, so the
    # 17th is the third and the 10th is the second.
    assert occurs(MONDAY) is True
    assert occurs(date(2026, 8, 10)) is False


def test_a_plan_past_its_end_date_does_not_run() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL7")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    _plan(
        service,
        firm.id,
        actor,
        route,
        "ENDED",
        starts_on=date(2026, 1, 5),
        ends_on=date(2026, 6, 29),
    )

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert entry.occurs is False
    assert entry.reason == "The plan has ended."


def test_named_outlets_on_a_plan_win_over_the_whole_round() -> None:
    """A route split into day-beats calls only the shops that beat names."""
    session = _session_factory()()
    firm = _firm(session, "CALL8")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    first = _customer(session, firm.id, "C1")
    second = _customer(session, firm.id, "C2")
    third = _customer(session, firm.id, "C3")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[first.id, second.id, third.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _plan(
        service,
        firm.id,
        actor,
        route,
        "MONBEAT",
        customer_stops=[
            BeatPlanCustomerStopInput(customer_id=third.id, stop_order=1),
            BeatPlanCustomerStopInput(customer_id=first.id, stop_order=2),
        ],
    )

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert [stop.customer_code for stop in entry.stops] == ["C3", "C1"]


def test_a_call_list_can_be_narrowed_to_one_salesperson() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL9")
    actor = uuid4()
    service = SalesTerritoryService(session)
    mine = _route(service, firm.id, actor, "RT01")
    theirs = _route(service, firm.id, actor, "RT02")
    rep = User(email="rep@example.local", full_name="Rep", password_hash="hash")
    session.add(rep)
    session.flush()
    session.add(UserFirm(user_id=rep.id, firm_id=firm.id, is_active=True))
    session.commit()
    service.set_salesmen(
        mine,
        TerritoryAssignSalesmenRequest(
            assignments=[SalesmanAssignmentInput(user_id=rep.id, is_primary=True)]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _plan(service, firm.id, actor, mine, "MINE")
    _plan(service, firm.id, actor, theirs, "THEIRS")

    listed = service.call_list(firm_scope=firm.id, on_date=MONDAY, salesman_id=rep.id)

    assert [entry.beat_plan_code for entry in listed.entries] == ["MINE"]


def test_an_inactive_plan_is_not_on_any_call_list() -> None:
    session = _session_factory()()
    firm = _firm(session, "CALL10")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    plan_id = _plan(service, firm.id, actor, route, "MON")
    plan = service.get_beat_plan(plan_id, firm_scope=firm.id)
    service.update_beat_plan(
        plan_id,
        BeatPlanUpdate(
            code=plan.code,
            name=plan.name,
            territory_id=plan.territory_id,
            plan_type=BeatPlanType.WEEKLY,
            weekday=1,
            is_active=False,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert service.call_list(firm_scope=firm.id, on_date=MONDAY).entries == []


def _route_with_window(
    service: SalesTerritoryService,
    firm_id: UUID,
    actor: UUID,
    code: str,
    *,
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> UUID:
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code=code,
            name=f"{code} node",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(
                visit_frequency=VisitFrequency.WEEKLY,
                effective_from=effective_from,
                effective_to=effective_to,
            ),
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return node.id


def test_a_route_out_of_its_window_calls_nobody() -> None:
    """The effective dates decide something now.

    They were written from the first migration and read nowhere, so a route
    "effective until June" still ran in August -- unlike UOM conversion rules
    and tax profiles, both of which filter on theirs.
    """
    session = _session_factory()()
    firm = _firm(session, "WIN1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route_with_window(
        service, firm.id, actor, "RT01", effective_to=date(2026, 6, 30)
    )
    customer = _customer(session, firm.id, "C1")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[customer.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _plan(service, firm.id, actor, route, "MON")

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert entry.occurs is False
    assert entry.reason == "The route is not in force on this date."
    assert entry.stops == []


def test_a_route_inside_its_window_still_runs() -> None:
    session = _session_factory()()
    firm = _firm(session, "WIN2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route_with_window(
        service,
        firm.id,
        actor,
        "RT01",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    customer = _customer(session, firm.id, "C1")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[customer.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _plan(service, firm.id, actor, route, "MON")

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert entry.occurs is True
    assert [stop.customer_code for stop in entry.stops] == ["C1"]


def test_a_route_before_it_starts_calls_nobody() -> None:
    session = _session_factory()()
    firm = _firm(session, "WIN3")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route_with_window(
        service, firm.id, actor, "RT01", effective_from=date(2026, 12, 1)
    )
    _plan(service, firm.id, actor, route, "MON")

    entry = service.call_list(firm_scope=firm.id, on_date=MONDAY).entries[0]

    assert entry.occurs is False
    assert entry.reason == "The route is not in force on this date."
