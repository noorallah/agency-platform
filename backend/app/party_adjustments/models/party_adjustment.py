"""A party balance moved without money and without tax (backlog 74 row 2).

Three kinds, one table, for the reason receipts and payments share one: the
rules that matter -- an allocation cannot exceed what a bill owes, the amount
must reach the ledger, a cancel reverses by what was stored -- are the same in
every kind, and two copies would drift.

* **Customer write-off** -- a debt the firm has given up collecting. Dr bad
  debts, Cr receivable.
* **Supplier write-back** -- a balance the firm owed and will not pay. Dr
  payable, Cr balances written back (other income).
* **Set-off** -- a customer and a supplier who are the same business: what
  they owe the firm is settled by what the firm owes them. Dr payable, Cr
  receivable.

**None of them touches tax.** Reducing the value of a supply is a credit note
or a debit note, which reverses the tax charged on it; an adjustment only says
the balance will not move as money.
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

#: What every adjustment above it needs: a second person holding
#: `PARTY_ADJUSTMENT_APPROVE` (decided by convention, 2026-10-01). A rupee
#: written off is a rupee of profit given away, and the usual control is a
#: maker and a checker above a small sum.
DEFAULT_APPROVAL_THRESHOLD = Decimal("1000.00")

#: The most a receipt or payment may round off without it being a discount
#: (decided by convention, 2026-10-01). Ten rupees covers a bill paid to the
#: nearest ten and a bank's paisa; anything larger is a decision somebody
#: should name as a discount or a write-off.
DEFAULT_ROUNDING_LIMIT = Decimal("10.00")


class PartyAdjustmentKind(StrEnum):
    """Which balance moves, and against what."""

    CUSTOMER_WRITE_OFF = "CUSTOMER_WRITE_OFF"
    SUPPLIER_WRITE_BACK = "SUPPLIER_WRITE_BACK"
    SET_OFF = "SET_OFF"


class PartyAdjustmentStatus(StrEnum):
    """Where an adjustment has got to.

    It posts at approval and is undone by cancelling, never edited after:
    the journal is mirrored and the customer's balance put back by the
    deltas the approval stored.
    """

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class PartyAdjustment(BaseEntity):
    """One balance moved without money: write-off, write-back or set-off."""

    __tablename__ = "party_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "adjustment_number", name="UQ_party_adjustments_number"
        ),
        CheckConstraint("amount > 0", name="CK_party_adjustments_amount_positive"),
        # The parties the kind implies, and no others.
        CheckConstraint(
            "(kind = 'CUSTOMER_WRITE_OFF' AND customer_id IS NOT NULL "
            "AND vendor_id IS NULL) OR (kind = 'SUPPLIER_WRITE_BACK' "
            "AND vendor_id IS NOT NULL AND customer_id IS NULL) OR "
            "(kind = 'SET_OFF' AND customer_id IS NOT NULL "
            "AND vendor_id IS NOT NULL)",
            name="CK_party_adjustments_parties_match_kind",
        ),
        Index("IX_party_adjustments_firm_date", "firm_id", "adjustment_date"),
        Index("IX_party_adjustments_firm_status", "firm_id", "status"),
        Index("IX_party_adjustments_firm_customer", "firm_id", "customer_id"),
        Index("IX_party_adjustments_firm_vendor", "firm_id", "vendor_id"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    adjustment_number: Mapped[str] = mapped_column(String(60), nullable=False)
    adjustment_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: Why the balance is being moved. Required: an auditor asks first.
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PartyAdjustmentStatus.DRAFT.value,
        server_default=PartyAdjustmentStatus.DRAFT.value,
    )
    #: The journal approval posted. Null while DRAFT.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: The mirror that cancelled it.
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: The customer's receivable row approval wrote, undone by its own deltas
    #: on cancel. No foreign key, as `tcs_collections` holds it: the row is the
    #: customer module's.
    receivable_transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_by: Mapped[UUID | None] = mapped_column(UUIDType())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
    cancel_reason: Mapped[str | None] = mapped_column(Text())


class PartyAdjustmentAllocation(BaseEntity):
    """How much of one adjustment came off one bill.

    Exactly one of the four bill columns, as on `settlement_allocations`. A
    set-off carries rows on both sides: sales bills it clears for the
    customer, purchase bills for the supplier.
    """

    __tablename__ = "party_adjustment_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_party_adjustment_allocations_positive"),
        UniqueConstraint(
            "party_adjustment_id",
            "sales_invoice_id",
            name="UQ_party_adjustment_allocations_sales_invoice",
        ),
        UniqueConstraint(
            "party_adjustment_id",
            "purchase_invoice_id",
            name="UQ_party_adjustment_allocations_purchase_invoice",
        ),
        UniqueConstraint(
            "party_adjustment_id",
            "customer_opening_bill_id",
            name="UQ_party_adjustment_allocations_customer_opening_bill",
        ),
        UniqueConstraint(
            "party_adjustment_id",
            "vendor_opening_bill_id",
            name="UQ_party_adjustment_allocations_vendor_opening_bill",
        ),
        Index("IX_party_adjustment_allocations_sales", "firm_id", "sales_invoice_id"),
        Index(
            "IX_party_adjustment_allocations_purchase", "firm_id", "purchase_invoice_id"
        ),
        Index(
            "IX_party_adjustment_allocations_customer_opening",
            "firm_id",
            "customer_opening_bill_id",
        ),
        Index(
            "IX_party_adjustment_allocations_vendor_opening",
            "firm_id",
            "vendor_opening_bill_id",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    party_adjustment_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("party_adjustments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="RESTRICT")
    )
    customer_opening_bill_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customer_opening_bills.id", ondelete="RESTRICT")
    )
    vendor_opening_bill_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendor_opening_bills.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class PartyAdjustmentSettings(BaseEntity):
    """A firm's limits on adjusting balances. A firm with no row has defaults.

    Two numbers: the amount above which an adjustment needs a second person
    holding `PARTY_ADJUSTMENT_APPROVE`, and the most a receipt or payment may
    round off. They sit together because both answer "how much may be cleared
    without money before somebody else has to agree".
    """

    __tablename__ = "party_adjustment_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_party_adjustment_settings_firm"),
        CheckConstraint(
            "approval_threshold >= 0",
            name="CK_party_adjustment_settings_threshold",
        ),
        CheckConstraint(
            "rounding_limit >= 0", name="CK_party_adjustment_settings_rounding"
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    approval_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=DEFAULT_APPROVAL_THRESHOLD,
        server_default="1000.00",
    )
    rounding_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=DEFAULT_ROUNDING_LIMIT,
        server_default="10.00",
    )
