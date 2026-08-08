"""Firm-scoped REST endpoints for goods receipt notes."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.firms.models import Firm
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
from app.identity.models import UserFirm

router = APIRouter(
    prefix="/api/v1/goods-receipts",
    tags=["Goods Receipts"],
    responses=STANDARD_ERROR_RESPONSES,
)


class GoodsReceiptScope:
    """Carry the authenticated principal and resolved firm scope."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Goods receipt operations require a user principal.")
        return self.principal.subject


class ActionReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def goods_receipt_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> GoodsReceiptScope:
    if "platform_admin" in principal.roles:
        if x_firm_id is None:
            raise AuthorizationError("X-Firm-ID is required for firm-owned resources.")
        firm = db.scalar(
            select(Firm.id).where(
                Firm.id == x_firm_id,
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        if firm is None:
            raise AuthorizationError("The selected firm is inactive or unavailable.")
        return GoodsReceiptScope(principal=principal, firm_id=x_firm_id)
    if not isinstance(principal.subject, UUID) or x_firm_id is None:
        raise AuthorizationError("An authorized active firm is required.")
    membership = db.scalar(
        select(UserFirm.id)
        .join(Firm, Firm.id == UserFirm.firm_id)
        .where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == x_firm_id,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return GoodsReceiptScope(principal=principal, firm_id=x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[GoodsReceiptScope, Depends(goods_receipt_scope)],
    ) -> GoodsReceiptScope:
        return scope

    return Depends(dependency)


GoodsReceiptViewScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_VIEW")]
GoodsReceiptCreateScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_CREATE")]
GoodsReceiptUpdateScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_UPDATE")]
GoodsReceiptCancelScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_CANCEL")]
GoodsReceiptCloseScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_APPROVE")]
GoodsReceiptImportScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_IMPORT")]
GoodsReceiptExportScope = Annotated[GoodsReceiptScope, _permission("PURCHASE_EXPORT")]


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
    page: int = 1,
    page_size: int = 20,
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
    service = GoodsReceiptService(db)
    row = service.create_receipt(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.receipt_response(row))


@router.put("/{receipt_id}", response_model=ApiResponse[GoodsReceiptResponse])
def update_goods_receipt(
    receipt_id: UUID,
    data: GoodsReceiptUpdate,
    scope: GoodsReceiptUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    service = GoodsReceiptService(db)
    row = service.update_receipt(
        receipt_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.receipt_response(row))


@router.post("/{receipt_id}/complete", response_model=ApiResponse[GoodsReceiptResponse])
def complete_goods_receipt(
    receipt_id: UUID,
    scope: GoodsReceiptCloseScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
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
    db: Session = Depends(get_db),
) -> ApiResponse[GoodsReceiptResponse]:
    service = GoodsReceiptService(db)
    return ApiResponse(
        data=service.receipt_response(
            service.get_receipt(receipt_id, firm_scope=scope.firm_id)
        )
    )


@router.get(
    "/{receipt_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def goods_receipt_history(
    receipt_id: UUID,
    scope: GoodsReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
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
    service = GoodsReceiptService(db)
    rows = service.partially_received_purchase_orders(firm_scope=scope.firm_id)
    return ApiResponse(data=rows)


@router.get("/export")
def export_goods_receipts(
    scope: GoodsReceiptExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_content = GoodsReceiptService(db).export_receipts_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=goods_receipts.csv"},
    )


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
