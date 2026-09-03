"""Sales invoice persistence models."""

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


class SalesInvoice(BaseEntity):
    """Store one customer invoice header."""

    __tablename__ = "sales_invoices"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "invoice_number", name="UQ_sales_invoices_firm_invoice_number"
        ),
        Index("IX_sales_invoices_firm_status", "firm_id", "status"),
        Index("IX_sales_invoices_firm_date", "firm_id", "invoice_date"),
        Index("IX_sales_invoices_firm_customer", "firm_id", "customer_id"),
        Index("IX_sales_invoices_firm_branch", "firm_id", "branch_id"),
        Index("IX_sales_invoices_firm_due_date", "firm_id", "due_date"),
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
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_invoice_number: Mapped[str | None] = mapped_column(String(120))
    #: The state the supply was made in, copied from the customer's billing
    #: address when the invoice is raised. It decides CGST + SGST against IGST,
    #: and it is stored rather than derived because a customer who moves must
    #: not silently change the tax treatment of an invoice already issued.
    place_of_supply: Mapped[str | None] = mapped_column(String(120))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    allow_direct_sales_order: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
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
    #: A discount on the whole document, negotiated once rather than typed on
    #: every line. It comes off what the lines discounted to, and each line
    #: carries its share so the tax is charged on the discounted value.
    #: How much was supplied free across the document. A statement, not a
    #: movement: the delivery note moved the goods.
    total_free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
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


class SalesInvoiceSource(BaseEntity):
    """Store customer invoice source document references."""

    __tablename__ = "sales_invoice_sources"
    __table_args__ = (
        UniqueConstraint(
            "sales_invoice_id",
            "source_document_type",
            "source_document_id",
            name="UQ_sales_invoice_sources_document",
        ),
        Index("IX_sales_invoice_sources_invoice", "sales_invoice_id"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )


class SalesInvoiceLine(BaseEntity):
    """Store one sales invoice line."""

    __tablename__ = "sales_invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "sales_invoice_id",
            "line_number",
            name="UQ_sales_invoice_lines_invoice_line",
        ),
        Index("IX_sales_invoice_lines_invoice", "sales_invoice_id"),
        Index(
            "IX_sales_invoice_lines_firm_source", "firm_id", "source_document_line_id"
        ),
        Index("IX_sales_invoice_lines_firm_product", "firm_id", "product_id"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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
    delivered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
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
    charges_amount: Mapped[Decimal] = mapped_column(
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
    #: Supplied free with this line. Excluded from `gross_amount` and from
    #: the tax base -- nothing is charged for it -- but stated on the bill,
    #: because a customer who receives eleven and is billed for ten asks why.
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
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
    #: What these goods cost the firm, snapshotted when the bill was raised.
    #:
    #: **Nullable, and NULL is not zero.** NULL means no cost could be traced
    #: -- an invoice raised straight off an order has no dispatch behind it,
    #: so nothing moved and nothing was costed. Zero would mean the goods were
    #: free, and a margin rule reading one as the other pays commission on the
    #: whole sale price as though the firm had bought the goods for nothing.
    #:
    #: Snapshotted rather than derived on demand because the moving average
    #: moves: re-reading it in September would answer about September, and a
    #: payout approved in March would then disagree with the report beside it.
    #: That is the same reason a payout is snapshotted at accrual.
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
    )
    order_uom_id: Mapped[UUID | None] = mapped_column(
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


class SalesInvoiceLineTax(BaseEntity):
    """Store the tax components one invoice line was actually charged.

    A line has always carried a single `tax_amount`, which is what the customer
    pays and is useless on a printed bill: a tax invoice has to state each
    component -- CGST 9% 90.00, SGST 9% 90.00 -- and the rate it was charged at.
    That breakup was computed by the rule engine at save time and then thrown
    away, surviving only in `tax_rule_execution_logs`, which the retention job
    prunes. Rules are effective-dated, so re-deriving it at print time can
    disagree with what the customer was billed; the only honest answer is to
    keep what was charged, on the document that charged it.

    `tax_component_id` carries no foreign key on purpose. It says which
    catalogue row produced this line at the time, and the catalogue moves on --
    a RESTRICT would stop a firm ever retiring a component, and a CASCADE would
    erase the evidence. The code, label and percentage beside it are the record.
    """

    __tablename__ = "sales_invoice_line_taxes"
    __table_args__ = (
        Index("IX_sales_invoice_line_taxes_line", "sales_invoice_line_id"),
        Index("IX_sales_invoice_line_taxes_firm", "firm_id"),
    )

    sales_invoice_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoice_lines.id", ondelete="CASCADE"),
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
    #: Whether the buyer may claim it as input credit.
    recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class SalesInvoiceAttachment(BaseEntity):
    """Store sales invoice attachments."""

    __tablename__ = "sales_invoice_attachments"
    __table_args__ = (
        Index("IX_sales_invoice_attachments_invoice", "sales_invoice_id"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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
        default="SALES_INVOICE_FILE",
        server_default="SALES_INVOICE_FILE",
    )


class SalesInvoiceNote(BaseEntity):
    """Store sales invoice notes."""

    __tablename__ = "sales_invoice_notes"
    __table_args__ = (Index("IX_sales_invoice_notes_invoice", "sales_invoice_id"),)

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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


class SalesInvoiceAccountingEvent(BaseEntity):
    """Store accounting events generated by sales invoice lifecycle."""

    __tablename__ = "sales_invoice_accounting_events"
    __table_args__ = (
        Index("IX_sales_invoice_accounting_events_invoice", "sales_invoice_id"),
        Index("IX_sales_invoice_accounting_events_type", "firm_id", "event_type"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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
