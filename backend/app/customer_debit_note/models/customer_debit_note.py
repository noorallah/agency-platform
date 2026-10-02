"""A debit note to a customer: an invoice found to have charged too little.

GST allows exactly one instrument for raising the value of a supply already
invoiced -- a debit note against that invoice (CGST Act s.34(3)) -- and until
backlog 77 row 5 this system had none on the selling side. A firm that revised
a price upward after billing could only raise a second invoice, which declares
a second supply where there was one, or move the customer's balance by hand,
which charged no output tax on the extra at all.

The mirror of `app/credit_note`, and deliberately shaped like it: **it always
names the invoice it corrects**, it moves no stock, and its tax is charged at
the rate the invoice line was charged, which only that line knows.

What it raises is owed **on that invoice**, as TallyPrime's "against
reference" debit note is: a receipt allocated to the invoice settles the
extra, and the ageing ages it from the invoice's due date. That keeps one
derivation of "what does this bill still owe" -- `settled_against` -- rather
than a second kind of bill every receipt screen, report and guard would have
to learn (OWNER_DECISIONS A40).
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


class CustomerDebitNoteStatus(StrEnum):
    """Where a debit note has got to.

    No COMPLETED, for the credit note's reason: the charge is real the moment
    it is approved, which is when it posts.
    """

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class CustomerDebitNoteReason(StrEnum):
    """Why the customer is being charged more.

    Recorded rather than free text because the note is reported to the tax
    authority and "why" is one of its columns.
    """

    PRICE_INCREASE = "PRICE_INCREASE"
    SHORT_BILLED = "SHORT_BILLED"
    ADDITIONAL_CHARGES = "ADDITIONAL_CHARGES"
    OTHER = "OTHER"


class CustomerDebitNote(BaseEntity):
    """One charge against one invoice, with the tax it adds."""

    __tablename__ = "customer_debit_notes"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "debit_note_number", name="UQ_customer_debit_notes_number"
        ),
        CheckConstraint("total_amount >= 0", name="CK_customer_debit_notes_total"),
        Index("IX_customer_debit_notes_firm_customer", "firm_id", "customer_id"),
        Index("IX_customer_debit_notes_firm_invoice", "firm_id", "sales_invoice_id"),
        Index("IX_customer_debit_notes_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    #: NOT NULL on purpose: a debit note that names no invoice cannot say what
    #: rate to charge, and cannot be reported against the supply it corrects.
    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    debit_note_number: Mapped[str] = mapped_column(String(80), nullable=False)
    debit_note_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=CustomerDebitNoteReason.OTHER.value,
        server_default=CustomerDebitNoteReason.OTHER.value,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CustomerDebitNoteStatus.DRAFT.value,
        server_default=CustomerDebitNoteStatus.DRAFT.value,
    )
    #: What is being charged, before tax.
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The tax charged with it, at the rate the invoice charged.
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
    #: The journal this note posted. Null while DRAFT.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: What raised the customer's balance, so cancelling undoes exactly that.
    receivable_transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())


class CustomerDebitNoteLine(BaseEntity):
    """One invoice line being charged more."""

    __tablename__ = "customer_debit_note_lines"
    __table_args__ = (
        CheckConstraint(
            "taxable_amount >= 0", name="CK_customer_debit_note_lines_taxable"
        ),
        CheckConstraint("quantity >= 0", name="CK_customer_debit_note_lines_quantity"),
        Index("IX_customer_debit_note_lines_note", "debit_note_id", "line_number"),
        Index(
            "IX_customer_debit_note_lines_source", "firm_id", "sales_invoice_line_id"
        ),
    )

    debit_note_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customer_debit_notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The invoice line this charges more on; its tax decides the rate.
    sales_invoice_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoice_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    #: Stated for the customer to recognise the line. A price increase charges
    #: value, not units, so it may be zero and is never what the charge is
    #: computed from; the HSN summary counts no units for it.
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
    #: Copied from the invoice line so the charge can be explained without
    #: re-reading a tax profile that may since have been edited.
    tax_profile_id: Mapped[UUID | None] = mapped_column(UUIDType())
    tax_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
