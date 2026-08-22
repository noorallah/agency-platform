"""Settings the hierarchy records, and flags a save used to destroy.

Four hierarchy settings were stored, returned by the API and checked nowhere,
so a platform administrator could turn any of them on and nothing changed --
the same shape as the business-profile features that were declared and
unenforced. `is_potential` was worse than unenforced: it is shown on the call
order dialog and counted on the grid, and every write path sent a hardcoded
`False`, so the count could only ever read zero.

The defaults matter as much as the rules. A firm with no configuration row, or
a level with no node limit, keeps the permissive behaviour it has always had --
a configuration gap is not a decision.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales.models import SalesHierarchyConfig, SalesTerritoryNode
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCreate,
    TerritoryListFilters,
    TerritoryUpdate,
)
from app.sales.schemas.territory import (
    HierarchyLevelInput,
    HierarchyUpdateRequest,
    RouteProfileInput,
    SalesmanAssignmentInput,
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


def _salesman(session: Session, firm_id: UUID, email: str) -> UUID:
    row = User(email=email, full_name="Rep", password_hash="hash")
    session.add(row)
    session.flush()
    session.add(UserFirm(user_id=row.id, firm_id=firm_id, is_active=True))
    session.commit()
    return row.id


def _node(
    service: SalesTerritoryService,
    firm_id: UUID,
    actor: UUID,
    code: str,
    *,
    level: int = 0,
    parent_id: UUID | None = None,
    is_route: bool = False,
) -> UUID:
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    created = service.create_territory(
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
    return created.id


def _settings(session: Session, firm_id: UUID, **flags: bool) -> None:
    config = session.scalar(
        select(SalesHierarchyConfig).where(SalesHierarchyConfig.firm_id == firm_id)
    )
    assert config is not None
    for key, value in flags.items():
        setattr(config, key, value)
    session.commit()


def test_potential_survives_a_save_that_says_nothing_about_it() -> None:
    """The flag every write path used to overwrite with False."""
    session = _session_factory()()
    firm = _firm(session, "POT1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _node(service, firm.id, actor, "RT01", is_route=True)
    shop = _customer(session, firm.id, "C1")

    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(customer_id=shop.id, is_potential=True)
            ]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    # A re-save that says nothing about the flag -- what every screen sends.
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    placed = service.customers(route, firm_scope=firm.id)
    assert [row.is_potential for row in placed] == [True]


def test_potential_can_be_turned_off_when_asked() -> None:
    session = _session_factory()()
    firm = _firm(session, "POT2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _node(service, firm.id, actor, "RT01", is_route=True)
    shop = _customer(session, firm.id, "C1")

    for flag in (True, False):
        service.set_customers(
            route,
            TerritoryAssignCustomersRequest(
                entries=[
                    TerritoryCustomerAssignmentInput(
                        customer_id=shop.id, is_potential=flag
                    )
                ]
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )

    placed = service.customers(route, firm_scope=firm.id)
    assert [row.is_potential for row in placed] == [False]


def test_one_salesperson_per_route_is_enforced_when_the_firm_asks() -> None:
    session = _session_factory()()
    firm = _firm(session, "POL1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _node(service, firm.id, actor, "RT01", is_route=True)
    first = _salesman(session, firm.id, "one@example.local")
    second = _salesman(session, firm.id, "two@example.local")
    _settings(session, firm.id, allow_multi_salesman_per_route=False)

    with pytest.raises(ValidationError, match="only one salesperson"):
        service.set_salesmen(
            route,
            TerritoryAssignSalesmenRequest(
                assignments=[
                    SalesmanAssignmentInput(user_id=first),
                    SalesmanAssignmentInput(user_id=second),
                ]
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )


def test_one_route_per_salesperson_is_enforced_when_the_firm_asks() -> None:
    session = _session_factory()()
    firm = _firm(session, "POL2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    first = _node(service, firm.id, actor, "RT01", is_route=True)
    second = _node(service, firm.id, actor, "RT02", is_route=True)
    rep = _salesman(session, firm.id, "rep@example.local")
    _settings(session, firm.id, allow_multi_route_per_salesman=False)

    service.set_salesmen(
        first,
        TerritoryAssignSalesmenRequest(
            assignments=[SalesmanAssignmentInput(user_id=rep)]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    with pytest.raises(ValidationError, match="already on RT01"):
        service.set_salesmen(
            second,
            TerritoryAssignSalesmenRequest(
                assignments=[SalesmanAssignmentInput(user_id=rep)]
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )


def test_customers_can_be_held_to_the_lowest_level() -> None:
    session = _session_factory()()
    firm = _firm(session, "POL3")
    actor = uuid4()
    service = SalesTerritoryService(session)
    region = _node(service, firm.id, actor, "REGION1")
    route = _node(
        service, firm.id, actor, "RT01", level=1, parent_id=region, is_route=True
    )
    shop = _customer(session, firm.id, "C1")
    _settings(session, firm.id, enforce_customer_leaf_assignment=True)

    with pytest.raises(ValidationError, match="lowest level"):
        service.set_customers(
            region,
            TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
            firm_scope=firm.id,
            actor_id=actor,
        )
    # The leaf itself is fine.
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(customer_ids=[shop.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert len(service.customers(route, firm_scope=firm.id)) == 1


def test_a_level_can_cap_how_many_nodes_sit_under_one_parent() -> None:
    session = _session_factory()()
    firm = _firm(session, "POL4")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    service.update_hierarchy(
        firm_scope=firm.id,
        actor_id=actor,
        payload=HierarchyUpdateRequest(
            max_levels=hierarchy.max_levels,
            levels=[
                HierarchyLevelInput(
                    level_order=level.level_order,
                    level_code=level.level_code,
                    display_name=level.display_name,
                    is_mandatory=level.is_mandatory,
                    is_enabled=level.is_enabled,
                    max_nodes_per_parent=1 if level.level_order == 1 else None,
                )
                for level in hierarchy.levels
            ],
        ),
    )

    _node(service, firm.id, actor, "FIRST")
    with pytest.raises(ValidationError, match="at most 1 node"):
        _node(service, firm.id, actor, "SECOND")


def test_a_firm_with_no_settings_row_keeps_the_permissive_defaults() -> None:
    """A configuration gap is not a decision."""
    session = _session_factory()()
    firm = _firm(session, "POL5")
    actor = uuid4()
    service = SalesTerritoryService(session)
    first = _node(service, firm.id, actor, "RT01", is_route=True)
    second = _node(service, firm.id, actor, "RT02", is_route=True)
    rep = _salesman(session, firm.id, "rep@example.local")

    for route in (first, second):
        service.set_salesmen(
            route,
            TerritoryAssignSalesmenRequest(
                assignments=[SalesmanAssignmentInput(user_id=rep)]
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )

    assert len(service.salesmen(second, firm_scope=firm.id)) == 1


def test_a_shop_can_say_which_rounds_call_it() -> None:
    """The relationship was one-directional: only territory → customers."""
    session = _session_factory()()
    firm = _firm(session, "CR1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    sales = _node(service, firm.id, actor, "SALES01", is_route=True)
    collection = _node(service, firm.id, actor, "COLL01", is_route=True)
    shop = _customer(session, firm.id, "C1")
    for route in (sales, collection):
        service.set_customers(
            route,
            TerritoryAssignCustomersRequest(
                entries=[
                    TerritoryCustomerAssignmentInput(
                        customer_id=shop.id, visit_sequence=3
                    )
                ]
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )

    rounds = service.customer_routes(shop.id, firm_scope=firm.id)

    assert [row.code for row in rounds] == ["SALES01", "COLL01"]
    # Primary first: it is the round a sale for this shop is filed under.
    assert rounds[0].is_primary is True
    assert rounds[1].is_primary is False
    assert all(row.is_route for row in rounds)
    assert rounds[0].visit_sequence == 3


def test_a_shop_on_no_round_lists_none() -> None:
    session = _session_factory()()
    firm = _firm(session, "CR2")
    service = SalesTerritoryService(session)
    shop = _customer(session, firm.id, "C1")

    assert service.customer_routes(shop.id, firm_scope=firm.id) == []


def test_an_import_that_fails_partway_writes_nothing() -> None:
    """`import_csv` looped over a create that commits.

    A file whose last row named an unknown level left every row before it
    written and returned an error -- and the corrected file then failed on
    those rows as duplicates, which is what made the branch and warehouse
    imports impossible to complete.
    """
    session = _session_factory()()
    firm = _firm(session, "IMP1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    top = hierarchy.levels[0].display_name

    csv_content = (
        "Code,Name,Level,ParentCode,Status\n"
        f"IMP-A,First,{top},,ACTIVE\n"
        f"IMP-B,Second,{top},,ACTIVE\n"
        "IMP-C,Third,NoSuchLevel,,ACTIVE\n"
    )

    with pytest.raises(ValidationError, match="Unknown hierarchy level"):
        service.import_csv(csv_content, firm_scope=firm.id, actor_id=actor)

    session.rollback()
    rows, total = service.list_territories(
        firm_scope=firm.id,
        filters=TerritoryListFilters(),
        page=1,
        page_size=50,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    assert total == 0
    assert rows == []


def test_a_clean_import_creates_every_row() -> None:
    session = _session_factory()()
    firm = _firm(session, "IMP2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    top = hierarchy.levels[0].display_name

    created = service.import_csv(
        "Code,Name,Level,ParentCode,Status\n"
        f"IMP-A,First,{top},,ACTIVE\n"
        f"IMP-B,Second,{top},,ACTIVE\n",
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert [row.code for row in created] == ["IMP-A", "IMP-B"]


def test_an_unassigned_firm_stamps_the_default_business_profile() -> None:
    """A firm with no assignment operates under the platform default profile.

    The service resolved the assignment itself and recorded None for a firm
    nobody had assigned, so its hierarchy and every node under it belonged to
    no industry at all and answered nothing to a business_profile_id filter --
    while the gate had already decided that firm runs as GENERIC.
    """
    session = _session_factory()()
    firm = _firm(session, "NOPROF")
    actor = uuid4()
    default_profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
        default_settings={},
        created_by=actor,
        updated_by=actor,
    )
    session.add(default_profile)
    session.commit()
    service = SalesTerritoryService(session)

    node_id = _node(service, firm.id, actor, "NP-A")

    config = session.scalar(
        select(SalesHierarchyConfig).where(SalesHierarchyConfig.firm_id == firm.id)
    )
    node = session.get(SalesTerritoryNode, node_id)
    assert config is not None
    assert config.business_profile_id == default_profile.id
    assert node is not None
    assert node.business_profile_id == default_profile.id


def test_a_territory_refuses_a_write_aimed_at_an_older_version() -> None:
    """The precondition travels even though the service returns a response.

    `app/sales` builds its response models in the service, so the router never
    holds the row -- `publish_version` puts the same number in the ETag that
    `set_etag` would have taken off the entity.
    """
    session = _session_factory()()
    firm = _firm(session, "TCONC")
    actor = uuid4()
    service = SalesTerritoryService(session)
    node_id = _node(service, firm.id, actor, "TC-A")
    node = service.get_territory(node_id, firm_scope=firm.id)
    read_at = node.version

    def rename(to: str, expected: int | None) -> None:
        service.update_territory(
            node_id,
            TerritoryUpdate(
                code=node.code,
                name=to,
                hierarchy_level_id=node.hierarchy_level_id,
            ),
            firm_scope=firm.id,
            actor_id=actor,
            expected_version=expected,
        )

    rename("First rename", read_at)

    with pytest.raises(ConflictError):
        rename("Second rename", read_at)

    rename("No precondition", None)
    assert service.get_territory(node_id, firm_scope=firm.id).name == "No precondition"
