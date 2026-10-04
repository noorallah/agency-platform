"""Enterprise purchase management persistence models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class PurchaseOrder(BaseEntity):
    """Store one enterprise purchase order header."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "po_number", name="UQ_purchase_orders_firm_po_number"
        ),
        Index("IX_purchase_orders_firm_status", "firm_id", "status"),
        Index("IX_purchase_orders_firm_date", "firm_id", "purchase_date"),
        Index("IX_purchase_orders_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_purchase_orders_firm_branch", "firm_id", "branch_id"),
        Index("IX_purchase_orders_firm_warehouse", "firm_id", "warehouse_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    buyer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT"), index=True
    )
    po_number: Mapped[str] = mapped_column(String(60), nullable=False)
    #: How many times the approved order was formally amended (BUY-8). Zero
    #: is the order as first approved; each earlier version is kept in
    #: ``purchase_order_revisions``.
    revision_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    vendor_contact: Mapped[str | None] = mapped_column(String(200))
    vendor_address: Mapped[str | None] = mapped_column(String(500))
    department: Mapped[str | None] = mapped_column(String(120))
    purchase_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="STANDARD_PURCHASE",
        server_default="STANDARD_PURCHASE",
    )
    purchase_category: Mapped[str | None] = mapped_column(String(120))
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    delivery_terms: Mapped[str | None] = mapped_column(String(200))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    reference_number: Mapped[str | None] = mapped_column(String(80))
    external_reference: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NORMAL", server_default="NORMAL"
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    line_discount_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    header_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    additional_charges: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    round_off: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    close_reason: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    #: When, how (EMAIL / PRINT / WHATSAPP / OTHER) and by whom the approved
    #: order was sent to the supplier (backlog 69 row 6). A flag beside the
    #: status rather than a status of its own: sending changes nothing the
    #: order commits the firm to, so "approved but never sent" is a filter.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_via: Mapped[str | None] = mapped_column(String(20))
    sent_by: Mapped[UUID | None] = mapped_column(UUIDType())
    #: The supplier bill that raised this order because the firm switched the
    #: purchase-order stage off (`purchase_workflow_settings`). That bill
    #: approved it for itself, and cancels it when a draft of it is
    #: cancelled; an order a person raised is theirs to cancel whatever the
    #: stage says now. A bare id: the bill module depends on this one.
    raised_by_purchase_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), nullable=True, index=True
    )


class PurchaseOrderLine(BaseEntity):
    """Store one purchase order line item."""

    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id",
            "line_number",
            name="UQ_purchase_order_lines_order_line",
        ),
        Index("IX_purchase_order_lines_order", "purchase_order_id"),
        Index("IX_purchase_order_lines_firm_product", "firm_id", "product_id"),
    )

    purchase_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    vendor_product_code: Mapped[str | None] = mapped_column(String(120))
    purchase_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id", name="FK_purchase_order_lines_purchase_uoms", ondelete="RESTRICT"
        ),
    )
    inventory_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_purchase_order_lines_inventory_uoms",
            ondelete="RESTRICT",
        ),
    )
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, default=Decimal("1"), server_default="1"
    )
    conversion_version: Mapped[int | None] = mapped_column(Integer)
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    base_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: This line's share of the order's whole-order discount, taken off before
    #: tax and inherited downstream pro-rated by quantity (D-BUY-19).
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    batch_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    expiry_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    serial_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    #: Not authoritative: nothing writes it after creation. Responses derive
    #: the line's status from its received quantity (``line_status`` in
    #: ``purchase/services/line_quantities.py``, D-BUY-24).
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ORDERED", server_default="ORDERED"
    )
    #: The tax rule that decided the line, by code and version_number; null
    #: when the profile alone did (GST-8). Kept here because the execution
    #: log that also says so is purged.
    tax_rule_code: Mapped[str | None] = mapped_column(String(50))
    tax_rule_version: Mapped[int | None] = mapped_column(Integer)
    #: Where the unit price came from (PG-9): ``RATE_CONTRACT``,
    #: ``PRICE_LIST``, ``CATALOGUE``, ``PRICE_REVISION``, ``PRODUCT`` or
    #: ``TYPED``; null on lines saved before it was recorded.
    rate_source: Mapped[str | None] = mapped_column(String(20))
    #: The rate contract line this line was priced from and draws on. A bare
    #: id, as other cross-document line references are; the contract line is
    #: never re-inserted, so it does not dangle.
    rate_contract_line_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    #: The supplier scheme the line's free goods came from (PG-11): filled
    #: by the scheme on the same product, or a line of another product's
    #: free goods the scheme earned. A bare id; the receipt and the bill
    #: reach it through the order line.
    scheme_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    #: The scheme as it read when the line took it ("10+2"); kept because the
    #: scheme itself may change or go.
    scheme_name: Mapped[str | None] = mapped_column(String(120))


class PurchaseDeliverySchedule(BaseEntity):
    """Store delivery schedules per order line."""

    __tablename__ = "purchase_delivery_schedules"
    __table_args__ = (
        Index("IX_purchase_delivery_schedules_line", "purchase_order_line_id"),
        Index("IX_purchase_delivery_schedules_firm_date", "firm_id", "delivery_date"),
    )

    purchase_order_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING", server_default="PENDING"
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class PurchaseAttachment(BaseEntity):
    """Store purchase document attachments."""

    __tablename__ = "purchase_attachments"
    __table_args__ = (Index("IX_purchase_attachments_order", "purchase_order_id"),)

    purchase_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachment_kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="PURCHASE_FILE",
        server_default="PURCHASE_FILE",
    )


class PurchaseNote(BaseEntity):
    """Store notes linked to purchase documents."""

    __tablename__ = "purchase_notes"
    __table_args__ = (Index("IX_purchase_notes_order", "purchase_order_id"),)

    purchase_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    note_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)


class PurchaseOrderHistory(BaseEntity):
    """Store immutable history events for purchase orders."""

    __tablename__ = "purchase_order_history"
    __table_args__ = (
        Index("IX_purchase_order_history_order", "purchase_order_id"),
        Index("IX_purchase_order_history_firm_action", "firm_id", "action"),
    )

    purchase_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    remarks: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text)


class PurchaseWorkflowSettings(BaseEntity):
    """Store which buying stages one firm fills in by hand.

    The chain is purchase order, goods receipt, supplier bill. A firm run by
    one person has the supplier's bill in hand and nothing else: typing an
    order, receiving it and then billing it is three screens for one delivery.
    Turning a stage off does not remove the document -- stock still arrives at
    the goods receipt and the accrual still passes through goods received not
    invoiced -- it means the bill raises that document itself.

    A stage per column rather than one ``mode``, for the reason the sales table
    gives: a firm changes shape, and each step should be a switch.

    The bill has no column: it is what the supplier sent and what is being
    recorded. A receipt is always raised against an order, so the receipt
    stage cannot be on while the order stage is off.
    """

    __tablename__ = "purchase_workflow_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_purchase_workflow_settings_firm"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: Both default to on, which is the chain as it has always worked; a firm
    #: with no row behaves exactly as it did before this table existed.
    purchase_order_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    goods_receipt_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Where a synthesised receipt puts the goods. Receiving refuses a line
    #: with no warehouse, and a firm on automatic never sees a field to type
    #: one into. Null falls back to the firm's default branch and warehouse.
    default_branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    default_warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    #: How far a supplier bill's rate may run over its order's rate, as a
    #: percentage, before the bill waits for somebody holding
    #: PURCHASE_APPROVE_OVER_TOLERANCE (BUY-10). Null: no check.
    bill_price_tolerance_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    #: The most a whole bill may come to over its order's prices before it
    #: waits (BUY-10). Null: no check.
    bill_tolerance_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    #: What approving an order past a purchase budget does (BUY-14): ``WARN``
    #: -- noted on its timeline -- or ``NEEDS_APPROVAL`` -- refused unless the
    #: approver holds PURCHASE_APPROVE_OVER_BUDGET.
    budget_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="WARN", server_default="WARN"
    )
    #: What an order line off the supplier's minimum or multiple does
    #: (BUY-5): ``WARN`` -- the editor suggests the quantity -- or ``REFUSE``.
    order_quantity_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default="WARN", server_default="WARN"
    )


class ReorderPlanningSettings(BaseEntity):
    """How one firm decides what to reorder (backlog 69 row 12, decision A39).

    ``LEVELS`` -- the default, and how reorder suggestions have always worked
    -- orders up to the reorder and maximum levels typed on each stock row.
    ``SALES`` derives a level for every product nobody typed one for, from
    what it actually sold: the net quantity dispatched to customers (less
    their returns) over the last ``sales_window_days``, as a daily rate. It is
    reordered when available stock falls to the rate times the lead time plus
    the safety days, and ordered up to that plus ``cover_days`` -- a month's
    stock, by default, which is "keep a month's minimum and replace what was
    sold". A level typed on a product always wins over the derived one.

    Firm-wide lead time until suppliers carry their own (backlog 69 row 3).
    """

    __tablename__ = "reorder_planning_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_reorder_planning_settings_firm"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    basis: Mapped[str] = mapped_column(
        String(10), nullable=False, default="LEVELS", server_default="LEVELS"
    )
    sales_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90"
    )
    lead_time_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default="7"
    )
    safety_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default="7"
    )
    cover_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )


class RolePurchaseApprovalLimit(BaseEntity):
    """The largest purchase order one role may approve, in one firm.

    BACKLOG 68 row 4, the buying sibling of ``role_discount_limits``: anybody
    holding ``PURCHASE_APPROVE`` could commit the firm to any amount. An order
    whose grand total (tax included) is above the approver's limit is refused
    at approval, naming the amount it needs, and stays submitted for somebody
    allowed more; the approval that clears it records both figures.

    Keyed by role **code**, per firm. A role with no row has no limit of its
    own; a person's limit is the largest among their roles that have one, and
    somebody none of whose roles has one -- or a platform administrator -- is
    not limited, so a firm that never sets one behaves as before.
    """

    __tablename__ = "role_purchase_approval_limits"
    __table_args__ = (
        Index(
            "UQ_role_purchase_approval_limits_firm_role_active",
            "firm_id",
            "role_code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` and `roles` live only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(String(100), nullable=False)
    max_order_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class PurchaseOrderRevision(BaseEntity):
    """One earlier version of an amended purchase order (BUY-8, A102).

    Written when an approved order is amended: what it said before -- the
    header terms and every line -- as it stood at ``revision_number``, with
    why it changed. A snapshot of a document, read back as it was, which is
    why it is kept whole rather than column by column.
    """

    __tablename__ = "purchase_order_revisions"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id",
            "revision_number",
            name="UQ_purchase_order_revisions_order_revision",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    purchase_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: The number the order carried before this amendment.
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class PurchaseBudget(BaseEntity):
    """What a firm means to spend on buying in one month (BUY-14, A106).

    Optionally narrowed to one branch and one product category; a blank one
    covers them all. What it has used is derived from approved orders, never
    stored.
    """

    __tablename__ = "purchase_budgets"
    __table_args__ = (
        Index("IX_purchase_budgets_firm_month", "firm_id", "budget_month"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: The first day of the month it covers.
    budget_month: Mapped[date] = mapped_column(Date, nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    product_category_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("product_categories.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
