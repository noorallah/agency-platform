"""Staff advance persistence model: money lent to an employee and taken back.

No payroll. An employee is a ledger account of his own in the *Staff Advances*
group, the way Tally keeps a ledger per person under *Loans and Advances
(Asset)*. An **advance** pays him out of cash or a bank account; a
**recovery** takes the account down again, either out of his salary (the
salary expense is then booked at the full salary, part of it paid by the
advance he already holds) or by money he hands back.

What he owes is never stored: it is the balance of his account, so an advance
paid by a cheque or a journal typed by hand counts exactly as one recorded
here.

Like an expense, an entry is posted when it is saved and a mistake is
cancelled with a mirror journal; nothing is edited or deleted.
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


class StaffAdvanceKind(StrEnum):
    """Which way an entry moves what the employee owes."""

    ADVANCE = "ADVANCE"
    RECOVERY = "RECOVERY"


class StaffAdvanceStatus(StrEnum):
    """The lifecycle of an entry: posted when saved, cancelled by a mirror."""

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class StaffAdvanceEntry(BaseEntity):
    """Store one advance to an employee or one recovery, and its journal."""

    __tablename__ = "staff_advance_entries"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "entry_number", name="UQ_staff_advance_entries_firm_number"
        ),
        CheckConstraint("amount > 0", name="CK_staff_advance_entries_amount_positive"),
        Index("IX_staff_advance_entries_firm_date", "firm_id", "entry_date"),
        Index(
            "IX_staff_advance_entries_firm_employee",
            "firm_id",
            "employee_account_id",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    entry_number: Mapped[str] = mapped_column(String(60), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The employee: his own account in the Staff Advances group.
    employee_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The other side. An advance: the cash or bank account it was paid from.
    #: A recovery: the expense account his salary is booked to, or the cash or
    #: bank account he paid it back into. Stored, so a later change to the
    #: chart cannot rewrite what this entry says happened.
    other_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=StaffAdvanceStatus.POSTED.value
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The mirror journal that cancelled it, and why; set with the status.
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
