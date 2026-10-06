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
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_today
from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.pagination.reports import ReportRows
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.validation.payloads import parse_payload
from app.document_files.api import download_response, read_upload
from app.document_files.schemas import DocumentFileResponse
from app.document_files.services import DocumentFileService, FileParent
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
    BulkCancelRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.finance.schemas.tds_sections import TdsProposalRecord
from app.purchase_invoice.schemas import (
    PurchaseInvoiceApproveRequest,
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
    PurchaseInvoiceSupplierIrnWrite,
    PurchaseInvoiceVendorOutstandingRecord,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_invoice.services.gst_purchase_register import (
    GstPurchaseRegisterService,
)
from app.purchase_invoice.services.payables_report import (
    MAX_MONTHS as MAX_PAYABLES_MONTHS,
)
from app.purchase_invoice.services.payables_report import PayablesReportService
from app.purchase_invoice.services.price_variance import PriceVarianceService
from app.purchase_invoice.services.purchase_analysis import (
    PurchaseAnalysisService,
)
from app.purchase_invoice.services.tcs_paid_report import TcsPaidReportService
from app.purchase_invoice.services.vendor_ageing import VendorAgeingService
from app.sales_invoice.api.router import SalesAnalysisResponse, analysis_response
from app.sales_invoice.services.sales_analysis import (
    SalesAnalysis,
    shifted_a_year,
    year_earlier,
)

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
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Create one purchase invoice."""
    service = PurchaseInvoiceService(db)
    row = service.create_invoice(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
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


class RateTrendPoint(BaseModel):
    """One bill's rate for a product (RPT-2)."""

    bill_id: UUID
    bill_number: str
    bill_date: date
    supplier_id: UUID
    supplier_name: str
    quantity: Decimal
    rate: Decimal


@router.get(
    "/reports/rate-trend",
    response_model=ApiResponse[list[RateTrendPoint]],
)
def purchase_rate_trend(
    scope: PurchaseInvoiceReportScope,
    product_id: UUID,
    from_date: date | None = None,
    to_date: date | None = None,
    supplier_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[RateTrendPoint]]:
    """One product's billed rate, bill by bill, oldest first (RPT-2).

    The period defaults to the last twelve months.
    """
    today = firm_today(db, scope.firm_id)
    points = PurchaseAnalysisService(db).rate_trend(
        scope.firm_id,
        product_id=product_id,
        from_date=from_date or year_earlier(today),
        to_date=to_date or today,
        supplier_id=supplier_id,
    )
    return ApiResponse(data=[RateTrendPoint(**vars(point)) for point in points])


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
    basis: str = "billed",
    compare_previous_year: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesAnalysisResponse]:
    """Billed purchases by one or two dimensions, net of returns (backlog 66).

    ``rows`` and ``columns`` are each one of day, week, month, quarter, year,
    product, category, supplier, supplier_category, branch. The period
    defaults to this month. The response has the sales analysis's shape.

    ``basis`` is ``billed`` (supplier bills), ``received`` (goods receipts)
    or ``ordered`` (purchase orders placed); ``compare_previous_year`` adds
    the same analysis a year earlier under ``previous`` (RPT-2).
    """
    today = firm_today(db, scope.firm_id)
    first = from_date or today.replace(day=1)
    last = to_date or today
    service = PurchaseAnalysisService(db)
    filters = _purchase_filters(
        product_id=product_id,
        category_id=category_id,
        supplier_id=supplier_id,
        supplier_category_id=supplier_category_id,
        branch_id=branch_id,
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
    return ApiResponse(data=analysis_response(result, previous=previous))


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


class TcsPaidRecord(BaseModel):
    """One bill that bore a supplier's TCS, or a quarter's total (PG-6).

    ``row_type`` is ``BILL`` or ``QUARTER_TOTAL``; a total row names the
    quarter and sums its bases and TCS, the rest of its fields empty.
    """

    model_config = ConfigDict(from_attributes=True)

    row_type: str
    quarter: str
    invoice_id: UUID | None
    invoice_number: str | None
    supplier_invoice_number: str | None
    invoice_date: date | None
    vendor_id: UUID | None
    vendor_name: str | None
    vendor_pan: str | None
    base_amount: Decimal
    tcs_rate_percent: Decimal | None
    tcs_amount: Decimal


@router.get(
    "/reports/tcs-paid",
    response_model=PaginatedResponse[TcsPaidRecord],
)
def tcs_paid_to_suppliers(
    scope: PurchaseInvoiceReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TcsPaidRecord]:
    """Return the TCS suppliers charged on approved bills, by quarter (PG-6)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        [
            TcsPaidRecord.model_validate(row)
            for row in TcsPaidReportService(db).rows(scope.firm_id, window)
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
            document_id,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
            may_exceed_tolerance=scope.principal.has_permission(
                "PURCHASE_APPROVE_OVER_TOLERANCE"
            ),
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
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Replace one purchase invoice.

    ``If-Match`` with the version last read refuses a save over somebody
    else's newer one (D-BUY-54); sending none saves with no precondition.
    """
    service = PurchaseInvoiceService(db)
    assert_version(
        service.get_invoice(invoice_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update_invoice(
        invoice_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.invoice_response(row))


@router.put(
    "/{invoice_id}/supplier-irn", response_model=ApiResponse[PurchaseInvoiceResponse]
)
def set_purchase_invoice_supplier_irn(
    invoice_id: UUID,
    data: PurchaseInvoiceSupplierIrnWrite,
    scope: PurchaseInvoiceUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Record or clear the supplier's IRN, approved bills included (78.5)."""
    service = PurchaseInvoiceService(db)
    row = service.set_supplier_irn(
        invoice_id,
        data.supplier_irn,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=service.invoice_response(row))


@router.post(
    "/{invoice_id}/approve", response_model=ApiResponse[PurchaseInvoiceResponse]
)
def approve_purchase_invoice(
    invoice_id: UUID,
    scope: PurchaseInvoiceApproveScope,
    data: PurchaseInvoiceApproveRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Approve one purchase invoice, paying it now if a payment block is sent.

    The block (PG-3) records an ordinary payment allocated to the bill in the
    same commit, so it needs PAYMENT_CREATE as ``POST /payments`` does. With no
    block the approval is exactly what it always was.
    """
    service = PurchaseInvoiceService(db)
    # A bill priced past the firm's tolerance over its order waits for
    # somebody who may approve it anyway (BUY-10).
    may_exceed_tolerance = scope.principal.has_permission(
        "PURCHASE_APPROVE_OVER_TOLERANCE"
    )
    # The TDS the bill proposes may be overridden here (PG-5).
    tds_amount = None if data is None else data.tds_amount
    if data is None or data.payment is None:
        row = service.approve_invoice(
            invoice_id,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
            may_exceed_tolerance=may_exceed_tolerance,
            tds_amount=tds_amount,
        )
        return ApiResponse(data=service.invoice_response(row))
    if not scope.principal.has_permission("PAYMENT_CREATE"):
        raise AuthorizationError(
            "Paying a bill as it is approved records a payment, which needs "
            "PAYMENT_CREATE. Approve it without the payment, or ask somebody "
            "who may record payments."
        )
    row, payment = service.approve_and_pay(
        invoice_id,
        data.payment,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        may_exceed_tolerance=may_exceed_tolerance,
        tds_amount=tds_amount,
    )
    return ApiResponse(
        data=service.invoice_response(row),
        message=(
            f"Bill approved and payment {payment.settlement_number} of "
            f"{payment.amount} recorded."
        ),
    )


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
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseInvoiceResponse]:
    """Return one purchase invoice."""
    service = PurchaseInvoiceService(db)
    row = service.get_invoice(invoice_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.invoice_response(row))


@router.get(
    "/{invoice_id}/tds-proposal",
    response_model=ApiResponse[TdsProposalRecord],
)
def purchase_invoice_tds_proposal(
    invoice_id: UUID,
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TdsProposalRecord]:
    """Return what approving this bill would deduct under 194C or 194J (PG-5).

    Worked on the bill's own base -- its lines and its additional charges,
    before GST -- by the method approval uses, so the Approve dialog shows
    the figure that will be posted (D-BUY-37).
    """
    proposal = PurchaseInvoiceService(db).tds_proposal(
        invoice_id, firm_scope=scope.firm_id
    )
    return ApiResponse(data=TdsProposalRecord.model_validate(proposal))


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
    "/reports/due",
    response_model=ApiResponse[list[PurchaseInvoiceOverdueRecord]],
)
def purchase_invoices_falling_due(
    scope: PurchaseInvoiceReportScope,
    days: Annotated[int, Query(ge=0, le=366)] = 7,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceOverdueRecord]]:
    """List the bills falling due from today to ``days`` ahead (ACC-6).

    ``days=0`` is what falls due today; the default, 7, is the week ahead.
    A bill already overdue is on the overdue list, not here.
    """
    return ApiResponse(
        data=PurchaseInvoiceService(db).overdue_report(
            firm_scope=scope.firm_id, due_within=days
        )
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


class GstPurchaseRegisterRecord(BaseModel):
    """One claimed supplier bill, debit note or purchase return, by tax head.

    Backlog §86 #17. A debit note's or a return's row is negative and names
    its bill.
    """

    model_config = ConfigDict(from_attributes=True)

    invoice_id: UUID
    invoice_date: date
    invoice_number: str
    supplier_invoice_number: str
    supplier_invoice_date: date
    vendor_id: UUID
    vendor_name: str
    vendor_gstin: str | None
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    total_tax: Decimal
    itc_not_claimable: Decimal
    reverse_charge_tax: Decimal
    invoice_total: Decimal
    #: Tax on capital-goods lines (PG-13), part of ``total_tax``.
    capital_goods_tax: Decimal = Decimal("0")
    #: ``BILL``, ``DEBIT_NOTE`` or ``PURCHASE_RETURN``.
    document_type: str = "BILL"
    #: What the desktop's grid shows for ``document_type``.
    document_type_label: str = "Bill"
    #: The bill a debit note or a return takes back from; empty on a bill.
    against_invoice_number: str = ""

    @model_validator(mode="after")
    def _label_the_type(self) -> "GstPurchaseRegisterRecord":
        """Say the document type in words."""
        self.document_type_label = {
            "DEBIT_NOTE": "Debit note",
            "PURCHASE_RETURN": "Purchase return",
        }.get(self.document_type, "Bill")
        return self


@router.get(
    "/reports/gst-register",
    response_model=PaginatedResponse[GstPurchaseRegisterRecord],
)
def gst_purchase_register(
    scope: PurchaseInvoiceReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[GstPurchaseRegisterRecord]:
    """Return a period's bills, debit notes and returns by tax head (§86 #17)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    rows = GstPurchaseRegisterService(db).register(scope.firm_id, window)
    return window.respond(
        [GstPurchaseRegisterRecord.model_validate(row) for row in rows]
        if not isinstance(rows, ReportRows)
        else ReportRows(
            [GstPurchaseRegisterRecord.model_validate(row) for row in rows],
            total_records=rows.total_records,
        )
    )


class HsnPurchaseRecord(BaseModel):
    """The inward supplies of one HSN code in one unit (backlog §86 #17)."""

    model_config = ConfigDict(from_attributes=True)

    hsn_code: str
    description: str
    unit: str
    quantity: Decimal
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    total_tax: Decimal
    bills: int


@router.get(
    "/reports/hsn-summary",
    response_model=PaginatedResponse[HsnPurchaseRecord],
)
def hsn_purchase_summary(
    scope: PurchaseInvoiceReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[HsnPurchaseRecord]:
    """Return a period's approved inward supplies by HSN code (§86 #17)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        [
            HsnPurchaseRecord.model_validate(row)
            for row in GstPurchaseRegisterService(db).hsn_summary(scope.firm_id, window)
        ]
    )


class PriceVarianceRecord(BaseModel):
    """One bill line charged at a rate other than its receipt's (65.5)."""

    model_config = ConfigDict(from_attributes=True)

    invoice_date: date
    invoice_number: str
    line_number: int
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
    purchase_invoice_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PriceVarianceRecord]:
    """List bill lines charged at a rate other than the receipt's (65.5).

    ``purchase_invoice_id`` narrows it to one bill in any status: the bill's
    own screen shows the same answer (65 row 5).
    """
    window = ReportWindow(from_date, to_date, page, page_size)
    rows = PriceVarianceService(db).report(
        scope.firm_id, window, purchase_invoice_id=purchase_invoice_id
    )
    return window.respond([PriceVarianceRecord.model_validate(row) for row in rows])


@router.get(
    "/reports/outstanding",
    response_model=ApiResponse[list[PurchaseInvoiceVendorOutstandingRecord]],
)
def vendor_outstanding_placeholder(
    scope: PurchaseInvoiceReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseInvoiceVendorOutstandingRecord]]:
    """Report the balance still owing per vendor.

    Superseded by ``/reports/payables`` (§85, PG-2), which nets supplier
    credits and checks its total against the books (D-BUY-32). Kept for one
    release, then removed with its caller.
    """
    return ApiResponse(
        data=PurchaseInvoiceService(db).outstanding_report(firm_scope=scope.firm_id),
        message="Superseded by /purchase-invoices/reports/payables.",
    )


class PayablesRowRecord(BaseModel):
    """One supplier's row of the payables report, or the total row (§85)."""

    model_config = ConfigDict(from_attributes=True)

    #: None on the total row.
    vendor_id: UUID | None
    vendor_code: str
    vendor_name: str
    #: Owed: bills dated (or due) before the first month shown. Paid: 0.
    older: Decimal
    #: One per entry of ``months``, in order.
    amounts: list[Decimal]
    #: Owed by due date: bills due after the last month shown. Otherwise 0.
    later: Decimal
    #: Owed: returns, debit notes and advances not set against a bill, as a
    #: negative figure. Paid: 0.
    credits: Decimal
    #: The row's sum: Outstanding on the Owed view, paid on the Paid view.
    total: Decimal
    #: Bills owing (Owed) or payments made (Paid) per month.
    counts: list[int]
    documents: int


class PayablesBooksCheckRecord(BaseModel):
    """The report's total against the payables account (§85 row 4)."""

    model_config = ConfigDict(from_attributes=True)

    #: Owed: the payables balance at the as-of date. Paid: what payments
    #: debited payables with in the window. None when it cannot be compared.
    ledger_balance: Decimal | None
    #: The total row's ``total`` less ``ledger_balance``, allowing for
    #: ``unrealised_revaluation``; zero when they agree.
    difference: Decimal | None
    note: str | None
    #: What a period-end exchange revaluation holds on the account at the
    #: as-of date (PG-12). It is in ``ledger_balance`` and on no bill, and is
    #: reversed the next day, so the check leaves it out (D-FIN-27).
    unrealised_revaluation: Decimal = Decimal("0")


class PayablesReportRecord(BaseModel):
    """Payables by supplier and month (§85, PG-2)."""

    model_config = ConfigDict(from_attributes=True)

    as_of: date
    basis: str
    view: str
    #: ``YYYY-MM``, oldest first, the as-of month last.
    months: list[str]
    rows: list[PayablesRowRecord]
    total: PayablesRowRecord
    books_check: PayablesBooksCheckRecord


@router.get(
    "/reports/payables",
    response_model=ApiResponse[PayablesReportRecord],
)
def payables_report(
    scope: PurchaseInvoiceReportScope,
    as_of: date | None = None,
    basis: Literal["invoice", "due"] = "invoice",
    months: Annotated[int, Query(ge=1, le=MAX_PAYABLES_MONTHS)] = 6,
    vendor_id: UUID | None = None,
    branch_id: UUID | None = None,
    view: Literal["owed", "paid"] = "owed",
    db: Session = Depends(get_db),
) -> ApiResponse[PayablesReportRecord]:
    """Report what each supplier is owed, or was paid, by month (§85, PG-2).

    Owed: each bill's outstanding (what ``settlement_allocations``, returns,
    debit notes, write-backs and applied credit leave) in its invoice or due
    month, older bills in Older, supplier credits in Credits, and a total
    checked against Trade Payables at ``as_of`` (today by default). Paid:
    payments per supplier per month, checked against what they debited
    payables with. Replaces ``/reports/outstanding`` (D-BUY-32).
    """
    report = PayablesReportService(db).report(
        scope.firm_id,
        as_of=as_of or firm_today(db, scope.firm_id),
        basis=basis,
        months=months,
        vendor_id=vendor_id,
        branch_id=branch_id,
        view=view,
    )
    return ApiResponse(data=PayablesReportRecord.model_validate(report))


class VendorAgeingBandRecord(BaseModel):
    """What one supplier is owed in one band of the firm's ageing (ACC-6)."""

    model_config = ConfigDict(from_attributes=True)

    from_days: int
    to_days: int | None
    label: str
    amount: Decimal


class VendorAgeingRecord(BaseModel):
    """One supplier's unpaid bills by days past due (backlog 55 S7)."""

    model_config = ConfigDict(from_attributes=True)

    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    as_of: date
    bills: int
    total_outstanding: Decimal
    #: One per band of the firm's ageing settings, in order (ACC-6).
    buckets: list[VendorAgeingBandRecord]
    oldest_days: int


@router.get(
    "/reports/vendor-ageing",
    response_model=ApiResponse[list[VendorAgeingRecord]],
)
def vendor_ageing(
    scope: PurchaseInvoiceReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[VendorAgeingRecord]]:
    """Report what each supplier is owed, by days past due, today (55 S7).

    The firm's ageing bands, as the customer ageing reads them (ACC-6), over
    what Record Payment says each bill still owes.
    """
    return ApiResponse(
        data=[
            VendorAgeingRecord.model_validate(row, from_attributes=True)
            for row in VendorAgeingService(db).ageing(scope.firm_id)
        ]
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
        parse_payload(PurchaseInvoiceImportRequest, payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=service.invoice_responses(rows))


# ---- the supplier's bill itself: uploaded files (PG-4) ----------------------

#: Whoever may enter or edit a bill may keep its paper with it.
PurchaseInvoiceFileScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope("PURCHASE_CREATE", "PURCHASE_UPDATE"),
]


@router.get(
    "/{invoice_id}/files", response_model=ApiResponse[list[DocumentFileResponse]]
)
def list_purchase_invoice_files(
    invoice_id: UUID,
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentFileResponse]]:
    """List the files uploaded onto one bill; metadata only."""
    rows = DocumentFileService(db).list_files(
        FileParent.PURCHASE_INVOICE, invoice_id, firm_id=scope.firm_id
    )
    return ApiResponse(data=[DocumentFileResponse.model_validate(r) for r in rows])


@router.post(
    "/{invoice_id}/files",
    response_model=ApiResponse[DocumentFileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_purchase_invoice_file(
    invoice_id: UUID,
    scope: PurchaseInvoiceFileScope,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str | None, Form(max_length=200)] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentFileResponse]:
    """Keep the supplier's PDF or a photo of it with the bill (10 MB, PDF/JPG/PNG)."""
    content = await read_upload(file)
    row = DocumentFileService(db).attach(
        FileParent.PURCHASE_INVOICE,
        invoice_id,
        file_name=file.filename or "",
        declared_type=file.content_type,
        content=content,
        caption=caption,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=DocumentFileResponse.model_validate(row))


@router.get("/{invoice_id}/files/{file_id}/content")
def download_purchase_invoice_file(
    invoice_id: UUID,
    file_id: UUID,
    scope: PurchaseInvoiceViewScope,
    db: Session = Depends(get_db),
) -> Response:
    """Download one file kept with a bill, under its own name and type."""
    row, content = DocumentFileService(db).download(
        FileParent.PURCHASE_INVOICE, invoice_id, file_id, firm_id=scope.firm_id
    )
    return download_response(row, content)


@router.delete("/{invoice_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_invoice_file(
    invoice_id: UUID,
    file_id: UUID,
    scope: PurchaseInvoiceFileScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove one file from a bill; the trail keeps that it was there."""
    DocumentFileService(db).remove(
        FileParent.PURCHASE_INVOICE,
        invoice_id,
        file_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
