"""SQLAlchemy persistence adapter for branch and warehouse management."""

from datetime import UTC, datetime, time
from uuid import UUID

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.branches.models import (
    Branch,
    BranchType,
    Warehouse,
    WarehouseStorageNode,
    WarehouseType,
)
from app.branches.schemas import BranchListFilters, WarehouseListFilters


class BranchWarehouseRepository:
    """Centralize branch and warehouse persistence operations."""

    BRANCH_SORT_COLUMNS = {
        "code": Branch.code,
        "name": Branch.name,
        "status": Branch.status,
        "created_at": Branch.created_at,
    }
    WAREHOUSE_SORT_COLUMNS = {
        "code": Warehouse.code,
        "name": Warehouse.name,
        "status": Warehouse.status,
        "created_at": Warehouse.created_at,
    }

    def __init__(self, session: Session) -> None:
        self._session = session

    def flush(self) -> None:
        self._session.flush()

    def add(self, row: object) -> None:
        self._session.add(row)

    def get_branch(
        self, branch_id: UUID, firm_scope: UUID | None, *, include_deleted: bool
    ) -> Branch | None:
        statement = (
            select(Branch)
            .options(selectinload(Branch.warehouses))
            .where(Branch.id == branch_id)
        )
        if firm_scope is not None:
            statement = statement.where(Branch.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(Branch.is_deleted.is_(False))
        return self._session.scalar(statement)

    def get_warehouse(
        self, warehouse_id: UUID, firm_scope: UUID | None, *, include_deleted: bool
    ) -> Warehouse | None:
        statement = (
            select(Warehouse)
            .options(selectinload(Warehouse.storage_nodes))
            .where(Warehouse.id == warehouse_id)
        )
        if firm_scope is not None:
            statement = statement.where(Warehouse.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(Warehouse.is_deleted.is_(False))
        return self._session.scalar(statement)

    def branch_duplicate_id(
        self,
        firm_id: UUID,
        *,
        code: str,
        excluding_id: UUID | None = None,
    ) -> UUID | None:
        statement = select(Branch.id).where(Branch.firm_id == firm_id, Branch.code == code)
        if excluding_id is not None:
            statement = statement.where(Branch.id != excluding_id)
        return self._session.scalar(statement)

    def warehouse_duplicate_id(
        self,
        firm_id: UUID,
        *,
        code: str,
        excluding_id: UUID | None = None,
    ) -> UUID | None:
        statement = select(Warehouse.id).where(
            Warehouse.firm_id == firm_id, Warehouse.code == code
        )
        if excluding_id is not None:
            statement = statement.where(Warehouse.id != excluding_id)
        return self._session.scalar(statement)

    def list_branches(
        self,
        *,
        firm_scope: UUID | None,
        filters: BranchListFilters,
        search: str | None,
        sort_by: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Branch], int]:
        statement = select(Branch).options(selectinload(Branch.warehouses))
        count = select(func.count()).select_from(Branch)
        conditions = self._branch_conditions(firm_scope, filters)
        statement = statement.where(*conditions)
        count = count.where(*conditions)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                Branch.code.ilike(term),
                Branch.name.ilike(term),
                Branch.display_name.ilike(term),
                Branch.email.ilike(term),
                Branch.phone.ilike(term),
                Branch.mobile.ilike(term),
                Branch.status.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering_column = self.BRANCH_SORT_COLUMNS[sort_by]
        ordering = ordering_column.desc() if descending else ordering_column.asc()
        rows = self._session.scalars(
            statement.order_by(ordering, Branch.id).offset(offset).limit(limit)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_warehouses(
        self,
        *,
        firm_scope: UUID | None,
        filters: WarehouseListFilters,
        search: str | None,
        sort_by: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Warehouse], int]:
        statement = select(Warehouse).options(selectinload(Warehouse.storage_nodes))
        count = select(func.count()).select_from(Warehouse)
        conditions = self._warehouse_conditions(firm_scope, filters)
        statement = statement.where(*conditions)
        count = count.where(*conditions)
        if search:
            term = f"%{search.strip()}%"
            branch_match = exists(
                select(Branch.id).where(
                    Branch.id == Warehouse.branch_id,
                    Branch.name.ilike(term),
                )
            )
            condition = or_(
                Warehouse.code.ilike(term),
                Warehouse.name.ilike(term),
                Warehouse.display_name.ilike(term),
                Warehouse.status.ilike(term),
                branch_match,
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering_column = self.WAREHOUSE_SORT_COLUMNS[sort_by]
        ordering = ordering_column.desc() if descending else ordering_column.asc()
        rows = self._session.scalars(
            statement.order_by(ordering, Warehouse.id).offset(offset).limit(limit)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def branch_summary(
        self, firm_scope: UUID | None, filters: BranchListFilters
    ) -> tuple[int, int, int, int, int, int]:
        row = self._session.execute(
            select(
                func.count(Branch.id),
                func.sum(case((Branch.status == "ACTIVE", 1), else_=0)),
                func.sum(case((Branch.status == "INACTIVE", 1), else_=0)),
                func.sum(case((Branch.status == "DRAFT", 1), else_=0)),
                func.sum(case((Branch.status == "ARCHIVED", 1), else_=0)),
                func.sum(case((Branch.is_deleted.is_(True), 1), else_=0)),
            ).where(*self._branch_conditions(firm_scope, filters))
        ).one()
        return tuple(int(item or 0) for item in row)  # type: ignore[return-value]

    def warehouse_summary(
        self, firm_scope: UUID | None, filters: WarehouseListFilters
    ) -> tuple[int, int, int, int, int, int]:
        row = self._session.execute(
            select(
                func.count(Warehouse.id),
                func.sum(case((Warehouse.status == "ACTIVE", 1), else_=0)),
                func.sum(case((Warehouse.status == "INACTIVE", 1), else_=0)),
                func.sum(case((Warehouse.status == "DRAFT", 1), else_=0)),
                func.sum(case((Warehouse.status == "ARCHIVED", 1), else_=0)),
                func.sum(case((Warehouse.is_deleted.is_(True), 1), else_=0)),
            ).where(*self._warehouse_conditions(firm_scope, filters))
        ).one()
        return tuple(int(item or 0) for item in row)  # type: ignore[return-value]

    def list_branch_types(self, firm_id: UUID, include_deleted: bool) -> list[BranchType]:
        statement = select(BranchType).where(BranchType.firm_id == firm_id)
        if not include_deleted:
            statement = statement.where(BranchType.is_deleted.is_(False))
        return list(self._session.scalars(statement.order_by(BranchType.name)))

    def get_branch_type(
        self, branch_type_id: UUID, firm_id: UUID, *, include_deleted: bool
    ) -> BranchType | None:
        statement = select(BranchType).where(
            BranchType.id == branch_type_id,
            BranchType.firm_id == firm_id,
        )
        if not include_deleted:
            statement = statement.where(BranchType.is_deleted.is_(False))
        return self._session.scalar(statement)

    def list_warehouse_types(
        self, firm_id: UUID, include_deleted: bool
    ) -> list[WarehouseType]:
        statement = select(WarehouseType).where(WarehouseType.firm_id == firm_id)
        if not include_deleted:
            statement = statement.where(WarehouseType.is_deleted.is_(False))
        return list(self._session.scalars(statement.order_by(WarehouseType.name)))

    def get_warehouse_type(
        self, warehouse_type_id: UUID, firm_id: UUID, *, include_deleted: bool
    ) -> WarehouseType | None:
        statement = select(WarehouseType).where(
            WarehouseType.id == warehouse_type_id,
            WarehouseType.firm_id == firm_id,
        )
        if not include_deleted:
            statement = statement.where(WarehouseType.is_deleted.is_(False))
        return self._session.scalar(statement)

    def get_storage_node(
        self,
        storage_node_id: UUID,
        firm_scope: UUID | None,
        *,
        include_deleted: bool,
    ) -> WarehouseStorageNode | None:
        statement = (
            select(WarehouseStorageNode)
            .join(Warehouse, Warehouse.id == WarehouseStorageNode.warehouse_id)
            .where(WarehouseStorageNode.id == storage_node_id)
        )
        if firm_scope is not None:
            statement = statement.where(Warehouse.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(WarehouseStorageNode.is_deleted.is_(False))
        return self._session.scalar(statement)

    def list_storage_nodes(
        self,
        *,
        warehouse_id: UUID,
        firm_scope: UUID | None,
        include_deleted: bool,
    ) -> list[WarehouseStorageNode]:
        statement = (
            select(WarehouseStorageNode)
            .join(Warehouse, Warehouse.id == WarehouseStorageNode.warehouse_id)
            .where(WarehouseStorageNode.warehouse_id == warehouse_id)
        )
        if firm_scope is not None:
            statement = statement.where(Warehouse.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(WarehouseStorageNode.is_deleted.is_(False))
        return list(
            self._session.scalars(
                statement.order_by(
                    WarehouseStorageNode.path,
                    WarehouseStorageNode.sort_order,
                    WarehouseStorageNode.name,
                )
            )
        )

    def _branch_conditions(
        self,
        firm_scope: UUID | None,
        filters: BranchListFilters,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if firm_scope is not None:
            conditions.append(Branch.firm_id == firm_scope)
        if not filters.include_deleted:
            conditions.append(Branch.is_deleted.is_(False))
        if filters.status is not None:
            conditions.append(Branch.status == filters.status.value)
        if filters.branch_type_id is not None:
            conditions.append(Branch.branch_type_id == filters.branch_type_id)
        if filters.manager_id is not None:
            conditions.append(Branch.branch_manager_id == filters.manager_id)
        if filters.business_profile_id is not None:
            conditions.append(Branch.business_profile_id == filters.business_profile_id)
        if filters.city_id is not None:
            conditions.append(Branch.city_id == filters.city_id)
        if filters.state_id is not None:
            conditions.append(Branch.state_id == filters.state_id)
        if filters.country_id is not None:
            conditions.append(Branch.country_id == filters.country_id)
        if filters.created_from:
            conditions.append(
                Branch.created_at >= datetime.combine(filters.created_from, time.min, UTC)
            )
        if filters.created_to:
            conditions.append(
                Branch.created_at <= datetime.combine(filters.created_to, time.max, UTC)
            )
        return conditions

    def _warehouse_conditions(
        self,
        firm_scope: UUID | None,
        filters: WarehouseListFilters,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if firm_scope is not None:
            conditions.append(Warehouse.firm_id == firm_scope)
        if not filters.include_deleted:
            conditions.append(Warehouse.is_deleted.is_(False))
        if filters.status is not None:
            conditions.append(Warehouse.status == filters.status.value)
        if filters.branch_id is not None:
            conditions.append(Warehouse.branch_id == filters.branch_id)
        if filters.warehouse_type_id is not None:
            conditions.append(Warehouse.warehouse_type_id == filters.warehouse_type_id)
        if filters.manager_id is not None:
            conditions.append(Warehouse.warehouse_manager_id == filters.manager_id)
        if filters.business_profile_id is not None:
            conditions.append(Warehouse.business_profile_id == filters.business_profile_id)
        if filters.city_id is not None:
            conditions.append(Warehouse.city_id == filters.city_id)
        if filters.state_id is not None:
            conditions.append(Warehouse.state_id == filters.state_id)
        if filters.country_id is not None:
            conditions.append(Warehouse.country_id == filters.country_id)
        if filters.created_from:
            conditions.append(
                Warehouse.created_at
                >= datetime.combine(filters.created_from, time.min, UTC)
            )
        if filters.created_to:
            conditions.append(
                Warehouse.created_at
                <= datetime.combine(filters.created_to, time.max, UTC)
            )
        return conditions
