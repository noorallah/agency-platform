"""Contracts for a supplier's catalogue (BUY-4, decision A101)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupplierProductWrite(BaseModel):
    """Add one dated catalogue row; a change is a new row, never an edit."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    supplier_product_code: str | None = Field(default=None, max_length=120)
    supplier_product_name: str | None = Field(default=None, max_length=200)
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    pack_size: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    minimum_order_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    effective_from: date
    remarks: str | None = Field(default=None, max_length=1000)


class SupplierProductResponse(BaseModel):
    """One catalogue row, with the product named."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    vendor_id: UUID
    product_id: UUID
    product_code: str
    product_name: str
    supplier_product_code: str | None
    supplier_product_name: str | None
    unit_price: Decimal | None
    pack_size: Decimal | None
    minimum_order_quantity: Decimal | None
    lead_time_days: int | None
    effective_from: date
    remarks: str | None
    #: Whether it is the row in force today, rather than history or future.
    is_current: bool
    created_at: datetime
