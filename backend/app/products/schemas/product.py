"""Validated request and response contracts for product management."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductType(StrEnum):
    """Supported product type classifications."""

    STOCK_ITEM = "STOCK_ITEM"
    SERVICE = "SERVICE"
    RAW_MATERIAL = "RAW_MATERIAL"
    FINISHED_GOODS = "FINISHED_GOODS"
    SEMI_FINISHED = "SEMI_FINISHED"
    ASSET = "ASSET"
    CONSUMABLE = "CONSUMABLE"
    BUNDLE = "BUNDLE"
    DIGITAL_PRODUCT = "DIGITAL_PRODUCT"


class IssueRule(StrEnum):
    """Which batch a product leaves from (STK-11, §70 row 15)."""

    #: Earliest expiry first -- the default, and what a product with no rule
    #: follows.
    FEFO = "FEFO"
    #: First received first, whatever the expiry.
    FIFO = "FIFO"
    #: A person chooses the batch on the line; nothing is drawn silently.
    PICK = "PICK"


class ProductStatus(StrEnum):
    """Supported product lifecycle statuses."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"
    #: No longer bought, still sold until the stock is gone (STK-17): refused
    #: on a purchase order and left out of reorder suggestions, sold as an
    #: ACTIVE product is.
    DISCONTINUED = "DISCONTINUED"


#: Whether tax paid on a purchase may be claimed as input credit (backlog 78
#: row 1): BLOCKED is s.17(5) -- a car, catering, personal use -- and
#: INELIGIBLE any other reason the credit is lost.
ItcEligibility = Literal["ELIGIBLE", "BLOCKED", "INELIGIBLE"]


class ProductSchema(BaseModel):
    """Strict API schema configuration for product module."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ProductCategoryCreate(ProductSchema):
    """Create payload for one hierarchical product category node."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    is_active: bool = True
    #: The trade licence its goods need (backlog 54). On an update, absent
    #: leaves it alone and an explicit null clears it.
    required_licence_type_id: UUID | None = None
    #: Its goods wait in quarantine on receipt (BUY-9). On an update, absent
    #: leaves it alone.
    inspection_required: bool = False
    #: Expiry rules (STK-5); blank takes the firm's. On an update absent
    #: leaves them alone.
    expiry_stop_sale_days: int | None = Field(default=None, ge=0, le=3650)
    expiry_alert_days: int | None = Field(default=None, ge=0, le=3650)
    expiry_return_days: int | None = Field(default=None, ge=0, le=3650)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize category code for deterministic matching."""
        return value.strip().upper()


class ProductCategoryUpdate(ProductCategoryCreate):
    """Replace payload for one category node."""


class ProductCategoryResponse(ProductSchema):
    """Response contract for one category node."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    parent_id: UUID | None
    level: int
    path: str
    is_active: bool
    required_licence_type_id: UUID | None = None
    inspection_required: bool = False
    expiry_stop_sale_days: int | None = None
    expiry_alert_days: int | None = None
    expiry_return_days: int | None = None
    created_at: datetime
    updated_at: datetime
    #: The concurrency counter, echoed as `If-Match` on the next edit.
    version: int


class ProductAttributeInput(ProductSchema):
    """One dynamic attribute value submitted for a product."""

    attribute_definition_id: UUID
    value: str | int | float | bool | date


class ProductMediaInput(ProductSchema):
    """One product media or document reference."""

    media_kind: str = Field(min_length=2, max_length=30)
    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    storage_path: str = Field(min_length=1, max_length=1024)
    is_primary: bool = False
    file_size_bytes: int | None = Field(default=None, ge=0)

    @field_validator("media_kind", mode="before")
    @classmethod
    def normalize_media_kind(cls, value: str) -> str:
        """Normalize media kind token to uppercase."""
        return value.strip().upper()


class ProductWrite(ProductSchema):
    """Shared writable payload for create and update."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    barcode: str | None = Field(default=None, max_length=120)
    qr_code: str | None = Field(default=None, max_length=300)
    name: str = Field(min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    product_type: ProductType
    category_id: UUID | None = None
    sub_category_id: UUID | None = None
    #: The trade licence this product needs, overriding its category's;
    #: null takes the category's (backlog 54).
    required_licence_type_id: UUID | None = None
    #: The supplier it is normally bought from; reorder orders from it (A18).
    preferred_vendor_id: UUID | None = None
    unit: str | None = Field(default=None, max_length=20)
    brand: str | None = Field(default=None, max_length=120)
    #: The brand row (MST-1); naming one sets ``brand`` to its name.
    brand_id: UUID | None = None
    model: str | None = Field(default=None, max_length=120)
    hsn_sac: str | None = Field(default=None, max_length=20)
    tax_profile_group_code: str | None = Field(
        default=None, max_length=50, pattern=r"^[A-Z0-9_-]+$"
    )
    #: Whether tax paid buying it is claimable credit (backlog 78 row 1).
    itc_eligibility: ItcEligibility = "ELIGIBLE"
    base_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    sales_uom_id: UUID | None = None
    default_receiving_uom_id: UUID | None = None
    default_dispatch_uom_id: UUID | None = None
    minimum_sales_uom_id: UUID | None = None
    weight: Decimal | None = Field(default=None, ge=0, max_digits=18)
    volume: Decimal | None = Field(default=None, ge=0, max_digits=18)
    length: Decimal | None = Field(default=None, ge=0, max_digits=18)
    width: Decimal | None = Field(default=None, ge=0, max_digits=18)
    height: Decimal | None = Field(default=None, ge=0, max_digits=18)
    allow_fraction: bool = False
    allow_decimal: bool = True
    purchase_price: Decimal | None = Field(default=None, ge=0, max_digits=18)
    selling_price: Decimal | None = Field(default=None, ge=0, max_digits=18)
    #: Per stock unit. Below it, a sale warns or is refused (BACKLOG 64 row 2).
    minimum_selling_price: Decimal | None = Field(default=None, ge=0, max_digits=18)
    mrp: Decimal | None = Field(default=None, ge=0, max_digits=18)
    status: ProductStatus = ProductStatus.ACTIVE
    #: Bought and stocked but never sold -- packing material, consumables
    #: (STK-17). Refused on every new sales line.
    not_for_sale: bool = False
    #: Days from manufacture to expiry (STK-18): a receipt typed with only a
    #: manufacturing date gets its expiry from it.
    shelf_life_days: int | None = Field(default=None, ge=1, le=3650)
    #: Which batch the goods leave from (STK-11). None is earliest expiry.
    issue_rule: IssueRule | None = None
    remarks: str | None = None
    track_batch: bool = False
    track_lot: bool = False
    track_serial: bool = False
    track_expiry: bool = False
    track_manufacturing_date: bool = False
    track_warranty: bool = False
    allow_negative_stock: bool = False
    require_batch_on_receipt: bool = False
    #: Received goods wait in quarantine until passed (BUY-9).
    inspection_required: bool = False
    #: Promotional stock, never sold at a price (BUY-1).
    free_issue_only: bool = False
    #: Expiry rules (STK-5); blank inherits the category's, then the firm's.
    expiry_stop_sale_days: int | None = Field(default=None, ge=0, le=3650)
    expiry_alert_days: int | None = Field(default=None, ge=0, le=3650)
    expiry_return_days: int | None = Field(default=None, ge=0, le=3650)
    require_batch_on_issue: bool = False
    require_serial_on_receipt: bool = False
    require_serial_on_issue: bool = False
    attributes: list[ProductAttributeInput] = Field(
        default_factory=list, max_length=300
    )
    media: list[ProductMediaInput] = Field(default_factory=list, max_length=200)

    @field_validator("code", "unit", "hsn_sac", mode="before")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        """Normalize selected identifier-like fields to uppercase."""
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @model_validator(mode="after")
    def validate_pricing(self) -> "ProductWrite":
        """Ensure selling price never exceeds MRP."""
        if (
            self.mrp is not None
            and self.selling_price is not None
            and self.mrp < self.selling_price
        ):
            raise ValueError("MRP must be greater than or equal to selling price.")
        return self


class ProductCreate(ProductWrite):
    """Create a product core record and all dynamic extensions."""

    #: Blank takes the next code from the firm's series (MST-5).
    code: str | None = Field(  # type: ignore[assignment]
        default=None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$"
    )


class ProductUpdate(ProductWrite):
    """Replace all editable product fields and dynamic values."""


class ProductImportRequest(ProductSchema):
    """Import request for JSON-based product batches."""

    records: list[ProductCreate] = Field(min_length=1, max_length=3000)


class ProductAttributeResponse(ProductSchema):
    """Persisted attribute value response."""

    id: UUID
    attribute_definition_id: UUID
    value_text: str | None
    value_number: Decimal | None
    value_date: date | None
    value_boolean: bool | None
    created_at: datetime
    updated_at: datetime


class ProductMediaResponse(ProductSchema):
    """Persisted media/document response."""

    id: UUID
    media_kind: str
    file_name: str
    mime_type: str | None
    storage_path: str
    is_primary: bool
    file_size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class ProductResponse(ProductSchema):
    """Full product response envelope payload."""

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    code: str
    barcode: str | None
    qr_code: str | None
    name: str
    short_name: str | None
    description: str | None
    product_type: ProductType
    category_id: UUID | None
    sub_category_id: UUID | None
    required_licence_type_id: UUID | None = None
    preferred_vendor_id: UUID | None = None
    unit: str | None
    brand: str | None
    brand_id: UUID | None = None
    model: str | None
    hsn_sac: str | None
    tax_profile_group_code: str | None
    itc_eligibility: str = "ELIGIBLE"
    base_uom_id: UUID | None
    inventory_uom_id: UUID | None
    purchase_uom_id: UUID | None
    sales_uom_id: UUID | None
    default_receiving_uom_id: UUID | None
    default_dispatch_uom_id: UUID | None
    minimum_sales_uom_id: UUID | None
    weight: Decimal | None
    volume: Decimal | None
    length: Decimal | None
    width: Decimal | None
    height: Decimal | None
    allow_fraction: bool
    allow_decimal: bool
    purchase_price: Decimal | None
    selling_price: Decimal | None
    minimum_selling_price: Decimal | None = None
    mrp: Decimal | None
    #: The three prices as they stand **today**, on the firm's own day: the
    #: latest dated revision that names the price, or the price above where
    #: none has started yet. The price above is the product's card; this is
    #: what a document dated today takes (D-PRC-15).
    purchase_price_in_force: Decimal | None = None
    selling_price_in_force: Decimal | None = None
    mrp_in_force: Decimal | None = None
    status: ProductStatus
    not_for_sale: bool = False
    shelf_life_days: int | None = None
    issue_rule: IssueRule | None = None
    remarks: str | None
    track_batch: bool
    track_lot: bool
    track_serial: bool
    track_expiry: bool
    track_manufacturing_date: bool
    track_warranty: bool
    allow_negative_stock: bool
    require_batch_on_receipt: bool
    inspection_required: bool = False
    free_issue_only: bool = False
    expiry_stop_sale_days: int | None = None
    expiry_alert_days: int | None = None
    expiry_return_days: int | None = None
    require_batch_on_issue: bool
    require_serial_on_receipt: bool
    require_serial_on_issue: bool
    is_deleted: bool
    deleted_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_by: UUID | None
    updated_at: datetime
    # Resolved from the shared attribute store by the router, not the ORM row.
    attributes: list[ProductAttributeResponse] = Field(default_factory=list)
    media: list[ProductMediaResponse]
    #: Read from the inventory by the router, not the ORM row: the quantity
    #: on hand across every warehouse, or ``None`` when the product has never
    #: been stocked anywhere -- which is not the same as a stock of zero.
    stock_on_hand: Decimal | None = None
    #: True when any warehouse holds it at or below its reorder level (else
    #: its minimum level, else zero) -- the inventory summary's definition.
    low_stock: bool = False


class ProductSummary(ProductSchema):
    """Aggregate product list summary."""

    total: int
    active: int
    inactive: int
    draft: int
    archived: int
    deleted: int
    #: Products some warehouse holds at or below its reorder level.
    low_stock: int = 0
    #: Products with no selling price, which cannot be sold as they stand.
    no_price: int = 0


class ProductListFilters(ProductSchema):
    """Validated filters for listing products."""

    status: ProductStatus | None = None
    product_type: ProductType | None = None
    category_id: UUID | None = None
    sub_category_id: UUID | None = None
    tax_profile_group_code: str | None = None
    brand: str | None = Field(default=None, max_length=120)
    #: The brand row (MST-1); naming one sets ``brand`` to its name.
    brand_id: UUID | None = None
    hsn_sac: str | None = Field(default=None, max_length=20)
    include_deleted: bool = False
    attribute_query: str | None = Field(default=None, max_length=200)
    #: Only products some warehouse holds at or below its reorder level.
    low_stock: bool = False
    #: Only products with no selling price.
    no_price: bool = False


class ProductCategoryFilter(ProductSchema):
    """Category tree list filter."""

    parent_id: UUID | None = None
    include_inactive: bool = False


class ProductFeatureState(ProductSchema):
    """Resolved feature flag state for current firm/profile."""

    code: str
    enabled: bool


class ProductTaxProfileOption(ProductSchema):
    """Tax profile option metadata for product tax selection."""

    id: UUID
    code: str
    group_code: str | None
    label: str
    tax_system_id: UUID


class ProductMetadataResponse(ProductSchema):
    """Dynamic metadata used by desktop product forms."""

    profile_code: str
    features: list[ProductFeatureState]
    categories: list[ProductCategoryResponse]
    tax_profiles: list[ProductTaxProfileOption]
    required_attribute_definition_ids: list[UUID]
    optional_attribute_definition_ids: list[UUID]


class BulkProductRequest(ProductSchema):
    """Bulk operation target identifiers."""

    ids: list[UUID] = Field(min_length=1, max_length=2000)
