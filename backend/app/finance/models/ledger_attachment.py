"""The scanned bill or letter kept with a journal, receipt or payment (ACC-10).

A journal entry made by hand, a receipt, a payment: each is money moved on
somebody's say-so, and an auditor asks for the paper behind it -- the
supplier's bill for a payment, the bank's advice for a receipt, the letter
behind a write-off journal. Like ``stock_attachments`` (STK-9) the row records
where the file is, not the file, and it belongs to exactly one entry.
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class LedgerAttachment(BaseEntity):
    """One file backing a journal entry or a settlement -- never both."""

    __tablename__ = "ledger_attachments"
    __table_args__ = (
        CheckConstraint(
            "(journal_entry_id IS NULL) <> (settlement_id IS NULL)",
            name="CK_ledger_attachments_one_parent",
        ),
        Index("IX_ledger_attachments_journal", "journal_entry_id"),
        Index("IX_ledger_attachments_settlement", "settlement_id"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="CASCADE")
    )
    #: A receipt, refund or payment.
    settlement_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("settlements.id", ondelete="CASCADE")
    )
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    #: What the file is, in a few words ("supplier bill 4412").
    caption: Mapped[str | None] = mapped_column(String(200))


__all__ = ["LedgerAttachment"]
