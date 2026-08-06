"""Purchase return persistence models."""

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


class PurchaseReturn(BaseEntity):
    """Store one supplier return header."""

    __tablename__ = "purchase_returns"
    __table_args__ = (
        UniqueConstraint("firm_id", "return_number", name="UQ_purchase_returns_firm_return_number"),
        Index("IX_purchase_returns_firm_status", "firm_id", "status"),
        Index("IX_purchase_returns_firm_date", "firm_id", "return_date"),
        Index("IX_purchase_returns_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_purchase_returns_firm_branch", "firm_id", "branch_id"),
        Index("IX_purchase_returns_firm_warehouse", "firm_id", "warehouse_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    return_number: Mapped[str] = mapped_column(String(60), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_return_number: Mapped[str | None] = mapped_column(String(120))
    supplier_return_date: Mapped[date | None] = mapped_column(Date)
    reference_grn_number: Mapped[str | None] = mapped_column(String(80))
    reference_invoice_number: Mapped[str | None] = mapped_column(String(80))
    return_reason: Mapped[str | None] = mapped_column(String(80))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    allow_direct_purchase_order: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_over_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    over_return_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", server_default="DRAFT")
    total_source_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_already_returned_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_current_return_quantity: Mapped[Decimal] = mapped_column(
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
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    close_reason: Mapped[str | None] = mapped_column(Text)


class PurchaseReturnSource(BaseEntity):
    """Store supplier return source document references."""

    __tablename__ = "purchase_return_sources"
    __table_args__ = (
        UniqueConstraint(
            "purchase_return_id",
            "source_document_type",
            "source_document_id",
            name="UQ_purchase_return_sources_document",
        ),
        Index("IX_purchase_return_sources_return", "purchase_return_id"),
    )

    purchase_return_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)


class PurchaseReturnLine(BaseEntity):
    """Store one purchase return line."""

    __tablename__ = "purchase_return_lines"
    __table_args__ = (
        UniqueConstraint(
            "purchase_return_id",
            "line_number",
            name="UQ_purchase_return_lines_return_line",
        ),
        Index("IX_purchase_return_lines_return", "purchase_return_id"),
        Index("IX_purchase_return_lines_firm_source", "firm_id", "source_document_line_id"),
        Index("IX_purchase_return_lines_firm_product", "firm_id", "product_id"),
    )

    purchase_return_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_line_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    already_returned_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    current_return_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    rejected_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reason_code: Mapped[str | None] = mapped_column(String(80))
    item_condition: Mapped[str | None] = mapped_column(String(80))
    replacement_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    refund_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_scrap: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_damaged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_expired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    charges_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    packaging_type_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT"))
    purchase_uom_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"))
    return_uom_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"))
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, default=Decimal("1"), server_default="1"
    )
    conversion_version: Mapped[int | None] = mapped_column(Integer)
    warehouse_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"))
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    batch_number: Mapped[str | None] = mapped_column(String(120))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)
    accounting_event_reference: Mapped[str | None] = mapped_column(String(120))


class PurchaseReturnAttachment(BaseEntity):
    """Store purchase return attachments."""

    __tablename__ = "purchase_return_attachments"
    __table_args__ = (Index("IX_purchase_return_attachments_return", "purchase_return_id"),)

    purchase_return_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachment_kind: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PURCHASE_RETURN_FILE", server_default="PURCHASE_RETURN_FILE"
    )


class PurchaseReturnNote(BaseEntity):
    """Store purchase return notes."""

    __tablename__ = "purchase_return_notes"
    __table_args__ = (Index("IX_purchase_return_notes_return", "purchase_return_id"),)

    purchase_return_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    note_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL", server_default="INTERNAL")
    note: Mapped[str] = mapped_column(Text, nullable=False)


class PurchaseReturnAccountingEvent(BaseEntity):
    """Store reusable accounting placeholder events."""

    __tablename__ = "purchase_return_accounting_events"
    __table_args__ = (
        Index("IX_purchase_return_accounting_events_return", "purchase_return_id"),
        Index("IX_purchase_return_accounting_events_type", "firm_id", "event_type"),
    )

    purchase_return_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    narration: Mapped[str | None] = mapped_column(Text)
    source_line_id: Mapped[UUID | None] = mapped_column(UUIDType())
