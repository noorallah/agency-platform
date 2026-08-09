"""Firm-scoped REST endpoints for branch and warehouse management."""

import csv
import io
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.branches.schemas import (
    BranchCreate,
    BranchImportRequest,
    BranchListFilters,
    BranchResponse,
    BranchStatus,
    BranchSummary,
    BranchTypeResponse,
    BranchTypeWrite,
    BranchUpdate,
    BranchWarehouseSchema,
    BulkBranchStatusRequest,
    BulkIdsRequest,
    BulkWarehouseStatusRequest,
    StorageNodeCreate,
    StorageNodeResponse,
    StorageNodeUpdate,
    WarehouseCreate,
    WarehouseImportRequest,
    WarehouseListFilters,
    WarehouseResponse,
    WarehouseStatus,
    WarehouseSummary,
    WarehouseTypeResponse,
    WarehouseTypeWrite,
    WarehouseUpdate,
)
from app.branches.services import BranchWarehouseService
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse

router = APIRouter(
    prefix="/api/v1",
    tags=["Branches & Warehouses"],
    responses=STANDARD_ERROR_RESPONSES,
)


BranchViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("BRANCH_VIEW")]
BranchCreateScope = Annotated[ResolvedFirmScope, firm_permission_scope("BRANCH_CREATE")]
BranchUpdateScope = Annotated[ResolvedFirmScope, firm_permission_scope("BRANCH_UPDATE")]
BranchDeleteScope = Annotated[ResolvedFirmScope, firm_permission_scope("BRANCH_DELETE")]
BranchRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("BRANCH_RESTORE")
]
WarehouseViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("WAREHOUSE_VIEW")
]
WarehouseCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("WAREHOUSE_CREATE")
]
WarehouseUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("WAREHOUSE_UPDATE")
]
WarehouseDeleteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("WAREHOUSE_DELETE")
]
WarehouseRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("WAREHOUSE_RESTORE")
]
StorageManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("STORAGE_AREA_MANAGE")
]
BranchWarehouseImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("BRANCH_WAREHOUSE_IMPORT")
]
BranchWarehouseExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("BRANCH_WAREHOUSE_EXPORT")
]


def _branch_filters(
    *,
    status_value: BranchStatus | None,
    branch_type_id: UUID | None,
    manager_id: UUID | None,
    business_profile_id: UUID | None,
    city_id: UUID | None,
    state_id: UUID | None,
    country_id: UUID | None,
    include_deleted: bool,
    created_from: date | None,
    created_to: date | None,
) -> BranchListFilters:
    try:
        return BranchListFilters(
            status=status_value,
            branch_type_id=branch_type_id,
            manager_id=manager_id,
            business_profile_id=business_profile_id,
            city_id=city_id,
            state_id=state_id,
            country_id=country_id,
            include_deleted=include_deleted,
            created_from=created_from,
            created_to=created_to,
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


def _warehouse_filters(
    *,
    status_value: WarehouseStatus | None,
    branch_id: UUID | None,
    warehouse_type_id: UUID | None,
    manager_id: UUID | None,
    business_profile_id: UUID | None,
    city_id: UUID | None,
    state_id: UUID | None,
    country_id: UUID | None,
    include_deleted: bool,
    created_from: date | None,
    created_to: date | None,
) -> WarehouseListFilters:
    try:
        return WarehouseListFilters(
            status=status_value,
            branch_id=branch_id,
            warehouse_type_id=warehouse_type_id,
            manager_id=manager_id,
            business_profile_id=business_profile_id,
            city_id=city_id,
            state_id=state_id,
            country_id=country_id,
            include_deleted=include_deleted,
            created_from=created_from,
            created_to=created_to,
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("/branches", response_model=PaginatedResponse[BranchResponse])
def list_branches(
    scope: BranchViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "status", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: Annotated[BranchStatus | None, Query(alias="status")] = None,
    branch_type_id: UUID | None = None,
    manager_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    city_id: UUID | None = None,
    state_id: UUID | None = None,
    country_id: UUID | None = None,
    include_deleted: bool = False,
    created_from: date | None = None,
    created_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BranchResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = _branch_filters(
        status_value=status_value,
        branch_type_id=branch_type_id,
        manager_id=manager_id,
        business_profile_id=business_profile_id,
        city_id=city_id,
        state_id=state_id,
        country_id=country_id,
        include_deleted=include_deleted,
        created_from=created_from,
        created_to=created_to,
    )
    rows, total = BranchWarehouseService(db).list_branches(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    data = []
    for row in rows:
        payload = BranchResponse.model_validate(row).model_dump(mode="python")
        payload["warehouse_count"] = len(
            [item for item in row.warehouses if not item.is_deleted]
        )
        data.append(BranchResponse.model_validate(payload))
    return PaginatedResponse(data=data, pagination=params.metadata(total))


@router.get("/branches/summary", response_model=ApiResponse[BranchSummary])
def branch_summary(
    scope: BranchViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchSummary]:
    summary = BranchWarehouseService(db).branch_summary(
        firm_scope=scope.firm_id,
        filters=BranchListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.post(
    "/branches",
    response_model=ApiResponse[BranchResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_branch(
    data: BranchCreate,
    scope: BranchCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchResponse]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when creating a branch.")
    row = BranchWarehouseService(db).create_branch(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    payload = BranchResponse.model_validate(row).model_dump(mode="python")
    payload["warehouse_count"] = 0
    return ApiResponse(data=BranchResponse.model_validate(payload))


@router.post(
    "/branches/import",
    response_model=ApiResponse[list[BranchResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_branches(
    data: BranchImportRequest,
    scope: BranchWarehouseImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[BranchResponse]]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing branches.")
    service = BranchWarehouseService(db)
    rows = [
        service.create_branch(record, firm_id=scope.firm_id, actor_id=scope.actor_id)
        for record in data.records
    ]
    payloads = []
    for row in rows:
        payload = BranchResponse.model_validate(row).model_dump(mode="python")
        payload["warehouse_count"] = 0
        payloads.append(BranchResponse.model_validate(payload))
    return ApiResponse(data=payloads)


@router.get("/branches/{branch_id}", response_model=ApiResponse[BranchResponse])
def get_branch(
    branch_id: UUID,
    scope: BranchViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchResponse]:
    row = BranchWarehouseService(db).get_branch(
        branch_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    payload = BranchResponse.model_validate(row).model_dump(mode="python")
    payload["warehouse_count"] = len(
        [item for item in row.warehouses if not item.is_deleted]
    )
    return ApiResponse(data=BranchResponse.model_validate(payload))


@router.put("/branches/{branch_id}", response_model=ApiResponse[BranchResponse])
def update_branch(
    branch_id: UUID,
    data: BranchUpdate,
    scope: BranchUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchResponse]:
    row = BranchWarehouseService(db).update_branch(
        branch_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    payload = BranchResponse.model_validate(row).model_dump(mode="python")
    payload["warehouse_count"] = len(
        [item for item in row.warehouses if not item.is_deleted]
    )
    return ApiResponse(data=BranchResponse.model_validate(payload))


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    branch_id: UUID,
    scope: BranchDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    BranchWarehouseService(db).delete_branch(
        branch_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/branches/{branch_id}/restore", response_model=ApiResponse[BranchResponse]
)
def restore_branch(
    branch_id: UUID,
    scope: BranchRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchResponse]:
    row = BranchWarehouseService(db).restore_branch(
        branch_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    payload = BranchResponse.model_validate(row).model_dump(mode="python")
    payload["warehouse_count"] = len(
        [item for item in row.warehouses if not item.is_deleted]
    )
    return ApiResponse(data=BranchResponse.model_validate(payload))


@router.post(
    "/branches/{branch_id}/duplicate", response_model=ApiResponse[BranchResponse]
)
def duplicate_branch(
    branch_id: UUID,
    scope: BranchCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchResponse]:
    row = BranchWarehouseService(db).duplicate_branch(
        branch_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    payload = BranchResponse.model_validate(row).model_dump(mode="python")
    payload["warehouse_count"] = 0
    return ApiResponse(data=BranchResponse.model_validate(payload))


@router.post("/branches/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_branches(
    data: BulkIdsRequest,
    scope: BranchDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = BranchWarehouseService(db).bulk_delete_branches(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/branches/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_branches(
    data: BulkIdsRequest,
    scope: BranchRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = BranchWarehouseService(db).bulk_restore_branches(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/branches/bulk-status", response_model=ApiResponse[dict[str, int]])
def bulk_branch_status(
    data: BulkBranchStatusRequest,
    scope: BranchUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = BranchWarehouseService(db).bulk_branch_status(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.get("/branches/export")
def export_branches(
    scope: BranchWarehouseExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Code", "Name", "Status", "Email", "Phone", "Mobile"])
    page = 1
    service = BranchWarehouseService(db)
    while True:
        rows, _ = service.list_branches(
            firm_scope=scope.firm_id,
            filters=BranchListFilters(),
            page=page,
            page_size=1000,
            search=search,
            sort_by="code",
            descending=False,
        )
        for row in rows:
            writer.writerow(
                [
                    row.code,
                    row.name,
                    row.status,
                    row.email or "",
                    row.phone or "",
                    row.mobile or "",
                ]
            )
        if len(rows) < 1000:
            break
        page += 1
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="branches.csv"'},
    )


@router.get("/warehouses", response_model=PaginatedResponse[WarehouseResponse])
def list_warehouses(
    scope: WarehouseViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "status", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: Annotated[WarehouseStatus | None, Query(alias="status")] = None,
    branch_id: UUID | None = None,
    warehouse_type_id: UUID | None = None,
    manager_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    city_id: UUID | None = None,
    state_id: UUID | None = None,
    country_id: UUID | None = None,
    include_deleted: bool = False,
    created_from: date | None = None,
    created_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[WarehouseResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = _warehouse_filters(
        status_value=status_value,
        branch_id=branch_id,
        warehouse_type_id=warehouse_type_id,
        manager_id=manager_id,
        business_profile_id=business_profile_id,
        city_id=city_id,
        state_id=state_id,
        country_id=country_id,
        include_deleted=include_deleted,
        created_from=created_from,
        created_to=created_to,
    )
    rows, total = BranchWarehouseService(db).list_warehouses(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[WarehouseResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get("/warehouses/summary", response_model=ApiResponse[WarehouseSummary])
def warehouse_summary(
    scope: WarehouseViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseSummary]:
    summary = BranchWarehouseService(db).warehouse_summary(
        firm_scope=scope.firm_id,
        filters=WarehouseListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.post(
    "/warehouses",
    response_model=ApiResponse[WarehouseResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_warehouse(
    data: WarehouseCreate,
    scope: WarehouseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseResponse]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when creating a warehouse.")
    row = BranchWarehouseService(db).create_warehouse(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=WarehouseResponse.model_validate(row))


@router.post(
    "/warehouses/import",
    response_model=ApiResponse[list[WarehouseResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_warehouses(
    data: WarehouseImportRequest,
    scope: BranchWarehouseImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[WarehouseResponse]]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing warehouses.")
    service = BranchWarehouseService(db)
    rows = [
        service.create_warehouse(record, firm_id=scope.firm_id, actor_id=scope.actor_id)
        for record in data.records
    ]
    return ApiResponse(data=[WarehouseResponse.model_validate(row) for row in rows])


@router.get("/warehouses/{warehouse_id}", response_model=ApiResponse[WarehouseResponse])
def get_warehouse(
    warehouse_id: UUID,
    scope: WarehouseViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseResponse]:
    row = BranchWarehouseService(db).get_warehouse(
        warehouse_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(data=WarehouseResponse.model_validate(row))


@router.put("/warehouses/{warehouse_id}", response_model=ApiResponse[WarehouseResponse])
def update_warehouse(
    warehouse_id: UUID,
    data: WarehouseUpdate,
    scope: WarehouseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseResponse]:
    row = BranchWarehouseService(db).update_warehouse(
        warehouse_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=WarehouseResponse.model_validate(row))


@router.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(
    warehouse_id: UUID,
    scope: WarehouseDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    BranchWarehouseService(db).delete_warehouse(
        warehouse_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/warehouses/{warehouse_id}/restore",
    response_model=ApiResponse[WarehouseResponse],
)
def restore_warehouse(
    warehouse_id: UUID,
    scope: WarehouseRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseResponse]:
    row = BranchWarehouseService(db).restore_warehouse(
        warehouse_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=WarehouseResponse.model_validate(row))


@router.post(
    "/warehouses/{warehouse_id}/duplicate",
    response_model=ApiResponse[WarehouseResponse],
)
def duplicate_warehouse(
    warehouse_id: UUID,
    scope: WarehouseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseResponse]:
    row = BranchWarehouseService(db).duplicate_warehouse(
        warehouse_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=WarehouseResponse.model_validate(row))


@router.post("/warehouses/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_warehouses(
    data: BulkIdsRequest,
    scope: WarehouseDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = BranchWarehouseService(db).bulk_delete_warehouses(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/warehouses/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_warehouses(
    data: BulkIdsRequest,
    scope: WarehouseRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = BranchWarehouseService(db).bulk_restore_warehouses(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/warehouses/bulk-status", response_model=ApiResponse[dict[str, int]])
def bulk_warehouse_status(
    data: BulkWarehouseStatusRequest,
    scope: WarehouseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = BranchWarehouseService(db).bulk_warehouse_status(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.get("/warehouses/export")
def export_warehouses(
    scope: BranchWarehouseExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Code", "Name", "Branch ID", "Status", "Capacity", "Capacity Unit"]
    )
    page = 1
    service = BranchWarehouseService(db)
    while True:
        rows, _ = service.list_warehouses(
            firm_scope=scope.firm_id,
            filters=WarehouseListFilters(),
            page=page,
            page_size=1000,
            search=search,
            sort_by="code",
            descending=False,
        )
        for row in rows:
            writer.writerow(
                [
                    row.code,
                    row.name,
                    str(row.branch_id),
                    row.status,
                    str(row.capacity or ""),
                    row.capacity_unit or "",
                ]
            )
        if len(rows) < 1000:
            break
        page += 1
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="warehouses.csv"'},
    )


@router.get(
    "/warehouses/{warehouse_id}/storage-nodes",
    response_model=ApiResponse[list[StorageNodeResponse]],
)
def list_storage_nodes(
    warehouse_id: UUID,
    scope: WarehouseViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StorageNodeResponse]]:
    rows = BranchWarehouseService(db).list_storage_nodes(
        warehouse_id=warehouse_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(data=[StorageNodeResponse.model_validate(item) for item in rows])


@router.post(
    "/warehouses/storage-nodes",
    response_model=ApiResponse[StorageNodeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_storage_node(
    data: StorageNodeCreate,
    scope: StorageManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StorageNodeResponse]:
    row = BranchWarehouseService(db).create_storage_node(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=StorageNodeResponse.model_validate(row))


@router.put(
    "/warehouses/storage-nodes/{storage_node_id}",
    response_model=ApiResponse[StorageNodeResponse],
)
def update_storage_node(
    storage_node_id: UUID,
    data: StorageNodeUpdate,
    scope: StorageManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StorageNodeResponse]:
    row = BranchWarehouseService(db).update_storage_node(
        storage_node_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=StorageNodeResponse.model_validate(row))


@router.delete(
    "/warehouses/storage-nodes/{storage_node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_storage_node(
    storage_node_id: UUID,
    scope: StorageManageScope,
    db: Session = Depends(get_db),
) -> Response:
    BranchWarehouseService(db).delete_storage_node(
        storage_node_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/branch-types", response_model=ApiResponse[list[BranchTypeResponse]])
def list_branch_types(
    scope: BranchViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[BranchTypeResponse]]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for branch types.")
    rows = BranchWarehouseService(db).list_branch_types(
        firm_id=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(data=[BranchTypeResponse.model_validate(item) for item in rows])


@router.post(
    "/branch-types",
    response_model=ApiResponse[BranchTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_branch_type(
    data: BranchTypeWrite,
    scope: BranchUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchTypeResponse]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for branch types.")
    row = BranchWarehouseService(db).create_branch_type(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=BranchTypeResponse.model_validate(row))


@router.put(
    "/branch-types/{branch_type_id}", response_model=ApiResponse[BranchTypeResponse]
)
def update_branch_type(
    branch_type_id: UUID,
    data: BranchTypeWrite,
    scope: BranchUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BranchTypeResponse]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for branch types.")
    row = BranchWarehouseService(db).update_branch_type(
        branch_type_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=BranchTypeResponse.model_validate(row))


@router.delete("/branch-types/{branch_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch_type(
    branch_type_id: UUID,
    scope: BranchDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for branch types.")
    BranchWarehouseService(db).delete_branch_type(
        branch_type_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/warehouse-types", response_model=ApiResponse[list[WarehouseTypeResponse]])
def list_warehouse_types(
    scope: WarehouseViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[WarehouseTypeResponse]]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for warehouse types.")
    rows = BranchWarehouseService(db).list_warehouse_types(
        firm_id=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(
        data=[WarehouseTypeResponse.model_validate(item) for item in rows]
    )


@router.post(
    "/warehouse-types",
    response_model=ApiResponse[WarehouseTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_warehouse_type(
    data: WarehouseTypeWrite,
    scope: WarehouseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseTypeResponse]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for warehouse types.")
    row = BranchWarehouseService(db).create_warehouse_type(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=WarehouseTypeResponse.model_validate(row))


@router.put(
    "/warehouse-types/{warehouse_type_id}",
    response_model=ApiResponse[WarehouseTypeResponse],
)
def update_warehouse_type(
    warehouse_type_id: UUID,
    data: WarehouseTypeWrite,
    scope: WarehouseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[WarehouseTypeResponse]:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for warehouse types.")
    row = BranchWarehouseService(db).update_warehouse_type(
        warehouse_type_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=WarehouseTypeResponse.model_validate(row))


@router.delete(
    "/warehouse-types/{warehouse_type_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_warehouse_type(
    warehouse_type_id: UUID,
    scope: WarehouseDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for warehouse types.")
    BranchWarehouseService(db).delete_warehouse_type(
        warehouse_type_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class BranchWarehouseSettingsResponse(BranchWarehouseSchema):
    """Report which branch-warehouse capabilities this deployment actually has.

    Every flag here was hardcoded ``True``, including five capabilities with no
    implementation anywhere in the backend. A client that trusts this response
    offers its users features that cannot work, so each flag now states the
    truth and must be flipped by the change that builds the capability.
    """

    stock_ledger_ready: bool = True
    inventory_ready: bool = True
    batch_tracking_ready: bool = True
    serial_number_ready: bool = True
    expiry_ready: bool = True
    # No transfer service or endpoint exists: TRANSFER_IN/TRANSFER_OUT are enum
    # members and `in_transit_quantity` is an unused column.
    stock_transfer_ready: bool = False
    inter_branch_transfer_ready: bool = False
    purchase_receipt_ready: bool = True
    sales_dispatch_ready: bool = True
    barcode_ready: bool = True
    qr_ready: bool = True
    # No RFID, IoT or warehouse-automation code exists in the backend.
    rfid_ready: bool = False
    iot_ready: bool = False
    warehouse_automation_ready: bool = False


@router.get(
    "/branch-warehouse/settings",
    response_model=ApiResponse[BranchWarehouseSettingsResponse],
)
def get_settings(
    scope: BranchViewScope,
) -> ApiResponse[BranchWarehouseSettingsResponse]:
    _ = scope
    return ApiResponse(data=BranchWarehouseSettingsResponse())
