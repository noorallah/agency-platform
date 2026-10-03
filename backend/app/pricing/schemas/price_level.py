"""Price level, product rate and unit price schemas (SEL-9)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.pricing.schemas.price_list import PricingSchema


class PriceLevelWrite(PricingSchema):
    """Create or replace one price level."""

    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, value: str) -> str:
        """Hold codes upper case, as every master code is."""
        return value.strip().upper() if isinstance(value, str) else value


class PriceLevelResponse(PricingSchema):
    """One stored price level."""

    id: UUID
    code: str
    name: str
    sort_order: int
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ProductLevelRate(PricingSchema):
    """One product's price at one level."""

    price_level_id: UUID
    rate: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class ProductLevelRatesWrite(PricingSchema):
    """Replace a product's prices per level; a level left out has none."""

    rates: list[ProductLevelRate] = Field(default_factory=list, max_length=100)


class ProductLevelRateResponse(PricingSchema):
    """One product's price at one level, with the level's name."""

    price_level_id: UUID
    price_level_code: str
    price_level_name: str
    rate: Decimal


class UnitPriceResponse(PricingSchema):
    """The price a line for this customer starts at (SEL-9)."""

    product_id: UUID
    unit_price: Decimal
    #: PRICE_LIST, PRICE_LEVEL or PRODUCT.
    source: str


class UnitPricesResponse(PricingSchema):
    """The prices a document's lines start at, and the customer's level."""

    price_level_id: UUID | None
    prices: list[UnitPriceResponse]
