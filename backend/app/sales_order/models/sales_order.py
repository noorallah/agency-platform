"""Sales order persistence models."""

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


class SalesOrder(BaseEntity):
    """Store one sales order header."""

    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "order_number", name="UQ_sales_orders_firm_order_number"
        ),
        Index("IX_sales_orders_firm_status", "firm_id", "status"),
        Index("IX_sales_orders_firm_date", "firm_id", "order_date"),
        Index("IX_sales_orders_firm_customer", "firm_id", "customer_id"),
        Index("IX_sales_orders_firm_branch", "firm_id", "branch_id"),
        Index("IX_sales_orders_firm_warehouse", "firm_id", "warehouse_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    salesman_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    territory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )
    route_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("territory_route_profiles.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    order_number: Mapped[str] = mapped_column(String(60), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date | None] = mapped_column(Date)
    customer_reference: Mapped[str | None] = mapped_column(String(80))
    #: The terms the sale was agreed on (backlog 67 row 4): the words, and the
    #: days of credit -- the customer's own unless the order says otherwise.
    #: The invoice inherits them rather than re-reading the customer, so a
    #: deal struck at 15 days stays 15 days when the bill is raised.
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    #: Where the goods go: one of the customer's own addresses (backlog 67
    #: row 3). A bare id, validated by ``app/customers/services/ship_to.py``
    #: when it is set, so a document still prints the address it named after
    #: the address is deleted. NULL only for a customer with no shipping
    #: address, which ships to the billing address as before.
    shipping_address_id: Mapped[UUID | None] = mapped_column(UUIDType())
    reference_number: Mapped[str | None] = mapped_column(String(80))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    remarks: Mapped[str | None] = mapped_column(Text)
    credit_limit_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    outstanding_balance_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The customer's standing discount when this document was raised. The
    #: rate is a starting point and every line may override it, so this says
    #: what it would have been rather than what any line was charged.
    customer_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    #: A discount on the whole document, negotiated once rather than typed on
    #: every line. It comes off what the lines discounted to, and each line
    #: carries its share so the tax is charged on the discounted value.
    bill_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: What the customer is charged for getting the goods to them.
    #:
    #: **Part of the taxable value, not an extra on the end.** Delivery charged
    #: by the seller is ancillary to the supply of the goods, so it is taxed at
    #: the goods' own rate -- which is what apportioning it across the lines
    #: achieves. `additional_charges` sits outside the tax and stays that way:
    #: it is for genuinely non-taxable additions, and silently re-taxing it
    #: would change the meaning of every document that carries one.
    #:
    #: The mirror image of `bill_discount_amount`, and it uses the same
    #: `apportion`: one reduces each line's taxable value and the other raises
    #: it, and both give the rounding residual to the largest line so the
    #: shares sum exactly to the header figure.
    freight_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: What a free-shipping offer took off the delivery charge asked for.
    #: `freight_amount` is what is charged; the two together are what the
    #: customer was asked, which is what an editor refills and what a save
    #: prices again -- otherwise a lapsed offer's waiver is baked into the
    #: order and the charge can never come back (D-SELL-35, the order twin of
    #: D-SELL-34 on the quotation).
    freight_waived_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    line_discount_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    subtotal: Mapped[Decimal] = mapped_column(
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
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The coupon the customer presented, if any. Stored on the order rather
    #: than the quotation because the order is the document that is approved,
    #: and approval is when a claim can be counted -- an offer is not a claim.
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    #: Where `bill_discount_amount` came from: ``typed`` when the caller sent
    #: a figure or a rate, ``promotion`` when an offer set it, ``none`` when
    #: nothing did. Stored because the amount looks the same either way, and
    #: an editor that refilled a promotion's figure as typed switched the
    #: offer off on the next save (plan item 10.7, 2026-09-13). NULL on
    #: orders saved before it existed, which an editor keeps as typed.
    bill_discount_source: Mapped[str | None] = mapped_column(String(20))
    #: Whether the rates typed on this order include GST (backlog 64 row 4).
    #: Each typed rate is stored before tax in ``unit_price`` and kept as
    #: typed in the line's ``entered_rate``.
    rate_includes_tax: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    #: A hold is a **flag, not a status**, and that is the whole design. An
    #: order that is PARTIALLY_DELIVERED can be held, and releasing it has to
    #: put it back to PARTIALLY_DELIVERED -- not to APPROVED. Writing HOLD into
    #: `status` would destroy the only record of how far the order had got,
    #: and releasing would then have to guess. Nothing is overwritten here, so
    #: nothing has to be restored.
    is_on_hold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    hold_reason: Mapped[str | None] = mapped_column(Text)
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    held_by: Mapped[UUID | None] = mapped_column(UUIDType())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[UUID | None] = mapped_column(UUIDType())
    close_reason: Mapped[str | None] = mapped_column(Text)


class SalesOrderLine(BaseEntity):
    """Store one sales order line."""

    __tablename__ = "sales_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "sales_order_id", "line_number", name="UQ_sales_order_lines_order_line"
        ),
        Index("IX_sales_order_lines_order", "sales_order_id"),
        Index("IX_sales_order_lines_firm_product", "firm_id", "product_id"),
    )

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
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
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    base_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reservable_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    available_stock: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reserved_stock: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    inventory_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
    )
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, default=Decimal("1"), server_default="1"
    )
    conversion_version: Mapped[int | None] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The rate as typed, GST included, on an order whose rates include GST
    #: (backlog 64 row 4); ``unit_price`` is the pre-tax rate it derived to.
    #: Null on a line whose rate was not typed inclusive.
    entered_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: The discount amount as typed with it, GST included; ``discount_amount``
    #: is its pre-tax equivalent. Null where no amount was typed so.
    entered_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Where the rate came from -- ``percent``/``amount`` when it was typed,
    #: ``promotion``/``price_list``/``customer``/``customer_group`` when the
    #: server resolved it, ``none`` when nothing applied. An editor reopening
    #: the line keeps a typed rate and re-resolves an inherited one; without
    #: this it re-sent every rate as typed, and a ladder never moved with
    #: the quantity (plan item 9.2, 2026-09-13).
    discount_source: Mapped[str | None] = mapped_column(String(20))
    discount_amount: Mapped[Decimal] = mapped_column(
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
    #: This line's share of the document's bill discount. Stored rather than
    #: derived at print time, because it is what the tax was computed on.
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: This line's share of the document's freight, in proportion to what the
    #: line is worth after its own discounts. Stored rather than derived at
    #: print time, for the reason the bill discount's share is: the tax was
    #: charged on it, so the number has to survive.
    freight_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    #: The batch the customer asked for (backlog 79 row 4). Approval holds
    #: this batch and no other -- what it cannot cover is a back order -- and
    #: a delivery note raised from the line starts with it picked.
    pinned_batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    #: The tax rule that decided the line, by code and version_number; null
    #: when the profile alone did (GST-8). Kept here because the execution
    #: log that also says so is purged.
    tax_rule_code: Mapped[str | None] = mapped_column(String(50))
    tax_rule_version: Mapped[int | None] = mapped_column(Integer)


class SalesOrderAttachment(BaseEntity):
    """Store sales order attachments."""

    __tablename__ = "sales_order_attachments"
    __table_args__ = (Index("IX_sales_order_attachments_order", "sales_order_id"),)

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
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
        default="SALES_ORDER_FILE",
        server_default="SALES_ORDER_FILE",
    )


class SalesOrderNote(BaseEntity):
    """Store sales order notes."""

    __tablename__ = "sales_order_notes"
    __table_args__ = (Index("IX_sales_order_notes_order", "sales_order_id"),)

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
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


class SalesWorkflowSettings(BaseEntity):
    """Store which sales stages one firm fills in by hand.

    The chain is quotation, sales order, delivery note, invoice, and a firm run
    by one person has no use for the first three: they are four screens for one
    counter sale. Turning a stage off does not remove the document -- stock
    still leaves at dispatch and cost of goods sold still belongs to the
    delivery note -- it means the service raises that document itself rather
    than waiting for somebody to type it.

    A stage per column rather than one ``mode``, because a firm changes shape:
    somebody trading alone hires a salesman, then a warehouse hand, and each
    step should be a switch rather than a migration. An enum would need a new
    value for every combination on that path.

    The invoice has no column. It is what the customer receives and what the
    user actually wants, so there is nothing beyond it to trigger it.
    """

    __tablename__ = "sales_workflow_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_sales_workflow_settings_firm"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: Every stage defaults to on, which is the chain as it has always worked.
    #: A firm with no row here behaves exactly as it did before this table
    #: existed, so switching it on is what changes a firm, never migrating.
    quotation_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    sales_order_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    delivery_note_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Where a synthesised delivery note ships from. Dispatch refuses a line
    #: with no warehouse, and a firm whose delivery-note stage is automatic
    #: never sees a field to type one into. Null falls back to the firm's
    #: default branch and warehouse, which is what most firms will use.
    #: How matching promotions meet on one document (backlog 59): COMBINE
    #: applies each in "Applies at" order until one that does not stack, as
    #: offers always have; BEST_OFFER gives only the single offer worth most.
    promotion_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="COMBINE", server_default="COMBINE"
    )
    #: In Combine mode, the most the offers together may take off one line,
    #: as a percentage of its gross (backlog 59 item 3). Null is no cap.
    max_line_discount_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    default_branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    default_warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    #: Whether a customer added by somebody without CUSTOMER_APPROVE starts
    #: PENDING (SEL-15): it takes orders, but is not billed until approved.
    new_outlets_need_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Whether a new counter bill reads a typed rate as including GST
    #: (backlog 64 row 4). Only the default: each bill carries its own switch.
    rate_includes_tax: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class PriceFloorSettings(BaseEntity):
    """One firm's policy on selling below cost or below a minimum price.

    BACKLOG 64 row 2. The shape of ``trade_licence_settings``: one row per
    firm, and a firm with no row warns and never blocks -- a check that stops
    trade on the day it ships is a check nobody switches on.
    """

    __tablename__ = "price_floor_settings"
    __table_args__ = (
        Index(
            "UQ_price_floor_settings_firm_active",
            "firm_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: OFF, WARN or BLOCK, judged when a sales order or a bill is approved.
    enforcement: Mapped[str] = mapped_column(
        String(10), nullable=False, default="WARN", server_default="WARN"
    )
    #: Whether cost is a floor as well as the product's minimum price. Off for
    #: a firm that clears old stock below cost on purpose and only wants the
    #: minimum it set.
    include_cost: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class RoleDiscountLimit(BaseEntity):
    """The largest discount one role may give on its own, in one firm.

    BACKLOG 64 row 3. Anybody who could edit an order could type any discount.
    A document whose **typed** discount -- not a price list's, a promotion's or
    the customer's standing rate, which are arrangements the firm made -- is
    above the approver's limit is refused at approval, naming the limit it
    needs, and the approval that clears it records who allowed it.

    Keyed by role **code**, which is how a role is named everywhere a person
    reads it, and per firm, because one firm's salesman may give 5% and
    another's 10%. A role with no row has no limit of its own; a person's limit
    is the largest among their roles that have one, and somebody none of whose
    roles has one is not limited.
    """

    __tablename__ = "role_discount_limits"
    __table_args__ = (
        Index(
            "UQ_role_discount_limits_firm_role_active",
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
    max_discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
