"""Firm-scoped REST endpoints for enterprise purchase returns."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile, status
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
from app.identity.models import UserFirm
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnImportRequest,
    PurchaseReturnListFilters,
    PurchaseReturnReconciliationRecord,
    PurchaseReturnRegisterRecord,
    PurchaseReturnResponse,
    PurchaseReturnStatus,
    PurchaseReturnSummary,
    PurchaseReturnVendorOutstandingRecord,
)
from app.purchase_return.services import PurchaseReturnService

router = APIRouter(
    prefix="/api/v1/purchase-returns",
    tags=["Purchase Returns"],
    responses=STANDARD_ERROR_RESPONSES,
)


class PurchaseReturnScope:
    """Carry principal and firm scope for return handlers."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Purchase return operations require a user principal.")
        return self.principal.subject


class ActionReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def purchase_return_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> PurchaseReturnScope:
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
        return PurchaseReturnScope(principal=principal, firm_id=x_firm_id)
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
    return PurchaseReturnScope(principal=principal, firm_id=x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[PurchaseReturnScope, Depends(purchase_return_scope)],
    ) -> PurchaseReturnScope:
        return scope

    return Depends(dependency)


PurchaseReturnViewScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_VIEW")]
PurchaseReturnCreateScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_CREATE")]
PurchaseReturnUpdateScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_UPDATE")]
PurchaseReturnApproveScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_APPROVE")]
PurchaseReturnCancelScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_CANCEL")]
PurchaseReturnExportScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_EXPORT")]
PurchaseReturnImportScope = Annotated[PurchaseReturnScope, _permission("PURCHASE_IMPORT")]


def _filters(
    *,
    vendor_id: UUID | None,
    branch_id: UUID | None,
    status_value: PurchaseReturnStatus | None,
    return_from: date | None,
    return_to: date | None,
    warehouse_id: UUID | None,
    include_deleted: bool,
) -> PurchaseReturnListFilters:
    try:
        return PurchaseReturnListFilters.model_validate(
            {
                "vendor_id": vendor_id,
                "branch_id": branch_id,
                "status": status_value,
                "return_from": return_from,
                "return_to": return_to,
                "warehouse_id": warehouse_id,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[PurchaseReturnResponse])
def list_purchase_returns(
    scope: PurchaseReturnViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "return_number", "return_date", "warehouse_id", "grand_total", "status", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    vendor_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    status_value: Annotated[PurchaseReturnStatus | None, Query(alias="status")] = None,
    return_from: date | None = None,
    return_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseReturnResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    service = PurchaseReturnService(db)
    rows, total = service.list_returns(
        firm_scope=scope.firm_id,
        filters=_filters(
            vendor_id=vendor_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            status_value=status_value,
            return_from=return_from,
            return_to=return_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.return_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[PurchaseReturnSummary])
def purchase_return_summary(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnSummary]:
    return ApiResponse(data=PurchaseReturnService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "", response_model=ApiResponse[PurchaseReturnResponse], status_code=status.HTTP_201_CREATED
)
def create_purchase_return(
    data: PurchaseReturnCreate,
    scope: PurchaseReturnCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    row = service.create_return(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.return_response(row))


@router.put("/{return_id}", response_model=ApiResponse[PurchaseReturnResponse])
def update_purchase_return(
    return_id: UUID,
    data: PurchaseReturnCreate,
    scope: PurchaseReturnUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    row = service.update_return(return_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/approve", response_model=ApiResponse[PurchaseReturnResponse])
def approve_purchase_return(
    return_id: UUID,
    scope: PurchaseReturnApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    row = service.approve_return(return_id, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/cancel", response_model=ApiResponse[PurchaseReturnResponse])
def cancel_purchase_return(
    return_id: UUID,
    data: ActionReasonRequest,
    scope: PurchaseReturnCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    row = service.cancel_return(
        return_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/close", response_model=ApiResponse[PurchaseReturnResponse])
def close_purchase_return(
    return_id: UUID,
    data: ActionReasonRequest,
    scope: PurchaseReturnApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    row = service.close_return(
        return_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/complete", response_model=ApiResponse[PurchaseReturnResponse])
def complete_purchase_return(
    return_id: UUID,
    scope: PurchaseReturnApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    row = service.complete_return(return_id, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.return_response(row))


@router.get("/{return_id}", response_model=ApiResponse[PurchaseReturnResponse])
def get_purchase_return(
    return_id: UUID,
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseReturnResponse]:
    service = PurchaseReturnService(db)
    return ApiResponse(data=service.return_response(service.get_return(return_id, firm_scope=scope.firm_id)))


@router.get("/{return_id}/history", response_model=ApiResponse[list[DocumentLifecycleEventResponse]])
def purchase_return_history(
    return_id: UUID,
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    rows = PurchaseReturnService(db).timeline(
        return_id=return_id, firm_scope=scope.firm_id, page=1, page_size=200
    )[0]
    return ApiResponse(data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows])


@router.get("/reports/register", response_model=ApiResponse[list[PurchaseReturnRegisterRecord]])
def purchase_return_register(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseReturnRegisterRecord]]:
    return ApiResponse(data=PurchaseReturnService(db).register_report(firm_scope=scope.firm_id))


@router.get("/reports/by-vendor", response_model=ApiResponse[list[PurchaseReturnVendorOutstandingRecord]])
def returns_by_vendor(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseReturnVendorOutstandingRecord]]:
    return ApiResponse(data=PurchaseReturnService(db).outstanding_report(firm_scope=scope.firm_id))


@router.get("/reports/by-product", response_model=ApiResponse[list[PurchaseReturnReconciliationRecord]])
def returns_by_product(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseReturnReconciliationRecord]]:
    return ApiResponse(data=PurchaseReturnService(db).reconciliation_report(firm_scope=scope.firm_id))


@router.get("/reports/damaged", response_model=ApiResponse[list[PurchaseReturnReconciliationRecord]])
def damaged_goods_report(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseReturnReconciliationRecord]]:
    rows = [
        item
        for item in PurchaseReturnService(db).reconciliation_report(firm_scope=scope.firm_id)
        if item.current_return_quantity > 0
    ]
    return ApiResponse(data=rows)


@router.get("/reports/expired", response_model=ApiResponse[list[PurchaseReturnReconciliationRecord]])
def expired_goods_report(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseReturnReconciliationRecord]]:
    rows = [
        item
        for item in PurchaseReturnService(db).reconciliation_report(firm_scope=scope.firm_id)
        if item.pending_quantity >= 0
    ]
    return ApiResponse(data=rows)


@router.get("/reports/supplier-analysis", response_model=ApiResponse[list[PurchaseReturnVendorOutstandingRecord]])
def supplier_return_analysis(
    scope: PurchaseReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseReturnVendorOutstandingRecord]]:
    return ApiResponse(data=PurchaseReturnService(db).outstanding_report(firm_scope=scope.firm_id))


@router.get("/export")
def export_purchase_returns(
    scope: PurchaseReturnExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_content = PurchaseReturnService(db).export_returns_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=purchase_returns.csv"},
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[PurchaseReturnResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_purchase_returns(
    scope: PurchaseReturnImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[PurchaseReturnResponse]]:
    if format != "json":
        raise ValidationError("Only JSON import is supported for purchase returns.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = PurchaseReturnService(db)
    rows = service.import_returns(
        PurchaseReturnImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.return_response(item) for item in rows])
