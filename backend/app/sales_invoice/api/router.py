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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
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
from app.core.pagination.reports import mapped_like
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
    BulkCancelRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.sales_invoice.models import SalesInvoiceLine
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
from app.sales_invoice.services.discount_report import DiscountReportService
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
)
from app.sales_invoice.services.sales_analysis import (
    AnalysisFilters,
    Cell,
    SalesAnalysis,
    SalesAnalysisService,
    shifted_a_year,
    year_earlier,
)
from app.sales_order.api.price_override import (
    PriceOverrideReason,
    authorised_price_override,
)
from app.sales_order.schemas import PriceFloorCheckResponse
from app.sales_order.services.price_floor import PriceFloorService, invoice_lines
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


@router.post("/bulk-approve", response_model=ApiResponse[BulkActionResult])
def bulk_approve_sales_invoices(
    data: BulkApproveRequest,
    scope: SalesInvoiceApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked sales invoices, each on its own (backlog 56 A).

    Each goes through the single approval's own service and commits on its
    own: a refused one is reported with the reason and the rest go ahead.
    One that needs a licence override is refused here -- the override is a
    reason given for one document, on its own screen.
    """
    service = SalesInvoiceService(db)

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
def bulk_cancel_sales_invoices(
    data: BulkCancelRequest,
    scope: SalesInvoiceCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Cancel the ticked sales invoices with one reason, each on its own (56 A)."""
    service = SalesInvoiceService(db)

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
    price_override_reason: PriceOverrideReason = None,
) -> ApiResponse[SalesInvoiceResponse]:
    """Approve a sales invoice."""
    service = SalesInvoiceService(db)
    row = service.approve_invoice(
        invoice_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        licence_override_reason=authorised_override(scope, licence_override_reason),
        price_override_reason=authorised_price_override(scope, price_override_reason),
    )
    return ApiResponse(data=service.invoice_response(row))


@router.get(
    "/{invoice_id}/price-check",
    response_model=ApiResponse[PriceFloorCheckResponse],
)
def check_sales_invoice_prices(
    scope: SalesInvoiceViewScope,
    db: Annotated[Session, Depends(get_db)],
    invoice_id: UUID,
) -> ApiResponse[PriceFloorCheckResponse]:
    """Say which lines are sold below cost or minimum price, before approving."""
    row = SalesInvoiceService(db).get_invoice(invoice_id, firm_scope=scope.firm_id)
    lines = db.scalars(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == row.id,
            SalesInvoiceLine.is_deleted.is_(False),
        )
    ).all()
    return ApiResponse(
        data=PriceFloorService(db).check(
            scope.firm_id, invoice_lines(lines), as_of=row.invoice_date
        )
    )


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
    #: What the goods cost and the margin over it (RPT-1), from the billed
    #: lines that recorded a cost. None unless the caller may see cost
    #: (``PRODUCT_VIEW_COST_PRICE``) and the basis is billed sales.
    cost: Decimal | None = None
    margin: Decimal | None = None
    #: Margin as a percentage of the costed lines' taxable value.
    margin_percent: Decimal | None = None


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
    #: The same analysis a year earlier, filed under this year's keys
    #: (RPT-1); present only when asked for.
    previous: "SalesAnalysisResponse | None" = None


class AnalysisInvoiceRecord(BaseModel):
    """One invoice behind a cell, and what its matching lines came to."""

    id: UUID
    invoice_number: str
    invoice_date: date
    customer_id: UUID
    net: Decimal


def _figures(cell: Cell, *, margin: bool = False) -> AnalysisFigures:
    paise = Decimal("0.01")
    margin_amount = cell.costed - cell.cost
    return AnalysisFigures(
        cost=cell.cost.quantize(paise) if margin else None,
        margin=margin_amount.quantize(paise) if margin else None,
        margin_percent=(
            (margin_amount * 100 / cell.costed).quantize(paise)
            if margin and cell.costed
            else None
        ),
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


def analysis_response(
    result: SalesAnalysis,
    *,
    margin: bool = False,
    previous: SalesAnalysis | None = None,
) -> SalesAnalysisResponse:
    """Shape a pivot for the wire; the purchase analysis shares it (66)."""
    return SalesAnalysisResponse(
        rows=[AnalysisHeading(**vars(key)) for key in result.rows],
        columns=[AnalysisHeading(**vars(key)) for key in result.columns],
        cells=[
            AnalysisCellRecord(
                row=row, column=column, figures=_figures(cell, margin=margin)
            )
            for (row, column), cell in result.cells.items()
        ],
        row_totals={
            k: _figures(v, margin=margin) for k, v in result.row_totals.items()
        },
        column_totals={
            k: _figures(v, margin=margin) for k, v in result.column_totals.items()
        },
        grand_total=_figures(result.grand_total, margin=margin),
        previous=(
            None if previous is None else analysis_response(previous, margin=margin)
        ),
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
    brand_id: UUID | None = None,
    principal_id: UUID | None = None,
) -> AnalysisFilters:
    return AnalysisFilters(
        brand_id=brand_id,
        principal_id=principal_id,
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
    brand_id: UUID | None = None,
    principal_id: UUID | None = None,
    basis: str = "billed",
    compare_previous_year: bool = False,
) -> ApiResponse[SalesAnalysisResponse]:
    """Billed sales by one or two dimensions, net of returns (backlog 62).

    ``rows`` and ``columns`` are each one of day, week, month, quarter, year,
    product, category, brand, principal, customer, customer_group, salesman,
    territory, route, branch. The period defaults to this month.

    ``basis`` is ``billed`` (invoices) or ``ordered`` (sales orders booked);
    ``compare_previous_year`` adds the same analysis a year earlier under
    ``previous``. Billed figures carry cost and margin for a caller who may
    see cost (RPT-1).
    """
    today = utc_now().date()
    first = from_date or today.replace(day=1)
    last = to_date or today
    service = SalesAnalysisService(db)
    filters = _analysis_filters(
        product_id,
        category_id,
        customer_id,
        customer_group_id,
        salesman_id,
        territory_id,
        route_id,
        branch_id,
        brand_id,
        principal_id,
    )

    def run(start: date, end: date) -> SalesAnalysis:
        """Analyse one period with this request's dimensions and filters."""
        return service.analyse(
            scope.firm_id,
            rows=rows,
            columns=columns,
            from_date=start,
            to_date=end,
            filters=filters,
            net_of_returns=net_of_returns,
            basis=basis,
        )

    result = run(first, last)
    previous = (
        shifted_a_year(run(year_earlier(first), year_earlier(last)), rows, columns)
        if compare_previous_year
        else None
    )
    margin = basis == "billed" and scope.principal.has_permission(
        "PRODUCT_VIEW_COST_PRICE"
    )
    return ApiResponse(data=analysis_response(result, margin=margin, previous=previous))


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
    brand_id: UUID | None = None,
    principal_id: UUID | None = None,
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
            brand_id,
            principal_id,
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
    "/reports/due",
    response_model=ApiResponse[list[SalesInvoiceOverdueRecord]],
    status_code=status.HTTP_200_OK,
)
def get_invoices_falling_due(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=0, le=366)] = 7,
) -> ApiResponse[list[SalesInvoiceOverdueRecord]]:
    """List the invoices falling due from today to ``days`` ahead (ACC-6).

    ``days=0`` is what falls due today; the default, 7, is the week ahead.
    An invoice already overdue is on the overdue list, not here.
    """
    return ApiResponse(
        data=SalesInvoiceService(db).overdue_report(
            firm_scope=scope.firm_id, due_within=days
        )
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


class DiscountGivenRecord(BaseModel):
    """One customer's, salesman's or product's discounts (backlog 67 row 8).

    ``typed_discount`` is what somebody keyed; ``arranged_discount`` what a
    price list or a standing customer or group rate applied; the bill's
    share of a bill discount is ``bill_discount``.
    """

    model_config = ConfigDict(from_attributes=True)

    key_id: UUID | None
    code: str
    name: str
    lines: int
    gross_amount: Decimal
    typed_discount: Decimal
    arranged_discount: Decimal
    promotion_discount: Decimal
    bill_discount: Decimal
    total_discount: Decimal
    discount_percent: Decimal


class PromotionDiscountRecord(BaseModel):
    """One offer's claims over the dates, as it costed them (67 row 8)."""

    model_config = ConfigDict(from_attributes=True)

    version_group_id: UUID
    code: str
    name: str
    claims: int
    customers: int
    benefit_amount: Decimal


def _discount_given(
    dimension: str,
    firm_id: UUID,
    db: Session,
    window: ReportWindow,
) -> PaginatedResponse[DiscountGivenRecord]:
    """Answer the discount given by one dimension, one page."""
    rows = DiscountReportService(db).by(firm_id, dimension, window)
    return window.respond(
        mapped_like(
            rows,
            (
                DiscountGivenRecord.model_validate(row, from_attributes=True)
                for row in rows
            ),
        )
    )


@router.get(
    "/reports/discount-by-customer",
    response_model=PaginatedResponse[DiscountGivenRecord],
)
def get_discount_by_customer(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PaginatedResponse[DiscountGivenRecord]:
    """Discount given on billed sales, per customer, typed against arranged."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return _discount_given("customer", scope.firm_id, db, window)


@router.get(
    "/reports/discount-by-salesman",
    response_model=PaginatedResponse[DiscountGivenRecord],
)
def get_discount_by_salesman(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PaginatedResponse[DiscountGivenRecord]:
    """Discount given on billed sales, per salesman, typed against arranged."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return _discount_given("salesman", scope.firm_id, db, window)


@router.get(
    "/reports/discount-by-product",
    response_model=PaginatedResponse[DiscountGivenRecord],
)
def get_discount_by_product(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PaginatedResponse[DiscountGivenRecord]:
    """Discount given on billed sales, per product, typed against arranged."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return _discount_given("product", scope.firm_id, db, window)


@router.get(
    "/reports/discount-by-promotion",
    response_model=PaginatedResponse[PromotionDiscountRecord],
)
def get_discount_by_promotion(
    scope: SalesInvoiceReportScope,
    db: Annotated[Session, Depends(get_db)],
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PaginatedResponse[PromotionDiscountRecord]:
    """Return what each offer was claimed for over the dates, costliest first."""
    window = ReportWindow(from_date, to_date, page, page_size)
    rows = DiscountReportService(db).by_promotion(scope.firm_id, window)
    return window.respond(
        [
            PromotionDiscountRecord.model_validate(row, from_attributes=True)
            for row in rows
        ]
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
    reference_copy: Annotated[bool, Query()] = False,
) -> StreamingResponse:
    """Render one invoice as the PDF a customer is sent.

    Rendered here rather than in the client so the layout is right in one
    place, and so the same bytes can be attached to an email later. Viewing is
    the permission: printing a bill shows nothing the screen does not.

    A B2B invoice the firm must e-invoice is refused until it has its IRN
    (77 row 6); ``reference_copy`` prints it marked not valid instead.
    """
    pdf, filename = SalesInvoicePrintService(db).render(
        invoice_id, firm_scope=scope.firm_id, reference_copy=reference_copy
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
