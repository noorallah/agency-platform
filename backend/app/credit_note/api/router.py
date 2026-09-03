"""Firm-scoped REST endpoints for credit notes.

Literal paths are declared **above** `/{note_id}`, because FastAPI matches in
declaration order and nine endpoints in eight routers were unreachable until
2026-08-22 for exactly that reason.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.credit_note.schemas import (
    CreditNoteCreate,
    CreditNoteResponse,
    CreditNoteStatusEnum,
    CreditNoteUpdate,
)
from app.credit_note.services import CreditNoteService

router = APIRouter(
    prefix="/api/v1/credit-notes",
    tags=["Credit Notes"],
    responses=STANDARD_ERROR_RESPONSES,
)

CreditNoteViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CREDIT_NOTE_VIEW")
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
    )
    return PaginatedResponse(
        data=[service.note_response(row) for row in rows],
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
