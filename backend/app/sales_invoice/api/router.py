"""Firm-scoped REST endpoints for enterprise sales invoices."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.firms.models import Firm
from app.identity.models import UserFirm
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


class SalesInvoiceScope:
    """Carry principal and firm scope for invoice handlers."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Sales invoice operations require a user principal.")
        return self.principal.subject


class ActionReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def sales_invoice_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> SalesInvoiceScope:
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
        return SalesInvoiceScope(principal=principal, firm_id=x_firm_id)
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
    return SalesInvoiceScope(principal=principal, firm_id=x_firm_id)


@router.get(
    "/",
    response_model=PaginatedResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def list_sales_invoices(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
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
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "/",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("sales_invoice:write"))],
)
def create_sales_invoice(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
    data: SalesInvoiceCreate,
) -> SalesInvoiceResponse:
    """Create a new sales invoice."""
    service = SalesInvoiceService(db)
    row = service.create_invoice(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    return service.invoice_response(row)


@router.get(
    "/{invoice_id}",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_sales_invoice(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
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
    dependencies=[Depends(require_permission("sales_invoice:write"))],
)
def update_sales_invoice(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: SalesInvoiceCreate,
) -> SalesInvoiceResponse:
    """Update an existing sales invoice."""
    service = SalesInvoiceService(db)
    row = service.update_invoice(
        invoice_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return service.invoice_response(row)


@router.post(
    "/{invoice_id}/approve",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:approve"))],
)
def approve_sales_invoice(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
) -> SalesInvoiceResponse:
    """Approve a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.approve_invoice(
        invoice_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return service.invoice_response(row)


@router.post(
    "/{invoice_id}/cancel",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:write"))],
)
def cancel_sales_invoice(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: ActionReasonRequest,
) -> SalesInvoiceResponse:
    """Cancel a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.cancel_invoice(
        invoice_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return service.invoice_response(row)


@router.post(
    "/{invoice_id}/close",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:write"))],
)
def close_sales_invoice(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: ActionReasonRequest,
) -> SalesInvoiceResponse:
    """Close a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.close_invoice(
        invoice_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return service.invoice_response(row)


@router.get(
    "/{invoice_id}/timeline",
    response_model=PaginatedResponse[DocumentLifecycleEventResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_sales_invoice_timeline(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    pagination: Annotated[PaginationParams, Depends()],
) -> PaginatedResponse[DocumentLifecycleEventResponse]:
    """Get timeline events for a sales invoice."""
    service = SalesInvoiceService(db)
    rows, total = service.timeline(
        invoice_id=invoice_id,
        firm_id=scope.firm_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=rows, total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.get(
    "/reports/pending",
    response_model=list[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_pending_invoices(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
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
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_overdue_invoices(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
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
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_sales_invoice_summary(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> SalesInvoiceSummary:
    """Get sales invoice summary."""
    service = SalesInvoiceService(db)
    return service.summary(firm_scope=scope.firm_id)


@router.get(
    "/reports/register",
    response_model=list[SalesInvoiceRegisterRecord],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_sales_invoice_register(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceRegisterRecord]:
    """Get sales invoice register report."""
    service = SalesInvoiceService(db)
    return service.register_report(firm_scope=scope.firm_id)


@router.get(
    "/reports/customer-outstanding",
    response_model=list[SalesInvoiceCustomerOutstandingRecord],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_customer_outstanding(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceCustomerOutstandingRecord]:
    """Get customer outstanding amounts report."""
    service = SalesInvoiceService(db)
    return service.customer_outstanding_report(firm_scope=scope.firm_id)


@router.get(
    "/reports/reconciliation",
    response_model=list[SalesInvoiceReconciliationRecord],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def get_sales_invoice_reconciliation(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesInvoiceReconciliationRecord]:
    """Get sales invoice vs delivery note reconciliation report."""
    service = SalesInvoiceService(db)
    return service.reconciliation_report(firm_scope=scope.firm_id)


@router.post(
    "/import",
    response_model=list[SalesInvoiceResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("sales_invoice:write"))],
)
def import_sales_invoices(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
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
    dependencies=[Depends(require_permission("sales_invoice:read"))],
)
def export_sales_invoices_csv(
    scope: Annotated[SalesInvoiceScope, Depends(sales_invoice_scope)],
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
