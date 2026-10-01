"""Firm-scoped REST endpoints for debit notes.

Literal paths are declared **above** `/{note_id}`, because FastAPI matches in
declaration order.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
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
from app.debit_note.schemas import (
    DebitNoteCancel,
    DebitNoteClaimableLine,
    DebitNoteCreate,
    DebitNoteRegisterRecord,
    DebitNoteResponse,
    DebitNoteStatusEnum,
    DebitNoteUpdate,
)
from app.debit_note.services import DebitNoteService

router = APIRouter(
    prefix="/api/v1/debit-notes",
    tags=["Debit Notes"],
    responses=STANDARD_ERROR_RESPONSES,
)

DebitNoteViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("DEBIT_NOTE_VIEW")
]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`.
DebitNoteReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("DEBIT_NOTE_VIEW", "REPORT_VIEW")
]
DebitNoteManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("DEBIT_NOTE_MANAGE")
]
#: Approving a debit note reduces what the firm owes a supplier and reverses
#: input tax it has claimed -- a separate authority from drafting one, the
#: split `CREDIT_NOTE_APPROVE` makes on the selling side.
DebitNoteApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("DEBIT_NOTE_APPROVE")
]


@router.get("", response_model=PaginatedResponse[DebitNoteResponse])
def list_debit_notes(
    scope: DebitNoteViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    vendor_id: Annotated[UUID | None, Query()] = None,
    purchase_invoice_id: Annotated[UUID | None, Query()] = None,
    note_status: Annotated[DebitNoteStatusEnum | None, Query(alias="status")] = None,
    search: str | None = None,
    debit_note_from: date | None = None,
    debit_note_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DebitNoteResponse]:
    """Return a page of debit notes."""
    service = DebitNoteService(db)
    rows, total = service.list_notes(
        firm_scope=scope.firm_id,
        page=page,
        page_size=page_size,
        vendor_id=vendor_id,
        purchase_invoice_id=purchase_invoice_id,
        status=note_status,
        search=search,
        debit_note_from=debit_note_from,
        debit_note_to=debit_note_to,
    )
    return PaginatedResponse(
        data=service.note_responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[DebitNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_debit_note(
    payload: DebitNoteCreate,
    scope: DebitNoteManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[DebitNoteResponse]:
    """Raise a debit note against an approved supplier bill."""
    service = DebitNoteService(db)
    row = service.create_note(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row), message="Debit note raised.")


@router.post("/preview", response_model=ApiResponse[DebitNoteResponse])
def preview_debit_note(
    payload: DebitNoteCreate,
    scope: DebitNoteManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DebitNoteResponse]:
    """Price a debit note as raising it would, and save nothing."""
    return ApiResponse(
        data=DebitNoteService(db).preview_note(
            payload, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.get(
    "/claimable-lines",
    response_model=ApiResponse[list[DebitNoteClaimableLine]],
)
def debit_note_claimable_lines(
    purchase_invoice_id: UUID,
    scope: DebitNoteManageScope,
    excluding_note_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DebitNoteClaimableLine]]:
    """Return a bill's lines and how much of each may still be claimed."""
    return ApiResponse(
        data=DebitNoteService(db).claimable_lines(
            purchase_invoice_id,
            firm_id=scope.firm_id,
            excluding_note_id=excluding_note_id,
        )
    )


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[DebitNoteRegisterRecord],
)
def debit_note_register(
    scope: DebitNoteReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DebitNoteRegisterRecord]:
    """Every debit note raised, with the bill it claims against."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        DebitNoteService(db).register_report(firm_scope=scope.firm_id, window=window)
    )


@router.get("/{note_id}", response_model=ApiResponse[DebitNoteResponse])
def get_debit_note(
    note_id: UUID,
    scope: DebitNoteViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[DebitNoteResponse]:
    """Return one debit note."""
    service = DebitNoteService(db)
    row = service.get_note(note_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row))


@router.put("/{note_id}", response_model=ApiResponse[DebitNoteResponse])
def update_debit_note(
    note_id: UUID,
    payload: DebitNoteUpdate,
    scope: DebitNoteManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DebitNoteResponse]:
    """Change a debit note that has not been approved."""
    service = DebitNoteService(db)
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
    return ApiResponse(data=service.note_response(row), message="Debit note updated.")


@router.post("/{note_id}/approve", response_model=ApiResponse[DebitNoteResponse])
def approve_debit_note(
    note_id: UUID,
    scope: DebitNoteApproveScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DebitNoteResponse]:
    """Post the claim and reduce what the bill still owes."""
    service = DebitNoteService(db)
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
        data=service.note_response(row), message="Debit note approved and posted."
    )


@router.post("/{note_id}/cancel", response_model=ApiResponse[DebitNoteResponse])
def cancel_debit_note(
    note_id: UUID,
    payload: DebitNoteCancel,
    scope: DebitNoteApproveScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DebitNoteResponse]:
    """Withdraw a debit note, reversing whatever it did."""
    service = DebitNoteService(db)
    row = service.cancel_note(
        note_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row), message="Debit note cancelled.")
