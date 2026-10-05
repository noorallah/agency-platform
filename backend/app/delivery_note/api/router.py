"""Firm-scoped REST endpoints for enterprise delivery notes."""

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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.batch_serial.schemas import DispatchBatchCheck
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
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.delivery_note.schemas import (
    DeliveryNoteByDimensionRecord,
    DeliveryNoteCreate,
    DeliveryNoteImportRequest,
    DeliveryNoteListFilters,
    DeliveryNoteOrderProgressRecord,
    DeliveryNoteRegisterRecord,
    DeliveryNoteResponse,
    DeliveryNoteStatus,
    DeliveryNoteSummary,
    DeliveryNoteUpdate,
    DeliveryProofWrite,
)
from app.delivery_note.services import DeliveryNoteService
from app.delivery_note.services.challan_print_service import (
    DeliveryChallanPrintService,
)
from app.delivery_note.services.dispatch_sheets import DispatchSheetService
from app.delivery_note.services.transporters import (
    TransporterResponse,
    TransporterService,
    TransporterWrite,
)
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
    BulkCancelRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.sales_invoice.schemas import SalesInvoiceResponse
from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService
from app.tax.schemas.gst_compliance import DispatchCheckResponse
from app.tax.services.gst_compliance import GstComplianceService
from app.trade_licences.api.override import (
    LicenceOverrideReason,
    authorised_override,
)

router = APIRouter(
    prefix="/api/v1/delivery-notes",
    tags=["Delivery Notes"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Carry the optional reason a lifecycle action was taken for."""

    reason: str | None = Field(default=None, max_length=500)


#: Why a near-expiry batch or a FEFO skip goes out, where the firm's batch
#: rules ask (backlog 79 row 6). A query parameter, as the licence override is:
#: dispatch has no body and every caller would change for one optional field.
BatchReason = Annotated[
    str | None,
    Query(
        max_length=500,
        description=(
            "Why a near-expiry batch, or a later batch ahead of an earlier "
            "one, is dispatched. Recorded in the audit trail."
        ),
    ),
]


DeliveryNoteViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_VIEW")
]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
DeliveryNoteReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("SALES_VIEW", "REPORT_VIEW")
]
DeliveryNoteCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CREATE")
]
DeliveryNoteUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_UPDATE")
]
DeliveryNoteApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_APPROVE")
]
DeliveryNoteCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CANCEL")
]
DeliveryNoteExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_EXPORT")
]
DeliveryNoteImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_IMPORT")
]


def _filters(
    *,
    sales_order_id: UUID | None,
    customer_id: UUID | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    status_value: DeliveryNoteStatus | None,
    delivery_from: date | None,
    delivery_to: date | None,
    include_deleted: bool,
    awaiting_delivery_proof: bool = False,
) -> DeliveryNoteListFilters:
    try:
        return DeliveryNoteListFilters.model_validate(
            {
                "sales_order_id": sales_order_id,
                "customer_id": customer_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "status": status_value,
                "delivery_from": delivery_from,
                "delivery_to": delivery_to,
                "include_deleted": include_deleted,
                "awaiting_delivery_proof": awaiting_delivery_proof,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("/transporters", response_model=ApiResponse[list[TransporterResponse]])
def list_transporters(
    scope: DeliveryNoteViewScope,
    db: Annotated[Session, Depends(get_db)],
    active_only: bool = False,
) -> ApiResponse[list[TransporterResponse]]:
    """Return the firm's transporters by name (backlog 87 #5)."""
    return ApiResponse(
        data=TransporterService(db).transporters(scope.firm_id, active_only=active_only)
    )


@router.post(
    "/transporters",
    response_model=ApiResponse[TransporterResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_transporter(
    data: TransporterWrite,
    scope: DeliveryNoteUpdateScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TransporterResponse]:
    """Add a transporter (backlog 87 #5)."""
    return ApiResponse(
        data=TransporterService(db).save(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.put(
    "/transporters/{transporter_id}",
    response_model=ApiResponse[TransporterResponse],
)
def update_transporter(
    transporter_id: UUID,
    data: TransporterWrite,
    scope: DeliveryNoteUpdateScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TransporterResponse]:
    """Change a transporter; notes already raised keep what they copied."""
    return ApiResponse(
        data=TransporterService(db).save(
            data,
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
            transporter_id=transporter_id,
        )
    )


@router.delete("/transporters/{transporter_id}", response_model=ApiResponse[None])
def delete_transporter(
    transporter_id: UUID,
    scope: DeliveryNoteUpdateScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    """Remove a transporter the firm no longer uses (backlog 87 #5)."""
    TransporterService(db).delete(
        transporter_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Transporter deleted.")


@router.get("", response_model=PaginatedResponse[DeliveryNoteResponse])
def list_delivery_notes(
    scope: DeliveryNoteViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "delivery_note_number", "delivery_date", "status", "grand_total", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    sales_order_id: UUID | None = None,
    customer_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    status_value: Annotated[DeliveryNoteStatus | None, Query(alias="status")] = None,
    delivery_from: date | None = None,
    delivery_to: date | None = None,
    include_deleted: bool = False,
    awaiting_delivery_proof: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteResponse]:
    """List delivery notes for the visible firm scope.

    ``awaiting_delivery_proof`` narrows it to notes whose goods have left
    with no proof of delivery recorded (backlog 67 row 6).
    """
    params = PaginationParams(page=page, page_size=page_size)
    service = DeliveryNoteService(db)
    rows, total = service.list_notes(
        firm_scope=scope.firm_id,
        filters=_filters(
            sales_order_id=sales_order_id,
            customer_id=customer_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            status_value=status_value,
            delivery_from=delivery_from,
            delivery_to=delivery_to,
            include_deleted=include_deleted,
            awaiting_delivery_proof=awaiting_delivery_proof,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=service.note_responses(rows),
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[DeliveryNoteSummary])
def delivery_note_summary(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteSummary]:
    """Return aggregate delivery note values for the visible firm scope."""
    return ApiResponse(data=DeliveryNoteService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "",
    response_model=ApiResponse[DeliveryNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_delivery_note(
    data: DeliveryNoteCreate,
    scope: DeliveryNoteCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    """Create one delivery note."""
    service = DeliveryNoteService(db)
    row = service.create_note(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.note_response(row))


# Declared above the `/{{id}}` route below on purpose: FastAPI matches in
# declaration order, so that route read "export" as an id and answered 422.
# Unreachable from the day it was written until 2026-08-22.
@router.get("/export")
def export_delivery_notes(
    scope: DeliveryNoteExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export matching delivery notes as CSV."""
    csv_content = DeliveryNoteService(db).export_notes_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=delivery_notes.csv"},
    )


class DispatchSheetRequest(BaseModel):
    """The delivery notes a pick list or loading sheet covers (SEL-13)."""

    model_config = ConfigDict(extra="forbid")

    note_ids: list[UUID] = Field(min_length=1, max_length=300)


def _pdf(content: bytes, filename: str) -> StreamingResponse:
    """Send a PDF to open in a viewer rather than save."""
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/pick-list", response_class=StreamingResponse)
def delivery_pick_list(
    data: DispatchSheetRequest,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Print what to pick for the chosen notes, by product and batch (SEL-13)."""
    return _pdf(
        DispatchSheetService(db).pick_list_pdf(scope.firm_id, data.note_ids),
        "pick-list.pdf",
    )


@router.post("/loading-sheet", response_class=StreamingResponse)
def delivery_loading_sheet(
    data: DispatchSheetRequest,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Print each vehicle's drops in round order, with what to collect (SEL-13)."""
    return _pdf(
        DispatchSheetService(db).loading_sheet_pdf(scope.firm_id, data.note_ids),
        "loading-sheet.pdf",
    )


@router.post("/bulk-approve", response_model=ApiResponse[BulkActionResult])
def bulk_approve_delivery_notes(
    data: BulkApproveRequest,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked delivery notes, each on its own (backlog 56 A).

    Each goes through the single approval's own service and commits on its
    own: a refused one is reported with the reason and the rest go ahead.
    One that needs a licence override is refused here -- the override is a
    reason given for one document, on its own screen.
    """
    service = DeliveryNoteService(db)

    def act(document_id: UUID) -> None:
        service.approve_note(
            document_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
        db.commit()

    return ApiResponse(
        data=run_each(
            db,
            data.items,
            load=lambda document_id: service.get_note(
                document_id, firm_scope=scope.firm_id
            ),
            act=act,
            number=lambda row: row.delivery_note_number,
        )
    )


@router.post("/bulk-cancel", response_model=ApiResponse[BulkActionResult])
def bulk_cancel_delivery_notes(
    data: BulkCancelRequest,
    scope: DeliveryNoteCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Cancel the ticked delivery notes with one reason, each on its own (56 A)."""
    service = DeliveryNoteService(db)

    def act(document_id: UUID) -> None:
        service.cancel_note(
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
            load=lambda document_id: service.get_note(
                document_id, firm_scope=scope.firm_id
            ),
            act=act,
            number=lambda row: row.delivery_note_number,
        )
    )


@router.put("/{note_id}", response_model=ApiResponse[DeliveryNoteResponse])
def update_delivery_note(
    note_id: UUID,
    data: DeliveryNoteUpdate,
    scope: DeliveryNoteUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[DeliveryNoteResponse]:
    """Replace one delivery note."""
    service = DeliveryNoteService(db)
    assert_version(
        service.get_note(note_id, firm_scope=scope.firm_id).version, expected_version
    )
    row = service.update_note(
        note_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/approve", response_model=ApiResponse[DeliveryNoteResponse])
def approve_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
    licence_override_reason: LicenceOverrideReason = None,
) -> ApiResponse[DeliveryNoteResponse]:
    """Approve one delivery note."""
    service = DeliveryNoteService(db)
    row = service.approve_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        licence_override_reason=authorised_override(scope, licence_override_reason),
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/dispatch", response_model=ApiResponse[DeliveryNoteResponse])
def dispatch_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
    batch_reason: BatchReason = None,
) -> ApiResponse[DeliveryNoteResponse]:
    """Dispatch one delivery note.

    ``batch_reason`` answers the firm's batch rules where they ask why a
    near-expiry batch or a FEFO skip goes out (backlog 79 row 6).
    """
    service = DeliveryNoteService(db)
    row = service.dispatch_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        batch_reason=batch_reason,
    )
    return ApiResponse(data=service.note_response(row))


@router.get("/{note_id}/batch-check", response_model=ApiResponse[DispatchBatchCheck])
def check_delivery_note_batches(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DispatchBatchCheck]:
    """Say what dispatching this note would meet under the batch rules (79)."""
    return ApiResponse(
        data=DeliveryNoteService(db).batch_check(note_id, firm_scope=scope.firm_id)
    )


@router.get(
    "/{note_id}/dispatch-check", response_model=ApiResponse[DispatchCheckResponse]
)
def check_delivery_note_dispatch(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DispatchCheckResponse]:
    """Say what dispatching this note by hand would meet (backlog 77 row 2)."""
    row = DeliveryNoteService(db).get_note(note_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=GstComplianceService(db).dispatch_check(
            scope.firm_id,
            note_number=row.delivery_note_number,
            challan_reason=row.challan_reason or "SALE",
        )
    )


@router.post(
    "/{note_id}/dispatch-and-invoice",
    response_model=ApiResponse[SalesInvoiceResponse],
)
def dispatch_and_invoice_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
    batch_reason: BatchReason = None,
) -> ApiResponse[SalesInvoiceResponse]:
    """Dispatch one approved note and raise and approve its bill, together.

    Backlog 77 row 2: the invoice exists when the goods leave (CGST s.31).
    Dispatching and approving a bill both take SALES_APPROVE; raising the bill
    takes SALES_INVOICE_CREATE as well, the code `POST /sales-invoices` asks
    for (D-ROLE-2).
    """
    if not scope.principal.has_permission("SALES_INVOICE_CREATE"):
        raise AuthorizationError(
            "Dispatch and invoice raises a bill, which needs SALES_INVOICE_CREATE."
        )
    service = SalesInvoiceService(db)
    row = service.dispatch_and_invoice(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        batch_reason=batch_reason,
    )
    return ApiResponse(
        data=service.invoice_response(row),
        message=f"Dispatched and invoiced as {row.invoice_number}.",
    )


@router.post("/{note_id}/complete", response_model=ApiResponse[DeliveryNoteResponse])
def complete_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    """Complete one delivery note."""
    service = DeliveryNoteService(db)
    row = service.complete_note(
        note_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.note_response(row))


@router.post(
    "/{note_id}/proof-of-delivery",
    response_model=ApiResponse[DeliveryNoteResponse],
)
def record_delivery_proof(
    note_id: UUID,
    data: DeliveryProofWrite,
    scope: DeliveryNoteUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    """Record that the customer received a dispatched note (backlog 67 row 6).

    SALES_UPDATE, not SALES_APPROVE: a proof records a fact the paper
    shows -- who signed for the goods, and when -- and the clerk who files
    the signed challan is not the person who approves sales.
    """
    service = DeliveryNoteService(db)
    row = service.record_delivery_proof(
        note_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/cancel", response_model=ApiResponse[DeliveryNoteResponse])
def cancel_delivery_note(
    note_id: UUID,
    data: ActionReasonRequest,
    scope: DeliveryNoteCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    """Cancel one delivery note."""
    service = DeliveryNoteService(db)
    row = service.cancel_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/close", response_model=ApiResponse[DeliveryNoteResponse])
def close_delivery_note(
    note_id: UUID,
    data: ActionReasonRequest,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    """Close one delivery note."""
    service = DeliveryNoteService(db)
    row = service.close_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.note_response(row))


@router.get(
    "/{note_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_delivery_challan(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Render one delivery note as the challan that travels with the goods.

    Viewing is the permission: the challan states what the screen already
    shows, and whoever hands paperwork to a driver is not necessarily the
    person who may approve a dispatch.
    """
    pdf, filename = DeliveryChallanPrintService(db).render(
        note_id, firm_scope=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            # `inline` so a viewer opens it rather than dropping a file the
            # user then has to find.
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{note_id}", response_model=ApiResponse[DeliveryNoteResponse])
def get_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    """Return one delivery note."""
    service = DeliveryNoteService(db)
    row = service.get_note(note_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row))


@router.get(
    "/{note_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def delivery_note_history(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    """Return the lifecycle timeline for one delivery note."""
    rows = DeliveryNoteService(db).timeline(
        note_id=note_id, firm_scope=scope.firm_id, page=1, page_size=200
    )[0]
    return ApiResponse(
        data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows]
    )


@router.get(
    "/reports/register", response_model=PaginatedResponse[DeliveryNoteRegisterRecord]
)
def delivery_note_register(
    scope: DeliveryNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteRegisterRecord]:
    """Return the delivery note register report for the visible firm scope."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        DeliveryNoteService(db).register_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/pending", response_model=ApiResponse[list[DeliveryNoteRegisterRecord]]
)
def pending_delivery_notes(
    scope: DeliveryNoteReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteRegisterRecord]]:
    """List the notes raised and not yet sent out, one flat row each."""
    return ApiResponse(
        data=DeliveryNoteService(db).register_report(
            firm_scope=scope.firm_id,
            statuses=(
                DeliveryNoteStatus.DRAFT.value,
                DeliveryNoteStatus.APPROVED.value,
            ),
        )
    )


@router.get(
    "/reports/partial",
    response_model=PaginatedResponse[DeliveryNoteOrderProgressRecord],
)
def partial_delivery_report(
    scope: DeliveryNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteOrderProgressRecord]:
    """Return the partial delivery report for the visible firm scope."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        DeliveryNoteService(db).partially_delivered_orders(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.get(
    "/reports/by-route", response_model=PaginatedResponse[DeliveryNoteByDimensionRecord]
)
def delivery_by_route(
    scope: DeliveryNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteByDimensionRecord]:
    """Total delivered value and count per route."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        DeliveryNoteService(db).by_route_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/by-salesman",
    response_model=PaginatedResponse[DeliveryNoteByDimensionRecord],
)
def delivery_by_salesman(
    scope: DeliveryNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteByDimensionRecord]:
    """Total delivered value and count per salesman."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        DeliveryNoteService(db).by_salesman_report(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.get(
    "/reports/by-warehouse",
    response_model=PaginatedResponse[DeliveryNoteByDimensionRecord],
)
def delivery_by_warehouse(
    scope: DeliveryNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteByDimensionRecord]:
    """Total delivered value and count per warehouse."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        DeliveryNoteService(db).by_warehouse_report(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[DeliveryNoteResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_delivery_notes(
    scope: DeliveryNoteImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[DeliveryNoteResponse]]:
    """Import a validated batch of delivery notes atomically."""
    if format != "json":
        raise ValidationError("Only JSON import is supported for delivery notes.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = DeliveryNoteService(db)
    rows = service.import_notes(
        DeliveryNoteImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=service.note_responses(rows))
