"""What a firm owes a salesman for a period, and whether it has been paid.

`app/commission` reported and paid nobody: it answered what a period earned
and stopped there, so the number lived on a screen and never in the books.
A payout is the record that closes that gap.

Three decisions shape the table.

**The amounts are snapshotted, never recomputed.** The report reads live
documents, so asking it again in September would answer a different number
than the one approved in April -- a receipt reversed, an invoice cancelled, a
rate corrected. What a firm approved is what it owes, and the row remembers
it. `CustomerService.reverse_receivable_transaction` reads stored deltas for
the same reason.

**One live payout per person per overlapping period.** Two would pay the same
collections twice, and nothing downstream could tell which was the real one.

**It goes through the ledger, not around it.** Approval posts
Dr Commission Expense / Cr Commission Payable, and payment clears the payable
against the account the money left. Both accounts are the firm's to nominate
through `firm_control_accounts`, because which account a firm books its
commission to is its accountant's decision and not something to guess.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class CommissionPayoutStatus(StrEnum):
    """Where a payout has got to.

    DRAFT is an accrual somebody can still argue with: the adjustment and the
    reason are editable and nothing has reached the ledger. APPROVED is a debt
    the firm has recognised, and it has a journal behind it. PAID is that debt
    settled. CANCELLED is an approval taken back, which reverses the journal
    rather than deleting it -- a posted entry is history.
    """

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class CommissionPayout(BaseEntity):
    """One period's commission for one salesman, from accrual to payment."""

    __tablename__ = "commission_payouts"
    __table_args__ = (
        CheckConstraint(
            "period_end >= period_start", name="CK_commission_payouts_period_order"
        ),
        CheckConstraint(
            "earned_amount >= 0", name="CK_commission_payouts_earned_amount"
        ),
        Index("IX_commission_payouts_firm_salesman", "firm_id", "salesman_id"),
        Index("IX_commission_payouts_firm_period", "firm_id", "period_start"),
        Index("IX_commission_payouts_firm_status", "firm_id", "status"),
        # One live payout per person per period, held by the database rather
        # than by the service's read alone. `_assert_period_is_free` reads and
        # then `accrue` writes, so two requests that both check before either
        # commits both pass -- driven on WHOLE01, and it left one salesman
        # holding two live payouts for one month, which pays the same
        # collections twice.
        #
        # Partial, so a CANCELLED accrual holds no claim and a period accrued
        # at the wrong rate stays correctable. PostgreSQL only, as with
        # `UQ_firms_code_active` and the rest -- the service check remains
        # authoritative, and it is also what covers *overlapping* periods,
        # which no unique key can express.
        Index(
            "UQ_commission_payouts_period_active",
            "firm_id",
            "salesman_id",
            "period_start",
            "period_end",
            unique=True,
            # Both dialects, and that matters: with only the PostgreSQL
            # clause, SQLite ignored it and `create_all` built an
            # *unconditional* unique index -- stricter than intended, and it
            # broke the documented behaviour that a CANCELLED payout frees
            # the period. The unit suite caught it.
            postgresql_where=text("NOT is_deleted AND status <> 'CANCELLED'"),
            sqlite_where=text("NOT is_deleted AND status <> 'CANCELLED'"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: NOT NULL, unlike a commission rule's: a rule can belong to the firm as a
    #: default, but there is nobody to pay a payout that names nobody.
    salesman_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    #: What the earning was measured on when it was accrued: COLLECTED,
    #: INVOICED, or MIXED where a rate change moved the arrangement mid-period.
    #: Held because the rule can change afterwards and this row still has to
    #: explain itself.
    basis: Mapped[str] = mapped_column(
        String(20), nullable=False, default="COLLECTED", server_default="COLLECTED"
    )
    #: The money the rate was applied to -- collected or invoiced, per `basis`.
    #: Kept beside the earning so a payout can be checked without re-running a
    #: report over documents that have since moved.
    measured_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: What the rules said, at accrual.
    earned_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: A correction agreed with the person, positive or negative. Editable only
    #: while the payout is DRAFT: changing what was approved without a trail is
    #: the whole defect this column exists to avoid.
    adjustment_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    adjustment_reason: Mapped[str | None] = mapped_column(Text)
    #: What is actually owed: earned plus the adjustment, floored at zero.
    #: Stored rather than derived because it is what posted to the ledger.
    payable_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CommissionPayoutStatus.DRAFT.value,
        server_default=CommissionPayoutStatus.DRAFT.value,
    )
    #: The date the accrual is booked on, and the date the journal carries.
    accrued_on: Mapped[date] = mapped_column(Date, nullable=False)
    paid_on: Mapped[date | None] = mapped_column(Date)
    #: Which cash or bank account the money left. Null until paid.
    money_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    #: The accrual journal. Null while DRAFT -- a payout nobody has approved is
    #: not yet a debt.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    #: The journal that cleared the payable. Null until paid.
    payment_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)
