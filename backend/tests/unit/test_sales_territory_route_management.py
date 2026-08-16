"""Sales territory framework service and authorization tests."""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
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
    TerritoryBulkStatusRequest,
    TerritoryStatus,
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


def test_salesman_candidates_lists_only_this_firm_s_active_members() -> None:
    """The picker needs names, and `/api/v1/users` is closed to these roles.

    Assigning a salesperson used to mean typing a raw user id, because the one
    endpoint that lists people is guarded by `USER_VIEW` -- a platform-admin
    permission that a sales manager does not hold. This endpoint answers the
    same question from inside the firm's own scope.
    """
    session = _session_factory()()
    firm = _firm(session, "CAND")
    other = _firm(session, "OTHR")
    service = SalesTerritoryService(session)

    active = User(
        email="ravi@example.local", full_name="Ravi Kumar", password_hash="hash"
    )
    inactive = User(
        email="old@example.local", full_name="Former Rep", password_hash="hash"
    )
    stranger = User(
        email="other@example.local", full_name="Other Firm", password_hash="hash"
    )
    removed = User(
        email="gone@example.local", full_name="Deleted User", password_hash="hash"
    )
    session.add_all([active, inactive, stranger, removed])
    session.flush()
    removed.is_deleted = True
    session.add_all(
        [
            UserFirm(user_id=active.id, firm_id=firm.id, is_active=True),
            UserFirm(user_id=inactive.id, firm_id=firm.id, is_active=False),
            UserFirm(user_id=stranger.id, firm_id=other.id, is_active=True),
            UserFirm(user_id=removed.id, firm_id=firm.id, is_active=True),
        ]
    )
    session.commit()

    candidates = service.salesman_candidates(firm_scope=firm.id)

    assert [row.user_id for row in candidates] == [active.id]
    assert candidates[0].full_name == "Ravi Kumar"
    assert candidates[0].email == "ravi@example.local"


def test_salesman_candidates_endpoint_needs_the_assign_permission() -> None:
    """Not `USER_VIEW`: the person who assigns a route is rarely an admin."""
    session = _session_factory()()
    firm = _firm(session, "PERM")
    user = User(email="rep@example.local", full_name="Rep", password_hash="hash")
    session.add(user)
    session.flush()
    session.add(UserFirm(user_id=user.id, firm_id=firm.id, is_active=True))
    session.commit()

    viewer = _principal(user.id, {"TERRITORY_VIEW"})
    with pytest.raises(AuthorizationError):
        require_permission("TERRITORY_ASSIGN_SALESMEN")(principal=viewer)

    assigner = _principal(user.id, {"TERRITORY_ASSIGN_SALESMEN"})
    require_permission("TERRITORY_ASSIGN_SALESMEN")(principal=assigner)
    scope = _firm_scope(assigner, session, firm.id)
    candidates = SalesTerritoryService(session).salesman_candidates(
        firm_scope=scope.firm_id
    )
    assert [row.email for row in candidates] == ["rep@example.local"]
