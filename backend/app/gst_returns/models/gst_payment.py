"""One month's GST settled: credit set off, cash paid, credit carried (63).

A month's GST is settled in two movements the GST portal records separately
-- input credit set off against output tax, by the statutory order, and the
cash paid by challan (PMT-06) for the rest -- and the firm's books record both
in one journal: output tax cleared, input tax used, the bank paid. What is
left of the credit carries to the next month, which is why each row keeps it:
the next month's brought-forward credit is this row's carried-forward.

The heads are stored as columns, never as JSON: the set-off is a statutory
calculation an auditor reads line by line, and a report filters on it.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType

HEADS: tuple[str, ...] = ("igst", "cgst", "sgst", "cess")


class GstPaymentStatus(StrEnum):
    """Whether a month's settlement stands."""

    POSTED = "POSTED"
    REVERSED = "REVERSED"


def _money() -> Mapped[Decimal]:
    return mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )


class GstPayment(BaseEntity):
    """A month's GST liability, the credit set off, the cash paid by challan."""

    __tablename__ = "gst_payments"
    __table_args__ = (
        # One standing settlement per month: a second would set the same
        # credit off twice.
        Index(
            "UQ_gst_payments_firm_period_posted",
            "firm_id",
            "return_period",
            unique=True,
            postgresql_where=text("status = 'POSTED' AND is_deleted = false"),
            sqlite_where=text("status = 'POSTED' AND is_deleted = 0"),
        ),
        Index("IX_gst_payments_firm_period", "firm_id", "return_period"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The return month, ``YYYY-MM``; for a quarterly filer the quarter's
    #: last month, and the row settles the whole quarter (GST-7).
    return_period: Mapped[str] = mapped_column(String(7), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: The bank or cash account the challan was paid from.
    money_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The challan's portal reference and the bank's, as PMT-06 states them.
    challan_cpin: Mapped[str | None] = mapped_column(String(20))
    challan_cin: Mapped[str | None] = mapped_column(String(30))

    # What the month owed (GSTR-3B 3.1(a), after credit notes).
    liability_igst: Mapped[Decimal] = _money()
    liability_cgst: Mapped[Decimal] = _money()
    liability_sgst: Mapped[Decimal] = _money()
    liability_cess: Mapped[Decimal] = _money()
    # Credit available: brought forward plus the month's net input credit.
    credit_igst: Mapped[Decimal] = _money()
    credit_cgst: Mapped[Decimal] = _money()
    credit_sgst: Mapped[Decimal] = _money()
    credit_cess: Mapped[Decimal] = _money()
    # Credit used, by the head it came from.
    used_igst: Mapped[Decimal] = _money()
    used_cgst: Mapped[Decimal] = _money()
    used_sgst: Mapped[Decimal] = _money()
    used_cess: Mapped[Decimal] = _money()
    # Cash paid, by the head it paid.
    cash_igst: Mapped[Decimal] = _money()
    cash_cgst: Mapped[Decimal] = _money()
    cash_sgst: Mapped[Decimal] = _money()
    cash_cess: Mapped[Decimal] = _money()
    # Reverse charge on inward supplies (GSTR-3B 3.1(d), backlog 68 row 8):
    # paid in cash only, section 49(4) -- no credit is ever set against it,
    # so it is kept apart from the liability the set-off works on.
    reverse_charge_igst: Mapped[Decimal] = _money()
    reverse_charge_cgst: Mapped[Decimal] = _money()
    reverse_charge_sgst: Mapped[Decimal] = _money()
    reverse_charge_cess: Mapped[Decimal] = _money()
    # Of the cash, what the PMT-06 deposits of a quarter's first two months
    # paid (GST-7): taken off the electronic cash ledger, not the bank.
    cash_ledger_igst: Mapped[Decimal] = _money()
    cash_ledger_cgst: Mapped[Decimal] = _money()
    cash_ledger_sgst: Mapped[Decimal] = _money()
    cash_ledger_cess: Mapped[Decimal] = _money()
    # Credit left, carried to the next month.
    carried_igst: Mapped[Decimal] = _money()
    carried_cgst: Mapped[Decimal] = _money()
    carried_sgst: Mapped[Decimal] = _money()
    carried_cess: Mapped[Decimal] = _money()

    #: Interest for paying late (section 50) and the late fee for filing
    #: late, each to an expense account of the firm's choosing -- never into
    #: the tax accounts, which must clear to nothing.
    interest_amount: Mapped[Decimal] = _money()
    interest_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    late_fee_amount: Mapped[Decimal] = _money()
    late_fee_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    narration: Mapped[str | None] = mapped_column(Text())

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=GstPaymentStatus.POSTED.value
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
