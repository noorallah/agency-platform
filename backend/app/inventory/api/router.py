"""Firm-scoped REST endpoints for the enterprise inventory foundation."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryCreate,
    InventoryListFilters,
    InventoryTransactionListFilters,
    OpeningStockBatchCreate,
    OpeningStockBatchListFilters,
    OpeningStockImportRequest,
    OpeningStockUpdate,
    StockLedgerListFilters,
)
from app.inventory.schemas.inventory import (
    InventoryLocationSummary,
    InventoryResponse,
    InventorySummary,
    InventoryTransactionResponse,
    InventoryUpdate,
    OpeningStockBatchResponse,
    StockLedgerResponse,
)
from app.inventory.services import InventoryService

router = APIRouter(
    prefix="/api/v1/inventory",
    tags=["Inventory"],
    responses=STANDARD_ERROR_RESPONSES,
)


InventoryViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_VIEW")
]
OpeningStockCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("OPENING_STOCK_CREATE")
]
OpeningStockUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("OPENING_STOCK_UPDATE")
]
InventoryLedgerViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_LEDGER_VIEW")
]
InventoryExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_EXPORT")
]
InventoryImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_IMPORT")
]
InventoryTransactionViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_TRANSACTION_VIEW")
]
InventoryAdjustScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_ADJUST")
]


@router.get("", response_model=PaginatedResponse[InventoryResponse])
def list_inventory(
    scope: InventoryViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at",
        "updated_at",
        "current_quantity",
        "available_quantity",
        "status",
        "product_code",
    ] = "updated_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: str | None = Query(default=None, alias="status"),
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    product_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    low_stock_only: bool = False,
    out_of_stock_only: bool = False,
    negative_only: bool = False,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[InventoryResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = InventoryListFilters.model_validate(
        {
            "status": status_value,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "storage_node_id": storage_node_id,
            "product_id": product_id,
            "business_profile_id": business_profile_id,
            "low_stock_only": low_stock_only,
            "out_of_stock_only": out_of_stock_only,
            "negative_only": negative_only,
            "include_deleted": include_deleted,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_inventory(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.inventory_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[InventorySummary])
def inventory_summary(
    scope: InventoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[InventorySummary]:
    summary = InventoryService(db).inventory_summary(
        firm_scope=scope.firm_id,
        filters=InventoryListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.get(
    "/summary/by-firm", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_firm(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    return ApiResponse(
        data=InventoryService(db).stock_by_firm(firm_scope=scope.firm_id)
    )


@router.get(
    "/summary/by-branch", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_branch(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    return ApiResponse(
        data=InventoryService(db).stock_by_branch(firm_scope=scope.firm_id)
    )


@router.get(
    "/summary/by-warehouse", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_warehouse(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    return ApiResponse(
        data=InventoryService(db).stock_by_warehouse(firm_scope=scope.firm_id)
    )


@router.post(
    "",
    response_model=ApiResponse[InventoryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_inventory(
    data: InventoryCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryResponse]:
    service = InventoryService(db)
    row = service.create_inventory_record(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.inventory_response(row))


@router.get(
    "/transactions", response_model=PaginatedResponse[InventoryTransactionResponse]
)
def list_transactions(
    scope: InventoryTransactionViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at",
        "transaction_date",
        "transaction_type",
        "reference_number",
        "quantity",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    transaction_type: str | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    product_id: UUID | None = None,
    reference_number: str | None = None,
    reference_type: str | None = None,
    transaction_from: str | None = None,
    transaction_to: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[InventoryTransactionResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = InventoryTransactionListFilters.model_validate(
        {
            "transaction_type": transaction_type,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "storage_node_id": storage_node_id,
            "product_id": product_id,
            "reference_number": reference_number,
            "reference_type": reference_type,
            "transaction_from": transaction_from,
            "transaction_to": transaction_to,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_transactions(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.transaction_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get("/ledger", response_model=PaginatedResponse[StockLedgerResponse])
def list_ledger(
    scope: InventoryLedgerViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at",
        "transaction_date",
        "transaction_type",
        "reference_number",
        "quantity",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    transaction_type: str | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    product_id: UUID | None = None,
    reference_number: str | None = None,
    reference_type: str | None = None,
    transaction_from: str | None = None,
    transaction_to: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[StockLedgerResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = StockLedgerListFilters.model_validate(
        {
            "transaction_type": transaction_type,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "storage_node_id": storage_node_id,
            "product_id": product_id,
            "reference_number": reference_number,
            "reference_type": reference_type,
            "transaction_from": transaction_from,
            "transaction_to": transaction_to,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_ledger(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.ledger_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/opening-stock",
    response_model=ApiResponse[OpeningStockBatchResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_opening_stock(
    data: OpeningStockBatchCreate,
    scope: OpeningStockCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    service = InventoryService(db)
    row = service.create_opening_stock_batch(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.get(
    "/opening-stock", response_model=PaginatedResponse[OpeningStockBatchResponse]
)
def list_opening_stock(
    scope: InventoryViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at", "posting_date", "reference_number", "status"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: str | None = Query(default=None, alias="status"),
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    posting_from: str | None = None,
    posting_to: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[OpeningStockBatchResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = OpeningStockBatchListFilters.model_validate(
        {
            "status": status_value,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "posting_from": posting_from,
            "posting_to": posting_to,
            "include_deleted": include_deleted,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_opening_stock_batches(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.opening_stock_batch_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get(
    "/opening-stock/{batch_id}", response_model=ApiResponse[OpeningStockBatchResponse]
)
def get_opening_stock(
    batch_id: UUID,
    scope: InventoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    service = InventoryService(db)
    row = service.get_opening_stock_batch(
        batch_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.put(
    "/opening-stock/{batch_id}", response_model=ApiResponse[OpeningStockBatchResponse]
)
def update_opening_stock(
    batch_id: UUID,
    data: OpeningStockUpdate,
    scope: OpeningStockUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    service = InventoryService(db)
    row = service.update_opening_stock_batch(
        batch_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.post(
    "/opening-stock/{batch_id}/post",
    response_model=ApiResponse[OpeningStockBatchResponse],
)
def post_opening_stock(
    batch_id: UUID,
    scope: OpeningStockCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    service = InventoryService(db)
    row = service.post_opening_stock_batch(
        batch_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.post(
    "/opening-stock/import",
    response_model=ApiResponse[OpeningStockBatchResponse],
    status_code=status.HTTP_201_CREATED,
)
async def import_opening_stock(
    scope: InventoryImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json", "csv", "xlsx"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    reference_number: Annotated[str | None, Form()] = None,
    posting_date: Annotated[str | None, Form()] = None,
    branch_id: Annotated[UUID | None, Form()] = None,
    warehouse_id: Annotated[UUID | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
    auto_post: Annotated[bool, Form()] = True,
) -> ApiResponse[OpeningStockBatchResponse]:
    service = InventoryService(db)
    if format == "json":
        if payload is None:
            raise ValidationError("payload is required for JSON import.")
        row = service.import_opening_stock_json(
            OpeningStockImportRequest.model_validate_json(payload),
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
        return ApiResponse(data=service.opening_stock_batch_response(row))
    if (
        file is None
        or reference_number is None
        or posting_date is None
        or branch_id is None
        or warehouse_id is None
    ):
        raise ValidationError(
            "file, reference_number, posting_date, branch_id, and warehouse_id are required for CSV/XLSX import."
        )
    try:
        parsed_posting_date = date.fromisoformat(posting_date)
    except ValueError as error:
        raise ValidationError("posting_date must be a valid ISO date.") from error
    content = await file.read()
    if format == "csv":
        row = service.import_opening_stock_csv(
            content.decode("utf-8"),
            reference_number=reference_number,
            posting_date=parsed_posting_date,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            remarks=remarks,
            auto_post=auto_post,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
    else:
        row = service.import_opening_stock_xlsx(
            content,
            reference_number=reference_number,
            posting_date=parsed_posting_date,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            remarks=remarks,
            auto_post=auto_post,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.post(
    "/adjustments",
    response_model=ApiResponse[InventoryTransactionResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_adjustment(
    data: InventoryAdjustmentCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryTransactionResponse]:
    service = InventoryService(db)
    row = service.create_adjustment(
        data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.transaction_response(row))


@router.get("/export")
def export_inventory(
    scope: InventoryExportScope,
    dataset: Literal["inventory", "ledger"] = "inventory",
    format: Literal["csv", "xlsx"] = "csv",
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    service = InventoryService(db)
    if dataset == "ledger":
        if format == "xlsx":
            content = service.export_ledger_xlsx(
                firm_scope=scope.firm_id, search=search
            )
            return StreamingResponse(
                iter([content]),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": 'attachment; filename="stock-ledger.xlsx"'
                },
            )
        text = service.export_ledger_csv(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([text]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="stock-ledger.csv"'},
        )
    if format == "xlsx":
        content = service.export_inventory_xlsx(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="inventory.xlsx"'},
        )
    text = service.export_inventory_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inventory.csv"'},
    )


@router.get("/{inventory_id}", response_model=ApiResponse[InventoryResponse])
def get_inventory(
    inventory_id: UUID,
    scope: InventoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryResponse]:
    service = InventoryService(db)
    row = service.get_inventory_record(
        inventory_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    return ApiResponse(data=service.inventory_response(row))


@router.put("/{inventory_id}", response_model=ApiResponse[InventoryResponse])
def update_inventory(
    inventory_id: UUID,
    data: InventoryUpdate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryResponse]:
    service = InventoryService(db)
    row = service.update_inventory_record(
        inventory_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.inventory_response(row))


@router.delete("/{inventory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory(
    inventory_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> Response:
    row = InventoryService(db).get_inventory_record(
        inventory_id, firm_scope=scope.firm_id
    )
    if any(
        value != 0
        for value in (
            row.current_quantity,
            row.reserved_quantity,
            row.available_quantity,
            row.blocked_quantity,
            row.damaged_quantity,
            row.quarantine_quantity,
            row.in_transit_quantity,
        )
    ):
        raise ValidationError("Inventory with stock balances cannot be deleted.")
    if row.transactions:
        raise ValidationError("Inventory with transaction history cannot be deleted.")
    row.is_deleted = True
    row.deleted_at = utc_now()
    row.deleted_by = scope.actor_id
    row.updated_by = scope.actor_id
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
