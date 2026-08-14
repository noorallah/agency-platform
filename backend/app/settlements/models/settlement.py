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

from datetime import date
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
from app.core.database.types import UUIDType


class SettlementDirection(StrEnum):
    """Which way the money went."""

    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"


class SettlementMethod(StrEnum):
    """How the money moved, which decides the account it lands in."""

    CASH = "CASH"
    BANK = "BANK"


class SettlementStatus(StrEnum):
    """The lifecycle of a settlement.

    There is exactly one state. A settlement is recorded after the money has
    moved, so there is nothing to approve; and it is not cancellable here,
    because reversing one has to unwind the customer's outstanding and advance
    balances by the exact amounts it moved them. That is its own piece of work
    rather than a flag.
    """

    POSTED = "POSTED"


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
            "(direction = 'RECEIPT' AND customer_id IS NOT NULL "
            "AND vendor_id IS NULL) OR (direction = 'PAYMENT' "
            "AND vendor_id IS NOT NULL AND customer_id IS NULL)",
            name="CK_settlements_party_matches_direction",
        ),
        CheckConstraint("amount > 0", name="CK_settlements_amount_positive"),
        Index("IX_settlements_firm_direction", "firm_id", "direction"),
        Index("IX_settlements_firm_date", "firm_id", "settlement_date"),
        Index("IX_settlements_firm_customer", "firm_id", "customer_id"),
        Index("IX_settlements_firm_vendor", "firm_id", "vendor_id"),
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
    instrument_reference: Mapped[str | None] = mapped_column(String(120))
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SettlementStatus.POSTED.value
    )
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
