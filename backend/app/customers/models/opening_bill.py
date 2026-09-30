"""What customers already owed the firm on the day it started here.

The customer mirror of `VendorOpeningBill`. A firm moving from another system
arrives owed money on bills this system never saw. Recorded as one figure on
the customer (`Customer.opening_balance`) every receipt against it is money on
account with nothing to clear, and the ageing knows nothing about how old the
debt is. Recorded **bill by bill** -- the shape Tally calls a bill-wise breakup
of the opening balance -- each old bill keeps its own date and due date, a
receipt is allocated against it exactly as against a sales invoice, and the
ageing puts it in the right bucket.

A customer's opening position is one or the other, never both:
`CustomerOpeningBillService` refuses a bill while the master carries a
non-zero opening balance, and `CustomerService` refuses a non-zero opening
balance while live bills stand. Both at once would count the same debt twice.

Each row posts Dr accounts receivable / Cr opening balance equity on the
cutover date and writes an `OPENING_BILL` receivable transaction, so the
customer's balance, statement, credit control and delete guard all see it. It
is deliberately **not** a sales invoice: it carries no goods and no tax, and a
row in `sales_invoices` would be read by the GST returns, the sales register,
e-invoicing and TCS turnover as trading that happened here.
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


class CustomerOpeningBillStatus(StrEnum):
    """Whether an opening bill still stands."""

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class CustomerOpeningBill(BaseEntity):
    """Store one bill a customer owed on the firm's first day here."""

    __tablename__ = "customer_opening_bills"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_customer_opening_bills_amount_positive"),
        UniqueConstraint(
            "firm_id", "bill_number", name="UQ_customer_opening_bills_firm_number"
        ),
        Index("IX_customer_opening_bills_firm_customer", "firm_id", "customer_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    #: This system's number, `OBC-00001`, issued in order across the firm. It
    #: is also the journal's reference, which is unique per firm -- hence a
    #: prefix the supplier series (`OB-`) cannot produce.
    bill_number: Mapped[str] = mapped_column(String(30), nullable=False)
    #: The bill's number as the old books held it.
    reference_number: Mapped[str | None] = mapped_column(String(60))
    #: When the customer was billed.
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: When it fell due, which is what the ageing counts from. Given, or the
    #: bill date plus the customer's payment terms at the time it was entered
    #: -- stored rather than derived so changing the terms later does not
    #: re-age debts from before the firm started here.
    due_date: Mapped[date | None] = mapped_column(Date)
    #: The cutover day the journal and the receivable row are dated.
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: What was still owed on it at cutover, not its original total.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CustomerOpeningBillStatus.POSTED.value
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
