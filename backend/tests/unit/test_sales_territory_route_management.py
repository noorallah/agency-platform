"""Sales territory framework service and authorization tests."""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales.api.router import list_territories
from app.sales.models import SalesTerritoryNode
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCopyRequest,
    TerritoryCreate,
    TerritoryUpdate,
)
from app.sales.schemas.territory import (
    HierarchyLevelInput,
    HierarchyUpdateRequest,
    RouteProfileInput,
    TerritoryBulkStatusRequest,
    TerritoryStatus,
    VisitFrequency,
)
from app.sales.services import SalesTerritoryService


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper.

    Routers no longer carry a private resolver; membership is validated once in
    ``app.common.scope`` against the platform store.
    """
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


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


def test_territory_service_supports_hierarchy_tree_and_assignments() -> None:
    session = _session_factory()()
    firm = _firm(session, "TER")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    assert hierarchy.levels[0].display_name == "Region"

    root = service.create_territory(
        TerritoryCreate(
            code="KAR",
            name="Karnataka",
            hierarchy_level_id=hierarchy.levels[0].id,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    child = service.create_territory(
        TerritoryCreate(
            code="BLR",
            name="Bangalore",
            hierarchy_level_id=hierarchy.levels[1].id,
            parent_id=root.id,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    customer = Customer(
        firm_id=firm.id,
        code="CUST-1",
        customer_type="BUSINESS",
        name="Acme Pharmacy",
        display_name="Acme Pharmacy",
        currency_code="INR",
        status="ACTIVE",
    )
    salesman = User(
        email="salesman@example.local",
        full_name="Salesman",
        password_hash="hash",
    )
    session.add(customer)
    session.add(salesman)
    session.flush()
    session.add(UserFirm(user_id=salesman.id, firm_id=firm.id, is_active=True))
    session.commit()

    assignments = service.set_customers(
        child.id,
        TerritoryAssignCustomersRequest(customer_ids=[customer.id]),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert [row.customer_id for row in assignments] == [customer.id]

    salesmen = service.set_salesmen(
        child.id,
        TerritoryAssignSalesmenRequest(
            assignments=[{"user_id": salesman.id, "include_children": True}]
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert salesmen[0]["user_id"] == salesman.id
    assert salesmen[0]["include_children"] is True

    tree = service.tree(firm_scope=firm.id)
    assert len(tree) == 1
    assert tree[0].children[0].id == child.id


def test_territory_service_rejects_invalid_level_parent() -> None:
    session = _session_factory()()
    firm = _firm(session, "VAL")
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=uuid4())
    with pytest.raises(ValidationError, match="Only top hierarchy level"):
        service.create_territory(
            TerritoryCreate(
                code="INVALID",
                name="Invalid",
                hierarchy_level_id=hierarchy.levels[1].id,
            ),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )


def test_territory_api_scope_and_permissions() -> None:
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "API-T")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()

    permissions = {"TERRITORY_VIEW", "TERRITORY_CREATE"}
    principal = _principal(user_id, permissions)
    session = factory()
    scope = _firm_scope(principal, session, firm.id)
    listed = list_territories(
        scope=scope,
        page=1,
        page_size=20,
        search=None,
        sort_by="created_at",
        sort_direction="desc",
        hierarchy_level_id=None,
        parent_id=None,
        status_value=None,
        salesman_id=None,
        include_deleted=False,
        db=session,
    )
    assert listed.pagination.total_records == 0
    with pytest.raises(AuthorizationError):
        require_permission("TERRITORY_DELETE")(principal)


def test_territory_validation_delete_and_circular_and_copy() -> None:
    session = _session_factory()()
    firm = _firm(session, "VAL2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    root = service.create_territory(
        TerritoryCreate(
            code="SOUTH",
            name="South",
            hierarchy_level_id=hierarchy.levels[0].id,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    child = service.create_territory(
        TerritoryCreate(
            code="CITY",
            name="City",
            hierarchy_level_id=hierarchy.levels[1].id,
            parent_id=root.id,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    with pytest.raises(ValidationError, match="active children"):
        service.delete_territory(root.id, firm_scope=firm.id, actor_id=actor)

    with pytest.raises(ValidationError, match="Circular hierarchy"):
        service.update_territory(
            root.id,
            TerritoryUpdate(
                code=root.code,
                name=root.name,
                hierarchy_level_id=root.hierarchy_level_id,
                parent_id=child.id,
                status=root.status,
                sort_order=0,
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )

    copied = service.copy_hierarchy(
        root.id,
        TerritoryCopyRequest(
            new_root_code="MYS",
            new_root_name="Mysore",
            include_assignments=False,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert copied.code == "MYS"


def test_territory_hierarchy_update_reuses_existing_levels() -> None:
    session = _session_factory()()
    firm = _firm(session, "CFG")
    actor = uuid4()
    service = SalesTerritoryService(session)

    updated = service.update_hierarchy(
        firm_scope=firm.id,
        actor_id=actor,
        payload=HierarchyUpdateRequest(
            max_levels=4,
            allow_multi_route_per_salesman=True,
            allow_multi_salesman_per_route=True,
            enforce_customer_leaf_assignment=True,
            levels=[
                HierarchyLevelInput(
                    level_order=1,
                    level_code="STATE",
                    display_name="State",
                    is_mandatory=True,
                    is_enabled=True,
                ),
                HierarchyLevelInput(
                    level_order=2,
                    level_code="CITY",
                    display_name="City",
                    is_mandatory=True,
                    is_enabled=True,
                ),
                HierarchyLevelInput(
                    level_order=3,
                    level_code="CIRCLE",
                    display_name="Circle",
                    is_mandatory=True,
                    is_enabled=True,
                ),
                HierarchyLevelInput(
                    level_order=4,
                    level_code="ROUTE",
                    display_name="Route",
                    is_mandatory=True,
                    is_enabled=True,
                ),
            ],
        ),
    )

    assert [level.level_code for level in updated.levels] == [
        "STATE",
        "CITY",
        "CIRCLE",
        "ROUTE",
    ]


def test_bulk_territory_changes_are_audited_per_territory() -> None:
    """One summary row keyed on the first id could not say which changed.

    The bulk endpoints recorded a single entry carrying only a count, so the
    trail said N territories moved without naming any of them.
    """
    session = _session_factory()()
    firm = _firm(session, "TERBULK")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)

    first = service.create_territory(
        TerritoryCreate(
            code="T1", name="North", hierarchy_level_id=hierarchy.levels[0].id
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    second = service.create_territory(
        TerritoryCreate(
            code="T2", name="South", hierarchy_level_id=hierarchy.levels[0].id
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    service.bulk_status_change(
        TerritoryBulkStatusRequest(
            territory_ids=[first.id, second.id], status=TerritoryStatus.INACTIVE
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    changed = session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_territory.status_changed")
    ).all()
    assert {row.entity_id for row in changed} == {first.id, second.id}
    assert all(row.firm_id == firm.id for row in changed)
    assert all(row.after_data == {"status": "INACTIVE"} for row in changed)


def test_an_edit_that_leaves_out_the_route_profile_keeps_the_route() -> None:
    """D-TER-7: a PUT without `route_profile` deleted the route.

    The node stopped being a round, its beat plans stopped running and its
    documents stopped being tagged with it, all from an omission. Now an
    omitted field keeps what is stored -- the profile, the status, the
    description -- and only an explicit null retires the round.
    """
    session = _session_factory()()
    firm = _firm(session, "TRU")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    route = service.create_territory(
        TerritoryCreate(
            code="N2",
            name="North Two",
            hierarchy_level_id=hierarchy.levels[0].id,
            description="Tuesday round",
            sort_order=7,
            route_profile=RouteProfileInput(
                visit_frequency=VisitFrequency.WEEKLY, working_days=[2]
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert route.route_profile is not None

    renamed = service.update_territory(
        route.id,
        TerritoryUpdate(name="North Two (Tue)"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert renamed.name == "North Two (Tue)"
    assert renamed.code == "N2"
    assert renamed.description == "Tuesday round"
    assert renamed.sort_order == 7
    assert renamed.route_profile is not None
    assert renamed.route_profile.working_days == [2]
    audit = session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_territory.updated")
    ).one()
    assert audit.before_data is not None and audit.after_data is not None
    assert audit.before_data["name"] == "North Two"
    assert audit.after_data["name"] == "North Two (Tue)"
    assert audit.before_data["is_route"] is True
    assert audit.after_data["is_route"] is True

    retired = service.update_territory(
        route.id,
        TerritoryUpdate(route_profile=None),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert retired.route_profile is None
    assert retired.name == "North Two (Tue)"


def _count_nodes(session: Session, firm_id: UUID) -> int:
    """How many live nodes the firm has."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(SalesTerritoryNode)
            .where(
                SalesTerritoryNode.firm_id == firm_id,
                SalesTerritoryNode.is_deleted.is_(False),
            )
        )
        or 0
    )


def test_copying_a_subtree_takes_its_children_and_not_a_sibling_s() -> None:
    """D-TER-13: the subtree was found by `path LIKE 'T-N%'`.

    Which also took `T-N2` and everything under it, and read `_` in a code
    as a wildcard. The copy of T-N is T-N and its one child: two nodes, not
    four.
    """
    session = _session_factory()()
    firm = _firm(session, "CPY1")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    for root_code, child_code in (("T-N", "T-N-A"), ("T-N2", "T-N2-A")):
        root = service.create_territory(
            TerritoryCreate(
                code=root_code,
                name=f"{root_code} region",
                hierarchy_level_id=hierarchy.levels[0].id,
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
        service.create_territory(
            TerritoryCreate(
                code=child_code,
                name=f"{child_code} zone",
                hierarchy_level_id=hierarchy.levels[1].id,
                parent_id=root.id,
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
    [source] = [node for node in service.tree(firm_scope=firm.id) if node.code == "T-N"]
    assert _count_nodes(session, firm.id) == 4

    copied = service.copy_hierarchy(
        source.id,
        TerritoryCopyRequest(new_root_code="T-S", new_root_name="T-S region"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert copied.code == "T-S"
    assert _count_nodes(session, firm.id) == 6
    [new_root] = [
        node for node in service.tree(firm_scope=firm.id) if node.code == "T-S"
    ]
    # One child, T-N's, under the next free code -- and nothing of T-N2's.
    assert [child.code for child in new_root.children] == ["T-N-A_2"]
    audit = session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_territory.copied")
    ).one()
    assert audit.after_data is not None
    assert audit.after_data["nodes"] == 2


def test_a_copy_refused_partway_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every node used to be committed as it was created.

    A refusal on the third node -- here, an assignment the policy will not
    allow -- left the first two written. The copy now commits once at the
    end, so a refusal anywhere leaves the firm exactly as it was.
    """
    session = _session_factory()()
    firm = _firm(session, "CPY2")
    actor = uuid4()
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor)
    root = service.create_territory(
        TerritoryCreate(
            code="WEST",
            name="West",
            hierarchy_level_id=hierarchy.levels[0].id,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    for code in ("W-A", "W-B"):
        service.create_territory(
            TerritoryCreate(
                code=code,
                name=f"{code} zone",
                hierarchy_level_id=hierarchy.levels[1].id,
                parent_id=root.id,
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
    before = _count_nodes(session, firm.id)

    calls: list[UUID] = []

    def refuse_the_third(
        self: SalesTerritoryService,
        node_id: UUID,
        *args: object,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        """Stand in for the salesman policy refusing the third node."""
        calls.append(node_id)
        if len(calls) == 3:
            raise ValidationError("A salesperson may be on only one route.")
        return []

    monkeypatch.setattr(SalesTerritoryService, "set_salesmen", refuse_the_third)

    with pytest.raises(ValidationError, match="only one route"):
        service.copy_hierarchy(
            root.id,
            TerritoryCopyRequest(
                new_root_code="EAST", new_root_name="East", include_assignments=True
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
    session.rollback()

    assert len(calls) == 3
    assert _count_nodes(session, firm.id) == before
