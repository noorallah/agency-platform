"""Common input credit given back for exempt supplies, rule 42 (GST-4, A84).

A firm that makes exempt supplies beside taxable ones may keep only the share
of its common input credit that its taxable turnover bears (CGST rule 42):
each return period it reverses ``D1 = C2 x E / F`` -- common credit times
exempt turnover over total turnover -- and once the year is over it works the
same out on the whole year's figures and puts the difference right, reversing
more or claiming some back (rule 42(2)).

Each row is one such reversal, for a return period (MONTHLY: a month, or a
quarterly filer's quarter) or for a financial year (ANNUAL: the true-up,
signed -- a negative head is credit claimed back). The figures it was worked
from are kept with it, so an auditor reads the arithmetic, not only the
result. Reversing the row takes its journal off; nothing is edited.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class CommonCreditKind(StrEnum):
    """Which reversal a row is."""

    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"


class CommonCreditStatus(StrEnum):
    """Whether a reversal stands."""

    POSTED = "POSTED"
    REVERSED = "REVERSED"


def _money() -> Mapped[Decimal]:
    return mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )


class ItcCommonReversal(BaseEntity):
    """One rule 42 reversal: a period's, or a year's true-up."""

    __tablename__ = "itc_common_reversals"
    __table_args__ = (
        # One standing reversal per period: a second would give the same
        # credit back twice.
        Index(
            "UQ_itc_common_reversals_firm_kind_period_posted",
            "firm_id",
            "kind",
            "period_from",
            unique=True,
            postgresql_where=text("status = 'POSTED' AND is_deleted = false"),
            sqlite_where=text("status = 'POSTED' AND is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: MONTHLY or ANNUAL.
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    #: The day it is reported and posted: within the GSTR-3B it goes in.
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: E: nil-rated, exempt and non-GST turnover of the period.
    exempt_turnover: Mapped[Decimal] = _money()
    #: F: all turnover -- taxable, zero-rated and E.
    total_turnover: Mapped[Decimal] = _money()
    # C2: the common credit, per head.
    common_igst: Mapped[Decimal] = _money()
    common_cgst: Mapped[Decimal] = _money()
    common_sgst: Mapped[Decimal] = _money()
    common_cess: Mapped[Decimal] = _money()
    # What was given back, per head; negative on a true-up is a reclaim.
    reversed_igst: Mapped[Decimal] = _money()
    reversed_cgst: Mapped[Decimal] = _money()
    reversed_sgst: Mapped[Decimal] = _money()
    reversed_cess: Mapped[Decimal] = _money()

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CommonCreditStatus.POSTED.value
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reversed_by: Mapped[UUID | None] = mapped_column(UUIDType())
    reversal_reason: Mapped[str | None] = mapped_column(Text())


__all__ = ["CommonCreditKind", "CommonCreditStatus", "ItcCommonReversal"]
