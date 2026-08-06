"""Firm-scoped REST endpoints for enterprise purchase invoices."""

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
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceImportRequest,
    PurchaseInvoiceListFilters,
    PurchaseInvoiceReconciliationRecord,
    PurchaseInvoiceRegisterRecord,
    PurchaseInvoiceResponse,
    PurchaseInvoiceStatus,
    PurchaseInvoiceSummary,
    PurchaseInvoiceVendorOutstandingRecord,
)
from app.purchase_invoice.services import PurchaseInvoiceService

router = APIRouter(
    prefix="/api/v1/purchase-invoices",
    tags=["Purchase Invoices"],
    responses=STANDARD_ERROR_RESPONSES,
)


class PurchaseInvoiceScope:
    """Carry principal and firm scope for invoice handlers."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Purchase invoice operations require a user principal.")
        return self.principal.subject


class ActionReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def purchase_invoice_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> PurchaseInvoiceScope:
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
        return PurchaseInvoiceScope(principal=principal, firm_id=x_firm_id)
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
    return PurchaseInvoiceScope(principal=principal, firm_id=x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[PurchaseInvoiceScope, Depends(purchase_invoice_scope)],
    ) -> PurchaseInvoiceScope:
        return scope

    return Depends(dependency)


PurchaseInvoiceViewScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_VIEW")]
PurchaseInvoiceCreateScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_CREATE")]
PurchaseInvoiceUpdateScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_UPDATE")]
PurchaseInvoiceApproveScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_APPROVE")]
PurchaseInvoiceCancelScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_CANCEL")]
PurchaseInvoiceExportScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_EXPORT")]
PurchaseInvoiceImportScope = Annotated[PurchaseInvoiceScope, _permission("PURCHASE_IMPORT")]


def _filters(
    *,
    vendor_id: UUID | None,
    branch_id: UUID | None,
    status_value: PurchaseInvoiceStatus | None,
    invoice_from: date | None,
    invoice_to: date | None,
    due_from: date | None,
    due_to: date | None,
    include_deleted: bool,
) -> PurchaseInvoiceListFilters:
    try:
        return PurchaseInvoiceListFilters.model_validate(
            {
                "vendor_id": vendor_id,
                "branch_id": branch_id,
                "status": status_value,
                "invoice_from": invoice_from,
                "invoice_to": invoice_to,
                "due_from": due_from,
                "due_to": due_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[PurchaseInvoiceResponse])
def list_purchase_invoices(
    scope: PurchaseInvoiceViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "invoice_number", "invoice_date", "due_date", "grand_total", "status", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    vendor_id: UUID | None = None,
    branch_id: UUID | None = None,
    status_value: Annotated[PurchaseInvoiceStatus | None, Query(alias="status")] = None,
    invoice_from: date | None = None,
    invoice_to: date | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseInvoiceResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    service = PurchaseInvoiceService(db)
    rows, total = service.list_invoices(
        firm_scope=scope.firm_id,
        filters=_filters(
            vendor_id=vendor_id,
            branch_id=branch_id,
            status_value=status_value,
            invoice_from=invoice_from,
            invoice_to=invoice_to,
            due_from=due_from,
            due_to=due_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.invoice_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[PurchaseInvoiceSummary])
def purchase_invoice_summary(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceSummary]:
    return ApiResponse(data=PurchaseInvoiceService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "", response_model=ApiResponse[PurchaseInvoiceResponse], status_code=status.HTTP_201_CREATED
)
def create_purchase_invoice(
    data: PurchaseInvoiceCreate,
    scope: PurchaseInvoiceCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    service = PurchaseInvoiceService(db)
    row = service.create_invoice(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.invoice_response(row))


@router.put("/{invoice_id}", response_model=ApiResponse[PurchaseInvoiceResponse])
def update_purchase_invoice(
    invoice_id: UUID,
    data: PurchaseInvoiceCreate,
    scope: PurchaseInvoiceUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    service = PurchaseInvoiceService(db)
    row = service.update_invoice(invoice_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.invoice_response(row))


@router.post("/{invoice_id}/approve", response_model=ApiResponse[PurchaseInvoiceResponse])
def approve_purchase_invoice(
    invoice_id: UUID,
    scope: PurchaseInvoiceApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    service = PurchaseInvoiceService(db)
    row = service.approve_invoice(invoice_id, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.invoice_response(row))


@router.post("/{invoice_id}/cancel", response_model=ApiResponse[PurchaseInvoiceResponse])
def cancel_purchase_invoice(
    invoice_id: UUID,
    data: ActionReasonRequest,
    scope: PurchaseInvoiceCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    service = PurchaseInvoiceService(db)
    row = service.cancel_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.invoice_response(row))


@router.post("/{invoice_id}/close", response_model=ApiResponse[PurchaseInvoiceResponse])
def close_purchase_invoice(
    invoice_id: UUID,
    data: ActionReasonRequest,
    scope: PurchaseInvoiceApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    service = PurchaseInvoiceService(db)
    row = service.close_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.invoice_response(row))


@router.get("/{invoice_id}", response_model=ApiResponse[PurchaseInvoiceResponse])
def get_purchase_invoice(
    invoice_id: UUID,
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    service = PurchaseInvoiceService(db)
    return ApiResponse(data=service.invoice_response(service.get_invoice(invoice_id, firm_scope=scope.firm_id)))


@router.get("/{invoice_id}/history", response_model=ApiResponse[list[DocumentLifecycleEventResponse]])
def purchase_invoice_history(
    invoice_id: UUID,
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    rows = PurchaseInvoiceService(db).timeline(
        invoice_id=invoice_id, firm_scope=scope.firm_id, page=1, page_size=200
    )[0]
    return ApiResponse(data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows])


@router.get("/reports/pending", response_model=ApiResponse[list[PurchaseInvoiceResponse]])
def pending_purchase_invoices(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceResponse]]:
    service = PurchaseInvoiceService(db)
    return ApiResponse(data=[service.invoice_response(item) for item in service.pending_invoices(firm_scope=scope.firm_id)])


@router.get("/reports/overdue", response_model=ApiResponse[list[PurchaseInvoiceResponse]])
def overdue_purchase_invoices(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceResponse]]:
    service = PurchaseInvoiceService(db)
    return ApiResponse(data=[service.invoice_response(item) for item in service.overdue_invoices(firm_scope=scope.firm_id)])


@router.get("/reports/register", response_model=ApiResponse[list[PurchaseInvoiceRegisterRecord]])
def purchase_invoice_register(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceRegisterRecord]]:
    return ApiResponse(data=PurchaseInvoiceService(db).register_report(firm_scope=scope.firm_id))


@router.get("/reports/outstanding", response_model=ApiResponse[list[PurchaseInvoiceVendorOutstandingRecord]])
def vendor_outstanding_placeholder(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceVendorOutstandingRecord]]:
    return ApiResponse(data=PurchaseInvoiceService(db).outstanding_report(firm_scope=scope.firm_id))


@router.get("/reports/reconciliation", response_model=ApiResponse[list[PurchaseInvoiceReconciliationRecord]])
def invoice_reconciliation_report(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceReconciliationRecord]]:
    return ApiResponse(data=PurchaseInvoiceService(db).reconciliation_report(firm_scope=scope.firm_id))


@router.get("/export")
def export_purchase_invoices(
    scope: PurchaseInvoiceExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_content = PurchaseInvoiceService(db).export_invoices_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=purchase_invoices.csv"},
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[PurchaseInvoiceResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_purchase_invoices(
    scope: PurchaseInvoiceImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[PurchaseInvoiceResponse]]:
    if format != "json":
        raise ValidationError("Only JSON import is supported for purchase invoices.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = PurchaseInvoiceService(db)
    rows = service.import_invoices(
        PurchaseInvoiceImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.invoice_response(item) for item in rows])

