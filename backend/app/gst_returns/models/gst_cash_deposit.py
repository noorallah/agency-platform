"""Tax deposited on PMT-06 in a quarter's first two months (GST-7, A83).

A quarterly filer (QRMP) files GSTR-3B once a quarter but pays every month:
by the 25th of months 2 and 3 it deposits month 1's and month 2's tax on a
PMT-06 challan, either 35% of the cash it paid for the last quarter (the
fixed sum method) or the month's own tax less its credit (self-assessment).
The money sits in the electronic cash ledger, head by head, until the
quarter's 3B uses it; nothing is set off at deposit.

So a deposit posts only Dr *GST Electronic Cash Ledger* / Cr the bank, and
the quarter's settlement (``gst_payments.cash_ledger_*``) credits that ledger
back for what it uses. What is left is the balance, derived on every read --
never a column.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class GstCashDepositStatus(StrEnum):
    """Whether a deposit stands."""

    POSTED = "POSTED"
    REVERSED = "REVERSED"


def _money() -> Mapped[Decimal]:
    return mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )


class GstCashDeposit(BaseEntity):
    """One PMT-06 challan paid for month 1 or 2 of a quarter."""

    __tablename__ = "gst_cash_deposits"
    __table_args__ = (
        Index("IX_gst_cash_deposits_firm_period", "firm_id", "return_period"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The month the deposit is for, ``YYYY-MM``: month 1 or 2 of a quarter.
    return_period: Mapped[str] = mapped_column(String(7), nullable=False)
    deposit_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: FIXED_SUM or SELF_ASSESSMENT: how the amount was worked out.
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The bank or cash account the challan was paid from.
    money_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    challan_cpin: Mapped[str | None] = mapped_column(String(20))
    challan_cin: Mapped[str | None] = mapped_column(String(30))
    # Deposited per head: the cash ledger keeps each head apart, and a
    # quarter's IGST cannot be paid from a CGST deposit.
    amount_igst: Mapped[Decimal] = _money()
    amount_cgst: Mapped[Decimal] = _money()
    amount_sgst: Mapped[Decimal] = _money()
    amount_cess: Mapped[Decimal] = _money()
    narration: Mapped[str | None] = mapped_column(Text())

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=GstCashDepositStatus.POSTED.value
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


__all__ = ["GstCashDeposit", "GstCashDepositStatus"]
