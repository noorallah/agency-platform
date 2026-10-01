"""Firm-scoped REST endpoints for enterprise sales invoices."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.sales_invoice.schemas import (
    BillableDocument,
    SalesInvoiceCreate,
    SalesInvoiceCustomerOutstandingRecord,
    SalesInvoiceImportRequest,
    SalesInvoiceListFilters,
    SalesInvoiceOverdueRecord,
    SalesInvoicePreview,
    SalesInvoiceReconciliationRecord,
    SalesInvoiceRegisterRecord,
    SalesInvoiceResponse,
    SalesInvoiceStatus,
    SalesInvoiceSummary,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
)
from app.sales_invoice.services.sales_analysis import (
    AnalysisFilters,
    Cell,
    SalesAnalysis,
    SalesAnalysisService,
)
from app.trade_licences.api.override import (
    LicenceOverrideReason,
    authorised_override,
)

router = APIRouter(
    prefix="/api/v1/sales-invoices",
    tags=["Sales Invoices"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Carry the optional reason a lifecycle action was taken for."""

    reason: str | None = Field(default=None, max_length=500)


SalesInvoiceViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_VIEW")
]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
SalesInvoiceReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("SALES_VIEW", "REPORT_VIEW")
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


# "" rather than "/", which is what the other fourteen list endpoints declare.
# With a slash, FastAPI serves the list at `/api/v1/sales-invoices/` and answers
# `/api/v1/sales-invoices` with a 307 -- and the desktop client sets
# `followRedirects = false`, so every call to it failed with "Request failed
# (307)". The sales invoice workspace had been in that state.
@router.get(
    "/billable",
    response_model=ApiResponse[list[BillableDocument]],
)
def list_billable_documents(
    scope: SalesInvoiceViewScope,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db),
) -> ApiResponse[list[BillableDocument]]:
    """List what is still waiting to be billed.

    A literal path, declared above `/{invoice_id}` deliberately: FastAPI
    matches in declaration order and this repository has had four features
    made unreachable by a literal sitting below a parameter that swallowed it.
    """
    return ApiResponse(
        data=SalesInvoiceService(db).billable_documents(
            firm_scope=scope.firm_id, limit=limit, page=page
        )
    )


@router.get(
    "",
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
        data=service.invoice_responses(rows),
        pagination=pagination.metadata(total),
    )


# "" for the same reason as the list above: a client posting to
# `/api/v1/sales-invoices` was redirected, and one that does not follow
# redirects cannot create an invoice at all.
@router.post(
    "",
    response_model=ApiResponse[SalesInvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_sales_invoice(
    scope: SalesInvoiceCreateScope,
    db: Annotated[Session, Depends(get_db)],
    data: SalesInvoiceCreate,
) -> ApiResponse[SalesInvoiceResponse]:
    """Create a new sales invoice."""
    service = SalesInvoiceService(db)
    row = service.create_invoice(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.invoice_response(row))


@router.post("/preview", response_model=ApiResponse[SalesInvoicePreview])
def preview_sales_invoice(
    scope: SalesInvoiceCreateScope,
    db: Annotated[Session, Depends(get_db)],
    data: SalesInvoiceCreate,
) -> ApiResponse[SalesInvoicePreview]:
    """Price an invoice as saving it would, and save nothing.

    What the invoice screen calls as its lines are typed, so the rates,
    discounts, tax and totals it shows are the ones the save will store.
    """
    return ApiResponse(
        data=SalesInvoiceService(db).preview_invoice(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.get(
    "/{invoice_id}",
    response_model=ApiResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
) -> ApiResponse[SalesInvoiceResponse]:
    """Get a specific sales invoice."""
    service = SalesInvoiceService(db)
    row = service.get_invoice(invoice_id, firm_scope=scope.firm_id)
    return ApiResponse(data=service.invoice_response(row))


@router.put(
    "/{invoice_id}",
    response_model=ApiResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def update_sales_invoice(
    scope: SalesInvoiceUpdateScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: SalesInvoiceCreate,
    response: Response,
    expected_version: ExpectedVersion = None,
) -> ApiResponse[SalesInvoiceResponse]:
    """Update an existing sales invoice.

    The update replaces the whole line collection, so a lost race costs every
    line somebody entered rather than a single field -- which is why this
    module joining the `If-Match` convention mattered before an editor existed
    to make the race reachable.
    """
    service = SalesInvoiceService(db)
    assert_version(
        service.get_invoice(invoice_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update_invoice(
        invoice_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.invoice_response(row))


@router.post(
    "/{invoice_id}/approve",
    response_model=ApiResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def approve_sales_invoice(
    scope: SalesInvoiceApproveScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    licence_override_reason: LicenceOverrideReason = None,
) -> ApiResponse[SalesInvoiceResponse]:
    """Approve a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.approve_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        licence_override_reason=authorised_override(scope, licence_override_reason),
    )
    return ApiResponse(data=service.invoice_response(row))


@router.post(
    "/{invoice_id}/cancel",
    response_model=ApiResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def cancel_sales_invoice(
    scope: SalesInvoiceCancelScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: ActionReasonRequest,
) -> ApiResponse[SalesInvoiceResponse]:
    """Cancel a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.cancel_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.invoice_response(row))


@router.post(
    "/{invoice_id}/close",
    response_model=ApiResponse[SalesInvoiceResponse],
    status_code=status.HTTP_200_OK,
)
def close_sales_invoice(
    scope: SalesInvoiceApproveScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
    data: ActionReasonRequest,
) -> ApiResponse[SalesInvoiceResponse]:
    """Close a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.close_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.invoice_response(row))


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


class AnalysisFigures(BaseModel):
    """The figures of one cell or total (backlog 62)."""

    quantity: Decimal
    taxable: Decimal
    tax: Decimal
    net: Decimal
    invoices: int
    #: Net sales per invoice; None where no invoice is counted.
    average_bill: Decimal | None


class AnalysisHeading(BaseModel):
    """One row or column heading, and for a time bucket the dates it covers."""

    key: str
    label: str
    from_date: date | None = None
    to_date: date | None = None


class AnalysisCellRecord(BaseModel):
    """One cell: its row key, column key and figures."""

    row: str
    column: str
    figures: AnalysisFigures


class SalesAnalysisResponse(BaseModel):
    """The pivot: headings both ways, cells, totals both ways, grand total."""

    rows: list[AnalysisHeading]
    columns: list[AnalysisHeading]
    cells: list[AnalysisCellRecord]
    row_totals: dict[str, AnalysisFigures]
    column_totals: dict[str, AnalysisFigures]
    grand_total: AnalysisFigures


class AnalysisInvoiceRecord(BaseModel):
    """One invoice behind a cell, and what its matching lines came to."""

    id: UUID
    invoice_number: str
    invoice_date: date
    customer_id: UUID
    net: Decimal


def _figures(cell: Cell) -> AnalysisFigures:
    paise = Decimal("0.01")
    return AnalysisFigures(
        quantity=cell.quantity,
        taxable=cell.taxable.quantize(paise),
        tax=cell.tax.quantize(paise),
        net=cell.net.quantize(paise),
        invoices=cell.invoices,
        average_bill=(
            (cell.net / cell.invoices).quantize(Decimal("0.01"))
            if cell.invoices
            else None
        ),
    )


def analysis_response(result: SalesAnalysis) -> SalesAnalysisResponse:
    """Shape a pivot for the wire; the purchase analysis shares it (66)."""
    return SalesAnalysisResponse(
        rows=[AnalysisHeading(**vars(key)) for key in result.rows],
        columns=[AnalysisHeading(**vars(key)) for key in result.columns],
        cells=[
            AnalysisCellRecord(row=row, column=column, figures=_figures(cell))
            for (row, column), cell in result.cells.items()
        ],
        row_totals={k: _figures(v) for k, v in result.row_totals.items()},
        column_totals={k: _figures(v) for k, v in result.column_totals.items()},
        grand_total=_figures(result.grand_total),
    )


def _analysis_filters(
    product_id: UUID | None,
    category_id: UUID | None,
    customer_id: UUID | None,
    customer_group_id: UUID | None,
    salesman_id: UUID | None,
    territory_id: UUID | None,
    route_id: UUID | None,
    branch_id: UUID | None,
) -> AnalysisFilters:
    return AnalysisFilters(
        product_id=product_id,
        category_id=category_id,
        customer_id=customer_id,
        customer_group_id=customer_group_id,
        salesman_id=salesman_id,
        territory_id=territory_id,
        route_id=route_id,
        branch_id=branch_id,
    )


@router.get(
    "/reports/analysis",
    response_model=ApiResponse[SalesAnalysisResponse],
)
def sales_analysis(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    rows: str = "product",
    columns: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    net_of_returns: bool = True,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    customer_id: UUID | None = None,
    customer_group_id: UUID | None = None,
    salesman_id: UUID | None = None,
    territory_id: UUID | None = None,
    route_id: UUID | None = None,
    branch_id: UUID | None = None,
) -> ApiResponse[SalesAnalysisResponse]:
    """Billed sales by one or two dimensions, net of returns (backlog 62).

    ``rows`` and ``columns`` are each one of day, week, month, quarter, year,
    product, category, customer, customer_group, salesman, territory, route,
    branch. The period defaults to this month.
    """
    today = utc_now().date()
    first = from_date or today.replace(day=1)
    last = to_date or today
    result = SalesAnalysisService(db).analyse(
        scope.firm_id,
        rows=rows,
        columns=columns,
        from_date=first,
        to_date=last,
        filters=_analysis_filters(
            product_id,
            category_id,
            customer_id,
            customer_group_id,
            salesman_id,
            territory_id,
            route_id,
            branch_id,
        ),
        net_of_returns=net_of_returns,
    )
    return ApiResponse(data=analysis_response(result))


@router.get(
    "/reports/analysis/invoices",
    response_model=ApiResponse[list[AnalysisInvoiceRecord]],
)
def sales_analysis_invoices(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date,
    to_date: date,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    customer_id: UUID | None = None,
    customer_group_id: UUID | None = None,
    salesman_id: UUID | None = None,
    territory_id: UUID | None = None,
    route_id: UUID | None = None,
    branch_id: UUID | None = None,
) -> ApiResponse[list[AnalysisInvoiceRecord]]:
    """List the invoices behind one cell of the analysis (backlog 62)."""
    rows = SalesAnalysisService(db).invoices(
        scope.firm_id,
        from_date=from_date,
        to_date=to_date,
        filters=_analysis_filters(
            product_id,
            category_id,
            customer_id,
            customer_group_id,
            salesman_id,
            territory_id,
            route_id,
            branch_id,
        ),
    )
    return ApiResponse(
        data=[
            AnalysisInvoiceRecord(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                customer_id=invoice.customer_id,
                net=net,
            )
            for invoice, net in rows
        ]
    )


@router.get(
    "/reports/pending",
    response_model=ApiResponse[list[SalesInvoiceRegisterRecord]],
    status_code=status.HTTP_200_OK,
)
def get_pending_invoices(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[SalesInvoiceRegisterRecord]]:
    """List the invoices not yet approved, one flat row each."""
    return ApiResponse(
        data=SalesInvoiceService(db).register_report(
            firm_scope=scope.firm_id, statuses=(SalesInvoiceStatus.DRAFT.value,)
        )
    )


@router.get(
    "/reports/overdue",
    response_model=ApiResponse[list[SalesInvoiceOverdueRecord]],
    status_code=status.HTTP_200_OK,
)
def get_overdue_invoices(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[SalesInvoiceOverdueRecord]]:
    """List the invoices past their due date that still owe something."""
    return ApiResponse(
        data=SalesInvoiceService(db).overdue_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/summary",
    response_model=ApiResponse[SalesInvoiceSummary],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_summary(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[SalesInvoiceSummary]:
    """Get sales invoice summary."""
    service = SalesInvoiceService(db)
    return ApiResponse(data=service.summary(firm_scope=scope.firm_id))


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[SalesInvoiceRegisterRecord],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_register(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PaginatedResponse[SalesInvoiceRegisterRecord]:
    """Every invoice raised in the window, on its `invoice_date`, one page."""
    service = SalesInvoiceService(db)
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        service.register_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/customer-outstanding",
    response_model=ApiResponse[list[SalesInvoiceCustomerOutstandingRecord]],
    status_code=status.HTTP_200_OK,
)
def get_customer_outstanding(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[SalesInvoiceCustomerOutstandingRecord]]:
    """Get customer outstanding amounts report."""
    service = SalesInvoiceService(db)
    return ApiResponse(data=service.outstanding_report(firm_scope=scope.firm_id))


@router.get(
    "/reports/reconciliation",
    response_model=PaginatedResponse[SalesInvoiceReconciliationRecord],
    status_code=status.HTTP_200_OK,
)
def get_sales_invoice_reconciliation(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PaginatedResponse[SalesInvoiceReconciliationRecord]:
    """Say what is billed against each delivered line billed in the window."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        SalesInvoiceService(db).reconciliation_report(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[SalesInvoiceResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_sales_invoices(
    scope: SalesInvoiceImportScope,
    db: Annotated[Session, Depends(get_db)],
    data: SalesInvoiceImportRequest,
) -> ApiResponse[list[SalesInvoiceResponse]]:
    """Import multiple sales invoices."""
    service = SalesInvoiceService(db)
    rows = service.import_invoices(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    return ApiResponse(data=service.invoice_responses(rows))


@router.get(
    "/{invoice_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_sales_invoice(
    invoice_id: UUID,
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Render one invoice as the PDF a customer is sent.

    Rendered here rather than in the client so the layout is right in one
    place, and so the same bytes can be attached to an email later. Viewing is
    the permission: printing a bill shows nothing the screen does not.
    """
    pdf, filename = SalesInvoicePrintService(db).render(
        invoice_id, firm_scope=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            # `inline` so a desktop or browser viewer opens it rather than
            # dropping a file the user then has to find.
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


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
