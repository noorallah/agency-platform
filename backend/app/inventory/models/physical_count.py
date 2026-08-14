"""Physical count persistence models.

A count is a document rather than an action: the sheet is filled in over hours
by people walking a warehouse, and posted once at the end. That is the whole
reason it needs tables -- an endpoint that took counted quantities and applied
them immediately would lose everything the moment somebody closed a laptop.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
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
from app.core.database.types import UTCDateTime, UUIDType


class PhysicalCountStatus(StrEnum):
    """Where a count sheet has got to."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class PhysicalCount(BaseEntity):
    """Store one count sheet for one warehouse."""

    __tablename__ = "physical_counts"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "count_number", name="UQ_physical_counts_firm_number"
        ),
        Index("IX_physical_counts_firm_status", "firm_id", "status"),
        Index("IX_physical_counts_firm_date", "firm_id", "count_date"),
        Index("IX_physical_counts_firm_warehouse", "firm_id", "warehouse_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    count_number: Mapped[str] = mapped_column(String(60), nullable=False)
    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PhysicalCountStatus.DRAFT.value
    )
    remarks: Mapped[str | None] = mapped_column(Text())
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    posted_by: Mapped[UUID | None] = mapped_column(UUIDType())


class PhysicalCountLine(BaseEntity):
    """Store one product's count on one sheet."""

    __tablename__ = "physical_count_lines"
    __table_args__ = (
        UniqueConstraint(
            "physical_count_id",
            "line_number",
            name="UQ_physical_count_lines_line_number",
        ),
        Index("IX_physical_count_lines_count", "physical_count_id"),
        Index("IX_physical_count_lines_firm_product", "firm_id", "product_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    physical_count_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("physical_counts.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    batch_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: What the system thought when the sheet was drawn up.
    #:
    #: Kept for the person reading the sheet afterwards -- "we expected 50" --
    #: and deliberately **not** what the variance is computed from. Stock moves
    #: while a warehouse is being counted, and posting against a snapshot taken
    #: hours earlier would undo every dispatch made in between.
    expected_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    #: What was actually on the shelf. Null until somebody counts that line,
    #: which is how a half-finished sheet is distinguished from one that found
    #: nothing there.
    counted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: What the count moved, filled in when the sheet is posted.
    variance_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())
    remarks: Mapped[str | None] = mapped_column(Text())
