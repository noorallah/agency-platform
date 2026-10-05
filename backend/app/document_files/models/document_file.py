"""The uploaded file on a document, and its bytes (PG-4, SG-6).

Metadata and content are two tables so that listing a document's files, or
counting them for a page of bills, never reads a megabyte of PDF. A file
belongs to exactly one document, held by one nullable foreign key per kind of
document and a check rather than a type column, so deleting the document takes
its files with it. Purchasing brought the bill and the goods receipt (PG-4);
sales added the quotation, order, delivery note, invoice and return (SG-6).
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import LargeBinary

from app.core.database.base import Base
from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType

#: The columns of which exactly one names the file's document.
PARENT_COLUMNS: tuple[str, ...] = (
    "purchase_invoice_id",
    "goods_receipt_id",
    "sales_quotation_id",
    "sales_order_id",
    "delivery_note_id",
    "sales_invoice_id",
    "sales_return_id",
)

#: Exactly one parent, spelt so SQLite and PostgreSQL both read it.
ONE_PARENT_CHECK = (
    "("
    + " + ".join(
        f"CASE WHEN {column} IS NULL THEN 0 ELSE 1 END" for column in PARENT_COLUMNS
    )
    + ") = 1"
)


class DocumentFile(BaseEntity):
    """One uploaded file kept with a purchase or a sales document."""

    __tablename__ = "document_files"
    __table_args__ = (
        CheckConstraint(ONE_PARENT_CHECK, name="one_parent"),
        Index("IX_document_files_purchase_invoice", "purchase_invoice_id"),
        Index("IX_document_files_goods_receipt", "goods_receipt_id"),
        Index("IX_document_files_sales_quotation", "sales_quotation_id"),
        Index("IX_document_files_sales_order", "sales_order_id"),
        Index("IX_document_files_delivery_note", "delivery_note_id"),
        Index("IX_document_files_sales_invoice", "sales_invoice_id"),
        Index("IX_document_files_sales_return", "sales_return_id"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="CASCADE")
    )
    goods_receipt_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("goods_receipts.id", ondelete="CASCADE")
    )
    sales_quotation_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_quotations.id", ondelete="CASCADE")
    )
    sales_order_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="CASCADE")
    )
    delivery_note_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("delivery_notes.id", ondelete="CASCADE")
    )
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="CASCADE")
    )
    sales_return_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_returns.id", ondelete="CASCADE")
    )
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    #: Decided from the file's first bytes, never only from what was declared.
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Hex SHA-256 of the content, so a download can be checked against it.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: What the file is, in a few words ("supplier bill 4412").
    caption: Mapped[str | None] = mapped_column(String(200))


class DocumentFileContent(Base):
    """The bytes of one :class:`DocumentFile`, read only to download it."""

    __tablename__ = "document_file_contents"

    file_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("document_files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


__all__ = [
    "ONE_PARENT_CHECK",
    "PARENT_COLUMNS",
    "DocumentFile",
    "DocumentFileContent",
]
