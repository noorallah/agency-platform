"""A supplier's volume rebate: "2% back on the year's purchases over 10 lakh".

BUY-13, decision A124. An agreement names one supplier, a period and its
slabs. The volume is the taxable value of the supplier's approved bills dated
in the period, less what completed purchase returns to it took back in the
same period -- derived every time, never stored until the period is accrued.
The highest slab the volume reaches sets the rate, and that rate applies to
the **whole** volume: crossing 10 lakh earns 2% on all of it, the way
principals write volume schemes.

At the end of the period the rebate is **accrued** once: Dr supplier rebates
receivable, Cr supplier incentives received. It is then **settled** by a
party adjustment of kind ``SUPPLIER_REBATE`` -- the supplier's credit note set
against its open bills, Dr payable, Cr rebates receivable -- which reuses the
approval, the posting and the reversal every other adjustment has.
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
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class SupplierRebateStatus(StrEnum):
    """Where an agreement has got to."""

    #: Counting: purchases in the period add to the volume.
    ACTIVE = "ACTIVE"
    #: The period is over and the rebate is in the books.
    ACCRUED = "ACCRUED"
    #: Withdrawn before anything was accrued.
    CANCELLED = "CANCELLED"


class SupplierRebateAgreement(BaseEntity):
    """One supplier's rebate over one period."""

    __tablename__ = "supplier_rebate_agreements"
    __table_args__ = (
        Index(
            "UQ_supplier_rebate_agreements_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_supplier_rebate_agreements_firm_vendor", "firm_id", "vendor_id"),
        CheckConstraint(
            "period_to >= period_from",
            name="CK_supplier_rebate_agreements_period_order",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SupplierRebateStatus.ACTIVE.value,
        server_default=SupplierRebateStatus.ACTIVE.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    #: Snapshotted at accrual and never re-read: what the journal said.
    accrued_volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    accrued_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    accrued_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    accrual_journal_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    accrued_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    accrued_by: Mapped[UUID | None] = mapped_column(UUIDType())


class SupplierRebateSlab(BaseEntity):
    """One step: from this volume, this rate on all of it."""

    __tablename__ = "supplier_rebate_slabs"
    __table_args__ = (
        Index("IX_supplier_rebate_slabs_agreement", "agreement_id"),
        CheckConstraint("threshold >= 0", name="CK_supplier_rebate_slabs_threshold"),
        CheckConstraint(
            "rate_percent > 0 AND rate_percent <= 100",
            name="CK_supplier_rebate_slabs_rate",
        ),
    )

    agreement_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("supplier_rebate_agreements.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
