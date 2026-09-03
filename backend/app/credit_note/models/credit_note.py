"""A credit note that reverses tax, for money credited without goods coming back.

A credit note already existed, as a row in `customer_receivable_transactions`
raised from the customers router. It reduced what the customer owed and booked
the whole figure to sales returns -- and reversed **no output tax at all**. So
a firm that agreed a rate difference after invoicing credited the customer the
gross amount and went on declaring tax on a price nobody paid.

This is the document that closes it, and it is deliberately *not* a sales
return. A return is goods coming back: stock moves, the warehouse counts them,
and cost of goods sold is reversed at what the movement was worth. A credit
note here moves no stock at all. Conflating the two would put a stock movement
behind a rate correction, which is the shape of defect that leaves a warehouse
disagreeing with its own ledger.

**It always names the invoice it credits.** Tax has to be reversed at the rate
that was charged, not at today's rate, and only the original line knows what
that was -- the same reasoning that stops an invoice re-reading a customer's
discount. It is also what a GST credit note has to state.
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


class CreditNoteStatus(StrEnum):
    """Where a credit note has got to.

    No COMPLETED: there is nothing to complete. A sales return has one because
    goods have to arrive before the credit is real; a credit note is real the
    moment it is approved, which is when it posts.
    """

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class CreditNoteReason(StrEnum):
    """Why the customer is being credited.

    Recorded rather than free text because a credit note has to be reported to
    the tax authority, and "why" is one of the columns. Goods coming back is
    deliberately absent: that is a sales return, which moves stock.
    """

    RATE_DIFFERENCE = "RATE_DIFFERENCE"
    POST_SALE_DISCOUNT = "POST_SALE_DISCOUNT"
    DEFICIENCY_IN_SERVICE = "DEFICIENCY_IN_SERVICE"
    OTHER = "OTHER"


class CreditNote(BaseEntity):
    """One credit against one invoice, with the tax it reverses."""

    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "credit_note_number", name="UQ_credit_notes_number"
        ),
        CheckConstraint("total_amount >= 0", name="CK_credit_notes_total"),
        Index("IX_credit_notes_firm_customer", "firm_id", "customer_id"),
        Index("IX_credit_notes_firm_invoice", "firm_id", "sales_invoice_id"),
        Index("IX_credit_notes_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    #: NOT NULL on purpose. A credit note that names no invoice cannot say
    #: what rate of tax to reverse, and cannot be reported against the supply
    #: it corrects.
    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credit_note_number: Mapped[str] = mapped_column(String(80), nullable=False)
    credit_note_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=CreditNoteReason.OTHER.value,
        server_default=CreditNoteReason.OTHER.value,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CreditNoteStatus.DRAFT.value,
        server_default=CreditNoteStatus.DRAFT.value,
    )
    #: What is being credited, before tax.
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The tax being reversed with it, at the rate the invoice charged.
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    salesman_id: Mapped[UUID | None] = mapped_column(UUIDType())
    territory_id: Mapped[UUID | None] = mapped_column(UUIDType())
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    #: The journal this note posted. Null while DRAFT -- a note nobody has
    #: approved has changed no books.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: What put the customer's balance back, so cancelling can undo exactly
    #: what was done rather than recomputing it.
    receivable_transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())


class CreditNoteLine(BaseEntity):
    """One invoice line being credited, in part or in whole."""

    __tablename__ = "credit_note_lines"
    __table_args__ = (
        CheckConstraint("taxable_amount >= 0", name="CK_credit_note_lines_taxable"),
        CheckConstraint("quantity >= 0", name="CK_credit_note_lines_quantity"),
        Index("IX_credit_note_lines_note", "credit_note_id", "line_number"),
        Index(
            "IX_credit_note_lines_source",
            "firm_id",
            "sales_invoice_line_id",
        ),
    )

    credit_note_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("credit_notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The invoice line this credits. Carries the tax profile that decides
    #: what rate comes off, so the reversal matches the charge.
    sales_invoice_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoice_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    #: Stated for the tax authority and for the customer to recognise the
    #: line. It is **not** what the credit is computed from -- a rate
    #: difference credits value, not units -- so it may be zero on a
    #: post-sale discount that applies to the whole line.
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
    #: Copied from the invoice line so the reversal can be explained without
    #: re-reading a tax profile that may since have been edited.
    tax_profile_id: Mapped[UUID | None] = mapped_column(UUIDType())
    tax_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
