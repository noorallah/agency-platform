"""A debit note: a claim on a supplier with no goods going back.

The purchasing mirror of `app/credit_note`. A supplier who billed above the
agreed rate, or billed for goods that never arrived, owes the firm the
difference -- and the input tax claimed on that difference was never really
paid, so it has to come off the firm's credit too. A purchase return is the
other case: goods go back, stock moves, and inventory is credited at what the
goods cost. A debit note moves no stock at all.

**It always names the bill it claims against**, and the lines within it. The
input tax has to be reversed at the rate the bill charged -- split across the
GST heads exactly as that bill's credit was claimed -- and only the bill line
knows that. It is also what a GST debit note has to state.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class DebitNoteStatus(StrEnum):
    """Where a debit note has got to.

    No COMPLETED: nothing has to arrive or leave. The claim is real the
    moment it is approved, which is when it posts.
    """

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class DebitNoteReason(StrEnum):
    """Why the supplier is being debited.

    Goods going back is deliberately absent: that is a purchase return, which
    moves stock.
    """

    PRICE_DIFFERENCE = "PRICE_DIFFERENCE"
    SHORT_SUPPLY = "SHORT_SUPPLY"
    OTHER = "OTHER"


class DebitNote(BaseEntity):
    """One claim against one supplier bill, with the input tax it reverses."""

    __tablename__ = "debit_notes"
    __table_args__ = (
        UniqueConstraint("firm_id", "debit_note_number", name="UQ_debit_notes_number"),
        CheckConstraint("total_amount >= 0", name="CK_debit_notes_total"),
        Index("IX_debit_notes_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_debit_notes_firm_invoice", "firm_id", "purchase_invoice_id"),
        Index("IX_debit_notes_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    #: NOT NULL on purpose: a debit note that names no bill cannot say what
    #: rate of input tax to reverse, nor which bill now owes less.
    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    debit_note_number: Mapped[str] = mapped_column(String(80), nullable=False)
    debit_note_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=DebitNoteReason.OTHER.value,
        server_default=DebitNoteReason.OTHER.value,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DebitNoteStatus.DRAFT.value,
        server_default=DebitNoteStatus.DRAFT.value,
    )
    #: What is being claimed, before tax.
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The input tax reversed with it, at the rate the bill charged.
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    #: The journal this note posted. Null while DRAFT.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )


class DebitNoteLine(BaseEntity):
    """One bill line being claimed against, in part or in whole."""

    __tablename__ = "debit_note_lines"
    __table_args__ = (
        CheckConstraint("taxable_amount >= 0", name="CK_debit_note_lines_taxable"),
        CheckConstraint("quantity >= 0", name="CK_debit_note_lines_quantity"),
        Index("IX_debit_note_lines_note", "debit_note_id", "line_number"),
        Index("IX_debit_note_lines_source", "firm_id", "purchase_invoice_line_id"),
    )

    debit_note_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("debit_notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_invoice_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoice_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    #: Stated for the supplier to recognise the line -- the units short on a
    #: short-supply claim. Not what the claim is computed from, so it may be
    #: zero on a price difference.
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(UUIDType())
    tax_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
