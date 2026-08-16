"""Finding the outlets a round should call, by where they are.

A beat is built by walking a pin code, not by recognising names in an
alphabetical list — and the customer list could not answer that question. It
filters on city and state and nothing finer, with no pin code and no street,
and it knows nothing about territory assignment, so "which shops on this pin
code are not on a round yet" had no query behind it at all.

Two rules here are the ones worth holding. A customer with several addresses
must appear once, not once per address — the paging is wrong otherwise in a way
that looks like duplicate data. And `unassigned_only` means *no* round, not
"not this round": a distributor calling one shop on both a sales beat and a
collection round is ordinary, so a shop already on another round stays visible
by default.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.customers.models import Customer, CustomerAddress
from app.firms.models import Firm
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryCreate,
)
from app.sales.schemas.territory import (
    AssignableCustomerFilters,
    RouteProfileInput,
    VisitFrequency,
)
from app.sales.services import SalesTerritoryService

NO_FILTERS = AssignableCustomerFilters()


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Beat Firm",
        code="BEAT01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _customer(
    session: Session,
    firm_id: UUID,
    code: str,
    *,
    postal_code: str = "600001",
    area: str = "Parrys",
    city: str = "Chennai",
    addresses: int = 1,
) -> Customer:
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
    session.flush()
    for index in range(addresses):
        session.add(
            CustomerAddress(
                customer_id=row.id,
                address_type="SHIPPING",
                address_line1=f"{index + 1} Big Street",
                area=area,
                city=city,
                state="Tamil Nadu",
                country="IN",
                postal_code=postal_code,
                is_default_shipping=index == 0,
            )
        )
    session.commit()
    return row


def _route(
    service: SalesTerritoryService, firm_id: UUID, actor: UUID, code: str
) -> UUID:
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code=code,
            name=f"{code} round",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(visit_frequency=VisitFrequency.WEEKLY),
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return node.id


def test_outlets_can_be_found_by_pin_code() -> None:
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTerritoryService(session)
    _customer(session, firm.id, "C1", postal_code="600001")
    _customer(session, firm.id, "C2", postal_code="600002")

    rows, total = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=None,
        filters=AssignableCustomerFilters(postal_code="600001"),
        search=None,
        page=1,
        page_size=20,
    )

    assert total == 1
    assert [row.code for row in rows] == ["C1"]
    assert rows[0].postal_code == "600001"


def test_outlets_can_be_found_by_street() -> None:
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTerritoryService(session)
    _customer(session, firm.id, "C1", area="Parrys Corner")
    _customer(session, firm.id, "C2", area="Mylapore")

    rows, _ = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=None,
        filters=AssignableCustomerFilters(area="parrys"),
        search=None,
        page=1,
        page_size=20,
    )

    assert [row.code for row in rows] == ["C1"]


def test_a_shop_with_several_addresses_is_listed_once() -> None:
    """Matched through EXISTS, not a join, or the page count is wrong too."""
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTerritoryService(session)
    _customer(session, firm.id, "C1", addresses=3)

    rows, total = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=None,
        filters=AssignableCustomerFilters(postal_code="600001"),
        search=None,
        page=1,
        page_size=20,
    )

    assert total == 1
    assert len(rows) == 1


def test_unassigned_only_means_on_no_round_at_all() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    placed = _customer(session, firm.id, "C1")
    _customer(session, firm.id, "C2")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[placed.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    rows, _ = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=route,
        filters=AssignableCustomerFilters(unassigned_only=True),
        search=None,
        page=1,
        page_size=20,
    )

    assert [row.code for row in rows] == ["C2"]


def test_a_shop_on_another_round_stays_visible_and_says_which() -> None:
    """One outlet on both a sales beat and a collection round is ordinary."""
    session = _session_factory()()
    firm = _firm(session)
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

    rows, _ = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=collection,
        filters=NO_FILTERS,
        search=None,
        page=1,
        page_size=20,
    )

    assert len(rows) == 1
    assert rows[0].on_this_route is False
    assert rows[0].other_routes == ["SALES01"]


def test_a_shop_already_on_this_round_reports_its_place() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm.id, actor, "RT01")
    first = _customer(session, firm.id, "C1")
    second = _customer(session, firm.id, "C2")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[first.id, second.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    rows, _ = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=route,
        filters=NO_FILTERS,
        search=None,
        page=1,
        page_size=20,
    )

    assert all(row.on_this_route for row in rows)
    assert all(row.other_routes == [] for row in rows)


def test_another_firms_customers_are_never_offered() -> None:
    session = _session_factory()()
    firm = _firm(session)
    other = Firm(
        name="Other",
        code="OTHER1",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(other)
    session.commit()
    service = SalesTerritoryService(session)
    _customer(session, firm.id, "MINE")
    _customer(session, other.id, "THEIRS")

    rows, total = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=None,
        filters=NO_FILTERS,
        search=None,
        page=1,
        page_size=20,
    )

    assert total == 1
    assert [row.code for row in rows] == ["MINE"]


def test_a_search_term_still_matches_name_and_code() -> None:
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTerritoryService(session)
    _customer(session, firm.id, "APEX")
    _customer(session, firm.id, "ZENITH")

    rows, _ = service.assignable_customers(
        firm_scope=firm.id,
        territory_id=None,
        filters=NO_FILTERS,
        search="apex",
        page=1,
        page_size=20,
    )

    assert [row.code for row in rows] == ["APEX"]
