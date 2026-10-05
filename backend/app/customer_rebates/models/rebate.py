"""A customer's turnover rebate: "2% back on the year's purchases over 10 lakh".

SG-9, backlog 87 row 9: the mirror of the supplier's volume rebate
(``app/supplier_rebates``, BUY-13). An agreement names **one customer or one
customer group**, a period and its slabs. The turnover is the taxable value of
the approved bills dated in the period, less the completed sales returns and
approved credit notes of the period, plus its approved debit notes -- derived
every time, never stored until the period is accrued. The highest slab the
turnover reaches sets the rate, and that rate applies to the **whole**
turnover.

At the end of the period the rebate is **accrued** once: Dr rebates allowed,
Cr customer rebate payable. It is then **settled** by a party adjustment of
kind ``CUSTOMER_REBATE`` -- Dr customer rebate payable, Cr receivable, set
against the customer's open bills -- which reuses the approval, the posting
and the reversal every other adjustment has.

No tax, anywhere. ``agreed_before_sale`` records whether the rebate was
promised before the supplies it rewards (CGST Act s.15(3)(b)): only then may
the firm's CA reduce the taxable value with a GST credit note; otherwise the
rebate is a financial credit and the tax charged stands.
"""

from datetime import date, datetime
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
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class CustomerRebateStatus(StrEnum):
    """Where an agreement has got to."""

    #: Counting: sales in the period add to the turnover.
    ACTIVE = "ACTIVE"
    #: The period is over and the rebate is in the books.
    ACCRUED = "ACCRUED"
    #: Withdrawn before anything was accrued.
    CANCELLED = "CANCELLED"


class CustomerRebateAgreement(BaseEntity):
    """One customer's, or one customer group's, rebate over one period."""

    __tablename__ = "customer_rebate_agreements"
    __table_args__ = (
        Index(
            "UQ_customer_rebate_agreements_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_customer_rebate_agreements_firm_customer", "firm_id", "customer_id"),
        Index(
            "IX_customer_rebate_agreements_firm_group",
            "firm_id",
            "customer_group_id",
        ),
        CheckConstraint("period_to >= period_from", name="period_order"),
        # One customer or one group, never both and never neither.
        CheckConstraint(
            "(customer_id IS NOT NULL AND customer_group_id IS NULL) OR "
            "(customer_id IS NULL AND customer_group_id IS NOT NULL)",
            name="one_party",
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    customer_group_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customer_groups.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CustomerRebateStatus.ACTIVE.value,
        server_default=CustomerRebateStatus.ACTIVE.value,
    )
    #: Whether the rebate was promised before the supplies it rewards
    #: (s.15(3)(b)). Recorded for the firm's CA; nothing here computes tax.
    agreed_before_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    notes: Mapped[str | None] = mapped_column(Text)
    #: Snapshotted at accrual and never re-read: what the journal said.
    accrued_turnover: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    accrued_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    accrued_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    accrual_journal_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    accrued_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    accrued_by: Mapped[UUID | None] = mapped_column(UUIDType())


class CustomerRebateSlab(BaseEntity):
    """One step: from this turnover, this rate on all of it."""

    __tablename__ = "customer_rebate_slabs"
    __table_args__ = (
        Index("IX_customer_rebate_slabs_agreement", "agreement_id"),
        CheckConstraint("threshold >= 0", name="threshold"),
        CheckConstraint("rate_percent > 0 AND rate_percent <= 100", name="rate"),
    )

    agreement_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customer_rebate_agreements.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
