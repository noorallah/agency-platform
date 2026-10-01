"""GSTR-2B as the portal gave it, and what each of its documents matched.

Backlog 78 row 3 (§42.5), decision A36. Input credit is claimable only on what
the supplier reported (CGST Act s.16(2)(aa)), and GSTR-2B is the portal's
monthly statement of it. Nothing compared the purchase bills with it, so a bill
the supplier never filed was claimed in 3B like any other.

A firm downloads the month's 2B JSON from the portal and imports it; each of its
supplier invoices and credit or debit notes becomes a row here, matched to the
firm's own bill or debit note. Importing a month again replaces the month: the
earlier import and its rows are soft-deleted, so what a month's reconciliation
reads is always one statement.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
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


class Gstr2bImport(BaseEntity):
    """One month's GSTR-2B, imported once; a re-import replaces it."""

    __tablename__ = "gstr2b_imports"
    __table_args__ = (
        Index(
            "UQ_gstr2b_imports_firm_period_active",
            "firm_id",
            "return_period",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The 2B month, ``YYYY-MM``.
    return_period: Mapped[str] = mapped_column(String(7), nullable=False)
    #: The GSTIN the statement is for, as the file says.
    gstin: Mapped[str | None] = mapped_column(String(15))
    #: What the person called the file, for the screen.
    source_name: Mapped[str | None] = mapped_column(String(260))
    document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: Sections of the file that were present and not read (amendments,
    #: imports of goods, ISD), so the screen can say so rather than hide them.
    skipped_sections: Mapped[str | None] = mapped_column(Text)


class Gstr2bDocument(BaseEntity):
    """One supplier document in a month's GSTR-2B, and what it matched."""

    __tablename__ = "gstr2b_documents"
    __table_args__ = (
        Index("IX_gstr2b_documents_import", "gstr2b_import_id"),
        Index("IX_gstr2b_documents_firm_gstin", "firm_id", "supplier_gstin"),
        Index("IX_gstr2b_documents_invoice", "purchase_invoice_id"),
    )

    gstr2b_import_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("gstr2b_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    supplier_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    #: INVOICE, CREDIT_NOTE or DEBIT_NOTE, as the supplier filed it.
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_number: Mapped[str] = mapped_column(String(40), nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    taxable_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    igst: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    cgst: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    sgst: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    cess: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    #: The portal's "ITC available" flag for the document.
    itc_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: MATCHED, DIFFERENT, NOT_IN_BOOKS or MANUAL (matched by a person).
    match_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NOT_IN_BOOKS",
        server_default="NOT_IN_BOOKS",
    )
    #: What differs, in words, when the status is DIFFERENT.
    match_note: Mapped[str | None] = mapped_column(Text)
    #: The firm's bill the document is, for an invoice. A bare id: a bill is
    #: soft-deleted, never removed, and the row must outlive a cancelled one.
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: The firm's debit note the supplier's credit note is (A31), for a note.
    debit_note_id: Mapped[UUID | None] = mapped_column(UUIDType())
