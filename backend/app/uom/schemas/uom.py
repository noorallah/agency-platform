"""Validated contracts for enterprise UOM and packaging APIs."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UomSchema(BaseModel):
    """Shared strict schema behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class UomCreate(UomSchema):
    """Fields accepted when adding a unit to the catalogue."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    symbol: str | None = Field(default=None, max_length=30)
    dimension: str = Field(default="COUNT", min_length=1, max_length=30)
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)
    is_decimal_allowed: bool = True


class UomUpdate(UomSchema):
    """Fields that may be changed on an existing unit."""

    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    symbol: str | None = Field(default=None, max_length=30)
    dimension: str | None = Field(default=None, min_length=1, max_length=30)
    status: str | None = Field(default=None, min_length=1, max_length=20)
    is_decimal_allowed: bool | None = None


class UomResponse(UomSchema):
    """A unit of measure as exposed by the API."""

    id: UUID
    code: str
    name: str
    symbol: str | None
    dimension: str
    status: str
    is_decimal_allowed: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class UomGroupCreate(UomSchema):
    """Fields accepted when creating a group of related units."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)


class UomGroupUpdate(UomSchema):
    """Fields that may be changed on an existing group."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    status: str | None = Field(default=None, min_length=1, max_length=20)


class UomGroupResponse(UomSchema):
    """A unit group as exposed by the API."""

    id: UUID
    code: str
    name: str
    description: str | None
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class PackagingTypeCreate(UomSchema):
    """Fields accepted when adding a packaging type."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)


class PackagingTypeUpdate(UomSchema):
    """Fields that may be changed on a packaging type."""

    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    status: str | None = Field(default=None, min_length=1, max_length=20)


class PackagingTypeResponse(UomSchema):
    """A packaging type as exposed by the API."""

    id: UUID
    code: str
    name: str
    description: str | None
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ConversionRuleCreate(UomSchema):
    """A new conversion rule version for one unit pair."""

    business_profile_id: UUID | None = None
    product_id: UUID | None = None
    from_uom_id: UUID
    to_uom_id: UUID
    conversion_factor: Decimal = Field(gt=0, max_digits=24)
    rounding_mode: str = Field(default="HALF_UP", min_length=1, max_length=20)
    precision_scale: int = Field(default=4, ge=0, le=10)
    effective_from: date
    effective_to: date | None = None
    version: int = Field(default=1, ge=1)
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)
    reason: str | None = None


class ConversionRuleUpdate(UomSchema):
    """Fields that may be changed on a conversion rule."""

    business_profile_id: UUID | None = None
    product_id: UUID | None = None
    from_uom_id: UUID | None = None
    to_uom_id: UUID | None = None
    conversion_factor: Decimal | None = Field(default=None, gt=0, max_digits=24)
    rounding_mode: str | None = Field(default=None, min_length=1, max_length=20)
    precision_scale: int | None = Field(default=None, ge=0, le=10)
    effective_from: date | None = None
    effective_to: date | None = None
    version: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, min_length=1, max_length=20)
    reason: str | None = None


class ConversionRuleResponse(UomSchema):
    """A conversion rule as exposed by the API."""

    id: UUID
    firm_id: UUID
    business_profile_id: UUID | None
    product_id: UUID | None
    from_uom_id: UUID
    to_uom_id: UUID
    conversion_factor: Decimal
    rounding_mode: str
    precision_scale: int
    effective_from: date
    effective_to: date | None
    # The published rule version, which is the column named version_number: the
    # entity's own ``version`` is the optimistic-concurrency counter and means
    # nothing to a caller.
    version: int = Field(validation_alias="version_number")
    status: str
    reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ConversionRuleListFilters(UomSchema):
    """Filters narrowing a conversion rule listing."""

    product_id: UUID | None = None
    business_profile_id: UUID | None = None
    from_uom_id: UUID | None = None
    to_uom_id: UUID | None = None
    status: str | None = None
    effective_on: date | None = None


class IndustryTemplateCreate(UomSchema):
    """Fields accepted when adding an industry template."""

    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=140)
    industry_type: str = Field(min_length=1, max_length=60)
    template_payload: dict[str, object] = Field(default_factory=dict)
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)
    is_system: bool = False


class IndustryTemplateUpdate(UomSchema):
    """Fields that may be changed on an industry template."""

    code: str | None = Field(default=None, min_length=1, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=140)
    industry_type: str | None = Field(default=None, min_length=1, max_length=60)
    template_payload: dict[str, object] | None = None
    status: str | None = Field(default=None, min_length=1, max_length=20)
    is_system: bool | None = None


class IndustryTemplateResponse(UomSchema):
    """An industry UOM template as exposed by the API."""

    id: UUID
    code: str
    name: str
    industry_type: str
    template_payload: dict[str, object]
    status: str
    is_system: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class BusinessProfileUomDefaultUpsert(UomSchema):
    """Default unit behaviour to store for a business profile."""

    base_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    sales_uom_id: UUID | None = None
    allow_fraction: bool = False
    allow_decimal: bool = True


class BusinessProfileUomDefaultResponse(UomSchema):
    """A profile's default unit behaviour as exposed by the API."""

    id: UUID
    firm_id: UUID | None
    business_profile_id: UUID
    base_uom_id: UUID | None
    inventory_uom_id: UUID | None
    purchase_uom_id: UUID | None
    sales_uom_id: UUID | None
    allow_fraction: bool
    allow_decimal: bool
    created_at: datetime
    updated_at: datetime


class ProductUomConfigUpsert(UomSchema):
    """Per-product unit selection and physical dimensions to store."""

    base_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    sales_uom_id: UUID | None = None
    default_receiving_uom_id: UUID | None = None
    default_dispatch_uom_id: UUID | None = None
    minimum_sales_uom_id: UUID | None = None
    allow_fraction: bool = False
    allow_decimal: bool = True
    weight: Decimal | None = Field(default=None, ge=0, max_digits=18)
    volume: Decimal | None = Field(default=None, ge=0, max_digits=18)
    length: Decimal | None = Field(default=None, ge=0, max_digits=18)
    width: Decimal | None = Field(default=None, ge=0, max_digits=18)
    height: Decimal | None = Field(default=None, ge=0, max_digits=18)


class ProductUomConfigResponse(UomSchema):
    """A product's unit configuration as exposed by the API."""

    id: UUID
    firm_id: UUID
    product_id: UUID
    base_uom_id: UUID | None
    inventory_uom_id: UUID | None
    purchase_uom_id: UUID | None
    sales_uom_id: UUID | None
    default_receiving_uom_id: UUID | None
    default_dispatch_uom_id: UUID | None
    minimum_sales_uom_id: UUID | None
    allow_fraction: bool
    allow_decimal: bool
    weight: Decimal | None
    volume: Decimal | None
    length: Decimal | None
    width: Decimal | None
    height: Decimal | None
    created_at: datetime
    updated_at: datetime


class PackagingLevelCreate(UomSchema):
    """One level of a product's packaging hierarchy."""

    parent_level_id: UUID | None = None
    packaging_type_id: UUID | None = None
    uom_id: UUID | None = None
    level_name: str = Field(min_length=1, max_length=120)
    conversion_to_base_factor: Decimal = Field(gt=0, max_digits=24)
    barcode: str | None = Field(default=None, max_length=120)
    qr_code: str | None = Field(default=None, max_length=300)
    gtin: str | None = Field(default=None, max_length=30)
    ean: str | None = Field(default=None, max_length=30)
    upc: str | None = Field(default=None, max_length=30)
    weight: Decimal | None = Field(default=None, ge=0, max_digits=18)
    volume: Decimal | None = Field(default=None, ge=0, max_digits=18)
    length: Decimal | None = Field(default=None, ge=0, max_digits=18)
    width: Decimal | None = Field(default=None, ge=0, max_digits=18)
    height: Decimal | None = Field(default=None, ge=0, max_digits=18)
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)
    display_order: int = Field(default=0, ge=0)


class PackagingLevelUpdate(UomSchema):
    """Fields that may be changed on a packaging level."""

    parent_level_id: UUID | None = None
    packaging_type_id: UUID | None = None
    uom_id: UUID | None = None
    level_name: str | None = Field(default=None, min_length=1, max_length=120)
    conversion_to_base_factor: Decimal | None = Field(default=None, gt=0, max_digits=24)
    barcode: str | None = Field(default=None, max_length=120)
    qr_code: str | None = Field(default=None, max_length=300)
    gtin: str | None = Field(default=None, max_length=30)
    ean: str | None = Field(default=None, max_length=30)
    upc: str | None = Field(default=None, max_length=30)
    weight: Decimal | None = Field(default=None, ge=0, max_digits=18)
    volume: Decimal | None = Field(default=None, ge=0, max_digits=18)
    length: Decimal | None = Field(default=None, ge=0, max_digits=18)
    width: Decimal | None = Field(default=None, ge=0, max_digits=18)
    height: Decimal | None = Field(default=None, ge=0, max_digits=18)
    status: str | None = Field(default=None, min_length=1, max_length=20)
    display_order: int | None = Field(default=None, ge=0)


class PackagingLevelResponse(UomSchema):
    """A packaging level as exposed by the API."""

    id: UUID
    firm_id: UUID
    product_id: UUID
    parent_level_id: UUID | None
    packaging_type_id: UUID | None
    uom_id: UUID | None
    level_name: str
    conversion_to_base_factor: Decimal
    barcode: str | None
    qr_code: str | None
    gtin: str | None
    ean: str | None
    upc: str | None
    weight: Decimal | None
    volume: Decimal | None
    length: Decimal | None
    width: Decimal | None
    height: Decimal | None
    status: str
    display_order: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ConversionRequest(UomSchema):
    """A quantity to convert between two units on a given date."""

    quantity: Decimal = Field(max_digits=24)
    from_uom_id: UUID
    to_uom_id: UUID
    product_id: UUID | None = None
    conversion_date: date | None = None


class ConversionResponse(UomSchema):
    """The converted quantity and the rule version that produced it."""

    quantity: Decimal
    converted_quantity: Decimal
    from_uom_id: UUID
    to_uom_id: UUID
    conversion_factor: Decimal
    version: int
    conversion_rule_id: UUID
    conversion_date: date
