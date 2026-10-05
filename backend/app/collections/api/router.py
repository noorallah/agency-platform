"""Firm-scoped REST endpoints for collection follow-up (backlog 87 #8, SG-8).

Reading takes ``RECEIPT_VIEW`` and writing a promise ``RECEIPT_CREATE``: the
people who take the money in are the people who chase it, and a promise moves
no money, so it needs no grant of its own.

Every literal path is declared above ``/promises/{promise_id}/withdraw``.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.collections.schemas import (
    CollectionSheetRow,
    PaymentPromiseCreate,
    PaymentPromiseResponse,
    PaymentPromiseWithdraw,
    PromiseStatus,
)
from app.collections.services import CollectionSheetService, PromiseService
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants.core import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse

router = APIRouter(
    prefix="/api/v1/collections",
    tags=["Collections"],
    responses=STANDARD_ERROR_RESPONSES,
)

CollectionViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("RECEIPT_VIEW")
]
CollectionWriteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("RECEIPT_CREATE")
]


@router.post(
    "/promises",
    response_model=ApiResponse[PaymentPromiseResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_payment_promise(
    data: PaymentPromiseCreate,
    scope: CollectionWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentPromiseResponse]:
    """Record what a customer promised to pay, on a bill or on the account."""
    return ApiResponse(
        data=PromiseService(db).record(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Promise recorded.",
    )


@router.get("/promises", response_model=PaginatedResponse[PaymentPromiseResponse])
def list_payment_promises(
    scope: CollectionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    customer_id: Annotated[UUID | None, Query()] = None,
    sales_invoice_id: Annotated[UUID | None, Query()] = None,
    promise_status: Annotated[PromiseStatus | None, Query(alias="status")] = None,
    due_from: Annotated[date | None, Query()] = None,
    due_to: Annotated[date | None, Query()] = None,
    collector_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PaymentPromiseResponse]:
    """List promises with what became of each, latest promised day first."""
    rows, total = PromiseService(db).list_promises(
        scope.firm_id,
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        sales_invoice_id=sales_invoice_id,
        status=promise_status,
        due_from=due_from,
        due_to=due_to,
        collector_id=collector_id,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get(
    "/promises/due-today",
    response_model=PaginatedResponse[PaymentPromiseResponse],
)
def list_promises_to_chase(
    scope: CollectionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    collector_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PaymentPromiseResponse]:
    """List the promises to chase today.

    Those promised for today and not yet paid, and the broken ones nobody has
    taken a newer promise on, oldest first.
    """
    rows, total = PromiseService(db).chase_list(
        scope.firm_id, page=page, page_size=page_size, collector_id=collector_id
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "/promises/{promise_id}/withdraw",
    response_model=ApiResponse[PaymentPromiseResponse],
)
def withdraw_payment_promise(
    promise_id: UUID,
    data: PaymentPromiseWithdraw,
    scope: CollectionWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentPromiseResponse]:
    """Take a promise back, with the reason; the record stays."""
    return ApiResponse(
        data=PromiseService(db).withdraw(
            promise_id,
            data.reason,
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
        ),
        message="Promise withdrawn.",
    )


@router.get("/sheet", response_model=PaginatedResponse[CollectionSheetRow])
def collection_sheet(
    scope: CollectionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    collector_id: Annotated[UUID | None, Query()] = None,
    route_id: Annotated[UUID | None, Query()] = None,
    as_of: Annotated[date | None, Query()] = None,
    overdue_only: Annotated[bool, Query()] = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CollectionSheetRow]:
    """List the bills still owing: by collector, then customer, then due date."""
    rows, total = CollectionSheetService(db).page(
        scope.firm_id,
        page=page,
        page_size=page_size,
        collector_id=collector_id,
        route_id=route_id,
        as_of=as_of,
        overdue_only=overdue_only,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/sheet/pdf", response_class=StreamingResponse)
def collection_sheet_pdf(
    scope: CollectionViewScope,
    collector_id: Annotated[UUID | None, Query()] = None,
    route_id: Annotated[UUID | None, Query()] = None,
    as_of: Annotated[date | None, Query()] = None,
    overdue_only: Annotated[bool, Query()] = False,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Print the collection sheet for a collector to carry."""
    content = CollectionSheetService(db).pdf(
        scope.firm_id,
        collector_id=collector_id,
        route_id=route_id,
        as_of=as_of,
        overdue_only=overdue_only,
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="collection-sheet.pdf"'},
    )
