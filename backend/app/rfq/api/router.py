"""Requests for quotation, supplier quotations and the comparison (PG-8)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.purchase.schemas import PurchaseOrderResponse
from app.purchase.services import PurchaseService
from app.rfq.schemas import (
    RfqCancel,
    RfqComparisonResponse,
    RfqCreate,
    RfqResponse,
    RfqSelectionsWrite,
    RfqUpdate,
    SupplierQuotationResponse,
    SupplierQuotationWrite,
)
from app.rfq.services import RfqService

router = APIRouter(
    prefix="/api/v1/rfqs",
    tags=["Requests for quotation"],
    responses=STANDARD_ERROR_RESPONSES,
)

RfqViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("RFQ_VIEW")]
RfqManageScope = Annotated[ResolvedFirmScope, firm_permission_scope("RFQ_MANAGE")]
#: Raising orders from the chosen quotes also takes the right to raise orders.
PurchaseCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CREATE")
]


def _one(
    service: RfqService, response: Response, rfq_id: UUID, firm_id: UUID
) -> RfqResponse:
    """Return one RFQ's response and publish its version."""
    row = service.get(rfq_id, firm_id=firm_id)
    set_etag(response, row)
    return service.responses([row])[0]


@router.get("", response_model=PaginatedResponse[RfqResponse])
def list_rfqs(
    scope: RfqViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[RfqResponse]:
    """Return one page of the firm's RFQs, newest first."""
    params = PaginationParams(page=page, page_size=page_size)
    service = RfqService(db)
    rows, total = service.page(
        scope.firm_id,
        status=status_filter,
        search=search,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.responses(rows), pagination=params.metadata(total)
    )


@router.post(
    "",
    response_model=ApiResponse[RfqResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_rfq(
    data: RfqCreate,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqResponse]:
    """Raise a draft RFQ."""
    service = RfqService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


# Declared above `/{rfq_id}`: FastAPI matches in declaration order.
@router.post(
    "/from-requisition/{requisition_id}",
    response_model=ApiResponse[RfqResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_rfq_from_requisition(
    requisition_id: UUID,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqResponse]:
    """Start a draft RFQ from an approved requisition."""
    service = RfqService(db)
    row = service.create_from_requisition(
        requisition_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get("/{rfq_id}", response_model=ApiResponse[RfqResponse])
def get_rfq(
    rfq_id: UUID,
    scope: RfqViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqResponse]:
    """Return one RFQ."""
    return ApiResponse(data=_one(RfqService(db), response, rfq_id, scope.firm_id))


@router.put("/{rfq_id}", response_model=ApiResponse[RfqResponse])
def update_rfq(
    rfq_id: UUID,
    data: RfqUpdate,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[RfqResponse]:
    """Change a draft RFQ; a field left out is left alone."""
    service = RfqService(db)
    assert_version(service.get(rfq_id, firm_id=scope.firm_id).version, expected_version)
    row = service.update(rfq_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{rfq_id}/send", response_model=ApiResponse[RfqResponse])
def send_rfq(
    rfq_id: UUID,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqResponse]:
    """Send a draft RFQ; its lines and suppliers are fixed from here."""
    service = RfqService(db)
    row = service.send(rfq_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{rfq_id}/cancel", response_model=ApiResponse[RfqResponse])
def cancel_rfq(
    rfq_id: UUID,
    data: RfqCancel,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqResponse]:
    """Call off a draft or sent RFQ."""
    service = RfqService(db)
    row = service.cancel(
        rfq_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{rfq_id}/close", response_model=ApiResponse[RfqResponse])
def close_rfq(
    rfq_id: UUID,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqResponse]:
    """Close a sent RFQ without raising any order."""
    service = RfqService(db)
    row = service.close(rfq_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get(
    "/{rfq_id}/quotations",
    response_model=ApiResponse[list[SupplierQuotationResponse]],
)
def list_rfq_quotations(
    rfq_id: UUID,
    scope: RfqViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SupplierQuotationResponse]]:
    """Return every supplier quotation entered on the RFQ."""
    service = RfqService(db)
    return ApiResponse(
        data=service.quotation_responses(
            service.quotations(rfq_id, firm_id=scope.firm_id)
        )
    )


@router.put(
    "/{rfq_id}/quotations/{vendor_id}",
    response_model=ApiResponse[SupplierQuotationResponse],
)
def save_rfq_quotation(
    rfq_id: UUID,
    vendor_id: UUID,
    data: SupplierQuotationWrite,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierQuotationResponse]:
    """Enter or replace an invited supplier's quotation on a sent RFQ."""
    service = RfqService(db)
    row = service.save_quotation(
        rfq_id, vendor_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.quotation_responses([row])[0])


@router.get("/{rfq_id}/comparison", response_model=ApiResponse[RfqComparisonResponse])
def compare_rfq_quotations(
    rfq_id: UUID,
    scope: RfqViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqComparisonResponse]:
    """Return every supplier's landed rate per line, the lowest marked."""
    return ApiResponse(data=RfqService(db).comparison(rfq_id, firm_id=scope.firm_id))


@router.put("/{rfq_id}/selections", response_model=ApiResponse[RfqComparisonResponse])
def save_rfq_selections(
    rfq_id: UUID,
    data: RfqSelectionsWrite,
    scope: RfqManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RfqComparisonResponse]:
    """Replace the quote chosen per line; a reason is needed off the lowest."""
    service = RfqService(db)
    row = service.set_selections(
        rfq_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.comparison(row.id, firm_id=scope.firm_id))


@router.post(
    "/{rfq_id}/raise-orders",
    response_model=ApiResponse[list[PurchaseOrderResponse]],
    status_code=status.HTTP_201_CREATED,
)
def raise_rfq_orders(
    rfq_id: UUID,
    scope: RfqManageScope,
    _orders: PurchaseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseOrderResponse]]:
    """Raise one draft order per chosen supplier and close the RFQ."""
    orders = RfqService(db).raise_orders(
        rfq_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=PurchaseService(db).order_responses(orders),
        message=f"{len(orders)} draft purchase order(s) raised.",
    )
