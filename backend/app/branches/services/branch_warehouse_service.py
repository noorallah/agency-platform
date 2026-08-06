"""Transactional service for enterprise branch and warehouse management."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.branches.models import Branch, BranchType, Warehouse, WarehouseStorageNode, WarehouseType
from app.branches.repositories import BranchWarehouseRepository
from app.branches.schemas import (
    BranchCreate,
    BranchListFilters,
    BranchSummary,
    BranchTypeWrite,
    BranchUpdate,
    BulkBranchStatusRequest,
    BulkIdsRequest,
    BulkWarehouseStatusRequest,
    StorageNodeCreate,
    StorageNodeUpdate,
    WarehouseCreate,
    WarehouseListFilters,
    WarehouseSummary,
    WarehouseTypeWrite,
    WarehouseUpdate,
)
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now


class BranchWarehouseService:
    """Coordinate branch and warehouse mutations, queries, and audits."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = BranchWarehouseRepository(session)

    def list_branches(
        self,
        *,
        firm_scope: UUID | None,
        filters: BranchListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[Branch], int]:
        return self._repository.list_branches(
            firm_scope=firm_scope,
            filters=filters,
            search=search,
            sort_by=sort_by,
            descending=descending,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def create_branch(self, data: BranchCreate, *, firm_id: UUID, actor_id: UUID) -> Branch:
        self._assert_unique_branch_code(firm_id, data.code)
        row = Branch(
            firm_id=firm_id,
            **self._branch_values(data),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(row)
        self._repository.flush()
        record_audit(
            self._session,
            action="branch.created",
            entity_type="branch",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "status": row.status},
        )
        self._commit_unique("Branch code already exists in this firm.")
        return row

    def get_branch(
        self, branch_id: UUID, *, firm_scope: UUID | None, include_deleted: bool = False
    ) -> Branch:
        row = self._repository.get_branch(
            branch_id, firm_scope, include_deleted=include_deleted
        )
        if row is None:
            raise ResourceNotFoundError("Branch not found.")
        return row

    def update_branch(
        self,
        branch_id: UUID,
        data: BranchUpdate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> Branch:
        row = self.get_branch(branch_id, firm_scope=firm_scope)
        self._assert_unique_branch_code(row.firm_id, data.code, excluding_id=row.id)
        before = {"code": row.code, "status": row.status}
        for field, value in self._branch_values(data).items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="branch.updated",
            entity_type="branch",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data=before,
            after_data={"code": row.code, "status": row.status},
        )
        self._commit_unique("Branch code already exists in this firm.")
        return row

    def delete_branch(self, branch_id: UUID, *, firm_scope: UUID | None, actor_id: UUID) -> None:
        row = self.get_branch(branch_id, firm_scope=firm_scope)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="branch.deleted",
            entity_type="branch",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data={"code": row.code},
        )
        self._session.commit()

    def restore_branch(
        self, branch_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Branch:
        row = self.get_branch(branch_id, firm_scope=firm_scope, include_deleted=True)
        if not row.is_deleted:
            return row
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="branch.restored",
            entity_type="branch",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={"code": row.code},
        )
        self._session.commit()
        return row

    def duplicate_branch(
        self, branch_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Branch:
        source = self.get_branch(branch_id, firm_scope=firm_scope)
        duplicate = Branch(
            firm_id=source.firm_id,
            code=f"{source.code}-COPY",
            name=source.name,
            display_name=f"{source.display_name} (Copy)",
            description=source.description,
            business_profile_id=source.business_profile_id,
            branch_type_id=source.branch_type_id,
            branch_manager_id=source.branch_manager_id,
            email=source.email,
            phone=source.phone,
            mobile=source.mobile,
            country_id=source.country_id,
            state_id=source.state_id,
            district_id=source.district_id,
            city_id=source.city_id,
            postal_code_id=source.postal_code_id,
            locality_id=source.locality_id,
            address_line1=source.address_line1,
            address_line2=source.address_line2,
            timezone=source.timezone,
            currency_code=source.currency_code,
            gst_registration=source.gst_registration,
            pan=source.pan,
            license_number=source.license_number,
            working_hours=dict(source.working_hours),
            is_default=False,
            status=source.status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(duplicate)
        self._commit_unique("Branch duplication created a duplicate code.")
        return duplicate

    def branch_summary(
        self, *, firm_scope: UUID | None, filters: BranchListFilters
    ) -> BranchSummary:
        total, active, inactive, draft, archived, deleted = self._repository.branch_summary(
            firm_scope, filters
        )
        return BranchSummary(
            total=total,
            active=active,
            inactive=inactive,
            draft=draft,
            archived=archived,
            deleted=deleted,
        )

    def bulk_delete_branches(
        self, data: BulkIdsRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        affected = 0
        for branch_id in data.ids:
            row = self.get_branch(branch_id, firm_scope=firm_scope)
            if row.is_deleted:
                continue
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_restore_branches(
        self, data: BulkIdsRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        affected = 0
        for branch_id in data.ids:
            row = self.get_branch(branch_id, firm_scope=firm_scope, include_deleted=True)
            if not row.is_deleted:
                continue
            row.is_deleted = False
            row.deleted_at = None
            row.deleted_by = None
            row.updated_by = actor_id
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_branch_status(
        self, data: BulkBranchStatusRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        affected = 0
        for branch_id in data.ids:
            row = self.get_branch(branch_id, firm_scope=firm_scope)
            if row.status == data.status.value:
                continue
            row.status = data.status.value
            row.updated_by = actor_id
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def list_warehouses(
        self,
        *,
        firm_scope: UUID | None,
        filters: WarehouseListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[Warehouse], int]:
        return self._repository.list_warehouses(
            firm_scope=firm_scope,
            filters=filters,
            search=search,
            sort_by=sort_by,
            descending=descending,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def create_warehouse(
        self, data: WarehouseCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Warehouse:
        self._assert_unique_warehouse_code(firm_id, data.code)
        branch = self.get_branch(data.branch_id, firm_scope=firm_id)
        row = Warehouse(
            firm_id=firm_id,
            **self._warehouse_values(data),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(row)
        self._repository.flush()
        record_audit(
            self._session,
            action="warehouse.created",
            entity_type="warehouse",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "branch_id": str(branch.id)},
        )
        self._commit_unique("Warehouse code already exists in this firm.")
        return row

    def get_warehouse(
        self,
        warehouse_id: UUID,
        *,
        firm_scope: UUID | None,
        include_deleted: bool = False,
    ) -> Warehouse:
        row = self._repository.get_warehouse(
            warehouse_id, firm_scope, include_deleted=include_deleted
        )
        if row is None:
            raise ResourceNotFoundError("Warehouse not found.")
        return row

    def update_warehouse(
        self,
        warehouse_id: UUID,
        data: WarehouseUpdate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> Warehouse:
        row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
        self._assert_unique_warehouse_code(row.firm_id, data.code, excluding_id=row.id)
        self.get_branch(data.branch_id, firm_scope=row.firm_id)
        before = {"code": row.code, "status": row.status}
        for field, value in self._warehouse_values(data).items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="warehouse.updated",
            entity_type="warehouse",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data=before,
            after_data={"code": row.code, "status": row.status},
        )
        self._commit_unique("Warehouse code already exists in this firm.")
        return row

    def delete_warehouse(
        self, warehouse_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="warehouse.deleted",
            entity_type="warehouse",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data={"code": row.code},
        )
        self._session.commit()

    def restore_warehouse(
        self, warehouse_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Warehouse:
        row = self.get_warehouse(warehouse_id, firm_scope=firm_scope, include_deleted=True)
        if not row.is_deleted:
            return row
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="warehouse.restored",
            entity_type="warehouse",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={"code": row.code},
        )
        self._session.commit()
        return row

    def duplicate_warehouse(
        self, warehouse_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Warehouse:
        source = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
        duplicate = Warehouse(
            firm_id=source.firm_id,
            branch_id=source.branch_id,
            code=f"{source.code}-COPY",
            name=source.name,
            display_name=f"{source.display_name} (Copy)",
            description=source.description,
            warehouse_type_id=source.warehouse_type_id,
            warehouse_manager_id=source.warehouse_manager_id,
            business_profile_id=source.business_profile_id,
            country_id=source.country_id,
            state_id=source.state_id,
            district_id=source.district_id,
            city_id=source.city_id,
            postal_code_id=source.postal_code_id,
            locality_id=source.locality_id,
            address_line1=source.address_line1,
            address_line2=source.address_line2,
            capacity=source.capacity,
            capacity_unit=source.capacity_unit,
            is_default=False,
            temperature_controlled=source.temperature_controlled,
            cold_storage=source.cold_storage,
            hazardous_storage=source.hazardous_storage,
            has_receiving_area=source.has_receiving_area,
            has_dispatch_area=source.has_dispatch_area,
            has_returns_area=source.has_returns_area,
            has_inspection_area=source.has_inspection_area,
            has_packing_area=source.has_packing_area,
            has_loading_dock=source.has_loading_dock,
            status=source.status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(duplicate)
        self._commit_unique("Warehouse duplication created a duplicate code.")
        return duplicate

    def warehouse_summary(
        self, *, firm_scope: UUID | None, filters: WarehouseListFilters
    ) -> WarehouseSummary:
        total, active, inactive, draft, archived, deleted = (
            self._repository.warehouse_summary(firm_scope, filters)
        )
        return WarehouseSummary(
            total=total,
            active=active,
            inactive=inactive,
            draft=draft,
            archived=archived,
            deleted=deleted,
        )

    def bulk_delete_warehouses(
        self, data: BulkIdsRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        affected = 0
        for warehouse_id in data.ids:
            row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
            if row.is_deleted:
                continue
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_restore_warehouses(
        self, data: BulkIdsRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        affected = 0
        for warehouse_id in data.ids:
            row = self.get_warehouse(
                warehouse_id, firm_scope=firm_scope, include_deleted=True
            )
            if not row.is_deleted:
                continue
            row.is_deleted = False
            row.deleted_at = None
            row.deleted_by = None
            row.updated_by = actor_id
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_warehouse_status(
        self,
        data: BulkWarehouseStatusRequest,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> int:
        affected = 0
        for warehouse_id in data.ids:
            row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
            if row.status == data.status.value:
                continue
            row.status = data.status.value
            row.updated_by = actor_id
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def create_storage_node(
        self, data: StorageNodeCreate, *, firm_scope: UUID | None, actor_id: UUID
    ) -> WarehouseStorageNode:
        warehouse = self.get_warehouse(data.warehouse_id, firm_scope=firm_scope)
        parent = None
        if data.parent_id is not None:
            parent = self._repository.get_storage_node(
                data.parent_id, firm_scope, include_deleted=False
            )
            if parent is None or parent.warehouse_id != data.warehouse_id:
                raise ValidationError("Parent storage node is invalid for this warehouse.")
        node = WarehouseStorageNode(
            warehouse_id=data.warehouse_id,
            parent_id=data.parent_id,
            node_type=data.node_type.value,
            code=data.code,
            name=data.name,
            description=data.description,
            path=self._build_path(parent.path if parent else None, data.code),
            sort_order=data.sort_order,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(node)
        self._repository.flush()
        record_audit(
            self._session,
            action="warehouse.storage_node.created",
            entity_type="warehouse_storage_node",
            entity_id=node.id,
            actor_id=actor_id,
            firm_id=warehouse.firm_id,
            after_data={"code": node.code, "warehouse_id": str(warehouse.id)},
        )
        self._commit_unique("Storage node code or name already exists in this warehouse.")
        return node

    def update_storage_node(
        self,
        storage_node_id: UUID,
        data: StorageNodeUpdate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> WarehouseStorageNode:
        node = self.get_storage_node(storage_node_id, firm_scope=firm_scope)
        if data.warehouse_id != node.warehouse_id:
            raise ValidationError("Storage node warehouse cannot be changed.")
        parent = None
        if data.parent_id is not None:
            if data.parent_id == node.id:
                raise ValidationError("Storage node cannot be its own parent.")
            parent = self._repository.get_storage_node(
                data.parent_id, firm_scope, include_deleted=False
            )
            if parent is None or parent.warehouse_id != node.warehouse_id:
                raise ValidationError("Parent storage node is invalid for this warehouse.")
            if parent.path.startswith(f"{node.path}/"):
                raise ValidationError("Circular storage hierarchy is not allowed.")
        old_path = node.path
        new_path = self._build_path(parent.path if parent else None, data.code)
        node.parent_id = data.parent_id
        node.node_type = data.node_type.value
        node.code = data.code
        node.name = data.name
        node.description = data.description
        node.path = new_path
        node.sort_order = data.sort_order
        node.is_active = data.is_active
        node.updated_by = actor_id
        if old_path != new_path:
            self._repath_descendants(node.warehouse_id, old_path, new_path)
        self._commit_unique("Storage node code or name already exists in this warehouse.")
        return node

    def delete_storage_node(
        self, storage_node_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        node = self.get_storage_node(storage_node_id, firm_scope=firm_scope)
        children = self._repository.list_storage_nodes(
            warehouse_id=node.warehouse_id,
            firm_scope=firm_scope,
            include_deleted=False,
        )
        if any(item.parent_id == node.id for item in children):
            raise ValidationError("Cannot delete a storage node with active children.")
        node.is_deleted = True
        node.deleted_at = utc_now()
        node.deleted_by = actor_id
        node.updated_by = actor_id
        self._session.commit()

    def get_storage_node(
        self,
        storage_node_id: UUID,
        *,
        firm_scope: UUID | None,
        include_deleted: bool = False,
    ) -> WarehouseStorageNode:
        node = self._repository.get_storage_node(
            storage_node_id,
            firm_scope,
            include_deleted=include_deleted,
        )
        if node is None:
            raise ResourceNotFoundError("Storage node not found.")
        return node

    def list_storage_nodes(
        self, *, warehouse_id: UUID, firm_scope: UUID | None, include_deleted: bool
    ) -> list[WarehouseStorageNode]:
        return self._repository.list_storage_nodes(
            warehouse_id=warehouse_id,
            firm_scope=firm_scope,
            include_deleted=include_deleted,
        )

    def list_branch_types(self, *, firm_id: UUID, include_deleted: bool) -> list[BranchType]:
        return self._repository.list_branch_types(firm_id, include_deleted)

    def create_branch_type(
        self, data: BranchTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> BranchType:
        row = BranchType(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(row)
        self._commit_unique("Branch type code or name already exists in this firm.")
        return row

    def update_branch_type(
        self,
        branch_type_id: UUID,
        data: BranchTypeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> BranchType:
        row = self._repository.get_branch_type(branch_type_id, firm_id, include_deleted=True)
        if row is None:
            raise ResourceNotFoundError("Branch type not found.")
        row.code = data.code
        row.name = data.name
        row.description = data.description
        row.is_active = data.is_active
        row.updated_by = actor_id
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        self._commit_unique("Branch type code or name already exists in this firm.")
        return row

    def delete_branch_type(self, branch_type_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        row = self._repository.get_branch_type(branch_type_id, firm_id, include_deleted=False)
        if row is None:
            raise ResourceNotFoundError("Branch type not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def list_warehouse_types(
        self, *, firm_id: UUID, include_deleted: bool
    ) -> list[WarehouseType]:
        return self._repository.list_warehouse_types(firm_id, include_deleted)

    def create_warehouse_type(
        self, data: WarehouseTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> WarehouseType:
        row = WarehouseType(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(row)
        self._commit_unique("Warehouse type code or name already exists in this firm.")
        return row

    def update_warehouse_type(
        self,
        warehouse_type_id: UUID,
        data: WarehouseTypeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> WarehouseType:
        row = self._repository.get_warehouse_type(
            warehouse_type_id, firm_id, include_deleted=True
        )
        if row is None:
            raise ResourceNotFoundError("Warehouse type not found.")
        row.code = data.code
        row.name = data.name
        row.description = data.description
        row.is_active = data.is_active
        row.updated_by = actor_id
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        self._commit_unique("Warehouse type code or name already exists in this firm.")
        return row

    def delete_warehouse_type(
        self, warehouse_type_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        row = self._repository.get_warehouse_type(
            warehouse_type_id, firm_id, include_deleted=False
        )
        if row is None:
            raise ResourceNotFoundError("Warehouse type not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def _assert_unique_branch_code(
        self, firm_id: UUID, code: str, excluding_id: UUID | None = None
    ) -> None:
        duplicate = self._repository.branch_duplicate_id(
            firm_id,
            code=code,
            excluding_id=excluding_id,
        )
        if duplicate is not None:
            raise ConflictError("Branch code already exists in this firm.")

    def _assert_unique_warehouse_code(
        self, firm_id: UUID, code: str, excluding_id: UUID | None = None
    ) -> None:
        duplicate = self._repository.warehouse_duplicate_id(
            firm_id,
            code=code,
            excluding_id=excluding_id,
        )
        if duplicate is not None:
            raise ConflictError("Warehouse code already exists in this firm.")

    def _commit_unique(self, message: str) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error

    @staticmethod
    def _branch_values(data: BranchCreate | BranchUpdate) -> dict[str, object]:
        values = data.model_dump(mode="python")
        values["status"] = data.status.value
        values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _warehouse_values(data: WarehouseCreate | WarehouseUpdate) -> dict[str, object]:
        values = data.model_dump(mode="python")
        values["status"] = data.status.value
        values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _build_path(parent_path: str | None, code: str) -> str:
        return f"{parent_path}/{code}" if parent_path else code

    def _repath_descendants(
        self, warehouse_id: UUID, old_path: str, new_path: str
    ) -> None:
        descendants = self._session.scalars(
            select(WarehouseStorageNode).where(
                WarehouseStorageNode.warehouse_id == warehouse_id,
                WarehouseStorageNode.path.like(f"{old_path}/%"),
                WarehouseStorageNode.is_deleted.is_(False),
            )
        ).all()
        for row in descendants:
            row.path = row.path.replace(old_path, new_path, 1)
