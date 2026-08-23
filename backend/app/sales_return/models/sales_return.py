"""Sales return persistence models.

The mirror of ``app/purchase_return``, on the other side of the business. A
purchase return sends goods back to a supplier and takes them out of stock; a
sales return takes goods back from a customer and puts them in. Until this
existed, a customer could be credit-noted for goods they sent back but the
units stayed counted as sold, so stock understated what was on the shelf for
good.
"""

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


class SalesReturn(BaseEntity):
    """Store one customer return header."""

    __tablename__ = "sales_returns"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "return_number", name="UQ_sales_returns_firm_return_number"
        ),
        Index("IX_sales_returns_firm_status", "firm_id", "status"),
        Index("IX_sales_returns_firm_date", "firm_id", "return_date"),
        Index("IX_sales_returns_firm_customer", "firm_id", "customer_id"),
        Index("IX_sales_returns_firm_branch", "firm_id", "branch_id"),
        Index("IX_sales_returns_firm_warehouse", "firm_id", "warehouse_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    #: Where the goods are being taken back into. A return is stock arriving, so
    #: it needs a destination the way a goods receipt does.
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    salesman_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    territory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    return_number: Mapped[str] = mapped_column(String(60), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: What the customer called it on their own paperwork.
    customer_return_number: Mapped[str | None] = mapped_column(String(120))
    customer_return_date: Mapped[date | None] = mapped_column(Date)
    reference_delivery_note_number: Mapped[str | None] = mapped_column(String(80))
    reference_invoice_number: Mapped[str | None] = mapped_column(String(80))
    return_reason: Mapped[str | None] = mapped_column(String(80))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    allow_over_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    over_return_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    total_source_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_already_returned_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_current_return_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: What came back fit to sell again, as opposed to damaged or scrapped.
    total_restock_quantity: Mapped[Decimal] = mapped_column(
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
    #: What the customer is credited, tax included.
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The journal that credited the customer, written when the return is
    #: completed. Nullable because a draft has not credited anybody yet.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: The journal that put the cost of the goods back into stock. Separate
    #: from the one above because they are separate facts: what the customer is
    #: credited is the selling price, what returns to inventory is the cost.
    cost_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    close_reason: Mapped[str | None] = mapped_column(Text)


class SalesReturnSource(BaseEntity):
    """Store the documents one return was raised against."""

    __tablename__ = "sales_return_sources"
    __table_args__ = (
        UniqueConstraint(
            "sales_return_id",
            "source_document_type",
            "source_document_id",
            name="UQ_sales_return_sources_document",
        ),
    )

    sales_return_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_returns.id", ondelete="CASCADE"),
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


class SalesReturnLine(BaseEntity):
    """Store one customer return line."""

    __tablename__ = "sales_return_lines"
    __table_args__ = (
        UniqueConstraint(
            "sales_return_id", "line_number", name="UQ_sales_return_lines_return_line"
        ),
        Index(
            "IX_sales_return_lines_firm_source", "firm_id", "source_document_line_id"
        ),
        Index("IX_sales_return_lines_firm_product", "firm_id", "product_id"),
    )

    sales_return_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_returns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    #: A bare id with no foreign key, the convention every downstream document
    #: follows: the source lives in another module and may be reconciled on its
    #: line number rather than its identity.
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_line_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    #: What the source document sent the customer.
    dispatched_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    already_returned_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    current_return_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: How much of what came back can be sold again. The rest is damaged or
    #: scrap: still owned and still worth what it cost, but not sellable, so it
    #: arrives in a different bucket.
    restock_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    scrap_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reason_code: Mapped[str | None] = mapped_column(String(80))
    item_condition: Mapped[str | None] = mapped_column(String(80))
    is_damaged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_expired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
    )
    sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    return_uom_id: Mapped[UUID | None] = mapped_column(
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
    #: The batch these goods go back into. A return never creates one: a batch
    #: number nobody ever shipped is a mistake to correct, not stock history to
    #: invent, which is the rule the purchase return already follows.
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT"), index=True
    )
    expiry_date: Mapped[date | None] = mapped_column(Date)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class SalesReturnLineTax(BaseEntity):
    """Store the tax components one return line actually credited.

    The mirror of `SalesInvoiceLineTax`, and missing for the same reason it
    was: a line carried a single `tax_amount`, which is what the customer gets
    back and is useless on a printed credit note. A GST credit note has to name
    each component it reverses.

    Re-asking the rule engine at print time is what this exists to prevent:
    rules are effective-dated, so the engine can answer differently from what
    was actually credited. `tax_component_id` carries no foreign key for the
    reason the invoice's does not -- it names the catalogue row that produced
    this line at the time, and the catalogue moves on.
    """

    __tablename__ = "sales_return_line_taxes"
    __table_args__ = (
        Index("IX_sales_return_line_taxes_line", "sales_return_line_id"),
        Index("IX_sales_return_line_taxes_firm", "firm_id"),
    )

    sales_return_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_return_lines.id", ondelete="CASCADE"),
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
    #: Tax already inside the price, which the note shows but does not add.
    included_in_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Whether the buyer had claimed it as input credit.
    recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class SalesReturnAttachment(BaseEntity):
    """Store sales return attachments."""

    __tablename__ = "sales_return_attachments"
    __table_args__ = ()

    sales_return_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_returns.id", ondelete="CASCADE"),
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
        default="SALES_RETURN_FILE",
        server_default="SALES_RETURN_FILE",
    )


class SalesReturnNote(BaseEntity):
    """Store sales return notes."""

    __tablename__ = "sales_return_notes"
    __table_args__ = ()

    sales_return_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_returns.id", ondelete="CASCADE"),
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
