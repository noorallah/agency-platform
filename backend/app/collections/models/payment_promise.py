"""A customer's promise to pay (backlog 87 #8, SG-8).

"He said Friday, five thousand." A distributor's collection runs on what was
promised and by when -- Tally's follow-up register, Busy and Marg's collection
list, Zoho's expected payment date -- and the firm had nowhere to write it.

**A promise is recorded, never posted.** It moves no balance and writes no
journal; it is a note beside a bill, or beside the account as a whole, that
the receipts later prove kept or broken.

**Whether it was kept is derived, never stored** (`app/collections/services`):
kept when the receipts dated from the day it was taken up to the day it was
promised for cover the amount, broken once that day has passed without them.
A stored status would be a second copy of the receipts, wrong the first time
one is reversed.

**A promise is withdrawn, never edited or deleted**, so the record of what the
customer said -- and how often -- survives. A changed promise is a withdrawn
one and a new one.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class PaymentPromise(BaseEntity):
    """Store one promise to pay, against a bill or the customer's account."""

    __tablename__ = "payment_promises"
    __table_args__ = (
        # Named by the metadata convention: CK_payment_promises_amount_positive.
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("IX_payment_promises_firm_promised_on", "firm_id", "promised_on"),
        Index("IX_payment_promises_firm_invoice", "firm_id", "sales_invoice_id"),
        Index("IX_payment_promises_firm_customer", "firm_id", "customer_id"),
    )

    #: The owning firm. No foreign key: `firms` lives only in the platform
    #: store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "customers.id",
            ondelete="RESTRICT",
            name="FK_payment_promises_customer_id",
        ),
        nullable=False,
    )
    #: The bill the promise is for; NULL is a promise for the account as a
    #: whole ("I will send ten thousand on Monday").
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "sales_invoices.id",
            ondelete="RESTRICT",
            name="FK_payment_promises_sales_invoice_id",
        ),
    )
    #: The day the payment is promised **for**.
    promised_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text())
    #: The UTC day the promise was taken. Receipts count toward it from here.
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Who wrote it down. A platform user id, so no foreign key.
    recorded_by: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    #: Who took the promise from the customer: the collector named when it
    #: was recorded, else the customer's collector that day. A platform user
    #: id, so no foreign key.
    collector_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: Set when the promise is withdrawn; the row stays.
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_reason: Mapped[str | None] = mapped_column(Text())
