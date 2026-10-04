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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class PurchaseInvoice(BaseEntity):
    """Store one supplier invoice header."""

    __tablename__ = "purchase_invoices"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "invoice_number", name="UQ_purchase_invoices_firm_invoice_number"
        ),
        Index("IX_purchase_invoices_firm_status", "firm_id", "status"),
        Index("IX_purchase_invoices_firm_date", "firm_id", "invoice_date"),
        Index("IX_purchase_invoices_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_purchase_invoices_firm_branch", "firm_id", "branch_id"),
        Index("IX_purchase_invoices_firm_due_date", "firm_id", "due_date"),
        # A self-invoice number is issued once, from its own series.
        Index(
            "UQ_purchase_invoices_firm_self_invoice_number",
            "firm_id",
            "self_invoice_number",
            unique=True,
            postgresql_where=text("self_invoice_number IS NOT NULL"),
            sqlite_where=text("self_invoice_number IS NOT NULL"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_invoice_number: Mapped[str] = mapped_column(String(120), nullable=False)
    supplier_invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: The Invoice Reference Number on the supplier's e-invoice, read off its
    #: QR code (backlog 78 row 5): 64 hexadecimal characters, stored lower.
    supplier_irn: Mapped[str | None] = mapped_column(String(64))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    #: The last day a bill to a micro or small supplier may be paid (backlog
    #: 68 row 2, `app/purchase_invoice/services/msme.py`), stamped when the
    #: bill is written so a supplier re-classified later does not move it.
    msme_pay_by: Mapped[date | None] = mapped_column(Date)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    # Retired (D-BUY-14): a bill is raised against a goods receipt, and no
    # request can say otherwise. The column stays so no migration is needed;
    # nothing reads or writes it.
    allow_direct_purchase_order: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Retired (D-BUY-15): a bill may never charge for more than was received,
    # and no request can say otherwise. The columns stay so no migration is
    # needed; nothing reads or writes them.
    allow_over_invoice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    over_invoice_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
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
    #: Tax the firm owes itself under reverse charge (backlog 68 row 8): the
    #: supplier does not charge it, so it is outside `tax_total` and
    #: `grand_total` and never part of the payable.
    reverse_charge_tax_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The self-invoice the firm raises for a reverse-charge supply (rule
    #: 47A), from its own series, issued when the bill is approved.
    self_invoice_number: Mapped[str | None] = mapped_column(String(60))
    #: TDS deducted on the bill at approval (PG-5): 194C or 194J, worked out
    #: as the earlier of credit and payment. ``tds_base_amount`` is what it
    #: was deducted on -- the bill before GST. ``tds_proposed_amount`` is what
    #: the server worked out; ``tds_amount`` what was deducted, which differs
    #: only where somebody overrode it. The payable is ``grand_total`` less
    #: ``tds_amount``; the rest is owed to the government (TDS Payable).
    tds_section: Mapped[str | None] = mapped_column(String(10))
    tds_base_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    tds_proposed_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tds_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: TCS the supplier charged on the bill (206C(1H), PG-6): the rate shown
    #: on it, and the amount -- typed, or the rate on ``grand_total`` (the
    #: section's base is the bill including GST). Outside GST's taxable
    #: value. The supplier is owed ``grand_total + tcs_amount - tds_amount``;
    #: the TCS is the firm's to claim (TCS Receivable).
    tcs_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    tcs_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
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
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )


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
        Index(
            "IX_purchase_invoice_lines_firm_source",
            "firm_id",
            "source_document_line_id",
        ),
        Index("IX_purchase_invoice_lines_firm_product", "firm_id", "product_id"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_line_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    already_invoiced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    current_invoice_quantity: Mapped[Decimal] = mapped_column(
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
    charges_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    #: Whether this line's tax is claimable credit (backlog 78 row 1):
    #: ELIGIBLE, BLOCKED (s.17(5)) or INELIGIBLE. Decides `recoverable` on its
    #: tax rows; blocked tax posts to the cost account, not to input tax.
    itc_eligibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ELIGIBLE", server_default="ELIGIBLE"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
    )
    purchase_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    invoice_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, default=Decimal("1"), server_default="1"
    )
    conversion_version: Mapped[int | None] = mapped_column(Integer)
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    batch_number: Mapped[str | None] = mapped_column(String(120))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)
    accounting_event_reference: Mapped[str | None] = mapped_column(String(120))
    #: The tax rule that decided the line, by code and version_number; null
    #: when the profile alone did (GST-8). Kept here because the execution
    #: log that also says so is purged.
    tax_rule_code: Mapped[str | None] = mapped_column(String(50))
    tax_rule_version: Mapped[int | None] = mapped_column(Integer)


class PurchaseInvoiceLineTax(BaseEntity):
    """Store the tax components one bill line was actually charged.

    A line has always carried a single `tax_amount`, which is what the supplier
    billed and is useless to the return: GSTR-3B claims input credit under
    IGST separately from CGST and SGST, and the ledger has to carry each
    component to its own input-tax account (D-CMP-20). That breakup was
    computed by the rule engine at save time and then thrown away, surviving
    only in `tax_rule_execution_logs`, which the retention job prunes. Rules
    are effective-dated, so re-deriving it later can disagree with what the
    supplier charged; the only honest answer is to keep what was charged, on
    the document that charged it -- exactly as `SalesInvoiceLineTax` does for
    the outward side.

    `tax_component_id` carries no foreign key on purpose. It says which
    catalogue row produced this line at the time, and the catalogue moves on --
    a RESTRICT would stop a firm ever retiring a component, and a CASCADE would
    erase the evidence. The code, label and percentage beside it are the record.
    """

    __tablename__ = "purchase_invoice_line_taxes"
    __table_args__ = (
        Index("IX_purchase_invoice_line_taxes_line", "purchase_invoice_line_id"),
        Index("IX_purchase_invoice_line_taxes_firm", "firm_id"),
    )

    purchase_invoice_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoice_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tax_component_id: Mapped[UUID | None] = mapped_column(UUIDType())
    component_code: Mapped[str] = mapped_column(String(40), nullable=False)
    component_label: Mapped[str] = mapped_column(String(120), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Tax already inside the price, which the bill shows but does not add.
    included_in_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Whether the firm may claim it as input credit.
    recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Owed by the firm itself under reverse charge rather than charged by
    #: the supplier (backlog 68 row 8): reported in GSTR-3B 3.1(d) and
    #: 4(A)(3), never in 4(A)(5), and never part of the payable.
    reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class PurchaseInvoiceAttachment(BaseEntity):
    """Store purchase invoice attachments."""

    __tablename__ = "purchase_invoice_attachments"
    __table_args__ = (
        Index("IX_purchase_invoice_attachments_invoice", "purchase_invoice_id"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
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
        default="PURCHASE_INVOICE_FILE",
        server_default="PURCHASE_INVOICE_FILE",
    )


class PurchaseInvoiceNote(BaseEntity):
    """Store purchase invoice notes."""

    __tablename__ = "purchase_invoice_notes"
    __table_args__ = (
        Index("IX_purchase_invoice_notes_invoice", "purchase_invoice_id"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
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


class PurchaseInvoiceAccountingEvent(BaseEntity):
    """Store reusable accounting placeholder events."""

    __tablename__ = "purchase_invoice_accounting_events"
    __table_args__ = (
        Index("IX_purchase_invoice_accounting_events_invoice", "purchase_invoice_id"),
        Index("IX_purchase_invoice_accounting_events_type", "firm_id", "event_type"),
    )

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    narration: Mapped[str | None] = mapped_column(Text)
    source_line_id: Mapped[UUID | None] = mapped_column(UUIDType())
