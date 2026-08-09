"""Branch and warehouse validation, service, tenancy, and API tests."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.api.router import (
    create_branch,
    create_warehouse,
    list_branches,
    list_warehouses,
)
from app.branches.schemas import BranchCreate, WarehouseCreate
from app.branches.schemas.branch_warehouse import BranchListFilters, WarehouseListFilters
from app.branches.services import BranchWarehouseService
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ConflictError, ResourceNotFoundError
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm


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


def _branch_data(code: str = "BR-001") -> BranchCreate:
    return BranchCreate.model_validate(
        {
            "code": code,
            "name": "Head Office",
            "display_name": "Head Office",
            "status": "ACTIVE",
            "email": "branch@example.test",
            "phone": "+919876543210",
            "currency_code": "INR",
            "working_hours": {"start": "09:00", "end": "18:00"},
        }
    )


def _warehouse_data(branch_id: UUID, code: str = "WH-001") -> WarehouseCreate:
    return WarehouseCreate.model_validate(
        {
            "branch_id": branch_id,
            "code": code,
            "name": "Central Warehouse",
            "display_name": "Central Warehouse",
            "status": "ACTIVE",
            "capacity": "1000",
            "capacity_unit": "KG",
            "has_receiving_area": True,
            "has_dispatch_area": True,
        }
    )


def test_branch_and_warehouse_service_lifecycle() -> None:
    factory = _session_factory()
    session = factory()
    first_firm = _firm(session, "BW-A")
    second_firm = _firm(session, "BW-B")
    actor_id = uuid4()
    service = BranchWarehouseService(session)

    branch = service.create_branch(_branch_data(), firm_id=first_firm.id, actor_id=actor_id)
    with pytest.raises(ConflictError):
        service.create_branch(_branch_data(), firm_id=first_firm.id, actor_id=actor_id)
    branch_other_firm = service.create_branch(
        _branch_data("BR-001"),
        firm_id=second_firm.id,
        actor_id=actor_id,
    )
    assert branch_other_firm.firm_id == second_firm.id
    with pytest.raises(ResourceNotFoundError):
        service.get_branch(branch.id, firm_scope=second_firm.id)

    warehouse = service.create_warehouse(
        _warehouse_data(branch.id),
        firm_id=first_firm.id,
        actor_id=actor_id,
    )
    with pytest.raises(ConflictError):
        service.create_warehouse(
            _warehouse_data(branch.id),
            firm_id=first_firm.id,
            actor_id=actor_id,
        )
    assert warehouse.branch_id == branch.id

    service.delete_branch(branch.id, firm_scope=first_firm.id, actor_id=actor_id)
    _, visible_total = service.list_branches(
        firm_scope=first_firm.id,
        filters=BranchListFilters(),
        page=1,
        page_size=20,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    assert visible_total == 0
    restored = service.restore_branch(branch.id, firm_scope=first_firm.id, actor_id=actor_id)
    assert restored.is_deleted is False

    service.delete_warehouse(warehouse.id, firm_scope=first_firm.id, actor_id=actor_id)
    _, warehouse_visible_total = service.list_warehouses(
        firm_scope=first_firm.id,
        filters=WarehouseListFilters(),
        page=1,
        page_size=20,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    assert warehouse_visible_total == 0
    restored_wh = service.restore_warehouse(
        warehouse.id,
        firm_scope=first_firm.id,
        actor_id=actor_id,
    )
    assert restored_wh.is_deleted is False


def test_branch_and_warehouse_api_scope_permissions_and_listing() -> None:
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "BW-API")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()

    permissions = {
        "BRANCH_VIEW",
        "BRANCH_CREATE",
        "WAREHOUSE_VIEW",
        "WAREHOUSE_CREATE",
    }
    principal = _principal(user_id, permissions)
    session = factory()
    # One SQLite session backs both the tenant and platform dependencies here.
    scope = _firm_scope(principal, session, firm.id)
    branch = create_branch(_branch_data("BR-API-1"), scope, session)
    assert branch.data.code == "BR-API-1"
    warehouse = create_warehouse(
        _warehouse_data(branch.data.id, "WH-API-1"),
        scope,
        session,
    )
    assert warehouse.data.code == "WH-API-1"

    branches = list_branches(
        scope=scope,
        page=1,
        page_size=20,
        search="BR-API",
        sort_by="created_at",
        sort_direction="desc",
        status_value=None,
        branch_type_id=None,
        manager_id=None,
        business_profile_id=None,
        city_id=None,
        state_id=None,
        country_id=None,
        include_deleted=False,
        created_from=None,
        created_to=None,
        db=session,
    )
    warehouses = list_warehouses(
        scope=scope,
        page=1,
        page_size=20,
        search="WH-API",
        sort_by="created_at",
        sort_direction="desc",
        status_value=None,
        branch_id=None,
        warehouse_type_id=None,
        manager_id=None,
        business_profile_id=None,
        city_id=None,
        state_id=None,
        country_id=None,
        include_deleted=False,
        created_from=None,
        created_to=None,
        db=session,
    )
    assert branches.pagination.total_records == 1
    assert warehouses.pagination.total_records == 1
    with pytest.raises(AuthorizationError):
        require_permission("BRANCH_DELETE")(principal)
