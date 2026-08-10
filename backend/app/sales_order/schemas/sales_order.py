"""Validated contracts for sales orders."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SalesOrderSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SalesOrderStatus(StrEnum):
    """Supported sales order lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class SalesOrderAttachmentWrite(SalesOrderSchema):
    """Carry one sales order attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="SALES_ORDER_FILE", min_length=1, max_length=40
    )


class SalesOrderNoteWrite(SalesOrderSchema):
    """Carry one sales order note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class SalesOrderLineWrite(SalesOrderSchema):
    """Carry one sales order line into a request."""

    line_number: int = Field(ge=1)
    product_id: UUID
    description: str | None = Field(default=None, max_length=500)
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    free_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    sales_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    packaging_type_id: UUID | None = None
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    remarks: str | None = None


class SalesOrderCreate(SalesOrderSchema):
    """Create one sales order."""

    customer_id: UUID
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    route_id: UUID | None = None
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None = None
    order_date: date
    delivery_date: date | None = None
    customer_reference: str | None = Field(default=None, max_length=80)
    reference_number: str | None = Field(default=None, max_length=80)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    remarks: str | None = None
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    order_number: str | None = Field(default=None, max_length=60)
    lines: list[SalesOrderLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[SalesOrderAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[SalesOrderNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("order_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None

    @field_validator("currency_code", mode="before")
    @classmethod
    def _normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class SalesOrderUpdate(SalesOrderCreate):
    """Replace one sales order."""

    pass


class SalesOrderImportRequest(SalesOrderSchema):
    """Import a validated batch of sales orders."""

    records: list[SalesOrderCreate] = Field(min_length=1, max_length=500)


class SalesOrderAttachmentResponse(SalesOrderSchema):
    """Return one sales order attachment."""

    id: UUID
    sales_order_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class SalesOrderNoteResponse(SalesOrderSchema):
    """Return one sales order note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class SalesOrderLineResponse(SalesOrderSchema):
    """Return one sales order line."""

    id: UUID
    sales_order_id: UUID
    line_number: int
    product_id: UUID
    description: str | None
    quantity: Decimal
    free_quantity: Decimal
    base_quantity: Decimal
    reservable_quantity: Decimal
    reserved_quantity: Decimal
    available_stock: Decimal
    reserved_stock: Decimal
    sales_uom_id: UUID | None
    inventory_uom_id: UUID | None
    packaging_type_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class SalesOrderResponse(SalesOrderSchema):
    """Return one sales order."""

    id: UUID
    firm_id: UUID
    customer_id: UUID
    salesman_id: UUID | None
    territory_id: UUID | None
    route_id: UUID | None
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None
    order_number: str
    order_date: date
    delivery_date: date | None
    customer_reference: str | None
    reference_number: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    remarks: str | None
    credit_limit_snapshot: Decimal
    outstanding_balance_snapshot: Decimal
    status: SalesOrderStatus
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    approved_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    close_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[SalesOrderLineResponse] = Field(default_factory=list)
    attachments: list[SalesOrderAttachmentResponse] = Field(default_factory=list)
    notes: list[SalesOrderNoteResponse] = Field(default_factory=list)


class SalesOrderListFilters(SalesOrderSchema):
    """Narrow a sales order list to the rows a caller asked for."""

    customer_id: UUID | None = None
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    status: SalesOrderStatus | None = None
    order_from: date | None = None
    order_to: date | None = None
    include_deleted: bool = False


class SalesOrderSummary(SalesOrderSchema):
    """Aggregate sales order counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    cancelled: int
    closed: int
    total_value: Decimal


class SalesOrderRegisterRecord(SalesOrderSchema):
    """One row of the sales order register report."""

    order_id: UUID
    order_number: str
    order_date: date
    customer_id: UUID
    salesman_id: UUID | None
    territory_id: UUID | None
    branch_id: UUID
    warehouse_id: UUID
    status: SalesOrderStatus
    grand_total: Decimal


class SalesOrderPendingRecord(SalesOrderSchema):
    """One row of the sales order pending report."""

    order_id: UUID
    order_number: str
    customer_id: UUID
    delivery_date: date | None
    status: SalesOrderStatus
    pending_value: Decimal


class SalesOrderBackOrderRecord(SalesOrderSchema):
    """One row of the sales order back order report."""

    order_id: UUID
    order_number: str
    line_id: UUID
    product_id: UUID
    requested_quantity: Decimal
    available_stock: Decimal
    back_order_quantity: Decimal


class SalesOrderByCustomerRecord(SalesOrderSchema):
    """One row of the sales order by customer report."""

    customer_id: UUID
    customer_name: str
    order_count: int
    total_value: Decimal


class SalesOrderBySalesmanRecord(SalesOrderSchema):
    """One row of the sales order by salesman report."""

    salesman_id: UUID
    salesman_name: str
    order_count: int
    total_value: Decimal


class SalesOrderByTerritoryRecord(SalesOrderSchema):
    """One row of the sales order by territory report."""

    territory_id: UUID
    territory_name: str
    order_count: int
    total_value: Decimal
