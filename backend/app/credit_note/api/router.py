"""Firm-scoped REST endpoints for credit notes.

Literal paths are declared **above** `/{note_id}`, because FastAPI matches in
declaration order and nine endpoints in eight routers were unreachable until
2026-08-22 for exactly that reason.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.credit_note.schemas import (
    CreditNoteByCustomerRecord,
    CreditNoteByReasonRecord,
    CreditNoteCreate,
    CreditNoteRegisterRecord,
    CreditNoteResponse,
    CreditNoteStatusEnum,
    CreditNoteUpdate,
)
from app.credit_note.services import CreditNoteService
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.sales_invoice.services.note_print_service import NotePrintService

router = APIRouter(
    prefix="/api/v1/credit-notes",
    tags=["Credit Notes"],
    responses=STANDARD_ERROR_RESPONSES,
)

CreditNoteViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CREDIT_NOTE_VIEW")
]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
CreditNoteReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("CREDIT_NOTE_VIEW", "REPORT_VIEW")
]
CreditNoteManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CREDIT_NOTE_MANAGE")
]
#: Approving a credit note reduces what a customer owes and reverses tax the
#: firm has declared. That is a separate authority from drafting one, exactly
#: as paying a commission payout is separate from accruing it.
CreditNoteApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CREDIT_NOTE_APPROVE")
]


@router.get("", response_model=PaginatedResponse[CreditNoteResponse])
def list_credit_notes(
    scope: CreditNoteViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    customer_id: Annotated[UUID | None, Query()] = None,
    note_status: Annotated[CreditNoteStatusEnum | None, Query(alias="status")] = None,
    search: str | None = None,
    credit_note_from: date | None = None,
    credit_note_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CreditNoteResponse]:
    """Return a page of credit notes."""
    service = CreditNoteService(db)
    rows, total = service.list_notes(
        firm_scope=scope.firm_id,
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        status=note_status,
        search=search,
        credit_note_from=credit_note_from,
        credit_note_to=credit_note_to,
    )
    return PaginatedResponse(
        data=service.note_responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[CreditNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_credit_note(
    payload: CreditNoteCreate,
    scope: CreditNoteManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditNoteResponse]:
    """Raise a credit note against an approved invoice."""
    service = CreditNoteService(db)
    row = service.create_note(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row), message="Credit note raised.")


@router.post("/preview", response_model=ApiResponse[CreditNoteResponse])
def preview_credit_note(
    payload: CreditNoteCreate,
    scope: CreditNoteManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditNoteResponse]:
    """Price a credit note as raising it would, and save nothing.

    What the credit note screen calls as its amounts are typed, so the tax
    it shows coming off is the one the note will reverse.
    """
    return ApiResponse(
        data=CreditNoteService(db).preview_note(
            payload, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[CreditNoteRegisterRecord],
)
def credit_note_register(
    scope: CreditNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CreditNoteRegisterRecord]:
    """Every credit note raised, with the invoice it credits."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        CreditNoteService(db).register_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/by-customer",
    response_model=PaginatedResponse[CreditNoteByCustomerRecord],
)
def credit_notes_by_customer(
    scope: CreditNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CreditNoteByCustomerRecord]:
    """Credited value and count per customer, cancelled notes excluded."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        CreditNoteService(db).by_customer_report(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.get(
    "/reports/by-reason",
    response_model=PaginatedResponse[CreditNoteByReasonRecord],
)
def credit_notes_by_reason(
    scope: CreditNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CreditNoteByReasonRecord]:
    """Report what the firm is crediting for, and how much of it."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        CreditNoteService(db).by_reason_report(firm_scope=scope.firm_id, window=window)
    )


@router.post("/bulk-approve", response_model=ApiResponse[BulkActionResult])
def bulk_approve_credit_notes(
    data: BulkApproveRequest,
    scope: CreditNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked credit notes, each on its own (backlog 56 A).

    Each goes through the single approval's own service and commits on its
    own: a refused one is reported with the reason and the rest go ahead.
    One that needs a licence override is refused here -- the override is a
    reason given for one document, on its own screen.
    """
    service = CreditNoteService(db)

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
            number=lambda row: row.credit_note_number,
        )
    )


@router.get("/{note_id}", response_model=ApiResponse[CreditNoteResponse])
def get_credit_note(
    note_id: UUID,
    scope: CreditNoteViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditNoteResponse]:
    """Return one credit note."""
    service = CreditNoteService(db)
    row = service.get_note(note_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row))


@router.put("/{note_id}", response_model=ApiResponse[CreditNoteResponse])
def update_credit_note(
    note_id: UUID,
    payload: CreditNoteUpdate,
    scope: CreditNoteManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditNoteResponse]:
    """Change a credit note that has not been approved."""
    service = CreditNoteService(db)
    row = service.update_note(
        note_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row), message="Credit note updated.")


@router.post("/{note_id}/approve", response_model=ApiResponse[CreditNoteResponse])
def approve_credit_note(
    note_id: UUID,
    scope: CreditNoteApproveScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditNoteResponse]:
    """Post the credit and reduce what the customer owes."""
    service = CreditNoteService(db)
    row = service.approve_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.note_response(row), message="Credit note approved and posted."
    )


@router.post("/{note_id}/cancel", response_model=ApiResponse[CreditNoteResponse])
def cancel_credit_note(
    note_id: UUID,
    scope: CreditNoteApproveScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditNoteResponse]:
    """Withdraw a credit note, reversing whatever it did."""
    service = CreditNoteService(db)
    row = service.cancel_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.note_response(row), message="Credit note cancelled."
    )


@router.get(
    "/{note_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_note(
    note_id: UUID,
    scope: CreditNoteViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Render the credit note as the PDF the customer is sent (77 row 11).

    In the invoice's layout, naming the invoice it corrects, with its IRN and
    signed QR once it is registered on the portal.
    """
    pdf, filename = NotePrintService(db).render(
        "CREDIT_NOTE", note_id, firm_scope=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
