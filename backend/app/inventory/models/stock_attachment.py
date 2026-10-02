"""Evidence kept with a stock movement or a count sheet (STK-9).

A write-off of a crushed carton, a count that found a shelf short, a transfer
the driver signed for: each is a decision somebody will later be asked to
justify, and the photo or signed slip is the justification. Like
``delivery_note_attachments`` the row records where the file is, not the file.
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class StockAttachment(BaseEntity):
    """Store one file backing a movement or a count sheet -- never both."""

    __tablename__ = "stock_attachments"
    __table_args__ = (
        CheckConstraint(
            "(inventory_transaction_id IS NULL) <> (physical_count_id IS NULL)",
            name="CK_stock_attachments_one_parent",
        ),
        Index("IX_stock_attachments_movement", "inventory_transaction_id"),
        Index("IX_stock_attachments_count", "physical_count_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: The adjustment, write-off or transfer leg the file backs. A transfer's
    #: evidence is kept on its outbound leg and read from either.
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("inventory_transactions.id", ondelete="CASCADE"),
    )
    physical_count_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("physical_counts.id", ondelete="CASCADE"),
    )
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    #: What the file shows, in a few words ("crushed cartons, bay 4").
    caption: Mapped[str | None] = mapped_column(String(200))
