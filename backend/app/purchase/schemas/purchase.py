"""Validated API contracts for enterprise purchase management."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.sales.schemas.document_preview import DocumentPreviewLine
from app.supplier_schemes.schemas import SupplierSchemeSuggestion


class PurchaseSchema(BaseModel):
    """Purchase Schema contract."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PurchaseOrderStatus(StrEnum):
    """Purchase Order Status contract."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PARTIALLY_ORDERED = "PARTIALLY_ORDERED"
    ORDERED = "ORDERED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class PurchaseType(StrEnum):
    """Purchase Type contract."""

    STANDARD_PURCHASE = "STANDARD_PURCHASE"
    LOCAL_PURCHASE = "LOCAL_PURCHASE"
    IMPORT_PURCHASE = "IMPORT_PURCHASE"
    CONSIGNMENT = "CONSIGNMENT"
    INTER_BRANCH = "INTER_BRANCH"
    INTER_COMPANY = "INTER_COMPANY"
    CAPITAL_GOODS = "CAPITAL_GOODS"
    SERVICES = "SERVICES"


class PurchaseNoteType(StrEnum):
    """Purchase Note Type contract."""

    INTERNAL = "INTERNAL"
    VENDOR = "VENDOR"
    SYSTEM = "SYSTEM"


class PurchaseLineWrite(PurchaseSchema):
    """Purchase Line Write contract."""

    product_id: UUID
    description: str | None = Field(default=None, max_length=500)
    vendor_product_code: str | None = Field(default=None, max_length=120)
    purchase_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    ordered_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    #: Blank takes the supplier's free scheme on the product, if one is in
    #: force (PG-11); zero refuses it. Blank with no scheme is zero.
    free_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: Set on a line of another product's free goods added from a scheme
    #: suggestion (PG-11): the scheme that earned them. Blank otherwise --
    #: the server records the scheme it applied to a line itself.
    scheme_id: UUID | None = None
    #: Blank takes the supplier's price (BUY-3): a fixed rate on the
    #: supplier's price list, else the product's purchase price. Zero is a
    #: price, not a silence.
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: Blank takes the supplier's arrangement (BUY-3): its price list's rate,
    #: else its standing discount. Zero refuses both.
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    batch_required: bool = False
    expiry_required: bool = False
    serial_required: bool = False
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    remarks: str | None = None


class PurchaseDeliveryScheduleWrite(PurchaseSchema):
    """Purchase Delivery Schedule Write contract."""

    line_number: int = Field(ge=1, le=100000)
    delivery_date: date
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    remarks: str | None = None


class PurchaseAttachmentWrite(PurchaseSchema):
    """Purchase Attachment Write contract."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(default="PURCHASE_FILE", min_length=1, max_length=40)


class PurchaseNoteWrite(PurchaseSchema):
    """Purchase Note Write contract."""

    note_type: PurchaseNoteType = PurchaseNoteType.INTERNAL
    note: str = Field(min_length=1)


class PurchaseOrderWrite(PurchaseSchema):
    """Purchase Order Write contract."""

    #: The firm's own fields on the document (MST-6). Replaced whole when
    #: sent; an update that omits them leaves them alone.
    attributes: list[AttributeValueInput] = Field(default_factory=list, max_length=100)

    branch_id: UUID
    warehouse_id: UUID
    vendor_id: UUID
    buyer_id: UUID | None = None
    tax_profile_id: UUID | None = None
    vendor_contact: str | None = Field(default=None, max_length=200)
    vendor_address: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=120)
    purchase_type: PurchaseType = PurchaseType.STANDARD_PURCHASE
    purchase_category: str | None = Field(default=None, max_length=120)
    purchase_date: date
    expected_delivery_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=200)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    reference_number: str | None = Field(default=None, max_length=80)
    external_reference: str | None = Field(default=None, max_length=80)
    priority: str = Field(default="NORMAL", max_length=20)
    remarks: str | None = None
    #: Never obeyed. A create accepts DRAFT or nothing and refuses anything
    #: else by name; an update ignores it. The status belongs to the lifecycle
    #: endpoints (submit, approve, cancel, close). It stays declared because
    #: clients send it -- the desktop's create body says DRAFT, and so does the
    #: import's Status column -- and the schema forbids unknown fields.
    status: PurchaseOrderStatus | None = None
    header_discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    lines: list[PurchaseLineWrite] = Field(min_length=1, max_length=1000)
    delivery_schedules: list[PurchaseDeliveryScheduleWrite] = Field(
        default_factory=list, max_length=2000
    )
    attachments: list[PurchaseAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[PurchaseNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("purchase_type", mode="before")
    @classmethod
    def normalize_type(cls, value: str | PurchaseType) -> str | PurchaseType:
        """Normalize type."""
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: str) -> str:
        """Normalize priority."""
        return value.strip().upper()


class PurchaseOrderCreate(PurchaseOrderWrite):
    """Purchase Order Create contract."""

    po_number: str | None = Field(default=None, max_length=60)


class PurchaseOrderUpdate(PurchaseOrderWrite):
    """Purchase Order Update contract."""

    pass


class PurchaseOrderAmend(PurchaseOrderWrite):
    """Amend an approved order formally (BUY-8): the whole new version, and why.

    The supplier cannot change. A line already received keeps its product and
    cannot drop below what was received.
    """

    reason: str = Field(min_length=3, max_length=1000)


class PurchaseOrderRevisionResponse(PurchaseSchema):
    """One earlier version of an amended order (BUY-8)."""

    id: UUID
    revision_number: int
    grand_total: Decimal
    reason: str
    amended_by: UUID | None
    amended_at: datetime
    #: The header terms and lines as they stood, as recorded.
    snapshot: dict[str, object]


class PurchaseOrderImportRequest(PurchaseSchema):
    """Purchase Order Import Request contract."""

    records: list[PurchaseOrderCreate] = Field(min_length=1, max_length=500)


class PurchaseOrderLineResponse(PurchaseSchema):
    """Purchase Order Line Response contract."""

    id: UUID
    purchase_order_id: UUID
    line_number: int
    product_id: UUID
    description: str | None
    vendor_product_code: str | None
    purchase_uom_id: UUID | None
    inventory_uom_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    ordered_quantity: Decimal
    free_quantity: Decimal
    base_quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    bill_discount_amount: Decimal = Decimal("0")
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    batch_required: bool
    expiry_required: bool
    serial_required: bool
    manufacturing_date: date | None
    expiry_date: date | None
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    remarks: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    #: What has happened to the line downstream (backlog 69 row 5), in its
    #: own unit, derived on every read from the live receipts, bills and
    #: returns against it.
    received_quantity: Decimal = Decimal("0")
    accepted_quantity: Decimal = Decimal("0")
    rejected_quantity: Decimal = Decimal("0")
    damaged_quantity: Decimal = Decimal("0")
    returned_quantity: Decimal = Decimal("0")
    invoiced_quantity: Decimal = Decimal("0")
    #: Ordered less received.
    pending_receipt_quantity: Decimal = Decimal("0")
    #: Accepted, less returned, less invoiced.
    to_invoice_quantity: Decimal = Decimal("0")
    #: The tax rule that decided the line and its version; null when the
    #: profile alone did (GST-8).
    tax_rule_code: str | None = None
    tax_rule_version: int | None = None
    #: Where the unit price came from (PG-9): ``RATE_CONTRACT``,
    #: ``PRICE_LIST``, ``CATALOGUE``, ``PRICE_REVISION``, ``PRODUCT`` or
    #: ``TYPED``; null on lines saved before it was recorded.
    rate_source: str | None = None
    #: The rate contract line the price came from and the line draws on.
    rate_contract_line_id: UUID | None = None
    #: The supplier scheme the line's free goods came from (PG-11), and its
    #: label as it read then ("10+2").
    scheme_id: UUID | None = None
    scheme_name: str | None = None


class PurchaseDeliveryScheduleResponse(PurchaseSchema):
    """Purchase Delivery Schedule Response contract."""

    id: UUID
    purchase_order_line_id: UUID
    line_number: int
    delivery_date: date
    quantity: Decimal
    status: str
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseAttachmentResponse(PurchaseSchema):
    """Purchase Attachment Response contract."""

    id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class PurchaseNoteResponse(PurchaseSchema):
    """Purchase Note Response contract."""

    id: UUID
    note_type: PurchaseNoteType
    note: str
    created_at: datetime
    updated_at: datetime


class PurchaseOrderHistoryResponse(PurchaseSchema):
    """Purchase Order History Response contract."""

    id: UUID
    action: str
    from_status: str | None
    to_status: str | None
    remarks: str | None
    details_json: str | None
    created_by: UUID | None
    created_at: datetime


class PurchaseOrderResponse(PurchaseSchema):
    """Purchase Order Response contract."""

    #: The firm's own fields on the document (MST-6).
    attributes: list[AttributeValueResponse] = Field(default_factory=list)

    id: UUID
    #: ``NOT_INVOICED``, ``PARTIALLY_INVOICED`` or ``INVOICED``, from the
    #: lines' figures (backlog 69 row 5). Beside ``status``, never in it, so
    #: billing does not overwrite how far receiving got (OWNER_DECISIONS A33).
    billing_status: str = "NOT_INVOICED"
    #: Every line received in full, and nothing kept is left to bill.
    is_complete: bool = False
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    vendor_id: UUID
    buyer_id: UUID | None
    tax_profile_id: UUID | None
    po_number: str
    #: Times the approved order was formally amended (BUY-8).
    revision_number: int = 0
    vendor_contact: str | None
    vendor_address: str | None
    department: str | None
    purchase_type: PurchaseType
    purchase_category: str | None
    purchase_date: date
    expected_delivery_date: date | None
    payment_terms: str | None
    delivery_terms: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    reference_number: str | None
    external_reference: str | None
    priority: str
    remarks: str | None
    status: PurchaseOrderStatus
    subtotal: Decimal
    line_discount_total: Decimal
    header_discount_amount: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    close_reason: str | None
    cancel_reason: str | None
    sent_at: datetime | None = None
    sent_via: str | None = None
    sent_by: UUID | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseOrderLineResponse] = Field(default_factory=list)
    delivery_schedules: list[PurchaseDeliveryScheduleResponse] = Field(
        default_factory=list
    )
    attachments: list[PurchaseAttachmentResponse] = Field(default_factory=list)
    notes: list[PurchaseNoteResponse] = Field(default_factory=list)
    #: Lines that take a rate contract past its contracted quantity, counting
    #: this order (PG-9). Derived on every read; warns, never refuses.
    rate_contract_warning: str | None = None


class PurchaseOrderListFilters(PurchaseSchema):
    """Purchase Order List Filters contract."""

    vendor_id: UUID | None = None
    status: PurchaseOrderStatus | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    buyer_id: UUID | None = None
    purchase_type: PurchaseType | None = None
    created_from: date | None = None
    created_to: date | None = None
    include_deleted: bool = False
    #: True lists orders sent to the supplier, False those approved and never
    #: sent (backlog 69 row 6); None both.
    sent: bool | None = None


class PurchaseOrderSentRequest(PurchaseSchema):
    """How an approved order reached the supplier (backlog 69 row 6)."""

    via: Literal["EMAIL", "PRINT", "WHATSAPP", "OTHER"]


class PurchaseSummary(PurchaseSchema):
    """Purchase Summary contract."""

    total: int
    draft: int
    open: int
    cancelled: int
    closed: int
    total_value: Decimal
    overdue_delivery: int


class PurchaseOrderRegisterRecord(PurchaseSchema):
    """One purchase order, as the register lists it."""

    order_id: UUID
    po_number: str
    purchase_date: date
    expected_delivery_date: date | None
    vendor_id: UUID
    vendor_name: str
    buyer_id: UUID | None
    branch_id: UUID
    warehouse_id: UUID | None
    status: PurchaseOrderStatus
    grand_total: Decimal


class PurchaseOrderPendingRecord(PurchaseSchema):
    """An order with goods still owed by the vendor.

    Read off the status rather than by summing receipts: the status is already
    derived from the completed receipts by `_resync_order_status`, and a
    second way of working out the same thing is a second answer waiting to
    disagree.
    """

    order_id: UUID
    po_number: str
    purchase_date: date
    expected_delivery_date: date | None
    vendor_id: UUID
    vendor_name: str
    status: PurchaseOrderStatus
    order_value: Decimal


class PurchaseOrderOverdueRecord(PurchaseSchema):
    """An order whose goods were expected and have not all arrived.

    The purchase side's back-order list. `days_overdue` is counted from the
    expected date in UTC, because everything stored here is UTC and the
    server's own date is already tomorrow for part of every day.
    """

    order_id: UUID
    po_number: str
    purchase_date: date
    expected_delivery_date: date
    days_overdue: int
    vendor_id: UUID
    vendor_name: str
    status: PurchaseOrderStatus
    order_value: Decimal


class PurchaseOrderByVendorRecord(PurchaseSchema):
    """Ordered value and count per vendor.

    Cancelled orders are left out: an order called off was never a purchase,
    and counting it would overstate what the firm has committed.
    """

    vendor_id: UUID
    vendor_name: str
    order_count: int
    total_value: Decimal


class PurchaseOrderByBuyerRecord(PurchaseSchema):
    """Ordered value and count per buyer.

    The name is read from the platform store: `users` lives only there, and a
    firm-owned session cannot see it.
    """

    buyer_id: UUID
    buyer_name: str
    order_count: int
    total_value: Decimal


class PurchaseOrderByProductRecord(PurchaseSchema):
    """What the firm is buying, by quantity and by value."""

    product_id: UUID
    product_code: str
    product_name: str
    ordered_quantity: Decimal
    total_value: Decimal
    order_count: int


class PurchaseQuantityHint(PurchaseSchema):
    """One order line off the supplier's minimum or multiple (BUY-5)."""

    line_number: int
    product_id: UUID
    quantity: Decimal
    minimum_order_quantity: Decimal | None
    order_multiple: Decimal | None
    suggested_quantity: Decimal
    message: str


class PurchaseOrderPreview(PurchaseSchema):
    """A purchase order priced exactly as saving it would, without saving it.

    ``interstate`` says how its tax splits: IGST from a supplier in another
    state, CGST and SGST from one in the firm's own.
    """

    order: PurchaseOrderResponse
    interstate: bool
    lines: list[DocumentPreviewLine]
    #: Lines off the supplier's minimum or multiple, with the quantity that
    #: would do (BUY-5).
    quantity_hints: list[PurchaseQuantityHint] = Field(default_factory=list)
    #: Free goods of another product the lines earn under a supplier scheme
    #: (PG-11), for the client to add as lines of their own (paid 0).
    scheme_suggestions: list[SupplierSchemeSuggestion] = Field(default_factory=list)


class PurchaseWorkflowSettingsResponse(PurchaseSchema):
    """Expose which buying stages the firm fills in by hand."""

    purchase_order_stage: bool
    goods_receipt_stage: bool
    default_branch_id: UUID | None
    default_warehouse_id: UUID | None
    #: How far a bill may run over its order before it waits (BUY-10).
    bill_price_tolerance_percent: Decimal | None = None
    bill_tolerance_amount: Decimal | None = None
    #: ``WARN`` or ``REFUSE`` an order line off the supplier's terms (BUY-5).
    order_quantity_policy: str = "WARN"
    #: ``WARN`` or ``NEEDS_APPROVAL`` past a purchase budget (BUY-14).
    budget_policy: str = "WARN"
    is_configured: bool


class PurchaseWorkflowSettingsWrite(PurchaseSchema):
    """Replace which buying stages the firm fills in by hand.

    Both stages are sent on every write, since they are read together to
    decide what a bill must raise. The two defaults are not: an omitted one is
    left as it is and an explicit null clears it, so a client that never showed
    them cannot wipe them -- the rule the sales settings learned (D-CFG-14).
    """

    purchase_order_stage: bool
    goods_receipt_stage: bool
    default_branch_id: UUID | None = None
    default_warehouse_id: UUID | None = None
    #: Absent keeps the firm's own; an explicit null switches the check off
    #: (BUY-10).
    bill_price_tolerance_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=7, decimal_places=4
    )
    bill_tolerance_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: Absent keeps the firm's own (BUY-14).
    budget_policy: Literal["WARN", "NEEDS_APPROVAL"] | None = None
    #: Absent keeps the firm's own (BUY-5).
    order_quantity_policy: Literal["WARN", "REFUSE"] | None = None


class RolePurchaseApprovalLimitItem(PurchaseSchema):
    """The largest order one role may approve (backlog 68 row 4)."""

    role_code: str = Field(min_length=1, max_length=100)
    #: The order's grand total, tax included.
    max_order_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class RolePurchaseApprovalLimitsWrite(PurchaseSchema):
    """Replace the firm's whole list; a role left out has no limit."""

    limits: list[RolePurchaseApprovalLimitItem]


class RolePurchaseApprovalLimitsResponse(PurchaseSchema):
    """The firm's approval limits, by role code."""

    limits: list[RolePurchaseApprovalLimitItem]


class PurchaseBudgetWrite(PurchaseSchema):
    """Create or change one purchase budget (BUY-14)."""

    #: Any day of the month; stored as its first day.
    budget_month: date
    branch_id: UUID | None = None
    product_category_id: UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class PurchaseBudgetResponse(PurchaseSchema):
    """One budget with what approved orders have used of it."""

    id: UUID
    budget_month: date
    branch_id: UUID | None
    product_category_id: UUID | None
    label: str
    amount: Decimal
    used: Decimal
    available: Decimal
    version: int


class PurchaseBudgetCheckRow(PurchaseSchema):
    """One budget an order touches, and what the order does to it."""

    budget_id: UUID
    label: str
    amount: Decimal
    used: Decimal
    this_order: Decimal
    available: Decimal
    exceeded: bool


class SupplierPerformanceRecord(PurchaseSchema):
    """How one supplier delivered over a window (BUY-12)."""

    vendor_id: UUID
    vendor_name: str
    receipts: int
    on_time_receipts: int
    receipts_with_expected_date: int
    on_time_percent: Decimal | None
    received_quantity: Decimal
    #: Rejected and damaged together.
    rejected_quantity: Decimal
    rejected_percent: Decimal | None
    returned_quantity: Decimal
    returned_percent: Decimal | None
    #: On finished orders (received in full, or closed) dated in the window.
    ordered_quantity: Decimal
    short_quantity: Decimal
    short_percent: Decimal | None


class SupplierPriceTrendPoint(PurchaseSchema):
    """A supplier's average billed rate in one month (BUY-12)."""

    #: ``YYYY-MM``.
    month: str
    quantity: Decimal
    average_rate: Decimal
