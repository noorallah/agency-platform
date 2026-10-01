"""What the firm already owed its suppliers on the day it started here.

A supplier's balance is not a column: it is the bills still owing, derived from
their totals less what was paid, returned and credited against them. A firm
moving from another system arrives owing money on bills this system never saw,
so the day-one position is recorded the way the old books held it -- **bill by
bill**, each with its own date and due date, the shape Tally calls bill-wise
opening balances. One lump sum per supplier would be simpler to type and would
make every payment an advance, since there is nothing for it to clear, and the
ageing would know nothing about how old the debt is.

Each row posts Dr opening balance equity / Cr accounts payable on the cutover
date and is then settled by ordinary payments, exactly like a purchase bill.
It is deliberately **not** a purchase invoice: it carries no goods and no tax,
and a row in `purchase_invoices` would be read by the GST returns, the purchase
register and every purchase analysis as trading that happened here.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class VendorOpeningBillStatus(StrEnum):
    """Whether an opening bill still stands."""

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class VendorOpeningBill(BaseEntity):
    """Store one bill a supplier was owed on the firm's first day here."""

    __tablename__ = "vendor_opening_bills"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_vendor_opening_bills_amount_positive"),
        UniqueConstraint(
            "firm_id", "bill_number", name="UQ_vendor_opening_bills_firm_number"
        ),
        Index("IX_vendor_opening_bills_firm_vendor", "firm_id", "vendor_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    #: This system's number, `OB-00001`, issued in order across the firm. It is
    #: also the journal's reference, which is unique per firm; the supplier's
    #: own bill number is `reference_number` and may repeat across suppliers.
    bill_number: Mapped[str] = mapped_column(String(30), nullable=False)
    #: The supplier's bill number as the old books held it.
    reference_number: Mapped[str | None] = mapped_column(String(60))
    #: When the supplier billed it, which is what the ageing counts from.
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    #: The cutover day the journal is dated. A bill two years old cannot be
    #: posted on its own date -- that period is not open, and it was not
    #: trading in these books -- so the ledger takes it on the day the books
    #: start.
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: What was still owed on it at cutover, not its original total: what was
    #: paid before then was paid in the other books.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=VendorOpeningBillStatus.POSTED.value
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
    cancellation_reason: Mapped[str | None] = mapped_column(Text())
