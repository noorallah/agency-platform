"""Bills of Entry: customs duty on imports (PG-12 part B, backlog 86 #5)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.bill_of_entry.schemas import (
    BillOfEntryCancel,
    BillOfEntryCreate,
    BillOfEntryResponse,
    BillOfEntryUpdate,
)
from app.bill_of_entry.services import BillOfEntryService
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse

router = APIRouter(
    prefix="/api/v1/bills-of-entry",
    tags=["Bills of Entry"],
    responses=STANDARD_ERROR_RESPONSES,
)

ViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("BILL_OF_ENTRY_VIEW")]
ManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("BILL_OF_ENTRY_MANAGE")
]
#: Posting books the duty and claims the IGST, and cancelling a posted one
#: reverses that: the same code as approving a bill.
ApproveScope = Annotated[ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")]


@router.get("", response_model=PaginatedResponse[BillOfEntryResponse])
def list_bills_of_entry(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    vendor_id: UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BillOfEntryResponse]:
    """Return one page of the firm's Bills of Entry, newest first.

    ``search`` matches the customs number, our number and the port code;
    ``from_date`` and ``to_date`` bound the Bill of Entry date, inclusive.
    """
    params = PaginationParams(page=page, page_size=page_size)
    service = BillOfEntryService(db)
    rows, total = service.page(
        scope.firm_id,
        status=status_filter,
        vendor_id=vendor_id,
        from_date=from_date,
        to_date=to_date,
        search=search,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.responses(rows), pagination=params.metadata(total)
    )


@router.post(
    "",
    response_model=ApiResponse[BillOfEntryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_bill_of_entry(
    data: BillOfEntryCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[BillOfEntryResponse]:
    """Type a draft Bill of Entry; each line's duty is worked out on save."""
    service = BillOfEntryService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get("/{boe_id}", response_model=ApiResponse[BillOfEntryResponse])
def get_bill_of_entry(
    boe_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[BillOfEntryResponse]:
    """Return one Bill of Entry with its lines and linked documents."""
    service = BillOfEntryService(db)
    row = service.get(boe_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.put("/{boe_id}", response_model=ApiResponse[BillOfEntryResponse])
def update_bill_of_entry(
    boe_id: UUID,
    data: BillOfEntryUpdate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BillOfEntryResponse]:
    """Change a draft Bill of Entry; a field left out is left alone."""
    service = BillOfEntryService(db)
    assert_version(service.get(boe_id, firm_id=scope.firm_id).version, expected_version)
    row = service.update(boe_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.delete("/{boe_id}", response_model=ApiResponse[None])
def delete_bill_of_entry(
    boe_id: UUID,
    scope: ManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Delete a draft Bill of Entry."""
    BillOfEntryService(db).delete(
        boe_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Bill of Entry deleted.")


@router.post("/{boe_id}/post", response_model=ApiResponse[BillOfEntryResponse])
def post_bill_of_entry(
    boe_id: UUID,
    scope: ApproveScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BillOfEntryResponse]:
    """Book the duty onto the receipts' stock and claim the IGST."""
    service = BillOfEntryService(db)
    assert_version(service.get(boe_id, firm_id=scope.firm_id).version, expected_version)
    row = service.post(boe_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Posted.")


@router.post("/{boe_id}/cancel", response_model=ApiResponse[BillOfEntryResponse])
def cancel_bill_of_entry(
    boe_id: UUID,
    data: BillOfEntryCancel,
    scope: ApproveScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[BillOfEntryResponse]:
    """Withdraw a Bill of Entry; a posted one has its posting reversed."""
    service = BillOfEntryService(db)
    row = service.cancel(
        boe_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Cancelled.")
