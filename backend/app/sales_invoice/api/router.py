"""Firm-scoped REST endpoints for enterprise sales invoices."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import PaginatedResponse
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceCustomerOutstandingRecord,
    SalesInvoiceImportRequest,
    SalesInvoiceListFilters,
    SalesInvoiceReconciliationRecord,
    SalesInvoiceRegisterRecord,
    SalesInvoiceResponse,
    SalesInvoiceStatus,
    SalesInvoiceSummary,
)
from app.sales_invoice.services import SalesInvoiceService

router = APIRouter(
    prefix="/api/v1/sales-invoices",
    tags=["Sales Invoices"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


SalesInvoiceViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_VIEW")
]
SalesInvoiceCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CREATE")
]
SalesInvoiceUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_UPDATE")
]
SalesInvoiceApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_APPROVE")
]
SalesInvoiceCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CANCEL")
]
SalesInvoiceExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_EXPORT")
]
SalesInvoiceImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_IMPORT")
]


@router.get(
    "/",
    response_model=PaginatedResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def list_sales_invoices(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
    customer_id: Annotated[UUID | None, Query()] = None,
    branch_id: Annotated[UUID | None, Query()] = None,
    salesman_id: Annotated[UUID | None, Query()] = None,
    territory_id: Annotated[UUID | None, Query()] = None,
    status: Annotated[SalesInvoiceStatus | None, Query()] = None,
    invoice_from: Annotated[date | None, Query()] = None,
    invoice_to: Annotated[date | None, Query()] = None,
    due_from: Annotated[date | None, Query()] = None,
    due_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    sort_by: Annotated[str, Query(max_length=30)] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[SalesInvoiceResponse]:
    """List sales invoices with optional filters."""
    service = SalesInvoiceService(db)
    rows, total = service.list_invoices(
        firm_scope=scope.firm_id,
        filters=SalesInvoiceListFilters(
            customer_id=customer_id,
            branch_id=branch_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            status=status,
            invoice_from=invoice_from,
            invoice_to=invoice_to,
            due_from=due_from,
            due_to=due_to,
        ),
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        sort_by=sort_by,
        descending=descending,
    )
    return PaginatedResponse(
        data=[service.invoice_response(row) for row in rows],
        pagination=pagination.metadata(total),
    )


@router.post(
    "/",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_invoice(
    scope: SalesInvoiceCreateScope,
    db: Annotated[Session, Depends(get_db)],
    data: SalesInvoiceCreate,
) -> SalesInvoiceResponse:
    """Create a new sales invoice."""
    service = SalesInvoiceService(db)
    row = service.create_invoice(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return service.invoice_response(row)


@router.get(
    "/{invoice_id}",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
) -> SalesInvoiceResponse:
    """Get a specific sales invoice."""
    service = SalesInvoiceService(db)
    row = service.get_invoice(invoice_id, firm_scope=scope.firm_id)
    return service.invoice_response(row)


@router.put(
    "/{invoice_id}",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
)
def update_sales_invoice(
    scope: SalesInvoiceUpdateScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: SalesInvoiceCreate,
) -> SalesInvoiceResponse:
    """Update an existing sales invoice."""
    service = SalesInvoiceService(db)
    row = service.update_invoice(
        invoice_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return service.invoice_response(row)


@router.post(
    "/{invoice_id}/approve",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
)
def approve_sales_invoice(
    scope: SalesInvoiceApproveScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
) -> SalesInvoiceResponse:
    """Approve a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.approve_invoice(
        invoice_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return service.invoice_response(row)


@router.post(
    "/{invoice_id}/cancel",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
)
def cancel_sales_invoice(
    scope: SalesInvoiceCancelScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: ActionReasonRequest,
) -> SalesInvoiceResponse:
    """Cancel a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.cancel_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return service.invoice_response(row)


@router.post(
    "/{invoice_id}/close",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
)
def close_sales_invoice(
    scope: SalesInvoiceApproveScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: ActionReasonRequest,
) -> SalesInvoiceResponse:
    """Close a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.close_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return service.invoice_response(row)


@router.get(
    "/{invoice_id}/timeline",
    response_model=PaginatedResponse[DocumentLifecycleEventResponse],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_timeline(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    pagination: Annotated[PaginationParams, Depends()],
) -> PaginatedResponse[DocumentLifecycleEventResponse]:
    """Get timeline events for a sales invoice."""
    service = SalesInvoiceService(db)
    rows, total = service.timeline(
        invoice_id=invoice_id,
        firm_scope=scope.firm_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[DocumentLifecycleEventResponse.model_validate(row) for row in rows],
        pagination=pagination.metadata(total),
    )


@router.get(
    "/reports/pending",
    response_model=list[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def get_pending_invoices(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceResponse]:
    """Get pending (draft) sales invoices."""
    service = SalesInvoiceService(db)
    rows = service.pending_invoices(firm_scope=scope.firm_id)
    return [service.invoice_response(row) for row in rows]


@router.get(
    "/reports/overdue",
    response_model=list[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def get_overdue_invoices(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceResponse]:
    """Get overdue sales invoices."""
    service = SalesInvoiceService(db)
    rows = service.overdue_invoices(firm_scope=scope.firm_id)
    return [service.invoice_response(row) for row in rows]


@router.get(
    "/reports/summary",
    response_model=SalesInvoiceSummary,
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_summary(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> SalesInvoiceSummary:
    """Get sales invoice summary."""
    service = SalesInvoiceService(db)
    return service.summary(firm_scope=scope.firm_id)


@router.get(
    "/reports/register",
    response_model=list[SalesInvoiceRegisterRecord],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_register(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceRegisterRecord]:
    """Get sales invoice register report."""
    service = SalesInvoiceService(db)
    return service.register_report(firm_scope=scope.firm_id)


@router.get(
    "/reports/customer-outstanding",
    response_model=list[SalesInvoiceCustomerOutstandingRecord],
    status_code=status.HTTP_200_OK,
)
def get_customer_outstanding(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceCustomerOutstandingRecord]:
    """Get customer outstanding amounts report."""
    service = SalesInvoiceService(db)
    return service.outstanding_report(firm_scope=scope.firm_id)


@router.get(
    "/reports/reconciliation",
    response_model=list[SalesInvoiceReconciliationRecord],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_reconciliation(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceReconciliationRecord]:
    """Get sales invoice vs delivery note reconciliation report."""
    service = SalesInvoiceService(db)
    return service.reconciliation_report(firm_scope=scope.firm_id)


@router.post(
    "/import",
    response_model=list[SalesInvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
def import_sales_invoices(
    scope: SalesInvoiceImportScope,
    db: Annotated[Session, Depends(get_db)],
    data: SalesInvoiceImportRequest,
) -> list[SalesInvoiceResponse]:
    """Import multiple sales invoices."""
    service = SalesInvoiceService(db)
    rows = service.import_invoices(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    return [service.invoice_response(row) for row in rows]


@router.get(
    "/export/csv",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def export_sales_invoices_csv(
    scope: SalesInvoiceExportScope,
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> StreamingResponse:
    """Export sales invoices to CSV."""
    service = SalesInvoiceService(db)
    csv_data = service.export_invoices_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_invoices.csv"},
    )
