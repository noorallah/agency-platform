"""Firm-scoped REST endpoints for enterprise purchase orders."""

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
from app.purchase.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderHistoryResponse,
    PurchaseOrderImportRequest,
    PurchaseOrderListFilters,
    PurchaseOrderResponse,
    PurchaseOrderStatus,
    PurchaseOrderUpdate,
    PurchaseSummary,
    PurchaseType,
)
from app.purchase.services import PurchaseService

router = APIRouter(
    prefix="/api/v1/purchases",
    tags=["Purchases"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Optional reason payload for cancellation/closure actions."""

    reason: str | None = Field(default=None, max_length=500)


PurchaseViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")]
PurchaseCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CREATE")
]
PurchaseUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_UPDATE")
]
PurchaseDeleteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_DELETE")
]
PurchaseRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_RESTORE")
]
PurchaseImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_IMPORT")
]
PurchaseExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_EXPORT")
]
PurchaseApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]
PurchaseCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CANCEL")
]


def _filters(
    *,
    vendor_id: UUID | None,
    status_value: PurchaseOrderStatus | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    buyer_id: UUID | None,
    purchase_type: PurchaseType | None,
    created_from: date | None,
    created_to: date | None,
    include_deleted: bool,
) -> PurchaseOrderListFilters:
    """Collect the purchase order list filters from the query string."""
    try:
        return PurchaseOrderListFilters.model_validate(
            {
                "vendor_id": vendor_id,
                "status": status_value,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "buyer_id": buyer_id,
                "purchase_type": purchase_type,
                "created_from": created_from,
                "created_to": created_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[PurchaseOrderResponse])
def list_purchase_orders(
    scope: PurchaseViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "po_number", "purchase_date", "status", "grand_total", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    vendor_id: UUID | None = None,
    status_value: Annotated[PurchaseOrderStatus | None, Query(alias="status")] = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    buyer_id: UUID | None = None,
    purchase_type: PurchaseType | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseOrderResponse]:
    """List purchase orders."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = PurchaseService(db).list_orders(
        firm_scope=scope.firm_id,
        filters=_filters(
            vendor_id=vendor_id,
            status_value=status_value,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            buyer_id=buyer_id,
            purchase_type=purchase_type,
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
    service = PurchaseService(db)
    return PaginatedResponse(
        data=[service.order_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[PurchaseSummary])
def purchase_summary(
    scope: PurchaseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseSummary]:
    """Purchase summary."""
    return ApiResponse(data=PurchaseService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "",
    response_model=ApiResponse[PurchaseOrderResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(
    data: PurchaseOrderCreate,
    scope: PurchaseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Create purchase order."""
    service = PurchaseService(db)
    row = service.create_order(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.order_response(row))


@router.post(
    "/import",
    response_model=ApiResponse[list[PurchaseOrderResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_purchase_orders(
    scope: PurchaseImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json", "csv", "xlsx"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[PurchaseOrderResponse]]:
    """Create several purchase orders from an upload or JSON body."""
    service = PurchaseService(db)
    if format == "json":
        if payload is None:
            raise ValidationError("payload is required for JSON import.")
        rows = service.import_orders(
            PurchaseOrderImportRequest.model_validate_json(payload),
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
        return ApiResponse(data=[service.order_response(item) for item in rows])
    if file is None:
        raise ValidationError("file is required for CSV/XLSX import.")
    content = await file.read()
    rows = (
        service.import_orders_csv(
            content.decode("utf-8"), firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
        if format == "csv"
        else service.import_orders_xlsx(
            content, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
    )
    return ApiResponse(data=[service.order_response(item) for item in rows])


@router.get("/export")
def export_purchase_orders(
    scope: PurchaseExportScope,
    format: Literal["csv", "xlsx"] = "csv",
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export purchase orders."""
    service = PurchaseService(db)
    if format == "xlsx":
        content = service.export_orders_xlsx(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="purchase_orders.xlsx"'
            },
        )
    text = service.export_orders_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="purchase_orders.csv"'},
    )


@router.get("/{order_id}", response_model=ApiResponse[PurchaseOrderResponse])
def get_purchase_order(
    order_id: UUID,
    scope: PurchaseViewScope,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Return purchase order."""
    service = PurchaseService(db)
    row = service.get_order(
        order_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    set_etag(response, row)
    return ApiResponse(data=service.order_response(row))


@router.put("/{order_id}", response_model=ApiResponse[PurchaseOrderResponse])
def update_purchase_order(
    order_id: UUID,
    data: PurchaseOrderUpdate,
    scope: PurchaseUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[PurchaseOrderResponse]:
    """Change purchase order."""
    service = PurchaseService(db)
    assert_version(
        service.get_order(order_id, firm_scope=scope.firm_id).version, expected_version
    )
    row = service.update_order(
        order_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.order_response(row))


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    order_id: UUID,
    scope: PurchaseDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete purchase order."""
    PurchaseService(db).delete_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{order_id}/restore", response_model=ApiResponse[PurchaseOrderResponse])
def restore_purchase_order(
    order_id: UUID,
    scope: PurchaseRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Restore purchase order."""
    service = PurchaseService(db)
    row = service.restore_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/submit", response_model=ApiResponse[PurchaseOrderResponse])
def submit_purchase_order(
    order_id: UUID,
    scope: PurchaseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Send a draft purchase order for approval."""
    service = PurchaseService(db)
    row = service.submit_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/approve", response_model=ApiResponse[PurchaseOrderResponse])
def approve_purchase_order(
    order_id: UUID,
    scope: PurchaseApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Approve a submitted purchase order.

    Takes `PURCHASE_APPROVE`, deliberately a different code from the
    `PURCHASE_UPDATE` that submitting needs: the point of the two steps is
    that the person who raises an order need not be the person who commits
    the firm to it.
    """
    service = PurchaseService(db)
    row = service.approve_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/cancel", response_model=ApiResponse[PurchaseOrderResponse])
def cancel_purchase_order(
    order_id: UUID,
    request: ActionReasonRequest,
    scope: PurchaseCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Cancel purchase order."""
    service = PurchaseService(db)
    row = service.cancel_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=request.reason,
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/close", response_model=ApiResponse[PurchaseOrderResponse])
def close_purchase_order(
    order_id: UUID,
    request: ActionReasonRequest,
    scope: PurchaseApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Close purchase order."""
    service = PurchaseService(db)
    row = service.close_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=request.reason,
    )
    return ApiResponse(data=service.order_response(row))


@router.get(
    "/{order_id}/history",
    response_model=ApiResponse[list[PurchaseOrderHistoryResponse]],
)
def purchase_order_history(
    order_id: UUID,
    scope: PurchaseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseOrderHistoryResponse]]:
    """Purchase order history."""
    rows = PurchaseService(db).order_history(
        order_id=order_id, firm_scope=scope.firm_id
    )
    return ApiResponse(
        data=[PurchaseOrderHistoryResponse.model_validate(item) for item in rows]
    )
