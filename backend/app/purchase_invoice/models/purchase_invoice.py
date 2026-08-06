"""Purchase invoice persistence models."""

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


class PurchaseInvoice(BaseEntity):
    """Store one supplier invoice header."""

    __tablename__ = "purchase_invoices"
    __table_args__ = (
        UniqueConstraint("firm_id", "invoice_number", name="UQ_purchase_invoices_firm_invoice_number"),
        Index("IX_purchase_invoices_firm_status", "firm_id", "status"),
        Index("IX_purchase_invoices_firm_date", "firm_id", "invoice_date"),
        Index("IX_purchase_invoices_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_purchase_invoices_firm_branch", "firm_id", "branch_id"),
        Index("IX_purchase_invoices_firm_due_date", "firm_id", "due_date"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_invoice_number: Mapped[str] = mapped_column(String(120), nullable=False)
    supplier_invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    allow_direct_purchase_order: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_over_invoice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    over_invoice_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", server_default="DRAFT")
    total_source_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_already_invoiced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_current_invoice_quantity: Mapped[Decimal] = mapped_column(
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


class PurchaseInvoiceSource(BaseEntity):
    """Store supplier invoice source document references."""

    __tablename__ = "purchase_invoice_sources"
    __table_args__ = (
        UniqueConstraint(
            "purchase_invoice_id",
            "source_document_type",
            "source_document_id",
            name="UQ_purchase_invoice_sources_document",
        ),
        Index("IX_purchase_invoice_sources_invoice", "purchase_invoice_id"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)


class PurchaseInvoiceLine(BaseEntity):
    """Store one purchase invoice line."""

    __tablename__ = "purchase_invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "purchase_invoice_id",
            "line_number",
            name="UQ_purchase_invoice_lines_invoice_line",
        ),
        Index("IX_purchase_invoice_lines_invoice", "purchase_invoice_id"),
        Index("IX_purchase_invoice_lines_firm_source", "firm_id", "source_document_line_id"),
        Index("IX_purchase_invoice_lines_firm_product", "firm_id", "product_id"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True
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
    already_invoiced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    current_invoice_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
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
    invoice_uom_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"))
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


class PurchaseInvoiceAttachment(BaseEntity):
    """Store purchase invoice attachments."""

    __tablename__ = "purchase_invoice_attachments"
    __table_args__ = (Index("IX_purchase_invoice_attachments_invoice", "purchase_invoice_id"),)

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachment_kind: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PURCHASE_INVOICE_FILE", server_default="PURCHASE_INVOICE_FILE"
    )


class PurchaseInvoiceNote(BaseEntity):
    """Store purchase invoice notes."""

    __tablename__ = "purchase_invoice_notes"
    __table_args__ = (Index("IX_purchase_invoice_notes_invoice", "purchase_invoice_id"),)

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    note_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL", server_default="INTERNAL")
    note: Mapped[str] = mapped_column(Text, nullable=False)


class PurchaseInvoiceAccountingEvent(BaseEntity):
    """Store reusable accounting placeholder events."""

    __tablename__ = "purchase_invoice_accounting_events"
    __table_args__ = (
        Index("IX_purchase_invoice_accounting_events_invoice", "purchase_invoice_id"),
        Index("IX_purchase_invoice_accounting_events_type", "firm_id", "event_type"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    narration: Mapped[str | None] = mapped_column(Text)
    source_line_id: Mapped[UUID | None] = mapped_column(UUIDType())

