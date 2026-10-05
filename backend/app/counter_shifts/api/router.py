"""Firm-scoped REST endpoints for counter shifts (backlog 87 #7, SG-7).

Opening, reading and closing one's own till take ``SALES_INVOICE_CREATE``,
the code that raises a bill: whoever sells at the counter runs its drawer,
and a shift moves no money by being opened. Closing somebody else's till
takes ``SALES_APPROVE`` as well. The list, one shift and its report open to
whoever may read sales or holds ``REPORT_VIEW``.

Every literal path is declared above ``/{shift_id}``.
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
from app.core.concurrency import publish_version
from app.core.constants.core import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.counter_shifts.models import CounterShiftStatus
from app.counter_shifts.schemas import (
    CounterShiftClose,
    CounterShiftOpen,
    CounterShiftResponse,
)
from app.counter_shifts.services import CounterShiftService

router = APIRouter(
    prefix="/api/v1/counter-shifts",
    tags=["Counter Shifts"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: Whoever raises a bill at the counter runs its drawer.
CounterShiftCashierScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_INVOICE_CREATE")
]
CounterShiftViewScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope("SALES_VIEW", "REPORT_VIEW", "SALES_INVOICE_CREATE"),
]
#: The code that lets somebody close a till that is not their own.
CLOSE_OTHERS_CODE = "SALES_APPROVE"


@router.post(
    "/open",
    response_model=ApiResponse[CounterShiftResponse],
    status_code=status.HTTP_201_CREATED,
)
def open_counter_shift(
    data: CounterShiftOpen,
    scope: CounterShiftCashierScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CounterShiftResponse]:
    """Open the caller's till with its float; 409 if they have one open."""
    service = CounterShiftService(db)
    row = service.open(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    publish_version(response, row.version)
    return ApiResponse(data=service.response(row), message="Shift opened.")


@router.get("/current", response_model=ApiResponse[CounterShiftResponse | None])
def current_counter_shift(
    scope: CounterShiftCashierScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CounterShiftResponse | None]:
    """Return the caller's open shift with what it has taken, or nothing."""
    service = CounterShiftService(db)
    row = service.current(firm_id=scope.firm_id, cashier_id=scope.actor_id)
    return ApiResponse(data=None if row is None else service.response(row))


@router.get("", response_model=PaginatedResponse[CounterShiftResponse])
def list_counter_shifts(
    scope: CounterShiftViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    shift_status: Annotated[CounterShiftStatus | None, Query(alias="status")] = None,
    cashier_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CounterShiftResponse]:
    """List the firm's shifts with what each took, the latest opened first."""
    service = CounterShiftService(db)
    rows, total = service.list_shifts(
        scope.firm_id,
        page=page,
        page_size=page_size,
        status=shift_status,
        cashier_id=cashier_id,
        from_date=from_date,
        to_date=to_date,
    )
    return PaginatedResponse(
        data=service.responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/{shift_id}", response_model=ApiResponse[CounterShiftResponse])
def get_counter_shift(
    shift_id: UUID,
    scope: CounterShiftViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CounterShiftResponse]:
    """Return one shift with its summary: bills, tenders by mode, the cash."""
    service = CounterShiftService(db)
    row = service.get(shift_id, firm_id=scope.firm_id)
    publish_version(response, row.version)
    return ApiResponse(data=service.response(row))


@router.post("/{shift_id}/close", response_model=ApiResponse[CounterShiftResponse])
def close_counter_shift(
    shift_id: UUID,
    data: CounterShiftClose,
    scope: CounterShiftCashierScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CounterShiftResponse]:
    """Close a till on what was counted; a difference posts one journal.

    Bills the cashier parked and never recalled are reported in
    ``summary.held_bills`` as a warning. They do not stop the close: a held
    bill is a draft, and no money was taken for it.
    """
    service = CounterShiftService(db)
    row = service.close(
        shift_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        may_close_others=scope.principal.has_permission(CLOSE_OTHERS_CODE),
    )
    publish_version(response, row.version)
    return ApiResponse(data=service.response(row), message="Shift closed.")


@router.get("/{shift_id}/report", response_class=StreamingResponse)
def counter_shift_report(
    shift_id: UUID,
    scope: CounterShiftViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Print the shift report: takings by mode, the count and the difference."""
    content = CounterShiftService(db).report_pdf(shift_id, firm_id=scope.firm_id)
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="shift-report.pdf"'},
    )
