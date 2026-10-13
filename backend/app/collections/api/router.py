"""Firm-scoped REST endpoints for collection follow-up (backlog 87 #8, SG-8).

Reading takes ``RECEIPT_VIEW`` and writing a promise ``RECEIPT_CREATE``: the
people who take the money in are the people who chase it, and a promise moves
no money, so it needs no grant of its own.

Handing bills to a collector and taking them back (backlog 122) takes
``COLLECTION_ASSIGN``, a code of its own: a collector who may record what he
collected must not be the one who decides which bills he carries. Reading who
carries what stays on ``RECEIPT_VIEW``.

A collector's own list (backlog 123) takes ``COLLECTION_OWN_VIEW`` and reads
the bills handed to **the caller**: whose bag it is comes from the token and
no parameter names anybody else. It is the one route here a person holding
neither receipt code can call.

The end-of-day line on a handed-out bill (backlog 124) has two doors. The
office writes any bill's line on ``RECEIPT_CREATE`` and the receipt is
recorded with it. A collector writes his own on ``COLLECTION_OWN_RECORD``,
for a bill in his own bag, and the receipt is recorded only where the firm
lets its collectors record; otherwise the office records it from the day's
sheet.

Every literal path is declared above ``/promises/{promise_id}/withdraw``.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.collections.schemas import (
    CollectionDaySheet,
    CollectionReturnCreate,
    CollectionReturnResponse,
    CollectionReturnWithdraw,
    CollectionSheetRow,
    HandedFilter,
    HandoverBillRow,
    HandoverCreate,
    HandoverMatching,
    HandoverResponse,
    HandoverResult,
    HandoverState,
    HandoverTakeBack,
    MyBillRow,
    PaymentPromiseCreate,
    PaymentPromiseResponse,
    PaymentPromiseWithdraw,
    PromiseStatus,
)
from app.collections.services import (
    BillHandoverService,
    CollectionReturnService,
    CollectionSheetService,
    PromiseService,
)
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants.core import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
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
CollectionAssignScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("COLLECTION_ASSIGN")
]
CollectionOwnScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("COLLECTION_OWN_VIEW")
]
CollectionOwnRecordScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("COLLECTION_OWN_RECORD")
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


@router.get("/my-bills", response_model=PaginatedResponse[MyBillRow])
def list_my_bills(
    scope: CollectionOwnScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[MyBillRow]:
    """List the unpaid bills handed to the caller, by customer.

    Beside each customer's, that customer's other unpaid bills, marked as not
    handed to the caller. Nothing of any other customer.
    """
    rows, total = BillHandoverService(db).my_bills_page(
        scope.firm_id,
        collector_id=scope.actor_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/my-bills/day-sheet", response_model=ApiResponse[CollectionDaySheet])
def my_day_sheet(
    scope: CollectionOwnScope,
    day: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionDaySheet]:
    """Return the caller's own lines for a day, and whether they add up."""
    return ApiResponse(
        data=CollectionReturnService(db).day_sheet(
            scope.firm_id, day=day, collector_id=scope.actor_id
        )
    )


@router.post(
    "/my-bills/returns",
    response_model=ApiResponse[CollectionReturnResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_my_return(
    data: CollectionReturnCreate,
    scope: CollectionOwnRecordScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionReturnResponse]:
    """Write today's line on a bill in the caller's own bag.

    The receipt is recorded with it only where the firm lets its collectors
    record; otherwise the line states what was taken and the office records
    the receipt.
    """
    return ApiResponse(
        data=CollectionReturnService(db).record(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id, own=True
        ),
        message="Line recorded.",
    )


@router.post(
    "/my-bills/returns/{return_id}/withdraw",
    response_model=ApiResponse[CollectionReturnResponse],
)
def withdraw_my_return(
    return_id: UUID,
    data: CollectionReturnWithdraw,
    scope: CollectionOwnRecordScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionReturnResponse]:
    """Take back a line of the caller's own, while no receipt stands on it."""
    return ApiResponse(
        data=CollectionReturnService(db).withdraw(
            return_id,
            data.reason,
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
            own=True,
        ),
        message="Line withdrawn.",
    )


@router.get("/day-sheet", response_model=ApiResponse[CollectionDaySheet])
def collection_day_sheet(
    scope: CollectionViewScope,
    day: Annotated[date | None, Query()] = None,
    collector_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionDaySheet]:
    """Return a day's lines, one collector's or all, and whether they add up.

    What the lines say was taken, what the receipts named on them took into
    the books, and the difference.
    """
    return ApiResponse(
        data=CollectionReturnService(db).day_sheet(
            scope.firm_id, day=day, collector_id=collector_id
        )
    )


@router.post(
    "/returns",
    response_model=ApiResponse[CollectionReturnResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_return(
    data: CollectionReturnCreate,
    scope: CollectionWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionReturnResponse]:
    """Write a day's line on any handed-out bill, and record its receipt."""
    return ApiResponse(
        data=CollectionReturnService(db).record(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id, own=False
        ),
        message="Line recorded.",
    )


@router.post(
    "/returns/{return_id}/receipt",
    response_model=ApiResponse[CollectionReturnResponse],
)
def record_return_receipt(
    return_id: UUID,
    scope: CollectionWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionReturnResponse]:
    """Record the receipt for a line that only states what was taken."""
    return ApiResponse(
        data=CollectionReturnService(db).record_receipt(
            return_id, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Receipt recorded.",
    )


@router.post(
    "/returns/{return_id}/withdraw",
    response_model=ApiResponse[CollectionReturnResponse],
)
def withdraw_return(
    return_id: UUID,
    data: CollectionReturnWithdraw,
    scope: CollectionWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CollectionReturnResponse]:
    """Take a day's line back, with the reason; the record stays."""
    return ApiResponse(
        data=CollectionReturnService(db).withdraw(
            return_id,
            data.reason,
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
            own=False,
        ),
        message="Line withdrawn.",
    )


@router.get("/handovers/bills", response_model=PaginatedResponse[HandoverBillRow])
def list_bills_to_hand_out(
    scope: CollectionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    handed: Annotated[HandedFilter, Query()] = HandedFilter.ALL,
    collector_id: Annotated[UUID | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    area: Annotated[str | None, Query(max_length=100)] = None,
    number_from: Annotated[str | None, Query(max_length=60)] = None,
    number_to: Annotated[str | None, Query(max_length=60)] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[HandoverBillRow]:
    """List the unpaid bills, each with who carries it, oldest first.

    Narrowed by the bill's date, the customer's area or city, a run of bill
    numbers of one series, a customer, and whether somebody carries it.
    """
    if date_from and date_to and date_to < date_from:
        raise ValidationError("The last day is before the first.")
    matching = HandoverMatching.model_construct(
        date_from=date_from,
        date_to=date_to,
        area=(area or "").strip() or None,
        number_from=(number_from or "").strip() or None,
        number_to=(number_to or "").strip() or None,
        customer_id=customer_id,
    )
    rows, total = BillHandoverService(db).bills_page(
        scope.firm_id,
        page=page,
        page_size=page_size,
        handed=handed,
        collector_id=collector_id,
        # Passed only when something is named, which is all its own check
        # asks; the date order is checked above.
        matching=matching if matching.model_dump(exclude_none=True) else None,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/handovers", response_model=PaginatedResponse[HandoverResponse])
def list_bill_handovers(
    scope: CollectionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    collector_id: Annotated[UUID | None, Query()] = None,
    state: Annotated[HandoverState | None, Query()] = None,
    handed_from: Annotated[date | None, Query()] = None,
    handed_to: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[HandoverResponse]:
    """List the handovers: bills still out first, then newest first."""
    rows, total = BillHandoverService(db).list_handovers(
        scope.firm_id,
        page=page,
        page_size=page_size,
        collector_id=collector_id,
        state=state,
        handed_from=handed_from,
        handed_to=handed_to,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "/handovers",
    response_model=ApiResponse[HandoverResult],
    status_code=status.HTTP_201_CREATED,
)
def hand_bills_to_a_collector(
    data: HandoverCreate,
    scope: CollectionAssignScope,
    db: Session = Depends(get_db),
) -> ApiResponse[HandoverResult]:
    """Hand unpaid bills to a collector: the ones ticked, or a bundle.

    It writes a note beside each bill and nothing else: no journal, no
    balance and no report changes.
    """
    result = BillHandoverService(db).hand_out(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=result, message=f"{result.bills} bill(s) handed out.")


@router.post("/handovers/take-back", response_model=ApiResponse[HandoverResult])
def take_bills_back(
    data: HandoverTakeBack,
    scope: CollectionAssignScope,
    db: Session = Depends(get_db),
) -> ApiResponse[HandoverResult]:
    """Take handed-out bills back into the office; the record stays."""
    result = BillHandoverService(db).take_back(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=result, message=f"{result.bills} bill(s) taken back.")
