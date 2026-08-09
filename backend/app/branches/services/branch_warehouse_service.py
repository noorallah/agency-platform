"""Transactional service for enterprise branch and warehouse management."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.branches.models import (
    Branch,
    BranchType,
    Warehouse,
    WarehouseStorageNode,
    WarehouseType,
)
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
from app.inventory.models import InventoryRecord


class BranchWarehouseService:
    """Coordinate branch and warehouse mutations, queries, and audits."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
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
        """Return a page of branches for the firm in scope."""
        return self._repository.list_branches(
            firm_scope=firm_scope,
            filters=filters,
            search=search,
            sort_by=sort_by,
            descending=descending,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def create_branch(
        self, data: BranchCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Branch:
        """Create a branch, demoting any previous default."""
        self._assert_unique_branch_code(firm_id, data.code)
        values = self._branch_values(data)
        self._demote_other_default_branches(
            firm_id, is_default=bool(values["is_default"]), exclude_id=None
        )
        row = Branch(
            firm_id=firm_id,
            **values,
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
        """Return one branch the firm owns."""
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
        """Replace a branch, demoting any previous default."""
        row = self.get_branch(branch_id, firm_scope=firm_scope)
        self._assert_unique_branch_code(row.firm_id, data.code, excluding_id=row.id)
        before: dict[str, object] = {"code": row.code, "status": row.status}
        values = self._branch_values(data)
        self._demote_other_default_branches(
            row.firm_id, is_default=bool(values["is_default"]), exclude_id=row.id
        )
        for field, value in values.items():
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

    def delete_branch(
        self, branch_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        """Soft delete a branch that has no live warehouses."""
        row = self.get_branch(branch_id, firm_scope=firm_scope)
        self._assert_branch_removable(row)
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
        """Restore a soft-deleted branch."""
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
        """Copy a branch under a suffixed code."""
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
        """Return branch counts by status."""
        total, active, inactive, draft, archived, deleted = (
            self._repository.branch_summary(firm_scope, filters)
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
        """Soft delete several branches, auditing each."""
        affected = 0
        for branch_id in data.ids:
            row = self.get_branch(branch_id, firm_scope=firm_scope)
            if row.is_deleted:
                continue
            self._assert_branch_removable(row)
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id
            self._audit_bulk(row, action="branch.deleted", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_restore_branches(
        self, data: BulkIdsRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        """Restore several branches, auditing each."""
        affected = 0
        for branch_id in data.ids:
            row = self.get_branch(
                branch_id, firm_scope=firm_scope, include_deleted=True
            )
            if not row.is_deleted:
                continue
            row.is_deleted = False
            row.deleted_at = None
            row.deleted_by = None
            row.updated_by = actor_id
            self._audit_bulk(row, action="branch.restored", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_branch_status(
        self, data: BulkBranchStatusRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        """Set the status of several branches, auditing each."""
        affected = 0
        for branch_id in data.ids:
            row = self.get_branch(branch_id, firm_scope=firm_scope)
            if row.status == data.status.value:
                continue
            row.status = data.status.value
            row.updated_by = actor_id
            self._audit_bulk(row, action="branch.updated", actor_id=actor_id)
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
        """Return a page of warehouses for the firm in scope."""
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
        """Create a warehouse under a branch the firm owns."""
        self._assert_unique_warehouse_code(firm_id, data.code)
        branch = self.get_branch(data.branch_id, firm_scope=firm_id)
        values = self._warehouse_values(data)
        self._demote_other_default_warehouses(
            branch.id, is_default=bool(values["is_default"]), exclude_id=None
        )
        row = Warehouse(
            firm_id=firm_id,
            **values,
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
        """Return one warehouse the firm owns."""
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
        """Replace a warehouse, demoting any previous default."""
        row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
        self._assert_unique_warehouse_code(row.firm_id, data.code, excluding_id=row.id)
        self.get_branch(data.branch_id, firm_scope=row.firm_id)
        before: dict[str, object] = {"code": row.code, "status": row.status}
        values = self._warehouse_values(data)
        self._demote_other_default_warehouses(
            data.branch_id, is_default=bool(values["is_default"]), exclude_id=row.id
        )
        for field, value in values.items():
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
        """Soft delete a warehouse that holds no stock."""
        row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
        self._assert_warehouse_removable(row)
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
        """Restore a soft-deleted warehouse."""
        row = self.get_warehouse(
            warehouse_id, firm_scope=firm_scope, include_deleted=True
        )
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
        """Copy a warehouse under a suffixed code."""
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
        """Return warehouse counts by status."""
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
        """Soft delete several warehouses, auditing each."""
        affected = 0
        for warehouse_id in data.ids:
            row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
            if row.is_deleted:
                continue
            self._assert_warehouse_removable(row)
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id
            self._audit_bulk(row, action="warehouse.deleted", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_restore_warehouses(
        self, data: BulkIdsRequest, *, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        """Restore several warehouses, auditing each."""
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
            self._audit_bulk(row, action="warehouse.restored", actor_id=actor_id)
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
        """Set the status of several warehouses, auditing each."""
        affected = 0
        for warehouse_id in data.ids:
            row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
            if row.status == data.status.value:
                continue
            row.status = data.status.value
            row.updated_by = actor_id
            self._audit_bulk(row, action="warehouse.updated", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def create_storage_node(
        self, data: StorageNodeCreate, *, firm_scope: UUID | None, actor_id: UUID
    ) -> WarehouseStorageNode:
        """Add a node to a warehouse's storage hierarchy."""
        warehouse = self.get_warehouse(data.warehouse_id, firm_scope=firm_scope)
        parent = None
        if data.parent_id is not None:
            parent = self._repository.get_storage_node(
                data.parent_id, firm_scope, include_deleted=False
            )
            if parent is None or parent.warehouse_id != data.warehouse_id:
                raise ValidationError(
                    "Parent storage node is invalid for this warehouse."
                )
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
        self._commit_unique(
            "Storage node code or name already exists in this warehouse."
        )
        return node

    def update_storage_node(
        self,
        storage_node_id: UUID,
        data: StorageNodeUpdate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> WarehouseStorageNode:
        """Change a storage node and repath its descendants."""
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
                raise ValidationError(
                    "Parent storage node is invalid for this warehouse."
                )
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
        self._commit_unique(
            "Storage node code or name already exists in this warehouse."
        )
        return node

    def delete_storage_node(
        self, storage_node_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        """Soft delete a storage node that has no children."""
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
        """Return one storage node, scoped through its warehouse."""
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
        """Return a warehouse's storage hierarchy."""
        return self._repository.list_storage_nodes(
            warehouse_id=warehouse_id,
            firm_scope=firm_scope,
            include_deleted=include_deleted,
        )

    def list_branch_types(
        self, *, firm_id: UUID, include_deleted: bool
    ) -> list[BranchType]:
        """Return the firm's branch types."""
        return self._repository.list_branch_types(firm_id, include_deleted)

    def create_branch_type(
        self, data: BranchTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> BranchType:
        """Add a branch type."""
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
        """Change a branch type."""
        row = self._repository.get_branch_type(
            branch_type_id, firm_id, include_deleted=True
        )
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

    def delete_branch_type(
        self, branch_type_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Soft delete a branch type."""
        row = self._repository.get_branch_type(
            branch_type_id, firm_id, include_deleted=False
        )
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
        """Return the firm's warehouse types."""
        return self._repository.list_warehouse_types(firm_id, include_deleted)

    def create_warehouse_type(
        self, data: WarehouseTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> WarehouseType:
        """Add a warehouse type."""
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
        """Change a warehouse type."""
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
        """Soft delete a warehouse type."""
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

    def _audit_bulk(
        self, row: Branch | Warehouse, *, action: str, actor_id: UUID
    ) -> None:
        """Record a bulk mutation the way the single-row endpoint records it.

        The six bulk endpoints wrote nothing at all, so deleting fifty branches
        through the toolbar left an audit trail showing none of it while
        deleting one through the row menu was recorded.
        """
        record_audit(
            self._session,
            action=action,
            entity_type="branch" if isinstance(row, Branch) else "warehouse",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data={"code": row.code},
            after_data={"status": row.status, "is_deleted": row.is_deleted},
        )

    def _assert_branch_removable(self, branch: Branch) -> None:
        """Refuse to delete a branch that still has live warehouses.

        Deleting one only hid the branch: its warehouses stayed active and kept
        receiving and issuing stock while pointing at a branch no listing shows.
        The module already refuses to delete a storage node with children.
        """
        live = self._session.scalar(
            select(Warehouse.id)
            .where(
                Warehouse.branch_id == branch.id,
                Warehouse.is_deleted.is_(False),
            )
            .limit(1)
        )
        if live is not None:
            raise ValidationError(
                "This branch still has warehouses. Remove or reassign them first."
            )

    def _assert_warehouse_removable(self, warehouse: Warehouse) -> None:
        """Refuse to delete a warehouse that still holds stock.

        The stock rows point at the warehouse and survive its deletion, so the
        quantity stayed on the books in a location nothing would show.
        """
        held = self._session.scalar(
            select(InventoryRecord.id)
            .where(
                InventoryRecord.warehouse_id == warehouse.id,
                InventoryRecord.is_deleted.is_(False),
                or_(
                    InventoryRecord.current_quantity != 0,
                    InventoryRecord.reserved_quantity != 0,
                ),
            )
            .limit(1)
        )
        if held is not None:
            raise ValidationError(
                "This warehouse still holds stock. Move or write it off first."
            )

    def _demote_other_default_branches(
        self, firm_id: UUID, *, is_default: bool, exclude_id: UUID | None
    ) -> None:
        """Keep at most one default branch per firm.

        Nothing maintained the flag, so every branch could be the default at
        once and any consumer picking "the default" got an arbitrary row. The
        demotion is flushed before the promoted row is written, because the
        partial unique index rejects two defaults at statement level.
        """
        if not is_default:
            return
        statement = select(Branch).where(
            Branch.firm_id == firm_id,
            Branch.is_default.is_(True),
            Branch.is_deleted.is_(False),
        )
        if exclude_id is not None:
            statement = statement.where(Branch.id != exclude_id)
        for row in self._session.scalars(statement).all():
            row.is_default = False
        self._session.flush()

    def _demote_other_default_warehouses(
        self, branch_id: UUID, *, is_default: bool, exclude_id: UUID | None
    ) -> None:
        """Keep at most one default warehouse per branch."""
        if not is_default:
            return
        statement = select(Warehouse).where(
            Warehouse.branch_id == branch_id,
            Warehouse.is_default.is_(True),
            Warehouse.is_deleted.is_(False),
        )
        if exclude_id is not None:
            statement = statement.where(Warehouse.id != exclude_id)
        for row in self._session.scalars(statement).all():
            row.is_default = False
        self._session.flush()

    def _assert_unique_branch_code(
        self, firm_id: UUID, code: str, excluding_id: UUID | None = None
    ) -> None:
        """Refuse a branch code the firm already uses."""
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
        """Refuse a warehouse code the firm already uses."""
        duplicate = self._repository.warehouse_duplicate_id(
            firm_id,
            code=code,
            excluding_id=excluding_id,
        )
        if duplicate is not None:
            raise ConflictError("Warehouse code already exists in this firm.")

    def _commit_unique(self, message: str) -> None:
        """Commit, turning a unique-key clash into a conflict."""
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error

    @staticmethod
    def _branch_values(data: BranchCreate | BranchUpdate) -> dict[str, object]:
        """Flatten a branch payload into column values."""
        values = data.model_dump(mode="python")
        values["status"] = data.status.value
        values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _warehouse_values(data: WarehouseCreate | WarehouseUpdate) -> dict[str, object]:
        """Flatten a warehouse payload into column values."""
        values = data.model_dump(mode="python")
        values["status"] = data.status.value
        values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _build_path(parent_path: str | None, code: str) -> str:
        """Join a parent path and a code into a node path."""
        return f"{parent_path}/{code}" if parent_path else code

    def _repath_descendants(
        self, warehouse_id: UUID, old_path: str, new_path: str
    ) -> None:
        """Rewrite the stored paths below a moved node."""
        descendants = self._session.scalars(
            select(WarehouseStorageNode).where(
                WarehouseStorageNode.warehouse_id == warehouse_id,
                WarehouseStorageNode.path.like(f"{old_path}/%"),
                WarehouseStorageNode.is_deleted.is_(False),
            )
        ).all()
        for row in descendants:
            row.path = row.path.replace(old_path, new_path, 1)
