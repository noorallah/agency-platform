"""API contracts for unit sets (backlog 89)."""

from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.core.validation.common import refuse_explicit_nulls
from app.uom.schemas.uom import UomSchema

_FACTOR = Field(default=None, gt=0, max_digits=24, decimal_places=10)


class UnitSetCreate(UomSchema):
    """Add a unit set of the firm's own."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_uom_id: UUID
    inventory_uom_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    sales_uom_id: UUID | None = None
    minimum_sales_uom_id: UUID | None = None
    default_receiving_uom_id: UUID | None = None
    default_dispatch_uom_id: UUID | None = None
    allow_decimal: bool = True
    #: One purchase unit is this many stock units.
    conversion_factor: Decimal | None = _FACTOR
    is_active: bool = True
    #: The goods types whose products are offered this set first; none
    #: offers it to every product.
    goods_type_ids: list[UUID] = Field(default_factory=list, max_length=200)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: str) -> str:
        """Match names regardless of the spaces around them."""
        return value.strip() if isinstance(value, str) else value


class UnitSetUpdate(UomSchema):
    """Change a unit set of the firm's own; absent means leave alone."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    sales_uom_id: UUID | None = None
    minimum_sales_uom_id: UUID | None = None
    default_receiving_uom_id: UUID | None = None
    default_dispatch_uom_id: UUID | None = None
    allow_decimal: bool | None = None
    conversion_factor: Decimal | None = _FACTOR
    is_active: bool | None = None
    goods_type_ids: list[UUID] | None = Field(default=None, max_length=200)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        """Match names regardless of the spaces around them."""
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _no_null_on_a_required_field(self) -> "UnitSetUpdate":
        """Refuse a null except on an optional unit, the note or the factor."""
        refuse_explicit_nulls(
            self,
            nullable={
                "description",
                "inventory_uom_id",
                "purchase_uom_id",
                "sales_uom_id",
                "minimum_sales_uom_id",
                "default_receiving_uom_id",
                "default_dispatch_uom_id",
                "conversion_factor",
            },
        )
        return self


class ProductUnitSetOption(UomSchema):
    """One unit set as the product form offers it."""

    id: UUID
    name: str
    base_uom_id: UUID
    inventory_uom_id: UUID | None
    purchase_uom_id: UUID | None
    sales_uom_id: UUID | None
    minimum_sales_uom_id: UUID | None
    default_receiving_uom_id: UUID | None
    default_dispatch_uom_id: UUID | None
    allow_decimal: bool
    conversion_factor: Decimal | None
    #: Empty offers the set to every product.
    goods_type_ids: list[UUID]


class UnitSetResponse(ProductUnitSetOption):
    """One unit set as the firm sees it."""

    #: Null is the shared catalogue, which a firm reads and cannot change.
    firm_id: UUID | None
    description: str | None
    is_active: bool
    #: Optimistic-concurrency counter, echoed back as ``If-Match``.
    version: int
