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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SalesOrder(BaseEntity):
    """Store one sales order header."""

    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("firm_id", "order_number", name="UQ_sales_orders_firm_order_number"),
        Index("IX_sales_orders_firm_status", "firm_id", "status"),
        Index("IX_sales_orders_firm_date", "firm_id", "order_date"),
        Index("IX_sales_orders_firm_customer", "firm_id", "customer_id"),
        Index("IX_sales_orders_firm_branch", "firm_id", "branch_id"),
        Index("IX_sales_orders_firm_warehouse", "firm_id", "warehouse_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    salesman_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("users.id", ondelete="RESTRICT"))
    territory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )
    route_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("territory_route_profiles.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
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
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", server_default="DRAFT")
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
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    close_reason: Mapped[str | None] = mapped_column(Text)


class SalesOrderLine(BaseEntity):
    """Store one sales order line."""

    __tablename__ = "sales_order_lines"
    __table_args__ = (
        UniqueConstraint("sales_order_id", "line_number", name="UQ_sales_order_lines_order_line"),
        Index("IX_sales_order_lines_order", "sales_order_id"),
        Index("IX_sales_order_lines_firm_product", "firm_id", "product_id"),
    )

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
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
    sales_uom_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"))
    inventory_uom_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"))
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
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    warehouse_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"))
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class SalesOrderAttachment(BaseEntity):
    """Store sales order attachments."""

    __tablename__ = "sales_order_attachments"
    __table_args__ = (Index("IX_sales_order_attachments_order", "sales_order_id"),)

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachment_kind: Mapped[str] = mapped_column(
        String(40), nullable=False, default="SALES_ORDER_FILE", server_default="SALES_ORDER_FILE"
    )


class SalesOrderNote(BaseEntity):
    """Store sales order notes."""

    __tablename__ = "sales_order_notes"
    __table_args__ = (Index("IX_sales_order_notes_order", "sales_order_id"),)

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    note_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL", server_default="INTERNAL")
    note: Mapped[str] = mapped_column(Text, nullable=False)
