"""Endpoints for a firm's price lists."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.pricing.schemas import PriceListFilters, PriceListResponse, PriceListWrite
from app.pricing.services import PriceListService

router = APIRouter(prefix="/api/v1/price-lists", tags=["Pricing"])

PriceListViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRICE_LIST_VIEW")
]
PriceListManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRICE_LIST_MANAGE")
]


@router.get("", response_model=PaginatedResponse[PriceListResponse])
def list_price_lists(
    scope: PriceListViewScope,
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str, Query(max_length=200)] = "",
    customer_id: Annotated[UUID | None, Query()] = None,
    territory_id: Annotated[UUID | None, Query()] = None,
    list_status: Annotated[str | None, Query(alias="status")] = None,
) -> PaginatedResponse[PriceListResponse]:
    """List the firm's price lists.

    The bounds are declared on the query parameters rather than by building
    `PaginationParams` in the body: constructing it here turns an over-cap
    request into a 500 instead of a 422 naming the limit.
    """
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = PriceListService(db).list_price_lists(
        firm_scope=scope.firm_id,
        pagination=params,
        search=search,
        filters=PriceListFilters(
            customer_id=customer_id,
            territory_id=territory_id,
            status=list_status,
        ),
    )
    return PaginatedResponse(data=rows, pagination=params.metadata(total))


@router.post(
    "",
    response_model=ApiResponse[PriceListResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_price_list(
    data: PriceListWrite,
    scope: PriceListManageScope,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[PriceListResponse]:
    """Create one price list and the rates it holds."""
    service = PriceListService(db)
    row = service.create(data, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.response(row))


@router.get("/{price_list_id}", response_model=ApiResponse[PriceListResponse])
def get_price_list(
    price_list_id: UUID,
    scope: PriceListViewScope,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[PriceListResponse]:
    """Return one price list."""
    service = PriceListService(db)
    row = service.get(price_list_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.response(row))


@router.put("/{price_list_id}", response_model=ApiResponse[PriceListResponse])
def update_price_list(
    price_list_id: UUID,
    data: PriceListWrite,
    scope: PriceListManageScope,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    expected_version: ExpectedVersion = None,
) -> ApiResponse[PriceListResponse]:
    """Revise one price list.

    The rates are replaced by what is sent, so a lost race costs every rate
    somebody entered -- which is why this takes `If-Match`.
    """
    service = PriceListService(db)
    assert_version(
        service.get(price_list_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update(
        price_list_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.response(row))


@router.delete("/{price_list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price_list(
    price_list_id: UUID,
    scope: PriceListManageScope,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Withdraw one price list.

    Documents already priced under it are untouched: the rate is stored on the
    line, so withdrawing the arrangement cannot rewrite what was agreed.
    """
    PriceListService(db).delete(
        price_list_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
