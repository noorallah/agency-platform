"""Branch and warehouse validation, service, tenancy, and API tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.api.router import (
    create_branch,
    create_warehouse,
    import_branches,
    import_warehouses,
    list_branches,
    list_warehouses,
)
from app.branches.models import Branch, Warehouse
from app.branches.schemas import BranchCreate, BranchUpdate, WarehouseCreate
from app.branches.schemas.branch_warehouse import (
    BranchImportRequest,
    BranchListFilters,
    BulkIdsRequest,
    WarehouseImportRequest,
    WarehouseListFilters,
)
from app.branches.services import BranchWarehouseService
from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.inventory.models import InventoryRecord


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
    """Codes are unique per firm and neither firm can see the other's rows."""
    factory = _session_factory()
    session = factory()
    first_firm = _firm(session, "BW-A")
    second_firm = _firm(session, "BW-B")
    actor_id = uuid4()
    service = BranchWarehouseService(session)

    branch = service.create_branch(
        _branch_data(), firm_id=first_firm.id, actor_id=actor_id
    )
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

    # The warehouse goes first: a branch that still has one cannot be deleted.
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
    restored = service.restore_branch(
        branch.id, firm_scope=first_firm.id, actor_id=actor_id
    )
    assert restored.is_deleted is False

    restored_wh = service.restore_warehouse(
        warehouse.id,
        firm_scope=first_firm.id,
        actor_id=actor_id,
    )
    assert restored_wh.is_deleted is False


def test_branch_and_warehouse_api_scope_permissions_and_listing() -> None:
    """The routers resolve firm scope and enforce their permission codes."""
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


def _stock(
    session: Session, *, firm_id: UUID, branch_id: UUID, warehouse_id: UUID
) -> None:
    """Put one product's stock into the warehouse."""
    session.add(
        InventoryRecord(
            firm_id=firm_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_locator="MAIN",
            product_id=uuid4(),
            current_quantity=Decimal("25"),
            available_quantity=Decimal("25"),
            created_by=uuid4(),
            updated_by=uuid4(),
        )
    )
    session.commit()


def test_a_branch_with_live_warehouses_cannot_be_deleted() -> None:
    """Deleting the branch only hid it; its warehouses kept trading.

    The warehouses stayed active, pointing at a branch no listing shows, and
    stock kept moving through them.
    """
    session = _session_factory()()
    service = BranchWarehouseService(session)
    actor_id = uuid4()
    firm = _firm(session, "BRDEL")
    branch = service.create_branch(_branch_data(), firm_id=firm.id, actor_id=actor_id)
    warehouse = service.create_warehouse(
        _warehouse_data(branch.id), firm_id=firm.id, actor_id=actor_id
    )

    with pytest.raises(ValidationError, match="still has warehouses"):
        service.delete_branch(branch.id, firm_scope=firm.id, actor_id=actor_id)

    service.delete_warehouse(warehouse.id, firm_scope=firm.id, actor_id=actor_id)
    service.delete_branch(branch.id, firm_scope=firm.id, actor_id=actor_id)
    assert service.get_branch(
        branch.id, firm_scope=firm.id, include_deleted=True
    ).is_deleted


def test_a_warehouse_holding_stock_cannot_be_deleted() -> None:
    """The stock rows survive the warehouse and keep counting toward the books."""
    session = _session_factory()()
    service = BranchWarehouseService(session)
    actor_id = uuid4()
    firm = _firm(session, "WHDEL")
    branch = service.create_branch(_branch_data(), firm_id=firm.id, actor_id=actor_id)
    warehouse = service.create_warehouse(
        _warehouse_data(branch.id), firm_id=firm.id, actor_id=actor_id
    )
    _stock(session, firm_id=firm.id, branch_id=branch.id, warehouse_id=warehouse.id)

    with pytest.raises(ValidationError, match="still holds stock"):
        service.delete_warehouse(warehouse.id, firm_scope=firm.id, actor_id=actor_id)


def test_only_one_branch_and_warehouse_can_be_the_default() -> None:
    """Nothing maintained the flag, so every row could claim to be the default."""
    session = _session_factory()()
    service = BranchWarehouseService(session)
    actor_id = uuid4()
    firm = _firm(session, "BRDEF")

    first = service.create_branch(
        _branch_data("BR-001").model_copy(update={"is_default": True}),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    second = service.create_branch(
        _branch_data("BR-002").model_copy(update={"is_default": True}),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.expire_all()
    assert session.get(Branch, first.id).is_default is False
    assert session.get(Branch, second.id).is_default is True

    one = service.create_warehouse(
        _warehouse_data(second.id, "WH-001").model_copy(update={"is_default": True}),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    two = service.create_warehouse(
        _warehouse_data(second.id, "WH-002").model_copy(update={"is_default": True}),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.expire_all()
    assert session.get(Warehouse, one.id).is_default is False
    assert session.get(Warehouse, two.id).is_default is True

    # Promoting through an update demotes the incumbent too.
    service.update_branch(
        first.id,
        BranchUpdate.model_validate(
            _branch_data("BR-001").model_dump() | {"is_default": True}
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    session.expire_all()
    assert session.get(Branch, first.id).is_default is True
    assert session.get(Branch, second.id).is_default is False


def test_bulk_operations_are_audited_like_single_row_ones() -> None:
    """Deleting fifty branches from the toolbar recorded nothing at all."""
    session = _session_factory()()
    service = BranchWarehouseService(session)
    actor_id = uuid4()
    firm = _firm(session, "BRBULK")
    first = service.create_branch(
        _branch_data("BR-001"), firm_id=firm.id, actor_id=actor_id
    )
    second = service.create_branch(
        _branch_data("BR-002"), firm_id=firm.id, actor_id=actor_id
    )

    service.bulk_delete_branches(
        BulkIdsRequest(ids=[first.id, second.id]),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    deleted = session.scalars(
        select(AuditLog).where(AuditLog.action == "branch.deleted")
    ).all()
    assert len(deleted) == 2
    assert {row.entity_id for row in deleted} == {first.id, second.id}
    assert all(row.firm_id == firm.id for row in deleted)

    service.bulk_restore_branches(
        BulkIdsRequest(ids=[first.id]), firm_scope=firm.id, actor_id=actor_id
    )
    restored = session.scalars(
        select(AuditLog).where(AuditLog.action == "branch.restored")
    ).all()
    assert [row.entity_id for row in restored] == [first.id]


def test_bulk_delete_refuses_a_branch_that_still_has_warehouses() -> None:
    """The bulk path enforces the same rule as the single-row one."""
    session = _session_factory()()
    service = BranchWarehouseService(session)
    actor_id = uuid4()
    firm = _firm(session, "BRBLK2")
    branch = service.create_branch(_branch_data(), firm_id=firm.id, actor_id=actor_id)
    service.create_warehouse(
        _warehouse_data(branch.id), firm_id=firm.id, actor_id=actor_id
    )

    with pytest.raises(ValidationError, match="still has warehouses"):
        service.bulk_delete_branches(
            BulkIdsRequest(ids=[branch.id]), firm_scope=firm.id, actor_id=actor_id
        )


def _import_scope(session: Session, firm: Firm) -> ResolvedFirmScope:
    """Resolve an import-capable scope for a member of one firm."""
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    return _firm_scope(
        _principal(user_id, {"BRANCH_WAREHOUSE_IMPORT", "BRANCH_VIEW"}),
        session,
        firm.id,
    )


def test_a_branch_import_that_fails_partway_writes_nothing() -> None:
    """A partial import that cannot be retried is worse than a refused one.

    The router called ``create_branch`` per record, and that commits. A batch
    whose third row clashed returned 409 with the first two already written --
    and re-running the corrected file then failed on those two as duplicates,
    so the import could never be completed.
    """
    session = _session_factory()()
    firm = _firm(session, "IMP1")
    scope = _import_scope(session, firm)

    with pytest.raises(ConflictError):
        import_branches(
            BranchImportRequest(
                records=[
                    _branch_data("B1"),
                    _branch_data("B2"),
                    _branch_data("B1"),
                ]
            ),
            scope,
            session,
        )

    session.expire_all()
    assert session.scalars(select(Branch.code)).all() == []


def test_a_refused_branch_import_can_be_retried_once_corrected() -> None:
    """The point of rolling back: the same file works after a fix."""
    session = _session_factory()()
    firm = _firm(session, "IMP2")
    scope = _import_scope(session, firm)

    with pytest.raises(ConflictError):
        import_branches(
            BranchImportRequest(records=[_branch_data("B1"), _branch_data("B1")]),
            scope,
            session,
        )

    response = import_branches(
        BranchImportRequest(records=[_branch_data("B1"), _branch_data("B2")]),
        scope,
        session,
    )

    assert sorted(row.code for row in response.data) == ["B1", "B2"]


def test_a_warehouse_import_that_fails_partway_writes_nothing() -> None:
    """Warehouses import all or nothing for the same reason branches do."""
    session = _session_factory()()
    firm = _firm(session, "IMP3")
    scope = _import_scope(session, firm)
    branch = BranchWarehouseService(session).create_branch(
        _branch_data("B1"), firm_id=firm.id, actor_id=scope.actor_id
    )

    with pytest.raises(ConflictError):
        import_warehouses(
            WarehouseImportRequest(
                records=[
                    _warehouse_data(branch.id, "W1"),
                    _warehouse_data(branch.id, "W1"),
                ]
            ),
            scope,
            session,
        )

    session.expire_all()
    assert session.scalars(select(Warehouse.code)).all() == []


def test_an_imported_batch_is_audited_row_by_row() -> None:
    """Staging must not cost the audit trail the single-row path writes.

    The bulk endpoints in this module already shipped once with no audit rows
    at all, so a rewrite of the import path is exactly where that recurs.
    """
    session = _session_factory()()
    firm = _firm(session, "IMP4")
    scope = _import_scope(session, firm)

    import_branches(
        BranchImportRequest(
            records=[_branch_data("B1"), _branch_data("B2"), _branch_data("B3")]
        ),
        scope,
        session,
    )

    entries = session.scalars(
        select(AuditLog).where(AuditLog.entity_type == "branch")
    ).all()
    assert len(entries) == 3
    assert {entry.after_data["code"] for entry in entries} == {"B1", "B2", "B3"}
