"""Transactional service for enterprise branch and warehouse management."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.branches.models import (
    Branch,
    BranchAttributeValue,
    BranchType,
    Warehouse,
    WarehouseAttributeValue,
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
from app.business.models import BusinessProfile
from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.business.services import AttributeInput, AttributeService
from app.common.audit.services import record_audit, record_change, row_state
from app.common.display_names import display_name_after_edit
from app.common.master_codes import assert_codes_free
from app.common.master_references import (
    MasterReferences,
    assert_master_references,
)
from app.common.open_documents import (
    describe_documents,
    describe_stock,
    find_open_documents,
    find_stock_holdings,
)
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryRecord
from app.sales_order.models import SalesWorkflowSettings

#: The masters a branch and a warehouse name by id. A type must be a live row
#: of the same firm; a business profile has no firm and is shared by every
#: firm in the store, so it only has to be live (D-MST-3).
_BRANCH_REFERENCES: MasterReferences = {
    "branch_type_id": (BranchType, "Branch type"),
    "business_profile_id": (BusinessProfile, "Business profile"),
}
_WAREHOUSE_REFERENCES: MasterReferences = {
    "warehouse_type_id": (WarehouseType, "Warehouse type"),
    "business_profile_id": (BusinessProfile, "Business profile"),
}


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

    def _stage_branch(
        self, data: BranchCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Branch:
        """Build and flush one branch without committing it.

        Split out so an import can stage a whole batch and commit once. The
        caller owns the transaction.
        """
        self._assert_unique_branch_code(firm_id, data.code)
        values = self._branch_values(data)
        assert_master_references(
            self._session, values, _BRANCH_REFERENCES, firm_id=firm_id
        )
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
        self._store_attributes(BranchAttributeValue, row, data.attributes, actor_id)
        record_audit(
            self._session,
            action="branch.created",
            entity_type="branch",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "status": row.status},
        )
        return row

    def create_branch(
        self, data: BranchCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Branch:
        """Create a branch, demoting any previous default."""
        row = self._stage_branch(data, firm_id=firm_id, actor_id=actor_id)
        self._commit_unique("Branch code already exists in this firm.")
        return row

    def import_branches(
        self, records: list[BranchCreate], *, firm_id: UUID, actor_id: UUID
    ) -> list[Branch]:
        """Create a validated branch batch in one transaction.

        The router used to call ``create_branch`` per record, and that commits.
        A batch whose fifth row clashed therefore returned 409 with the first
        four already written -- and re-running the corrected file then failed on
        those four as duplicates, so the import could not be retried. All or
        nothing, the way ``CustomerService.import_customers`` has always
        behaved.
        """
        try:
            rows = [
                self._stage_branch(record, firm_id=firm_id, actor_id=actor_id)
                for record in records
            ]
        except (ConflictError, IntegrityError):
            self._session.rollback()
            raise
        self._commit_unique("Branch code already exists in this firm.")
        return rows

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
        """Update a branch, demoting any previous default.

        Only the fields the caller sent are applied; the rest keep what they
        hold.
        """
        row = self.get_branch(branch_id, firm_scope=firm_scope)
        self._assert_unique_branch_code(row.firm_id, data.code, excluding_id=row.id)
        before: dict[str, object] = {"code": row.code, "status": row.status}
        values = self._branch_values(data, partial=True)
        assert_master_references(
            self._session,
            values,
            _BRANCH_REFERENCES,
            firm_id=row.firm_id,
            current=row,
        )
        self._demote_other_default_branches(
            row.firm_id,
            is_default=bool(values.get("is_default", row.is_default)),
            exclude_id=row.id,
        )
        previous_name = row.name
        for field, value in values.items():
            setattr(row, field, value)
        row.display_name = display_name_after_edit(
            current=row.display_name,
            previous_name=previous_name,
            name=row.name,
            sent=data.display_name,
            was_sent="display_name" in data.model_fields_set,
        )
        row.updated_by = actor_id
        if "attributes" in data.model_fields_set:
            self._store_attributes(BranchAttributeValue, row, data.attributes, actor_id)
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
        self._assert_branch_restorable(row)
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
            self._assert_branch_restorable(row)
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

    def _resolve_branch(
        self,
        data: WarehouseCreate | WarehouseUpdate,
        *,
        firm_id: UUID,
        current_id: UUID | None = None,
    ) -> Branch:
        """Find the branch a warehouse payload names, by id or by code.

        ``current_id`` is the branch an existing warehouse already belongs to,
        used when an update names neither. A code nobody in the firm holds is
        refused by name: an import file is where codes come from, and the
        person correcting it needs to know which cell.
        """
        if data.branch_id is not None:
            return self.get_branch(data.branch_id, firm_scope=firm_id)
        if data.branch_code:
            branch_id = self._repository.branch_duplicate_id(
                firm_id, code=data.branch_code
            )
            if branch_id is None:
                raise ValidationError(
                    f"No branch with code {data.branch_code} in this firm."
                )
            return self.get_branch(branch_id, firm_scope=firm_id)
        if current_id is not None:
            return self.get_branch(current_id, firm_scope=firm_id)
        raise ValidationError("Either branch_id or branch_code is required.")

    def _stage_warehouse(
        self, data: WarehouseCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Warehouse:
        """Build and flush one warehouse without committing it."""
        self._assert_unique_warehouse_code(firm_id, data.code)
        branch = self._resolve_branch(data, firm_id=firm_id)
        values = self._warehouse_values(data)
        assert_master_references(
            self._session, values, _WAREHOUSE_REFERENCES, firm_id=firm_id
        )
        values["branch_id"] = branch.id
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
        self._store_attributes(WarehouseAttributeValue, row, data.attributes, actor_id)
        record_audit(
            self._session,
            action="warehouse.created",
            entity_type="warehouse",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "branch_id": str(branch.id)},
        )
        return row

    def create_warehouse(
        self, data: WarehouseCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Warehouse:
        """Create a warehouse under a branch the firm owns."""
        row = self._stage_warehouse(data, firm_id=firm_id, actor_id=actor_id)
        self._commit_unique("Warehouse code already exists in this firm.")
        return row

    def import_warehouses(
        self, records: list[WarehouseCreate], *, firm_id: UUID, actor_id: UUID
    ) -> list[Warehouse]:
        """Create a validated warehouse batch in one transaction.

        Same reason as :meth:`import_branches`: a partial import that cannot be
        retried is worse than a refused one.
        """
        try:
            rows = [
                self._stage_warehouse(record, firm_id=firm_id, actor_id=actor_id)
                for record in records
            ]
        except (ConflictError, IntegrityError):
            self._session.rollback()
            raise
        self._commit_unique("Warehouse code already exists in this firm.")
        return rows

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
        """Update a warehouse, demoting any previous default.

        Only the fields the caller sent are applied; the rest keep what they
        hold.
        """
        row = self.get_warehouse(warehouse_id, firm_scope=firm_scope)
        self._assert_unique_warehouse_code(row.firm_id, data.code, excluding_id=row.id)
        branch = self._resolve_branch(
            data, firm_id=row.firm_id, current_id=row.branch_id
        )
        before: dict[str, object] = {"code": row.code, "status": row.status}
        values = self._warehouse_values(data, partial=True)
        assert_master_references(
            self._session,
            values,
            _WAREHOUSE_REFERENCES,
            firm_id=row.firm_id,
            current=row,
        )
        if "branch_id" in values or data.branch_code:
            values["branch_id"] = branch.id
        self._demote_other_default_warehouses(
            branch.id,
            is_default=bool(values.get("is_default", row.is_default)),
            exclude_id=row.id,
        )
        previous_name = row.name
        for field, value in values.items():
            setattr(row, field, value)
        row.display_name = display_name_after_edit(
            current=row.display_name,
            previous_name=previous_name,
            name=row.name,
            sent=data.display_name,
            was_sent="display_name" in data.model_fields_set,
        )
        row.updated_by = actor_id
        if "attributes" in data.model_fields_set:
            self._store_attributes(
                WarehouseAttributeValue, row, data.attributes, actor_id
            )
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
        self._assert_warehouse_restorable(row)
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
            self._assert_warehouse_restorable(row)
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
        self._assert_storage_node_free(
            warehouse_id=data.warehouse_id,
            parent_id=data.parent_id,
            code=data.code,
            name=data.name,
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
        self._assert_storage_node_free(
            warehouse_id=node.warehouse_id,
            parent_id=data.parent_id,
            code=data.code,
            name=data.name,
            excluding_id=node.id,
        )
        before = row_state(node)
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
        # The edit wrote no trail (D-MST-11); the node's firm is its
        # warehouse's.
        warehouse = self.get_warehouse(node.warehouse_id, firm_scope=firm_scope)
        record_change(
            self._session,
            action="warehouse.storage_node.updated",
            entity_type="warehouse_storage_node",
            row=node,
            actor_id=actor_id,
            before=before,
            firm_id=warehouse.firm_id,
        )
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
        warehouse = self.get_warehouse(node.warehouse_id, firm_scope=firm_scope)
        self._assert_storage_node_removable(node, warehouse)
        node.is_deleted = True
        node.deleted_at = utc_now()
        node.deleted_by = actor_id
        node.updated_by = actor_id
        # The delete wrote no audit row at all, so a bin disappearing from the
        # hierarchy left nothing in the trail to say who removed it.
        record_audit(
            self._session,
            action="warehouse.storage_node.deleted",
            entity_type="warehouse_storage_node",
            entity_id=node.id,
            actor_id=actor_id,
            firm_id=warehouse.firm_id,
            before_data={"code": node.code, "warehouse": warehouse.code},
        )
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

    def _store_attributes(
        self,
        model: type[BranchAttributeValue] | type[WarehouseAttributeValue],
        row: Branch | Warehouse,
        attributes: list[AttributeValueInput],
        actor_id: UUID,
    ) -> None:
        """Validate and persist a branch's or warehouse's custom fields."""
        AttributeService(self._session).replace_values(
            model,
            row.id,
            [
                AttributeInput(
                    attribute_definition_id=item.attribute_definition_id,
                    value=item.value,
                )
                for item in attributes
            ],
            firm_id=row.firm_id,
            actor_id=actor_id,
        )

    def attribute_responses(
        self,
        model: type[BranchAttributeValue] | type[WarehouseAttributeValue],
        row: Branch | Warehouse,
    ) -> list[AttributeValueResponse]:
        """Return one record's stored custom fields in response shape."""
        return [
            AttributeValueResponse.model_validate(value)
            for value in AttributeService(self._session).value_rows(model, row.id)
        ]

    def attribute_responses_for_many(
        self,
        model: type[BranchAttributeValue] | type[WarehouseAttributeValue],
        rows: list[Branch] | list[Warehouse],
    ) -> dict[UUID, list[AttributeValueResponse]]:
        """Return a page of records' custom fields in one query (D-CFG-20)."""
        grouped = AttributeService(self._session).value_rows_for_many(
            model, [row.id for row in rows]
        )
        return {
            owner: [AttributeValueResponse.model_validate(value) for value in values]
            for owner, values in grouped.items()
        }

    def create_branch_type(
        self, data: BranchTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> BranchType:
        """Add a branch type."""
        self._assert_type_free(BranchType, data, firm_id=firm_id)
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
        self._session.flush()
        # Type writes left no trail at all (D-MST-11).
        record_change(
            self._session,
            action="branch_type.created",
            entity_type="branch_type",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._commit_unique("Branch type code or name already exists in this firm.")
        return row

    def update_branch_type(
        self,
        branch_type_id: UUID,
        data: BranchTypeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> BranchType:
        """Change a live branch type.

        A retired one is not found (D-MST-11): this loaded deleted rows too and
        cleared the flag, so an edit silently brought the type back.
        """
        row = self._repository.get_branch_type(
            branch_type_id, firm_id, include_deleted=False
        )
        if row is None:
            raise ResourceNotFoundError("Branch type not found.")
        assert_version(row.version, expected_version)
        self._assert_type_free(BranchType, data, firm_id=firm_id, excluding_id=row.id)
        before = row_state(row)
        row.code = data.code
        row.name = data.name
        row.description = data.description
        row.is_active = data.is_active
        row.updated_by = actor_id
        record_change(
            self._session,
            action="branch_type.updated",
            entity_type="branch_type",
            row=row,
            actor_id=actor_id,
            before=before,
            firm_id=firm_id,
        )
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
        record_change(
            self._session,
            action="branch_type.deleted",
            entity_type="branch_type",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
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
        self._assert_type_free(WarehouseType, data, firm_id=firm_id)
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
        self._session.flush()
        # Type writes left no trail at all (D-MST-11).
        record_change(
            self._session,
            action="warehouse_type.created",
            entity_type="warehouse_type",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._commit_unique("Warehouse type code or name already exists in this firm.")
        return row

    def update_warehouse_type(
        self,
        warehouse_type_id: UUID,
        data: WarehouseTypeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> WarehouseType:
        """Change a live warehouse type.

        A retired one is not found (D-MST-11): this loaded deleted rows too and
        cleared the flag, so an edit silently brought the type back.
        """
        row = self._repository.get_warehouse_type(
            warehouse_type_id, firm_id, include_deleted=False
        )
        if row is None:
            raise ResourceNotFoundError("Warehouse type not found.")
        assert_version(row.version, expected_version)
        self._assert_type_free(
            WarehouseType, data, firm_id=firm_id, excluding_id=row.id
        )
        before = row_state(row)
        row.code = data.code
        row.name = data.name
        row.description = data.description
        row.is_active = data.is_active
        row.updated_by = actor_id
        record_change(
            self._session,
            action="warehouse_type.updated",
            entity_type="warehouse_type",
            row=row,
            actor_id=actor_id,
            before=before,
            firm_id=firm_id,
        )
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
        record_change(
            self._session,
            action="warehouse_type.deleted",
            entity_type="warehouse_type",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
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

    def _assert_storage_node_removable(
        self, node: WarehouseStorageNode, warehouse: Warehouse
    ) -> None:
        """Refuse to delete a storage area that holds stock or is on a document.

        The warehouse guard's missing twin (D-MST-8). Stock is held per node
        (``inventories.storage_node_id``), and ``_validate_references`` refuses
        any movement naming a deleted one -- "Storage node does not belong to
        the selected warehouse." -- so 5 units in a deleted bin could be
        neither seen nor moved back out. A line of an open document naming the
        bin would fail the same way at dispatch or receipt.
        """
        reasons: list[str] = []
        holdings = find_stock_holdings(
            self._session, warehouse.firm_id, storage_node_id=node.id
        )
        if holdings:
            reasons.append(f"holds {describe_stock(holdings)}")
        documents = find_open_documents(
            self._session, warehouse.firm_id, storage_node_id=node.id
        )
        if documents:
            reasons.append(f"is named on {describe_documents(documents)}")
        if reasons:
            raise ValidationError(
                f"{node.code} cannot be deleted: it {' and '.join(reasons)}. "
                "Move the stock out and finish, cancel or close what is open "
                "first, or set the storage area inactive to stop using it."
            )

    def _assert_no_open_documents(
        self, row: Branch | Warehouse, *, branch: bool
    ) -> None:
        """Refuse to delete a branch or warehouse a document in flight names.

        Every document service loads its branch and warehouse with
        ``is_deleted`` false, so an approved order for a deleted warehouse can
        be neither delivered nor cancelled (D-MST-8).
        """
        documents = find_open_documents(
            self._session,
            row.firm_id,
            branch_id=row.id if branch else None,
            warehouse_id=None if branch else row.id,
        )
        if documents:
            raise ValidationError(
                f"{row.code} cannot be deleted: it is named on "
                f"{describe_documents(documents)}. Finish, cancel or close "
                "them first, or set it inactive to stop using it."
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
        self._assert_not_a_sales_default(
            SalesWorkflowSettings.default_branch_id, branch, "branch"
        )
        self._assert_no_open_documents(branch, branch=True)

    def _assert_not_a_sales_default(
        self,
        column: InstrumentedAttribute[UUID | None],
        row: Branch | Warehouse,
        noun: str,
    ) -> None:
        """Refuse to delete the place the firm's bare bills ship from.

        ``sales_workflow_settings`` names a default branch and warehouse by id
        with no foreign key, so deleting one left every bill raised without an
        order or a note failing at bill time, far from the delete that broke
        it (D-CFG-14). Refused by name here instead.
        """
        named = self._session.scalar(
            select(SalesWorkflowSettings.id).where(
                SalesWorkflowSettings.firm_id == row.firm_id,
                SalesWorkflowSettings.is_deleted.is_(False),
                column == row.id,
            )
        )
        if named is not None:
            raise ValidationError(
                f"{noun.capitalize()} {row.code} is the default {noun} bills "
                "ship from when no order or note names one. Choose another in "
                "Sales stages first."
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
        self._assert_not_a_sales_default(
            SalesWorkflowSettings.default_warehouse_id, warehouse, "warehouse"
        )
        self._assert_no_open_documents(warehouse, branch=False)

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

    def _assert_branch_restorable(self, row: Branch) -> None:
        """Refuse a restore into a code a live branch now holds (D-MST-11)."""
        if self._repository.branch_duplicate_id(
            row.firm_id, code=row.code, excluding_id=row.id
        ):
            raise ConflictError(
                f"{row.code} cannot be restored: a live branch now holds its code."
            )

    def _assert_warehouse_restorable(self, row: Warehouse) -> None:
        """Refuse a restore into a code a live warehouse now holds (D-MST-11)."""
        if self._repository.warehouse_duplicate_id(
            row.firm_id, code=row.code, excluding_id=row.id
        ):
            raise ConflictError(
                f"{row.code} cannot be restored: a live warehouse now holds its "
                "code."
            )

    def _assert_type_free(
        self,
        model: type[BranchType] | type[WarehouseType],
        data: BranchTypeWrite | WarehouseTypeWrite,
        *,
        firm_id: UUID,
        excluding_id: UUID | None = None,
    ) -> None:
        """Refuse a code or name a live type of the same kind already holds."""
        label = "branch type" if model is BranchType else "warehouse type"
        for column, value in (("code", data.code), ("name", data.name)):
            assert_codes_free(
                self._session,
                model,
                scope={"firm_id": firm_id},
                values={column: value},
                excluding_id=excluding_id,
                message=f"A {label} with this {column} already exists.",
            )

    def _assert_storage_node_free(
        self,
        *,
        warehouse_id: UUID,
        parent_id: UUID | None,
        code: str,
        name: str,
        excluding_id: UUID | None = None,
    ) -> None:
        """Refuse a code the warehouse, or a name the parent, already uses."""
        assert_codes_free(
            self._session,
            WarehouseStorageNode,
            scope={"warehouse_id": warehouse_id},
            values={"code": code},
            excluding_id=excluding_id,
            message="A storage node with this code already exists in this warehouse.",
        )
        assert_codes_free(
            self._session,
            WarehouseStorageNode,
            scope={"warehouse_id": warehouse_id, "parent_id": parent_id},
            values={"name": name},
            excluding_id=excluding_id,
            message="A storage node with this name already exists at this level.",
        )

    def _commit_unique(self, message: str) -> None:
        """Commit, turning a unique-key clash into a conflict."""
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error

    @staticmethod
    def _branch_values(
        data: BranchCreate | BranchUpdate, *, partial: bool = False
    ) -> dict[str, object]:
        """Flatten a branch payload into column values.

        On an update `partial` keeps the fields the caller never mentioned out
        of the result, so they are left alone rather than reset to their
        defaults -- see `_warehouse_values` for why that mattered.
        """
        values = data.model_dump(
            mode="python", exclude_unset=partial, exclude={"attributes"}
        )
        if "status" in values:
            values["status"] = data.status.value
        # An edit decides the display name itself (D-MST-11), so a custom
        # one survives a save that did not send it.
        values.pop("display_name", None)
        if not partial:
            values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _warehouse_values(
        data: WarehouseCreate | WarehouseUpdate, *, partial: bool = False
    ) -> dict[str, object]:
        """Flatten a warehouse payload into column values.

        Every field on the write schema carries a default, so a full dump turns
        an omission into an instruction: one rename from a client that does not
        edit addresses cleared the branch's street lines, its city, its default
        flag and its GST registration. `partial` dumps only what was actually
        sent, so absent means leave alone and an explicit `null` still clears.
        """
        values = data.model_dump(
            mode="python", exclude_unset=partial, exclude={"attributes"}
        )
        # Resolved to an id by the caller; the row has no such column.
        values.pop("branch_code", None)
        if "status" in values:
            values["status"] = data.status.value
        # An edit decides the display name itself (D-MST-11), so a custom
        # one survives a save that did not send it.
        values.pop("display_name", None)
        if not partial:
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
