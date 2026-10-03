"""Endpoints for price levels, product prices per level, and line prices (SEL-9)."""

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
from app.core.database.dependencies import get_db
from app.core.exceptions import ResourceNotFoundError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.customers.models import Customer
from app.pricing.schemas.price_level import (
    PriceLevelResponse,
    PriceLevelWrite,
    ProductLevelRateResponse,
    ProductLevelRatesWrite,
    UnitPriceResponse,
    UnitPricesResponse,
)
from app.pricing.services.price_levels import PriceLevelService
from app.pricing.services.unit_price import UnitPriceResolver

router = APIRouter(
    prefix="/api/v1/price-levels",
    tags=["Pricing"],
    responses=STANDARD_ERROR_RESPONSES,
)

LevelViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PRICE_LIST_VIEW")]
LevelManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRICE_LIST_MANAGE")
]
#: Whoever raises a sales document needs the price its lines start at.
LinePriceScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope(
        "PRICE_LIST_VIEW",
        "SALES_QUOTATION_CREATE",
        "SALES_ORDER_CREATE",
        "SALES_INVOICE_CREATE",
    ),
]


@router.get("", response_model=ApiResponse[list[PriceLevelResponse]])
def list_price_levels(
    scope: LevelViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PriceLevelResponse]]:
    """List the firm's price levels in their order."""
    return ApiResponse(
        data=[
            PriceLevelResponse.model_validate(row)
            for row in PriceLevelService(db).list_levels(scope.firm_id)
        ]
    )


@router.post(
    "",
    response_model=ApiResponse[PriceLevelResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_price_level(
    data: PriceLevelWrite,
    scope: LevelManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PriceLevelResponse]:
    """Create one price level: Retail, Wholesale, Dealer."""
    row = PriceLevelService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=PriceLevelResponse.model_validate(row))


@router.get("/unit-prices", response_model=ApiResponse[UnitPricesResponse])
def unit_prices(
    scope: LinePriceScope,
    product_ids: Annotated[list[UUID], Query(min_length=1, max_length=200)],
    on: Annotated[date, Query()],
    customer_id: Annotated[UUID | None, Query()] = None,
    territory_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[UnitPricesResponse]:
    """Return the price each product's line starts at for this customer.

    A fixed rate on a price list for the customer, then the customer's (or
    its group's) price level, then the product's own price (SEL-9). What a
    document fills a blank price with, offered here for the editor to show.
    """
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None or customer.firm_id != scope.firm_id:
            raise ResourceNotFoundError("Customer not found.")
    resolver = UnitPriceResolver(
        db,
        firm_id=scope.firm_id,
        customer_id=customer_id,
        territory_id=territory_id,
        on=on,
    )
    prices = []
    for product_id in dict.fromkeys(product_ids):
        found = resolver.price(product_id)
        prices.append(
            UnitPriceResponse(
                product_id=product_id, unit_price=found.price, source=found.source
            )
        )
    return ApiResponse(
        data=UnitPricesResponse(price_level_id=resolver.level_id, prices=prices)
    )


@router.get(
    "/products/{product_id}",
    response_model=ApiResponse[list[ProductLevelRateResponse]],
)
def product_level_rates(
    product_id: UUID,
    scope: LevelViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ProductLevelRateResponse]]:
    """Return one product's price at each level that prices it."""
    return ApiResponse(
        data=PriceLevelService(db).product_rates(product_id, firm_id=scope.firm_id)
    )


@router.put(
    "/products/{product_id}",
    response_model=ApiResponse[list[ProductLevelRateResponse]],
)
def replace_product_level_rates(
    product_id: UUID,
    data: ProductLevelRatesWrite,
    scope: LevelManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ProductLevelRateResponse]]:
    """Replace one product's prices per level; a level left out has none."""
    rows = PriceLevelService(db).replace_product_rates(
        product_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=rows)


@router.put("/{level_id}", response_model=ApiResponse[PriceLevelResponse])
def update_price_level(
    level_id: UUID,
    data: PriceLevelWrite,
    scope: LevelManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PriceLevelResponse]:
    """Replace one price level's details."""
    row = PriceLevelService(db).update(
        level_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=PriceLevelResponse.model_validate(row))


@router.delete("/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price_level(
    level_id: UUID,
    scope: LevelManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire a price level no customer or group buys at."""
    PriceLevelService(db).delete(
        level_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
