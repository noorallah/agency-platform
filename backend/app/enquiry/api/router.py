"""Firm-scoped REST endpoints for enquiries (SEL-10)."""

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
from app.core.constants.core import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.enquiry.services import (
    EnquiryConvertWrite,
    EnquiryFollowUpWrite,
    EnquiryLostWrite,
    EnquiryResponse,
    EnquiryService,
    EnquiryWrite,
    LostReasonRow,
)

router = APIRouter(
    prefix="/api/v1/enquiries",
    tags=["Enquiries"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: An enquiry is the step before a quotation, so it is read, raised and
#: worked under the quotation's own codes rather than new ones nobody holds.
EnquiryViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
EnquiryReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("SALES_VIEW", "REPORT_VIEW")
]
EnquiryCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_QUOTATION_CREATE")
]
EnquiryUpdateScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_UPDATE")]


@router.get("", response_model=PaginatedResponse[EnquiryResponse])
def list_enquiries(
    scope: EnquiryViewScope,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    salesman_id: Annotated[UUID | None, Query()] = None,
) -> PaginatedResponse[EnquiryResponse]:
    """Return one page of the firm's enquiries, newest first.

    Paged like every other document list (D-SELL-63): ``page`` and
    ``page_size`` were ignored and every enquiry came back.
    """
    service = EnquiryService(db)
    rows, total = service.list_page(
        scope.firm_id,
        page=page,
        page_size=page_size,
        status=status_filter,
        salesman_id=salesman_id,
    )
    return PaginatedResponse(
        data=service.responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/follow-ups-due", response_model=PaginatedResponse[EnquiryResponse])
def follow_ups_due(
    scope: EnquiryViewScope,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    on: Annotated[date | None, Query()] = None,
    salesman_id: Annotated[UUID | None, Query()] = None,
) -> PaginatedResponse[EnquiryResponse]:
    """Return a page of the live enquiries to follow up by a day.

    Today by default, soonest first. Paged with the standard bounds, as the
    enquiry list is (D-SELL-63): it answered every row whatever was asked.
    """
    service = EnquiryService(db)
    rows, total = service.list_page(
        scope.firm_id,
        page=page,
        page_size=page_size,
        salesman_id=salesman_id,
        due_on=on or utc_now().date(),
    )
    return PaginatedResponse(
        data=service.responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/reports/lost", response_model=ApiResponse[list[LostReasonRow]])
def lost_reasons(
    scope: EnquiryReportScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[list[LostReasonRow]]:
    """Why enquiries were lost in a period, by reason, with their value."""
    return ApiResponse(
        data=EnquiryService(db).lost_reasons(
            scope.firm_id, from_date=from_date, to_date=to_date
        )
    )


@router.post(
    "",
    response_model=ApiResponse[EnquiryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_enquiry(
    data: EnquiryWrite,
    scope: EnquiryCreateScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[EnquiryResponse]:
    """Record an enquiry."""
    service = EnquiryService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Enquiry saved.")


@router.get("/{enquiry_id}", response_model=ApiResponse[EnquiryResponse])
def get_enquiry(
    enquiry_id: UUID,
    scope: EnquiryViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[EnquiryResponse]:
    """Return one enquiry with its lines and follow-ups."""
    service = EnquiryService(db)
    row = service.get(enquiry_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.put("/{enquiry_id}", response_model=ApiResponse[EnquiryResponse])
def update_enquiry(
    enquiry_id: UUID,
    data: EnquiryWrite,
    scope: EnquiryUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[EnquiryResponse]:
    """Rewrite an open enquiry."""
    service = EnquiryService(db)
    row = service.update(
        enquiry_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Enquiry saved.")


@router.post(
    "/{enquiry_id}/follow-ups",
    response_model=ApiResponse[EnquiryResponse],
    status_code=status.HTTP_201_CREATED,
)
def log_follow_up(
    enquiry_id: UUID,
    data: EnquiryFollowUpWrite,
    scope: EnquiryUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EnquiryResponse]:
    """Log a contact with the buyer and the next follow-up date."""
    service = EnquiryService(db)
    row = service.follow_up(
        enquiry_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Follow-up logged.")


@router.post("/{enquiry_id}/lost", response_model=ApiResponse[EnquiryResponse])
def mark_lost(
    enquiry_id: UUID,
    data: EnquiryLostWrite,
    scope: EnquiryUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EnquiryResponse]:
    """Close an enquiry as lost, with the reason."""
    service = EnquiryService(db)
    row = service.mark_lost(
        enquiry_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Marked lost.")


@router.post("/{enquiry_id}/convert", response_model=ApiResponse[EnquiryResponse])
def convert_enquiry(
    enquiry_id: UUID,
    data: EnquiryConvertWrite,
    scope: EnquiryCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EnquiryResponse]:
    """Raise the quotation from the enquiry; a prospect becomes a customer."""
    service = EnquiryService(db)
    row = service.convert(
        enquiry_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Quotation raised.")
