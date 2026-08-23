"""Request and response shapes for price lists."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PricingSchema(BaseModel):
    """Base model for the pricing module."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PriceListItemWrite(PricingSchema):
    """One product's rate on a list."""

    product_id: UUID
    discount_percent: Decimal = Field(ge=0, le=100, max_digits=9, decimal_places=4)


class PriceListWrite(PricingSchema):
    """Create or replace one price list."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None

    #: Both absent is the firm's own standing list. Naming both is refused
    #: below: an arrangement that is somehow customer-scoped and route-scoped
    #: at once has no defensible precedence against one that is only the first.
    customer_id: UUID | None = None
    territory_id: UUID | None = None

    effective_from: date
    effective_to: date | None = None
    status: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|INACTIVE)$")

    items: list[PriceListItemWrite] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def _scope_is_one_thing(self) -> PriceListWrite:
        """Refuse a list scoped to a customer and a territory at once."""
        if self.customer_id is not None and self.territory_id is not None:
            raise ValueError("A price list names a customer or a territory, not both.")
        return self

    @model_validator(mode="after")
    def _window_is_not_backwards(self) -> PriceListWrite:
        """Refuse a window that ends before it starts."""
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be earlier than effective_from.")
        return self


class PriceListItemResponse(PricingSchema):
    """One rate, as stored."""

    id: UUID
    product_id: UUID
    product_code: str | None = None
    product_name: str | None = None
    discount_percent: Decimal


class PriceListResponse(PricingSchema):
    """One price list and the rates it holds."""

    id: UUID
    version: int
    firm_id: UUID
    code: str
    name: str
    description: str | None
    customer_id: UUID | None
    customer_name: str | None = None
    territory_id: UUID | None
    territory_name: str | None = None
    effective_from: date
    effective_to: date | None
    status: str
    items: list[PriceListItemResponse]
    created_at: datetime
    updated_at: datetime


class PriceListFilters(PricingSchema):
    """Narrow a price list listing."""

    customer_id: UUID | None = None
    territory_id: UUID | None = None
    status: str | None = None
    include_deleted: bool = False
