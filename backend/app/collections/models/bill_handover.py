"""A bill handed to a collector (backlog 122, first customer row M4).

In the morning the office hands a bundle of unpaid bills to the person who
goes round for the money, and in the evening takes back what he did not
collect. This table is that bundle: which bill went out, with whom, on which
day, and when it came back.

**A handover is a note beside a bill and never touches the books.** It moves
no balance, writes no journal and changes no report: what a bill owes is still
derived from the receipts, and a bill is owed the same whether it is in the
office or in a collector's bag. Neither column here is read by anything that
states money.

**A bill is out with one person at a time**, held by a partial unique index
per kind of bill rather than by a read, because two people handing out the
same bundle is a decision about a key. Taking a bill back keeps the row, so
who carried a bill, and when, survives.

**The collector is a platform user id with no foreign key**: ``users`` lives
only in the platform store.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType

_OUT = "NOT is_deleted AND returned_at IS NULL"


class BillHandover(BaseEntity):
    """Store one bill handed to one collector, and when it came back."""

    __tablename__ = "bill_handovers"
    __table_args__ = (
        # A bill is a sales invoice or a bill owed from before the firm
        # started here, never both and never neither.
        CheckConstraint(
            "(sales_invoice_id IS NULL) <> (customer_opening_bill_id IS NULL)",
            name="one_bill",
        ),
        Index(
            "UQ_bill_handovers_invoice_out",
            "sales_invoice_id",
            unique=True,
            postgresql_where=text(_OUT),
            sqlite_where=text(_OUT),
        ),
        Index(
            "UQ_bill_handovers_opening_bill_out",
            "customer_opening_bill_id",
            unique=True,
            postgresql_where=text(_OUT),
            sqlite_where=text(_OUT),
        ),
        Index("IX_bill_handovers_firm_collector", "firm_id", "collector_id"),
        Index("IX_bill_handovers_firm_handed_on", "firm_id", "handed_on"),
        Index("IX_bill_handovers_firm_customer", "firm_id", "customer_id"),
    )

    #: The owning firm. No foreign key: `firms` lives only in the platform
    #: store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "customers.id",
            ondelete="RESTRICT",
            name="FK_bill_handovers_customer_id",
        ),
        nullable=False,
    )
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "sales_invoices.id",
            ondelete="RESTRICT",
            name="FK_bill_handovers_sales_invoice_id",
        ),
    )
    customer_opening_bill_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "customer_opening_bills.id",
            ondelete="RESTRICT",
            name="FK_bill_handovers_customer_opening_bill_id",
        ),
    )
    #: Who carries the bill. A platform user id, so no foreign key.
    collector_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    #: The firm's day the bill went out.
    handed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Who handed it out. A platform user id, so no foreign key.
    handed_by: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    #: What the bill owed as it went out: a note of that moment, never a
    #: balance. What it owes now is read from the receipts.
    outstanding_at_handover: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    #: Set when the bill is taken back; the row stays.
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    returned_by: Mapped[UUID | None] = mapped_column(UUIDType())
    return_note: Mapped[str | None] = mapped_column(Text())
