"""Firm-scoped REST endpoints for enterprise purchase invoices."""

from datetime import date
from decimal import Decimal
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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
    BulkCancelRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceImportRequest,
    PurchaseInvoiceListFilters,
    PurchaseInvoiceMsmeDueRecord,
    PurchaseInvoiceOverdueRecord,
    PurchaseInvoicePreview,
    PurchaseInvoiceReconciliationRecord,
    PurchaseInvoiceRegisterRecord,
    PurchaseInvoiceResponse,
    PurchaseInvoiceStatus,
    PurchaseInvoiceSummary,
    PurchaseInvoiceVendorOutstandingRecord,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_invoice.services.price_variance import PriceVarianceService
from app.purchase_invoice.services.purchase_analysis import (
    PurchaseAnalysisService,
)
from app.sales_invoice.api.router import SalesAnalysisResponse, analysis_response

router = APIRouter(
    prefix="/api/v1/purchase-invoices",
    tags=["Purchase Invoices"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Carry the optional reason a lifecycle action was taken for."""

    reason: str | None = Field(default=None, max_length=500)


PurchaseInvoiceViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")
]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
PurchaseInvoiceReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("PURCHASE_VIEW", "REPORT_VIEW")
]
PurchaseInvoiceCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CREATE")
]
PurchaseInvoiceUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_UPDATE")
]
PurchaseInvoiceApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]
PurchaseInvoiceCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CANCEL")
]
PurchaseInvoiceExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_EXPORT")
]
PurchaseInvoiceImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_IMPORT")
]


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
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "invoice_number",
        "invoice_date",
        "due_date",
        "grand_total",
        "status",
        "created_at",
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
    """List purchase invoices for the visible firm scope."""
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
        data=service.invoice_responses(rows),
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[PurchaseInvoiceSummary])
def purchase_invoice_summary(
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceSummary]:
    """Return aggregate purchase invoice values for the visible firm scope."""
    return ApiResponse(
        data=PurchaseInvoiceService(db).summary(firm_scope=scope.firm_id)
    )


@router.post(
    "",
    response_model=ApiResponse[PurchaseInvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_invoice(
    data: PurchaseInvoiceCreate,
    scope: PurchaseInvoiceCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Create one purchase invoice."""
    service = PurchaseInvoiceService(db)
    row = service.create_invoice(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.invoice_response(row))


@router.post("/preview", response_model=ApiResponse[PurchaseInvoicePreview])
def preview_purchase_invoice(
    data: PurchaseInvoiceCreate,
    scope: PurchaseInvoiceCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoicePreview]:
    """Price a supplier bill as saving it would, and save nothing.

    What the bill screen calls as its lines are typed, so the tax and total
    it shows -- to be checked against the paper -- are the ones the save will
    store.
    """
    return ApiResponse(
        data=PurchaseInvoiceService(db).preview_invoice(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


# Declared above the `/{{id}}` route below on purpose: FastAPI matches in
# declaration order, so that route read "export" as an id and answered 422.
# Unreachable from the day it was written until 2026-08-22.
@router.get("/export")
def export_purchase_invoices(
    scope: PurchaseInvoiceExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export matching purchase invoices as CSV."""
    csv_content = PurchaseInvoiceService(db).export_invoices_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=purchase_invoices.csv"},
    )


class PurchaseAnalysisBill(BaseModel):
    """One bill behind a cell, and what its matching lines came to."""

    id: UUID
    invoice_number: str
    invoice_date: date
    vendor_id: UUID
    net: Decimal


def _purchase_filters(**values: UUID | None) -> dict[str, UUID]:
    return {name: value for name, value in values.items() if value is not None}


@router.get("/reports/analysis", response_model=ApiResponse[SalesAnalysisResponse])
def purchase_analysis(
    scope: PurchaseInvoiceReportScope,
    rows: str = "product",
    columns: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    net_of_returns: bool = True,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    supplier_id: UUID | None = None,
    supplier_category_id: UUID | None = None,
    branch_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesAnalysisResponse]:
    """Billed purchases by one or two dimensions, net of returns (backlog 66).

    ``rows`` and ``columns`` are each one of day, week, month, quarter, year,
    product, category, supplier, supplier_category, branch. The period
    defaults to this month. The response has the sales analysis's shape.
    """
    today = utc_now().date()
    result = PurchaseAnalysisService(db).analyse(
        scope.firm_id,
        rows=rows,
        columns=columns,
        from_date=from_date or today.replace(day=1),
        to_date=to_date or today,
        filters=_purchase_filters(
            product_id=product_id,
            category_id=category_id,
            supplier_id=supplier_id,
            supplier_category_id=supplier_category_id,
            branch_id=branch_id,
        ),
        net_of_returns=net_of_returns,
    )
    return ApiResponse(data=analysis_response(result))


@router.get(
    "/reports/analysis/bills",
    response_model=ApiResponse[list[PurchaseAnalysisBill]],
)
def purchase_analysis_bills(
    scope: PurchaseInvoiceReportScope,
    from_date: date,
    to_date: date,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    supplier_id: UUID | None = None,
    supplier_category_id: UUID | None = None,
    branch_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseAnalysisBill]]:
    """List the bills behind one cell of the purchase analysis (backlog 66)."""
    rows = PurchaseAnalysisService(db).bills(
        scope.firm_id,
        from_date=from_date,
        to_date=to_date,
        filters=_purchase_filters(
            product_id=product_id,
            category_id=category_id,
            supplier_id=supplier_id,
            supplier_category_id=supplier_category_id,
            branch_id=branch_id,
        ),
    )
    return ApiResponse(
        data=[
            PurchaseAnalysisBill(
                id=bill.id,
                invoice_number=bill.invoice_number,
                invoice_date=bill.invoice_date,
                vendor_id=bill.vendor_id,
                net=net,
            )
            for bill, net in rows
        ]
    )


@router.post("/bulk-approve", response_model=ApiResponse[BulkActionResult])
def bulk_approve_purchase_invoices(
    data: BulkApproveRequest,
    scope: PurchaseInvoiceApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked purchase invoices, each on its own (backlog 56 A).

    Each goes through the single approval's own service and commits on its
    own: a refused one is reported with the reason and the rest go ahead.
    One that needs a licence override is refused here -- the override is a
    reason given for one document, on its own screen.
    """
    service = PurchaseInvoiceService(db)

    def act(document_id: UUID) -> None:
        service.approve_invoice(
            document_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
        db.commit()

    return ApiResponse(
        data=run_each(
            db,
            data.items,
            load=lambda document_id: service.get_invoice(
                document_id, firm_scope=scope.firm_id
            ),
            act=act,
            number=lambda row: row.invoice_number,
        )
    )


@router.post("/bulk-cancel", response_model=ApiResponse[BulkActionResult])
def bulk_cancel_purchase_invoices(
    data: BulkCancelRequest,
    scope: PurchaseInvoiceCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Cancel the ticked purchase invoices with one reason, each on its own (56 A)."""
    service = PurchaseInvoiceService(db)

    def act(document_id: UUID) -> None:
        service.cancel_invoice(
            document_id,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
            reason=data.reason,
        )
        db.commit()

    return ApiResponse(
        data=run_each(
            db,
            data.items,
            load=lambda document_id: service.get_invoice(
                document_id, firm_scope=scope.firm_id
            ),
            act=act,
            number=lambda row: row.invoice_number,
        )
    )


@router.put("/{invoice_id}", response_model=ApiResponse[PurchaseInvoiceResponse])
def update_purchase_invoice(
    invoice_id: UUID,
    data: PurchaseInvoiceCreate,
    scope: PurchaseInvoiceUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Replace one purchase invoice."""
    service = PurchaseInvoiceService(db)
    row = service.update_invoice(
        invoice_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.invoice_response(row))


@router.post(
    "/{invoice_id}/approve", response_model=ApiResponse[PurchaseInvoiceResponse]
)
def approve_purchase_invoice(
    invoice_id: UUID,
    scope: PurchaseInvoiceApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Approve one purchase invoice."""
    service = PurchaseInvoiceService(db)
    row = service.approve_invoice(
        invoice_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.invoice_response(row))


@router.post(
    "/{invoice_id}/cancel", response_model=ApiResponse[PurchaseInvoiceResponse]
)
def cancel_purchase_invoice(
    invoice_id: UUID,
    data: ActionReasonRequest,
    scope: PurchaseInvoiceCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Cancel one purchase invoice."""
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
    """Close one purchase invoice."""
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
    """Return one purchase invoice."""
    service = PurchaseInvoiceService(db)
    return ApiResponse(
        data=service.invoice_response(
            service.get_invoice(invoice_id, firm_scope=scope.firm_id)
        )
    )


@router.get(
    "/{invoice_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def purchase_invoice_history(
    invoice_id: UUID,
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    """Return the lifecycle timeline for one purchase invoice."""
    rows = PurchaseInvoiceService(db).timeline(
        invoice_id=invoice_id, firm_scope=scope.firm_id, page=1, page_size=200
    )[0]
    return ApiResponse(
        data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows]
    )


@router.get(
    "/reports/pending",
    response_model=ApiResponse[list[PurchaseInvoiceRegisterRecord]],
)
def pending_purchase_invoices(
    scope: PurchaseInvoiceReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceRegisterRecord]]:
    """List the bills still in draft, one flat row each."""
    return ApiResponse(
        data=PurchaseInvoiceService(db).register_report(
            firm_scope=scope.firm_id, statuses=(PurchaseInvoiceStatus.DRAFT.value,)
        )
    )


@router.get(
    "/reports/msme-dues",
    response_model=ApiResponse[list[PurchaseInvoiceMsmeDueRecord]],
)
def msme_purchase_invoice_dues(
    scope: PurchaseInvoiceReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceMsmeDueRecord]]:
    """List unpaid bills to micro and small suppliers against their legal date."""
    return ApiResponse(
        data=PurchaseInvoiceService(db).msme_dues_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/overdue",
    response_model=ApiResponse[list[PurchaseInvoiceOverdueRecord]],
)
def overdue_purchase_invoices(
    scope: PurchaseInvoiceReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceOverdueRecord]]:
    """List the bills past their due date that still owe something."""
    return ApiResponse(
        data=PurchaseInvoiceService(db).overdue_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/register", response_model=PaginatedResponse[PurchaseInvoiceRegisterRecord]
)
def purchase_invoice_register(
    scope: PurchaseInvoiceReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseInvoiceRegisterRecord]:
    """Return the purchase invoice register report for the visible firm scope."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PurchaseInvoiceService(db).register_report(
            firm_scope=scope.firm_id, window=window
        )
    )


class PriceVarianceRecord(BaseModel):
    """One bill line charged at a rate other than its receipt's (65.5)."""

    model_config = ConfigDict(from_attributes=True)

    invoice_date: date
    invoice_number: str
    supplier_invoice_number: str
    supplier_name: str
    receipt_number: str
    product_code: str
    product_name: str
    quantity: Decimal
    receipt_rate: Decimal
    bill_rate: Decimal
    variance: Decimal
    note: str


@router.get(
    "/reports/price-variance",
    response_model=PaginatedResponse[PriceVarianceRecord],
)
def purchase_price_variance(
    scope: PurchaseInvoiceReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PriceVarianceRecord]:
    """List bill lines charged at a rate other than the receipt's (65.5)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    rows = PriceVarianceService(db).report(scope.firm_id, window)
    return window.respond([PriceVarianceRecord.model_validate(row) for row in rows])


@router.get(
    "/reports/outstanding",
    response_model=ApiResponse[list[PurchaseInvoiceVendorOutstandingRecord]],
)
def vendor_outstanding_placeholder(
    scope: PurchaseInvoiceReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceVendorOutstandingRecord]]:
    """Report the balance still owing per vendor."""
    return ApiResponse(
        data=PurchaseInvoiceService(db).outstanding_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/reconciliation",
    response_model=PaginatedResponse[PurchaseInvoiceReconciliationRecord],
)
def invoice_reconciliation_report(
    scope: PurchaseInvoiceReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseInvoiceReconciliationRecord]:
    """Say what is billed against each received line billed in the window."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PurchaseInvoiceService(db).reconciliation_report(
            firm_scope=scope.firm_id, window=window
        )
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
    """Import a validated batch of purchase invoices atomically."""
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
    return ApiResponse(data=service.invoice_responses(rows))
