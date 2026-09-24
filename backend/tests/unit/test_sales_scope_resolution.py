"""Which territory, route and salesman a sales document lands in.

`sales_orders`, `sales_invoices` and `delivery_notes` have carried
`territory_id`, `route_id` and `salesman_id` since they were written, and
`/reports/by-territory`, `/reports/by-route` and `/reports/by-salesman` read
them -- but nothing had ever populated one. Every seeded order had all three
NULL and every one of those reports answered `[]` from an endpoint that was
itself correct.

These tests hold the resolution rules that feed them, and the one rule that
matters most is the refusal: a document must never be tagged with a guess,
because a report full of plausible rows is worse than an empty one.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.sales.models import TerritoryRouteProfile
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCreate,
)
from app.sales.schemas.territory import (
    RouteProfileInput,
    SalesmanAssignmentInput,
    TerritoryCustomerAssignmentInput,
    VisitFrequency,
)
from app.sales.services import SalesTerritoryService
from app.sales.services.scope_resolution import resolve_sales_scope
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401


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
        name="Scope Firm",
        code="SCOPE01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, firm_id: UUID, code: str = "CUS-001") -> Customer:
    row = Customer(
        firm_id=firm_id,
        code=code,
        customer_type="RETAIL",
        name=f"Customer {code}",
        display_name=f"Customer {code}",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _territory(
    service: SalesTerritoryService,
    firm_id: UUID,
    actor: UUID,
    code: str,
    *,
    level: int = 0,
    parent_id: UUID | None = None,
    is_route: bool = True,
) -> UUID:
    """Create one node, optionally carrying a route profile."""
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code=code,
            name=f"{code} node",
            hierarchy_level_id=hierarchy.levels[level].id,
            parent_id=parent_id,
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


def _assign_customer(
    service: SalesTerritoryService,
    territory_id: UUID,
    customer_id: UUID,
    firm_id: UUID,
    actor: UUID,
    *,
    is_primary: bool = True,
) -> None:
    service.set_customers(
        territory_id,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(
                    customer_id=customer_id, is_primary=is_primary
                )
            ]
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )


def _salesman(session: Session, firm_id: UUID, email: str) -> UUID:
    """Build a real user with active firm membership -- assignment needs both."""
    row = User(email=email, full_name="Rep", password_hash="hash")
    session.add(row)
    session.flush()
    session.add(UserFirm(user_id=row.id, firm_id=firm_id, is_active=True))
    session.commit()
    return row.id


def test_a_document_inherits_the_round_its_customer_is_on() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _territory(service, firm.id, actor, "RT01")
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.territory_id == route
    # The route id is the profile row, not the node -- that is what the three
    # document columns reference.
    assert scope.route_id is not None


def test_a_customer_on_no_round_resolves_to_nothing() -> None:
    session = _session_factory()()
    firm = _firm(session)
    customer = _customer(session, firm.id)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.territory_id is None
    assert scope.route_id is None
    assert scope.salesman_id is None


def test_two_rounds_with_no_primary_resolve_to_nothing() -> None:
    """A shop called on both a sales beat and a collection round names neither.

    This is the case the whole feature turns on. Picking the first row would
    fill `/reports/by-territory` with numbers that look right and credit the
    wrong round; an empty field at least says it does not know.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales = _territory(service, firm.id, actor, "SALES01")
    collection = _territory(service, firm.id, actor, "COLL01")
    customer = _customer(session, firm.id)
    _assign_customer(service, sales, customer.id, firm.id, actor, is_primary=False)
    _assign_customer(service, collection, customer.id, firm.id, actor, is_primary=False)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.territory_id is None


def test_the_primary_round_wins_when_one_is_marked() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales = _territory(service, firm.id, actor, "SALES01")
    collection = _territory(service, firm.id, actor, "COLL01")
    customer = _customer(session, firm.id)
    _assign_customer(service, sales, customer.id, firm.id, actor, is_primary=True)
    _assign_customer(service, collection, customer.id, firm.id, actor, is_primary=False)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.territory_id == sales


def test_a_territory_the_customer_is_not_on_is_refused() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _territory(service, firm.id, actor, "RT01")
    other = _territory(service, firm.id, actor, "RT02")
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)

    with pytest.raises(ValidationError, match="not assigned to RT02"):
        resolve_sales_scope(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            territory_id=other,
        )


def test_a_salesperson_off_the_round_is_refused() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _territory(service, firm.id, actor, "RT01")
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)
    stranger = _salesman(session, firm.id, "stranger@example.local")

    with pytest.raises(ValidationError, match="not assigned to this territory"):
        resolve_sales_scope(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            salesman_id=stranger,
        )


def test_a_salesperson_who_does_not_work_here_is_refused() -> None:
    """Membership is asked before coverage, and whether or not there is a round.

    The order, the delivery note and the invoice each asked it in their own
    service; the quotation and the sales return did not, so with no territory
    to check against **any id at all** was stored (D-TER-15). Asking it in
    the shared resolver asks it once, for all five.
    """
    session = _session_factory()()
    firm = _firm(session)
    customer = _customer(session, firm.id)

    with pytest.raises(ValidationError, match="not an active member"):
        resolve_sales_scope(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            salesman_id=uuid4(),
        )


def test_the_round_names_its_salesperson() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    salesman = _salesman(session, firm.id, "rep@example.local")
    route = _territory(service, firm.id, actor, "RT01")
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)
    service.set_salesmen(
        route,
        TerritoryAssignSalesmenRequest(
            assignments=[SalesmanAssignmentInput(user_id=salesman, is_primary=True)]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id == salesman


def test_a_manager_covering_children_is_inherited_by_the_route() -> None:
    """A region manager with `include_children` covers the rounds beneath them.

    Without this, a firm that assigns people at the region level -- which the
    assignment dialog encourages, since `include_children` is offered there --
    would file every document under nobody.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    manager = _salesman(session, firm.id, "manager@example.local")
    region = _territory(service, firm.id, actor, "REGION1", is_route=False)
    route = _territory(
        service, firm.id, actor, "RT01", level=1, parent_id=region, is_route=True
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)
    service.set_salesmen(
        region,
        TerritoryAssignSalesmenRequest(
            assignments=[
                SalesmanAssignmentInput(
                    user_id=manager, is_primary=True, include_children=True
                )
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id == manager


def test_a_route_above_the_leaf_still_reaches_the_document() -> None:
    """A firm whose round sits above the customer's node still gets a route id."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _territory(service, firm.id, actor, "RT01", is_route=True)
    leaf = _territory(
        service, firm.id, actor, "SUB01", level=1, parent_id=route, is_route=False
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, leaf, customer.id, firm.id, actor)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.territory_id == leaf
    assert scope.route_id is not None


def test_a_sales_order_saves_the_scope_the_reports_read() -> None:
    """The end the whole stage exists for: an order that reports can group.

    Resolution is server-side precisely so this holds for every creation path
    -- this order names no territory and no salesman, exactly as the desktop
    editor and the demo seeder send it.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    salesman = _salesman(session, firm.id, "rep@example.local")
    branch = Branch(
        firm_id=firm.id,
        code="BR-001",
        name="Branch",
        display_name="Branch",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(branch)
    session.commit()
    warehouse = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="WH-001",
        name="Warehouse",
        display_name="Warehouse",
        status="ACTIVE",
    )
    product = Product(
        firm_id=firm.id,
        code="SKU-001",
        name="Product",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add_all([warehouse, product])
    session.commit()

    territory_service = SalesTerritoryService(session)
    route = _territory(territory_service, firm.id, actor, "RT01")
    customer = _customer(session, firm.id)
    _assign_customer(territory_service, route, customer.id, firm.id, actor)
    territory_service.set_salesmen(
        route,
        TerritoryAssignSalesmenRequest(
            assignments=[SalesmanAssignmentInput(user_id=salesman, is_primary=True)]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    order = SalesOrderService(session).create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 16),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("2"),
                    unit_price=Decimal("50"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor,
    )

    assert order.territory_id == route
    assert order.salesman_id == salesman
    assert order.route_id is not None


def test_a_document_is_not_tagged_with_a_route_that_had_ended() -> None:
    """The effective window decides document tagging too, not only call lists.

    A sale dated after the round closed used to be filed against it, which is
    the kind of row that makes `/reports/by-route` look right and be wrong.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code="RT01",
            name="RT01 node",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(
                visit_frequency=VisitFrequency.WEEKLY,
                effective_to=date(2026, 6, 30),
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, node.id, customer.id, firm.id, actor)

    after = resolve_sales_scope(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        on_date=date(2026, 8, 16),
    )
    during = resolve_sales_scope(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        on_date=date(2026, 5, 1),
    )

    # The territory still applies -- the shop is on it either way. Only the
    # route, which is what the window describes, drops out.
    assert after.territory_id == node.id
    assert after.route_id is None
    assert during.route_id is not None


def test_with_no_date_the_route_still_applies() -> None:
    """A caller that cannot say when is not evidence the round had closed."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code="RT01",
            name="RT01 node",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(
                visit_frequency=VisitFrequency.WEEKLY,
                effective_to=date(2026, 6, 30),
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, node.id, customer.id, firm.id, actor)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.route_id is not None


def _route_of(session: Session, territory_id: UUID) -> UUID:
    """Return the live route profile id on a node."""
    profile_id = session.scalar(
        select(TerritoryRouteProfile.id).where(
            TerritoryRouteProfile.territory_id == territory_id,
            TerritoryRouteProfile.is_deleted.is_(False),
        )
    )
    assert profile_id is not None
    return profile_id


def test_a_named_route_that_had_ended_is_refused() -> None:
    """D-TER-9: the window was enforced on a blank and on nothing else.

    With the round closed at the end of June, a blank took no route -- and a
    caller who named it kept it. Now both are judged on the document's date.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    node = service.create_territory(
        TerritoryCreate(
            code="S1",
            name="S1 node",
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(
                visit_frequency=VisitFrequency.WEEKLY,
                effective_to=date(2026, 6, 30),
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, node.id, customer.id, firm.id, actor)
    route = _route_of(session, node.id)

    with pytest.raises(ValidationError, match="not in force on 2026-09-19"):
        resolve_sales_scope(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            route_id=route,
            on_date=date(2026, 9, 19),
        )
    during = resolve_sales_scope(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        route_id=route,
        on_date=date(2026, 5, 1),
    )
    assert during.route_id == route


def test_a_named_route_the_customer_is_not_on_is_refused() -> None:
    """A round that does not call this shop cannot carry its sale.

    N2 is a live round, but the customer is on S1; naming N2 was kept as
    sent. It is refused unless the customer is on N2 or a node beneath it.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    on_s1 = _territory(service, firm.id, actor, "S1")
    other = _territory(service, firm.id, actor, "N2")
    customer = _customer(session, firm.id)
    _assign_customer(service, on_s1, customer.id, firm.id, actor)

    with pytest.raises(ValidationError, match="Route N2 does not cover"):
        resolve_sales_scope(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            route_id=_route_of(session, other),
            on_date=date(2026, 9, 19),
        )
    resolved = resolve_sales_scope(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        route_id=_route_of(session, on_s1),
        on_date=date(2026, 9, 19),
    )
    assert resolved.route_id == _route_of(session, on_s1)
    assert resolved.territory_id == on_s1


def test_a_named_route_above_the_customer_s_node_is_accepted() -> None:
    """A route above the leaf reaches the document the way a derived one does."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    region = _territory(service, firm.id, actor, "RGN", is_route=True)
    leaf = _territory(
        service, firm.id, actor, "LEAF", level=1, parent_id=region, is_route=False
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, leaf, customer.id, firm.id, actor)

    resolved = resolve_sales_scope(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        route_id=_route_of(session, region),
        on_date=date(2026, 9, 19),
    )

    assert resolved.territory_id == leaf
    assert resolved.route_id == _route_of(session, region)


def test_another_firm_s_route_is_refused() -> None:
    """In the shared store an id is just an id; the firm is checked."""
    session = _session_factory()()
    firm = _firm(session)
    other = Firm(
        name="Other Firm",
        code="SCOPE02",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(other)
    session.commit()
    actor = uuid4()
    service = SalesTerritoryService(session)
    theirs = _territory(service, other.id, actor, "X1")
    customer = _customer(session, firm.id)

    with pytest.raises(ValidationError, match="does not belong to this firm"):
        resolve_sales_scope(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            route_id=_route_of(session, theirs),
            on_date=date(2026, 9, 19),
        )


def _leaves(session: Session, firm_id: UUID, user_id: UUID) -> None:
    """End somebody's membership of the firm, as an administrator would."""
    membership = session.scalars(
        select(UserFirm).where(UserFirm.user_id == user_id, UserFirm.firm_id == firm_id)
    ).one()
    membership.is_active = False
    session.commit()


def test_somebody_who_has_left_is_not_derived_on_to_a_document() -> None:
    """D-TER-11: the assignment row outlives the membership.

    Deleting a user or ending a membership touches no firm store, so the
    round still names Asha; an order was created and approved in her name
    and its delivery note -- which does check -- was refused. The derivation
    now skips anybody who is no longer an active member: the round's other
    assignee if there is exactly one, else nobody.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    asha = _salesman(session, firm.id, "asha@example.local")
    route = _territory(service, firm.id, actor, "N1")
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)
    service.set_salesmen(
        route,
        TerritoryAssignSalesmenRequest(
            assignments=[SalesmanAssignmentInput(user_id=asha, is_primary=True)]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    before = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)
    assert before.salesman_id == asha

    _leaves(session, firm.id, asha)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)
    assert scope.territory_id == route
    assert scope.salesman_id is None


def test_the_round_s_remaining_person_takes_over_from_one_who_left() -> None:
    """With the primary gone, the one person still on the round is the answer."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    asha = _salesman(session, firm.id, "asha@example.local")
    bala = _salesman(session, firm.id, "bala@example.local")
    route = _territory(service, firm.id, actor, "N1")
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)
    service.set_salesmen(
        route,
        TerritoryAssignSalesmenRequest(
            assignments=[
                SalesmanAssignmentInput(user_id=asha, is_primary=True),
                SalesmanAssignmentInput(user_id=bala, is_primary=False),
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _leaves(session, firm.id, asha)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id == bala


def test_a_manager_who_has_left_is_not_inherited_either() -> None:
    """The walk up the tree applies the same test."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    manager = _salesman(session, firm.id, "manager@example.local")
    region = _territory(service, firm.id, actor, "REGION1", is_route=False)
    route = _territory(
        service, firm.id, actor, "RT01", level=1, parent_id=region, is_route=True
    )
    customer = _customer(session, firm.id)
    _assign_customer(service, route, customer.id, firm.id, actor)
    service.set_salesmen(
        region,
        TerritoryAssignSalesmenRequest(
            assignments=[
                SalesmanAssignmentInput(
                    user_id=manager, is_primary=True, include_children=True
                )
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    _leaves(session, firm.id, manager)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id is None
