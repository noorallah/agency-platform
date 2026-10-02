"""Firm-scoped REST endpoints for debit notes to customers.

Literal paths are declared **above** `/{note_id}`, because FastAPI matches in
declaration order.
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
from app.customer_debit_note.schemas import (
    CustomerDebitNoteCreate,
    CustomerDebitNoteRegisterRecord,
    CustomerDebitNoteResponse,
    CustomerDebitNoteStatusEnum,
    CustomerDebitNoteUpdate,
)
from app.customer_debit_note.services import CustomerDebitNoteService
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.sales_invoice.services.note_print_service import NotePrintService

router = APIRouter(
    prefix="/api/v1/customer-debit-notes",
    tags=["Customer Debit Notes"],
    responses=STANDARD_ERROR_RESPONSES,
)

ViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_DEBIT_NOTE_VIEW")
]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`.
ReportScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope("CUSTOMER_DEBIT_NOTE_VIEW", "REPORT_VIEW"),
]
ManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_DEBIT_NOTE_MANAGE")
]
#: Approving raises what a customer owes and the output tax the firm declares,
#: a separate authority from drafting -- the split the credit note makes.
ApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_DEBIT_NOTE_APPROVE")
]


@router.get("", response_model=PaginatedResponse[CustomerDebitNoteResponse])
def list_customer_debit_notes(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    customer_id: Annotated[UUID | None, Query()] = None,
    sales_invoice_id: Annotated[UUID | None, Query()] = None,
    note_status: Annotated[
        CustomerDebitNoteStatusEnum | None, Query(alias="status")
    ] = None,
    search: str | None = None,
    debit_note_from: date | None = None,
    debit_note_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerDebitNoteResponse]:
    """Return a page of debit notes to customers."""
    service = CustomerDebitNoteService(db)
    rows, total = service.list_notes(
        firm_scope=scope.firm_id,
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        sales_invoice_id=sales_invoice_id,
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
    response_model=ApiResponse[CustomerDebitNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_customer_debit_note(
    payload: CustomerDebitNoteCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerDebitNoteResponse]:
    """Raise a debit note against an approved invoice."""
    service = CustomerDebitNoteService(db)
    row = service.create_note(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row), message="Debit note raised.")


@router.post("/preview", response_model=ApiResponse[CustomerDebitNoteResponse])
def preview_customer_debit_note(
    payload: CustomerDebitNoteCreate,
    scope: ManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerDebitNoteResponse]:
    """Price a debit note as raising it would, and save nothing."""
    return ApiResponse(
        data=CustomerDebitNoteService(db).preview_note(
            payload, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[CustomerDebitNoteRegisterRecord],
)
def customer_debit_note_register(
    scope: ReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerDebitNoteRegisterRecord]:
    """Every debit note raised, with the invoice it charges."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        CustomerDebitNoteService(db).register_report(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.post("/bulk-approve", response_model=ApiResponse[BulkActionResult])
def bulk_approve_customer_debit_notes(
    data: BulkApproveRequest,
    scope: ApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked debit notes, each on its own."""
    service = CustomerDebitNoteService(db)

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
            number=lambda row: row.debit_note_number,
        )
    )


@router.get("/{note_id}", response_model=ApiResponse[CustomerDebitNoteResponse])
def get_customer_debit_note(
    note_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerDebitNoteResponse]:
    """Return one debit note."""
    service = CustomerDebitNoteService(db)
    row = service.get_note(note_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row))


@router.put("/{note_id}", response_model=ApiResponse[CustomerDebitNoteResponse])
def update_customer_debit_note(
    note_id: UUID,
    payload: CustomerDebitNoteUpdate,
    scope: ManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerDebitNoteResponse]:
    """Change a debit note that has not been approved."""
    service = CustomerDebitNoteService(db)
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


@router.post(
    "/{note_id}/approve", response_model=ApiResponse[CustomerDebitNoteResponse]
)
def approve_customer_debit_note(
    note_id: UUID,
    scope: ApproveScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerDebitNoteResponse]:
    """Post the charge and raise what the customer owes."""
    service = CustomerDebitNoteService(db)
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


@router.post("/{note_id}/cancel", response_model=ApiResponse[CustomerDebitNoteResponse])
def cancel_customer_debit_note(
    note_id: UUID,
    scope: ApproveScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerDebitNoteResponse]:
    """Withdraw a debit note, reversing whatever it did."""
    service = CustomerDebitNoteService(db)
    row = service.cancel_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.note_response(row), message="Debit note cancelled.")


@router.get(
    "/{note_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_note(
    note_id: UUID,
    scope: ViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Render the debit note as the PDF the customer is sent (77 row 11).

    In the invoice's layout, naming the invoice it corrects, with its IRN and
    signed QR once it is registered on the portal.
    """
    pdf, filename = NotePrintService(db).render(
        "DEBIT_NOTE", note_id, firm_scope=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
