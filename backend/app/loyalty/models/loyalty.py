"""Credit a customer earns on what they buy, and spends on what they buy next.

Loyalty points and cashback are the same subsystem seen twice -- a balance the
customer holds and can spend -- so there is one ledger rather than two. What a
firm calls it is a matter of the conversion rate: a point worth one rupee is
cashback, and a point worth less is a points scheme.

**Redeeming settles the bill; it does not discount it.** The supply is worth
what it is worth and the full tax is charged on it; the customer pays part of it
with credit the firm already owes them, exactly as a gift voucher works. The
alternative -- treating a redemption as a discount -- reduces the taxable value
and so reduces the GST the firm collects, which is a decision about tax rather
than about loyalty and is not one this module should be making quietly.

That choice is what makes the accounting honest as well. Points cost the firm
money **when they are earned**, not when they are spent: earning posts
`Dr Loyalty Expense / Cr Loyalty Payable`, and redeeming posts
`Dr Loyalty Payable / Cr Accounts Receivable`. A scheme's cost therefore shows
up in the month it was incurred rather than whenever customers happen to
collect.

**The balance is derived, never stored.** It is the sum of the ledger, the way
an invoice's outstanding is the sum of its allocations -- a balance column would
be a second copy, and the copy is wrong the first time anything writes one
without going through this service.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from app.core.database.types import UUIDType


class LoyaltyEntryKind(StrEnum):
    """Why points moved.

    Every kind carries a signed `points`, so the balance is one sum rather than
    a set of rules about which kinds add and which subtract. A kind that had to
    be interpreted before it could be totalled is a kind somebody will
    eventually interpret differently.
    """

    EARNED = "EARNED"
    REDEEMED = "REDEEMED"
    #: Points that ran out of time. Written by the expiry sweep rather than
    #: inferred at read time, so the balance is answerable without knowing
    #: today's date and a customer can be shown what lapsed and when.
    EXPIRED = "EXPIRED"
    #: A correction somebody made by hand, with a reason. Kept apart from
    #: EARNED so a scheme's cost can be reported without goodwill gestures in
    #: the middle of it.
    ADJUSTED = "ADJUSTED"
    #: Undoes an earlier entry -- a cancelled invoice takes its points back.
    REVERSED = "REVERSED"


class LoyaltySettings(BaseEntity):
    """One firm's scheme.

    Off by default, so shipping this credits nobody until a firm says what its
    scheme is.
    """

    __tablename__ = "loyalty_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_loyalty_settings_firm"),
        CheckConstraint("points_per_amount >= 0", name="CK_loyalty_settings_earn_rate"),
        CheckConstraint(
            "amount_per_point >= 0", name="CK_loyalty_settings_point_value"
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: How many points a hundred of billed value earns. Expressed per hundred
    #: rather than per rupee so a firm can say "two points per hundred"
    #: without a fraction nobody can read back.
    points_per_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("1"), server_default="1"
    )
    #: What one point is worth when it is spent. A point worth one rupee is
    #: cashback; a point worth less is a points scheme. The same ledger either
    #: way, which is why there is one module and not two.
    amount_per_point: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("1"), server_default="1"
    )
    #: Below this, a balance cannot be spent. Firms use it to stop a scheme
    #: turning into a two-rupee deduction on every bill.
    minimum_redemption_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: How long points last. NULL means they do not expire, which is a real
    #: choice and not a missing value -- zero would mean they expire the day
    #: they are earned.
    expiry_months: Mapped[int | None] = mapped_column(Integer)


class LoyaltyEntry(BaseEntity):
    """One movement of a customer's credit.

    Append-only in spirit: nothing here is edited. A mistake is corrected by a
    further entry, so the ledger reads as what happened rather than as what
    somebody last decided it should look like.
    """

    __tablename__ = "loyalty_entries"
    __table_args__ = (
        CheckConstraint("points <> 0", name="CK_loyalty_entries_points_nonzero"),
        Index("IX_loyalty_entries_firm_customer", "firm_id", "customer_id"),
        Index("IX_loyalty_entries_firm_expiry", "firm_id", "expires_on"),
        Index("IX_loyalty_entries_firm_invoice", "firm_id", "sales_invoice_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Signed, so the balance is one sum. Positive earns, negative spends.
    points: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: What the points were worth in money when they moved. Stored rather than
    #: derived from today's `amount_per_point`, because a scheme's rate
    #: changes and a redemption made in March was worth what it was worth in
    #: March -- the same reason an invoice inherits the line it bills.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The bill that earned them, or the bill they were spent on.
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    earned_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: NULL where the scheme has no expiry. An entry that has expired is not
    #: deleted; an EXPIRED entry is written against it.
    expires_on: Mapped[date | None] = mapped_column(Date)
    #: The entry this one undoes or expires, so a sweep cannot take the same
    #: points twice and a reversal can be traced to what it reversed.
    reverses_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("loyalty_entries.id", ondelete="RESTRICT")
    )
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
