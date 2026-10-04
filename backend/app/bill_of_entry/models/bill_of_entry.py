"""Bills of Entry: the customs side of an import (PG-12 part B, backlog 86 #5)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType

_MONEY = Numeric(18, 2)
_RATE = Numeric(9, 4)


class BillOfEntry(BaseEntity):
    """One Bill of Entry: the duty customs assessed on imported goods.

    ``DRAFT`` while it is typed, ``POSTED`` once its duty is booked, and
    ``CANCELLED`` when withdrawn -- a posted one by reversing its journal and
    taking the duty back off the stock. The status moves only through the
    transition endpoints.

    Basic customs duty and the social welfare surcharge are a cost of the
    goods and carry no credit; the IGST and cess on import are input tax,
    claimed in GSTR-3B 4(A)(1) for the period of ``boe_date``.
    """

    __tablename__ = "bills_of_entry"
    __table_args__ = (
        Index("IX_bills_of_entry_firm_date", "firm_id", "boe_date"),
        Index("IX_bills_of_entry_firm_vendor_status", "firm_id", "vendor_id", "status"),
        Index(
            "UQ_bills_of_entry_number_active",
            "firm_id",
            "document_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: Our own number, from the document framework's series.
    document_number: Mapped[str] = mapped_column(String(60), nullable=False)
    #: The number customs gave it, as printed on the Bill of Entry.
    boe_number: Mapped[str] = mapped_column(String(30), nullable=False)
    boe_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: The customs port code (six characters, e.g. ``INNSA1``).
    port_code: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The supplier abroad.
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    #: The branch that imported, which places the credit under its GSTIN.
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    #: The invoice currency and the rate customs assessed it at (rupees per
    #: unit). Recorded as printed; every amount here is already in rupees.
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    assessable_value: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    basic_customs_duty: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    social_welfare_surcharge: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    total_duty: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    #: Where the cost part (duty and surcharge) went when posted: onto stock
    #: still held, to cost of goods already sold, or -- for a line no linked
    #: receipt carries -- to *Customs Duty* expense.
    inventory_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    cogs_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    expense_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    #: ``DRAFT``, ``POSTED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[UUID | None] = mapped_column(UUIDType())
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class BillOfEntryLine(BaseEntity):
    """One item on a Bill of Entry and the duty assessed on it.

    IGST is charged on the assessable value plus basic duty plus surcharge.
    Each amount is worked out from its rate unless it was typed, and a typed
    amount wins: customs rounds per line, and the printed figure is the one
    that was paid.
    """

    __tablename__ = "bill_of_entry_lines"
    __table_args__ = (
        Index("IX_bill_of_entry_lines_boe", "bill_of_entry_id"),
        Index("IX_bill_of_entry_lines_firm_product", "firm_id", "product_id"),
    )

    bill_of_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("bills_of_entry.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    assessable_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    bcd_rate: Mapped[Decimal | None] = mapped_column(_RATE)
    bcd_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    #: Percent of the basic duty; 10 unless typed otherwise.
    sws_rate: Mapped[Decimal | None] = mapped_column(_RATE)
    sws_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    igst_rate: Mapped[Decimal | None] = mapped_column(_RATE)
    igst_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    total_duty: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    inventory_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    cogs_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    expense_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )


class BillOfEntryDocument(BaseEntity):
    """A purchase invoice or goods receipt the Bill of Entry belongs to.

    A bare id, as other cross-document references are: the link says which
    bill and which receipts the goods came on, and a cancelled one is simply
    no longer read.
    """

    __tablename__ = "bill_of_entry_documents"
    __table_args__ = (
        Index("IX_bill_of_entry_documents_boe", "bill_of_entry_id"),
        Index("IX_bill_of_entry_documents_document", "document_id"),
    )

    bill_of_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("bills_of_entry.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: ``PURCHASE_INVOICE`` or ``GOODS_RECEIPT``.
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)


class BillOfEntryAllocation(BaseEntity):
    """The share of a line's duty one receipt line carried into stock."""

    __tablename__ = "bill_of_entry_allocations"
    __table_args__ = (
        Index("IX_bill_of_entry_allocations_boe", "bill_of_entry_id"),
        Index("IX_bill_of_entry_allocations_receipt", "goods_receipt_id"),
    )

    bill_of_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("bills_of_entry.id", ondelete="CASCADE"),
        nullable=False,
    )
    bill_of_entry_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("bill_of_entry_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    goods_receipt_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("goods_receipts.id", ondelete="RESTRICT"), nullable=False
    )
    goods_receipt_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("goods_receipt_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Received, in the stock unit.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    inventory_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    cogs_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
