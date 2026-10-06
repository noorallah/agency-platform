"""Contracts for supplier free-goods schemes (PG-11)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupplierSchemeSchema(BaseModel):
    """Base contract: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class SupplierSchemeCreate(SupplierSchemeSchema):
    """Set a scheme up: buy so many of a product, get so many free."""

    #: Blank is a scheme from every supplier of the product.
    vendor_id: UUID | None = None
    product_id: UUID
    buy_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    free_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    #: Blank gives the same product free.
    free_product_id: UUID | None = None
    valid_from: date
    #: Blank runs until the scheme is switched off.
    valid_to: date | None = None
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class SupplierSchemeUpdate(SupplierSchemeSchema):
    """Change a scheme; a field left out is left alone, null clears it."""

    vendor_id: UUID | None = None
    product_id: UUID | None = None
    buy_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    free_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    free_product_id: UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SupplierSchemeResponse(SupplierSchemeSchema):
    """One scheme, with the names a grid shows."""

    id: UUID
    vendor_id: UUID | None
    #: Null with ``vendor_id``: every supplier.
    vendor_code: str | None
    vendor_name: str | None
    product_id: UUID
    product_code: str
    product_name: str
    buy_quantity: Decimal
    free_quantity: Decimal
    free_product_id: UUID | None
    #: The product given free: the same product when ``free_product_id`` is
    #: null.
    free_product_code: str
    free_product_name: str
    #: "10+2", or "10 + 1 Bucket" for another product.
    label: str
    valid_from: date
    valid_to: date | None
    is_active: bool
    #: Active and in force today.
    in_force: bool
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class SupplierSchemeSuggestion(SupplierSchemeSchema):
    """Free goods of another product a priced order line earns (PG-11).

    Offered on the order preview, never written by it: the client adds the
    line (``product_id`` = ``free_product_id``, ordered 0, free
    ``free_quantity``, ``scheme_id``) if the buyer accepts it.
    """

    #: The order line whose quantity earns the free goods.
    line_number: int
    scheme_id: UUID
    scheme_label: str
    free_product_id: UUID
    free_product_code: str
    free_product_name: str
    free_quantity: Decimal
    #: The line already carrying these free goods (same product and scheme),
    #: if the order has one; its free quantity may differ from
    #: ``free_quantity`` after the paid line's quantity changed.
    existing_line_number: int | None = None
    #: The unit ``free_quantity`` is in where the free goods are of the paid
    #: line's **own** product (D-PRC-39): its stock unit, because 2 pieces
    #: earned by a line of 2 BOX cannot go on the box line. The line added
    #: for it is saved in this unit whatever unit it is sent in. Null for
    #: free goods of another product.
    free_uom_id: UUID | None = None
