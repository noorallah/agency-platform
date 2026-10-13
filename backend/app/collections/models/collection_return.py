"""What a collector brought home on one handed-out bill (backlog 124, row M6).

In the evening each bill in a collector's bag gets one line: collected in
full, part collected, promised, or not collected. This table is that line.

**The line is a statement, and the money is a receipt.** ``amount_collected``
is what the collector says he took; it moves no balance and posts nothing.
The money enters the books through a receipt (``settlements``) like any
other, and ``settlement_id`` names the one recorded for this line: with the
line, where the office wrote it or the firm lets its collectors record their
own, or afterwards by the office. A day's sheet therefore adds up to the
receipts recorded, and shows what is still stated and not yet received into
the books.

**One live line per handed-out bill per day**, held by a partial unique index
rather than by a read. A bill out for three days has three lines. A line is
withdrawn, never edited or deleted, so what was first said survives.

**The collector is a platform user id with no foreign key**: ``users`` lives
only in the platform store.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType

_LIVE = "NOT is_deleted AND cancelled_at IS NULL"


class CollectionReturn(BaseEntity):
    """Store one day's outcome on one bill handed to a collector."""

    __tablename__ = "collection_returns"
    __table_args__ = (
        CheckConstraint("amount_collected >= 0", name="amount_not_negative"),
        Index(
            "UQ_collection_returns_handover_day",
            "handover_id",
            "return_date",
            unique=True,
            postgresql_where=text(_LIVE),
            sqlite_where=text(_LIVE),
        ),
        Index(
            "IX_collection_returns_firm_day_collector",
            "firm_id",
            "return_date",
            "collector_id",
        ),
        Index("IX_collection_returns_firm_settlement", "firm_id", "settlement_id"),
    )

    #: The owning firm. No foreign key: `firms` lives only in the platform
    #: store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    handover_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "bill_handovers.id",
            ondelete="RESTRICT",
            name="FK_collection_returns_handover_id",
        ),
        nullable=False,
    )
    #: Who carried the bill that day, copied from the handover so a day's
    #: sheet is one indexed read. A platform user id, so no foreign key.
    collector_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    #: The firm's day the line is for.
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: COLLECTED, PART, PROMISED or NOT_COLLECTED.
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    #: What the bill owed when the line was written: a note of that moment.
    outstanding_before: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: What the collector says he took. Zero for a promise and for nothing
    #: collected. A statement, never a balance.
    amount_collected: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    #: How it was paid, in the receipt's own words (CASH, CHEQUE, UPI ...).
    payment_mode: Mapped[str | None] = mapped_column(String(20))
    #: The cheque or transfer number, where there is one.
    instrument_reference: Mapped[str | None] = mapped_column(String(120))
    #: The receipt that took this money into the books; NULL while it is
    #: only stated.
    settlement_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "settlements.id",
            ondelete="RESTRICT",
            name="FK_collection_returns_settlement_id",
        ),
    )
    #: The promise taken at the door, where one was.
    payment_promise_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "payment_promises.id",
            ondelete="RESTRICT",
            name="FK_collection_returns_payment_promise_id",
        ),
    )
    note: Mapped[str | None] = mapped_column(Text())
    #: Who wrote the line: the collector himself or the office. A platform
    #: user id, so no foreign key.
    recorded_by: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    #: Set when the line is withdrawn; the row stays.
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
    cancel_reason: Mapped[str | None] = mapped_column(Text())
