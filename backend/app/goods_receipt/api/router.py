"""Firm-scoped REST endpoints for goods receipt notes."""

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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.goods_receipt.schemas import (
    GoodsReceiptCreate,
    GoodsReceiptImportRequest,
    GoodsReceiptLineResponse,
    GoodsReceiptListFilters,
    GoodsReceiptPurchaseOrderReport,
    GoodsReceiptResponse,
    GoodsReceiptStatus,
    GoodsReceiptSummary,
    GoodsReceiptUpdate,
)
from app.goods_receipt.services import GoodsReceiptService

router = APIRouter(
    prefix="/api/v1/goods-receipts",
    tags=["Goods Receipts"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Action Reason Request contract."""

    reason: str | None = Field(default=None, max_length=500)


GoodsReceiptViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")
]
GoodsReceiptCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CREATE")
]
GoodsReceiptUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_UPDATE")
]
GoodsReceiptCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CANCEL")
]
GoodsReceiptCloseScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]
GoodsReceiptImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_IMPORT")
]
GoodsReceiptExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_EXPORT")
]


def _filters(
    *,
    purchase_order_id: UUID | None,
    vendor_id: UUID | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    status_value: GoodsReceiptStatus | None,
    created_from: date | None,
    created_to: date | None,
    include_deleted: bool,
) -> GoodsReceiptListFilters:
    """Collect the goods receipt list filters from the query string."""
    try:
        return GoodsReceiptListFilters.model_validate(
            {
                "purchase_order_id": purchase_order_id,
                "vendor_id": vendor_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "status": status_value,
                "created_from": created_from,
                "created_to": created_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[GoodsReceiptResponse])
def list_goods_receipts(
    scope: GoodsReceiptViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "grn_number", "receipt_date", "status", "created_at", "updated_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    purchase_order_id: UUID | None = None,
    vendor_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    status_value: Annotated[GoodsReceiptStatus | None, Query(alias="status")] = None,
    created_from: date | None = None,
    created_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[GoodsReceiptResponse]:
    """List goods receipts."""
    params = PaginationParams(page=page, page_size=page_size)
    service = GoodsReceiptService(db)
    rows, total = service.list_receipts(
        firm_scope=scope.firm_id,
        filters=_filters(
            purchase_order_id=purchase_order_id,
            vendor_id=vendor_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            status_value=status_value,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.receipt_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[GoodsReceiptSummary])
def goods_receipt_summary(
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptSummary]:
    """Goods receipt summary."""
    return ApiResponse(data=GoodsReceiptService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "",
    response_model=ApiResponse[GoodsReceiptResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_goods_receipt(
    data: GoodsReceiptCreate,
    scope: GoodsReceiptCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    """Create goods receipt."""
    service = GoodsReceiptService(db)
    row = service.create_receipt(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.receipt_response(row))


# Declared above the `/{{id}}` route below on purpose: FastAPI matches in
# declaration order, so that route read "export" as an id and answered 422.
# Unreachable from the day it was written until 2026-08-22.
@router.get("/export")
def export_goods_receipts(
    scope: GoodsReceiptExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export goods receipts."""
    csv_content = GoodsReceiptService(db).export_receipts_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=goods_receipts.csv"},
    )


@router.put("/{receipt_id}", response_model=ApiResponse[GoodsReceiptResponse])
def update_goods_receipt(
    receipt_id: UUID,
    data: GoodsReceiptUpdate,
    scope: GoodsReceiptUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GoodsReceiptResponse]:
    """Change goods receipt."""
    service = GoodsReceiptService(db)
    assert_version(
        service.get_receipt(receipt_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update_receipt(
        receipt_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.receipt_response(row))


@router.post("/{receipt_id}/complete", response_model=ApiResponse[GoodsReceiptResponse])
def complete_goods_receipt(
    receipt_id: UUID,
    scope: GoodsReceiptCloseScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    """Complete goods receipt."""
    service = GoodsReceiptService(db)
    row = service.complete_receipt(
        receipt_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.receipt_response(row))


@router.post("/{receipt_id}/cancel", response_model=ApiResponse[GoodsReceiptResponse])
def cancel_goods_receipt(
    receipt_id: UUID,
    data: ActionReasonRequest,
    scope: GoodsReceiptCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    """Cancel goods receipt."""
    service = GoodsReceiptService(db)
    row = service.cancel_receipt(
        receipt_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.receipt_response(row))


@router.post("/{receipt_id}/close", response_model=ApiResponse[GoodsReceiptResponse])
def close_goods_receipt(
    receipt_id: UUID,
    data: ActionReasonRequest,
    scope: GoodsReceiptCloseScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    """Close goods receipt."""
    service = GoodsReceiptService(db)
    row = service.close_receipt(
        receipt_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.receipt_response(row))


@router.get("/{receipt_id}", response_model=ApiResponse[GoodsReceiptResponse])
def get_goods_receipt(
    receipt_id: UUID,
    scope: GoodsReceiptViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    """Return goods receipt."""
    service = GoodsReceiptService(db)
    row = service.get_receipt(receipt_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.receipt_response(row))


@router.get(
    "/{receipt_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def goods_receipt_history(
    receipt_id: UUID,
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    """Goods receipt history."""
    service = GoodsReceiptService(db)
    rows = service.receipt_history(receipt_id=receipt_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows]
    )


@router.get("/reports/pending", response_model=ApiResponse[list[GoodsReceiptResponse]])
def pending_goods_receipts(
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GoodsReceiptResponse]]:
    """Return goods receipts."""
    service = GoodsReceiptService(db)
    return ApiResponse(
        data=[
            service.receipt_response(item)
            for item in service.pending_receipts(firm_scope=scope.firm_id)
        ]
    )


@router.get(
    "/reports/completed", response_model=ApiResponse[list[GoodsReceiptResponse]]
)
def completed_goods_receipts(
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GoodsReceiptResponse]]:
    """Return goods receipts."""
    service = GoodsReceiptService(db)
    return ApiResponse(
        data=[
            service.receipt_response(item)
            for item in service.completed_receipts(firm_scope=scope.firm_id)
        ]
    )


@router.get(
    "/reports/rejected", response_model=ApiResponse[list[GoodsReceiptLineResponse]]
)
def rejected_goods_receipt_items(
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GoodsReceiptLineResponse]]:
    """Return goods receipt items."""
    service = GoodsReceiptService(db)
    rows = service.rejected_items(firm_scope=scope.firm_id)
    return ApiResponse(
        data=[GoodsReceiptLineResponse.model_validate(item) for item in rows]
    )


@router.get(
    "/reports/damaged", response_model=ApiResponse[list[GoodsReceiptLineResponse]]
)
def damaged_goods_receipt_items(
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GoodsReceiptLineResponse]]:
    """Return goods receipt items."""
    service = GoodsReceiptService(db)
    rows = service.damaged_items(firm_scope=scope.firm_id)
    return ApiResponse(
        data=[GoodsReceiptLineResponse.model_validate(item) for item in rows]
    )


@router.get(
    "/reports/partial",
    response_model=ApiResponse[list[GoodsReceiptPurchaseOrderReport]],
)
def partial_purchase_orders(
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GoodsReceiptPurchaseOrderReport]]:
    """Partial purchase orders."""
    service = GoodsReceiptService(db)
    rows = service.partially_received_purchase_orders(firm_scope=scope.firm_id)
    return ApiResponse(data=rows)


@router.post(
    "/import",
    response_model=ApiResponse[list[GoodsReceiptResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_goods_receipts(
    scope: GoodsReceiptImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[GoodsReceiptResponse]]:
    """Import goods receipts."""
    if format != "json":
        raise ValidationError("Only JSON import is supported for goods receipts.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = GoodsReceiptService(db)
    rows = service.import_receipts(
        GoodsReceiptImportRequest.model_validate_json(payload).records,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.receipt_response(item) for item in rows])
