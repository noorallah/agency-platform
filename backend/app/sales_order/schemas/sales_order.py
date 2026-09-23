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
    """Supported sales order lifecycle statuses.

    `PARTIALLY_DELIVERED` and `DELIVERED` are written by
    `DeliveryNoteService`, which resyncs the order as notes are dispatched and
    walks it back as they are cancelled. Until 2026-08-23 neither existed: a
    fully delivered order and one nothing had shipped against both read
    APPROVED, and every screen had to work out "is this finished?" from the
    notes. The purchase side has had the same pair since 2026-08-18.
    """

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED"
    DELIVERED = "DELIVERED"
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
    #: None means the caller said nothing, so the customer's standing
    #: discount applies. Zero means they said no discount.
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
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
    #: The code the customer presented, if any. An offer that requires one is
    #: not applied without it, and a code nobody recognises leaves the order
    #: saveable -- a typo in a field that gives money away must not refuse a
    #: sale.
    coupon_code: str | None = Field(default=None, max_length=40)
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    order_number: str | None = Field(default=None, max_length=60)
    #: A discount on the whole document, taken off what the lines discounted
    #: to and split across them so the tax is charged on the reduced value.
    #: An amount beats a rate, exactly as on a line.
    bill_discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    bill_discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: What the customer is charged for delivery. Part of the taxable value:
    #: it is split across the lines and taxed with them, because delivery
    #: charged by the seller is ancillary to the supply of the goods.
    #: `additional_charges` stays outside the tax, for additions that really
    #: are outside it.
    freight_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
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
    #: See the line model: typed (``percent``/``amount``) or resolved.
    discount_source: str | None = None
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    #: This line's share of the document's bill discount.
    bill_discount_amount: Decimal
    #: This line's share of the document's freight.
    freight_amount: Decimal = Decimal("0")
    net_amount: Decimal
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class SalesOrderAdvance(SalesOrderSchema):
    """One receipt taken against an order, and what is left of it."""

    settlement_id: UUID
    settlement_number: str
    settlement_date: date
    amount: Decimal
    #: What of this receipt has not been set against any invoice yet. The
    #: figure somebody actually wants: "how much of that deposit is still
    #: sitting there".
    unallocated_amount: Decimal
    status: str
    narration: str | None = None


class SalesOrderAdvanceSummary(SalesOrderSchema):
    """What a customer has paid against one order."""

    sales_order_id: UUID
    order_number: str
    #: Everything received against the order, reversed receipts excluded --
    #: a reversed receipt is money the firm does not have.
    total_received: Decimal
    #: The part of it not yet set against any invoice.
    total_unapplied: Decimal
    receipts: list[SalesOrderAdvance]


class SalesOrderResponse(SalesOrderSchema):
    """Return one sales order."""

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    customer_id: UUID
    #: Who the order is for, by name, so a picker of orders -- the
    #: proforma's -- says whose each one is (plan item 9.25, 2026-09-13).
    customer_name: str = ""
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
    #: The customer's standing discount on the day this was raised.
    customer_discount_percent: Decimal
    #: What was taken off the whole document, and the rate it represents.
    bill_discount_percent: Decimal
    bill_discount_amount: Decimal
    #: ``typed``, ``promotion`` or ``none``; NULL on orders saved before it
    #: was recorded. What an editor needs to refill only what was typed.
    bill_discount_source: str | None = None
    #: The coupon presented. Absent from the response until 2026-09-13, so an
    #: editor reopened an order with an empty Coupon box and saving it
    #: removed the coupon and the offer it reached (plan item 10.7).
    coupon_code: str | None = None
    #: What was charged for delivery, split across the lines and taxed there.
    freight_amount: Decimal = Decimal("0")
    #: What a free-shipping offer took off it. The two together are what the
    #: customer was asked, which is what an editor refills (D-SELL-35).
    freight_waived_amount: Decimal = Decimal("0")
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
    #: A hold is a flag beside the status, not a status of its own: an order
    #: that is PARTIALLY_DELIVERED can be held, and releasing it has to put it
    #: back to PARTIALLY_DELIVERED rather than guess.
    is_on_hold: bool = False
    #: Kept after release, not cleared -- "why was this held" is the question
    #: asked afterwards.
    hold_reason: str | None = None
    held_at: datetime | None = None
    released_at: datetime | None = None
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
    #: Each id keeps a name beside it: the grid derives its columns from the
    #: row, so a register of ids alone showed seven columns of UUIDs
    #: (D-RPT-17). A name is ``None`` only where the id itself is.
    customer_name: str
    salesman_id: UUID | None
    salesman_name: str | None
    territory_id: UUID | None
    territory_name: str | None
    branch_id: UUID
    branch_name: str
    warehouse_id: UUID
    warehouse_name: str
    status: SalesOrderStatus
    grand_total: Decimal


class SalesOrderPendingRecord(SalesOrderSchema):
    """One order still owing stock to its customer.

    APPROVED or PARTIALLY_DELIVERED -- an order with a reservation standing
    and goods not yet out. The report used to hold DRAFT and APPROVED alone,
    so the order that most literally still owed stock was absent and an
    unapproved draft was in, and `pending_value` was the whole total whatever
    had left (D-RPT-7). `pending_value` is now each line's worth, tax in,
    pro-rated by what is still to go.
    """

    order_id: UUID
    order_number: str
    customer_id: UUID
    customer_name: str
    delivery_date: date | None
    status: SalesOrderStatus
    is_on_hold: bool
    ordered_quantity: Decimal
    delivered_quantity: Decimal
    pending_quantity: Decimal
    pending_value: Decimal


class SalesOrderBackOrderRecord(SalesOrderSchema):
    """One row of the sales order back order report."""

    order_id: UUID
    order_number: str
    customer_name: str
    warehouse_id: UUID | None
    line_id: UUID
    product_id: UUID
    product_code: str
    product_name: str
    #: What the line still owes: reservable less what left the warehouse.
    requested_quantity: Decimal
    delivered_quantity: Decimal
    #: Held for this line by its reservation, and on hand in the warehouse now.
    reserved_quantity: Decimal
    available_stock: Decimal
    #: What is owed beyond what the warehouse's stock can meet once the older
    #: open orders have taken theirs -- the shortfall as it stands today, not
    #: as it stood the day the order was typed (D-RPT-8).
    back_order_quantity: Decimal


class SalesOrderByCustomerRecord(SalesOrderSchema):
    """One row of the sales order by customer report."""

    customer_id: UUID
    customer_name: str
    order_count: int
    total_value: Decimal


class SalesOrderBySalesmanRecord(SalesOrderSchema):
    """One row of the sales order by salesman report.

    ``salesman_id`` is ``None`` for the **Unassigned** bucket: an order
    nobody is credited with used to fall out of the report altogether, so the
    total could not be reconciled against the register (D-RPT-19).
    """

    salesman_id: UUID | None
    salesman_name: str
    order_count: int
    total_value: Decimal


class SalesOrderByTerritoryRecord(SalesOrderSchema):
    """One row of the sales order by territory report.

    ``territory_id`` is ``None`` for the **Unassigned** bucket, for the same
    reason as the by-salesman report (D-RPT-19).
    """

    territory_id: UUID | None
    territory_name: str
    order_count: int
    total_value: Decimal


class SalesWorkflowSettingsResponse(SalesOrderSchema):
    """Expose which sales stages the firm fills in by hand."""

    quotation_stage: bool
    sales_order_stage: bool
    delivery_note_stage: bool
    default_branch_id: UUID | None
    default_warehouse_id: UUID | None
    is_configured: bool


class SalesWorkflowSettingsWrite(SalesOrderSchema):
    """Replace which sales stages the firm fills in by hand.

    Every stage is sent on every write. There is no partial form of this: the
    three switches are read together to decide what a document must synthesise,
    and a caller that omitted one would be asking for a chain nobody described.

    The two defaults are different: an omitted one is left as it is and an
    explicit null clears it, so a client that never showed them cannot wipe
    them (D-CFG-14). Whatever is sent must be a live, active branch and
    warehouse of this firm, the warehouse inside the branch.
    """

    quotation_stage: bool
    sales_order_stage: bool
    delivery_note_stage: bool
    default_branch_id: UUID | None = None
    default_warehouse_id: UUID | None = None
