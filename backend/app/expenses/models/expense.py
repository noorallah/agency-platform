"""Expense persistence model: money the firm spent that no document raised.

Rent, fuel, salaries, electricity -- the costs of running the firm that no
purchase bill or payout carries. Tally records them as a payment voucher and
Zoho Books as an *Expense*: pick what it was for, how much, and where the money
came from, and the journal is written for you. Before this module the only way
in was a journal typed by hand, which needs an accountant's authority to post.

An expense is recorded after the money has left, so there is nothing to
approve: it is posted when it is saved. A mistake is cancelled rather than
edited -- a mirror journal takes it back and both stay on the record, the way a
settlement is reversed.
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


class ExpenseStatus(StrEnum):
    """The lifecycle of an expense.

    Two states and no approval between them, for the reason a settlement has
    none: the money has already moved, so there is nothing left to decide.
    """

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class Expense(BaseEntity):
    """Store one amount the firm spent, and the journal that records it."""

    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("firm_id", "expense_number", name="UQ_expenses_firm_number"),
        CheckConstraint("amount > 0", name="CK_expenses_amount_positive"),
        Index("IX_expenses_firm_date", "firm_id", "expense_date"),
        Index("IX_expenses_firm_account", "firm_id", "expense_account_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    expense_number: Mapped[str] = mapped_column(String(60), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: What the money was spent on: an EXPENSE account no document posts to.
    expense_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Where the money came from: cash, a bank account, petty cash -- an ASSET
    #: account. Stored rather than re-derived, so changing the firm's chart
    #: later cannot rewrite what this expense says happened.
    paid_from_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: Who was paid -- the landlord, the fuel station. Free text: most payees
    #: of an expense are nobody the firm keeps a vendor record for.
    payee: Mapped[str | None] = mapped_column(String(200))
    #: The bill or receipt number, as printed on the paper.
    reference: Mapped[str | None] = mapped_column(String(120))
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExpenseStatus.POSTED.value
    )
    #: The journal this wrote. An expense that did not reach the ledger is the
    #: thing this module exists to make impossible, so the link is required.
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The mirror journal that cancelled it, and why. Set together with the
    #: status, so a cancelled expense always shows what undid it.
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
