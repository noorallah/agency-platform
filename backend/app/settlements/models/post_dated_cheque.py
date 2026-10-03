"""A cheque dated ahead, held until it can be banked (backlog 42.3, ACC-2).

A cheque received today for the 30th is not money until the 30th, so it is not
a receipt yet: recording one would clear the customer's bills, move the bank
book and count as a collection on a day the bank would refuse it. It is held
here instead, and becomes a real receipt -- through `ReceiptService.create`,
like any other -- the day it is deposited. A cheque the firm hands a supplier
dated ahead is the same document the other way round, becoming a payment the
day it is presented.

What happens next is the bank's answer. **Cleared** posts nothing: the money
was counted when it was banked, as Tally's PDC does. **Bounced** reverses the
receipt through the settlement's own reversal, so the bills owe again and the
bank book gives the money back; what the bank charged the firm for the return,
and what the firm charges the customer for it, each post a journal of their
own. A cheque still held can be cancelled -- handed back or replaced -- and was
never posted, so nothing is undone.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class PostDatedChequeStatus(StrEnum):
    """Where a post-dated cheque has got to."""

    #: Received (or written) and waiting for its date. Nothing is posted.
    HELD = "HELD"
    #: Banked (or presented); the receipt or payment is posted.
    DEPOSITED = "DEPOSITED"
    #: The bank honoured it. Nothing more is posted.
    CLEARED = "CLEARED"
    #: The bank returned it; the receipt or payment was reversed.
    BOUNCED = "BOUNCED"
    #: Handed back or replaced before it was banked.
    CANCELLED = "CANCELLED"


#: The states in which the cheque still stands for money somebody means to pay.
LIVE_STATUSES: frozenset[str] = frozenset(
    {
        PostDatedChequeStatus.HELD.value,
        PostDatedChequeStatus.DEPOSITED.value,
        PostDatedChequeStatus.CLEARED.value,
    }
)


class PostDatedCheque(BaseEntity):
    """Store one cheque dated ahead, from a customer or to a supplier."""

    __tablename__ = "post_dated_cheques"
    __table_args__ = (
        CheckConstraint(
            "(direction = 'RECEIPT' AND customer_id IS NOT NULL AND vendor_id IS "
            "NULL) OR (direction = 'PAYMENT' AND vendor_id IS NOT NULL AND "
            "customer_id IS NULL)",
            name="CK_post_dated_cheques_party_matches_direction",
        ),
        CheckConstraint("amount > 0", name="CK_post_dated_cheques_amount_positive"),
        CheckConstraint(
            "bank_charges_amount >= 0 AND customer_charge_amount >= 0",
            name="CK_post_dated_cheques_charges_not_negative",
        ),
        Index(
            "IX_post_dated_cheques_firm_status_date",
            "firm_id",
            "status",
            "cheque_date",
        ),
        Index("IX_post_dated_cheques_firm_customer", "firm_id", "customer_id"),
        Index("IX_post_dated_cheques_firm_vendor", "firm_id", "vendor_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: ``RECEIPT`` (a customer's cheque) or ``PAYMENT`` (the firm's own).
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    cheque_number: Mapped[str] = mapped_column(String(30), nullable=False)
    #: The date written on the cheque: the first day it can be banked.
    cheque_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: The bank it is drawn on, as printed on the leaf.
    drawn_on_bank: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The day the firm took the cheque in, or handed it over.
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PostDatedChequeStatus.HELD.value,
        server_default=PostDatedChequeStatus.HELD.value,
    )
    #: The receipt or payment it became when banked.
    settlement_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("settlements.id", ondelete="RESTRICT")
    )
    deposited_on: Mapped[date | None] = mapped_column(Date)
    cleared_on: Mapped[date | None] = mapped_column(Date)
    bounced_on: Mapped[date | None] = mapped_column(Date)
    bounce_reason: Mapped[str | None] = mapped_column(Text())
    #: What the firm's own bank charged for the returned cheque.
    bank_charges_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    #: What the firm charged the customer for it (receipts only).
    customer_charge_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    #: The journal the two charges posted, where there were any.
    charges_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: The customer's receivable row the charge wrote, so the balance and the
    #: ledger move together.
    charge_receivable_transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_reason: Mapped[str | None] = mapped_column(Text())
