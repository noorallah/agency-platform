"""Request contract for printing product labels (STK-16)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.products.services.barcode_labels import MAX_LABELS, LabelLayout


class LabelItemRequest(BaseModel):
    """One product and how many of its labels to print."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    copies: int = Field(default=1, ge=1, le=MAX_LABELS)


class ProductLabelRequest(BaseModel):
    """The products to label, the stock they print on and what they show."""

    model_config = ConfigDict(extra="forbid")

    items: list[LabelItemRequest] = Field(min_length=1, max_length=500)
    layout: LabelLayout = LabelLayout.A4_65
    #: Positions of the first A4 sheet already used last time.
    skip: int = Field(default=0, ge=0, le=64)
    show_price: bool = True
