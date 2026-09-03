"""Settlement persistence models: money arriving, and money going out.

A settlement is one movement of money against a party -- a receipt from a
customer or a payment to a vendor -- together with the invoices it clears.

Both directions are one table because they are the same document with the
signs reversed. Splitting them would double every rule that matters (the
allocation cannot exceed the amount, the amount must reach the ledger, an
invoice cannot be over-cleared) and the two copies would drift, which is what
happened to the seven transactional document modules before they were given a
shared base.
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


class SettlementDirection(StrEnum):
    """Which way the money went."""

    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"
    #: Money back to a customer. It is money out like a payment and
    #: about a customer like a receipt, which is why it is neither of
    #: them: refunding a customer reduces what they have paid in
    #: advance rather than settling anything the firm owes a supplier.
    REFUND = "REFUND"


class SettlementMethod(StrEnum):
    """How the money moved, which decides the account it lands in."""

    CASH = "CASH"
    BANK = "BANK"


class SettlementStatus(StrEnum):
    """The lifecycle of a settlement.

    Two states, and no approval between them: a settlement is recorded after
    the money has moved, so there is nothing to decide. A mistake is taken back
    rather than edited -- the original stays, a mirror journal cancels it, and
    both are visible. Money that was recorded and then unrecorded is a fact
    about the day, not something to erase.
    """

    POSTED = "POSTED"
    REVERSED = "REVERSED"


class Settlement(BaseEntity):
    """Store one receipt from a customer or payment to a vendor."""

    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "settlement_number", name="UQ_settlements_firm_number"
        ),
        # Exactly one party, and it is the one the direction implies. A receipt
        # from a vendor is not a thing this document records.
        CheckConstraint(
            "(direction IN ('RECEIPT', 'REFUND') AND customer_id IS "
            "NOT NULL AND vendor_id IS NULL) OR (direction = 'PAYMENT' "
            "AND vendor_id IS NOT NULL AND customer_id IS NULL)",
            name="CK_settlements_party_matches_direction",
        ),
        CheckConstraint("amount > 0", name="CK_settlements_amount_positive"),
        Index("IX_settlements_firm_direction", "firm_id", "direction"),
        Index("IX_settlements_firm_date", "firm_id", "settlement_date"),
        Index("IX_settlements_firm_customer", "firm_id", "customer_id"),
        Index("IX_settlements_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_settlements_firm_order", "firm_id", "sales_order_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    settlement_number: Mapped[str] = mapped_column(String(60), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: What was allocated to invoices, and what was not. The remainder is an
    #: advance: money held against nothing in particular, which is a normal
    #: thing for a customer to send and has to be visible rather than inferred.
    allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    unallocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The cash or bank account the money actually moved through, resolved from
    #: the firm's control accounts at the time and then stored. Re-deriving it
    #: later would rewrite history if the mapping is ever changed.
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The order this money came in against, where it came in against one.
    #:
    #: A note about *why* the money arrived, not a ring-fence around it. The
    #: cash is the customer's balance either way: if the order is cancelled the
    #: deposit does not vanish, it stays on account. Recording the order is
    #: what makes "what has this customer paid us for order X" answerable, and
    #: what lets the bill for that order find the deposit when it is raised.
    sales_order_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="RESTRICT")
    )
    instrument_reference: Mapped[str | None] = mapped_column(String(120))
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SettlementStatus.POSTED.value
    )
    #: The mirror journal that cancelled this one, and why. Set together with
    #: the status so a reversed settlement can always show what undid it.
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reversed_by: Mapped[UUID | None] = mapped_column(UUIDType())
    reversal_reason: Mapped[str | None] = mapped_column(Text())
    #: The journal this wrote. A settlement that did not reach the ledger is
    #: the defect this module exists to fix, so the link is not optional.
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )


class SettlementAllocation(BaseEntity):
    """Store how much of one settlement cleared one invoice."""

    __tablename__ = "settlement_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_settlement_allocations_positive"),
        # One row per settlement per invoice: two lines against the same
        # invoice are one allocation, and keeping them apart would make the
        # outstanding arithmetic depend on how somebody typed it.
        UniqueConstraint(
            "settlement_id",
            "sales_invoice_id",
            name="UQ_settlement_allocations_sales_invoice",
        ),
        UniqueConstraint(
            "settlement_id",
            "purchase_invoice_id",
            name="UQ_settlement_allocations_purchase_invoice",
        ),
        Index("IX_settlement_allocations_sales", "firm_id", "sales_invoice_id"),
        Index("IX_settlement_allocations_purchase", "firm_id", "purchase_invoice_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    settlement_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("settlements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
