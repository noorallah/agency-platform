"""Contra voucher persistence model (backlog 74 row 3).

Money moved between the firm's own cash and bank accounts: cash paid into the
bank, cash drawn out of it, one bank account to another, one cash box to
another. Nobody outside the firm is a party to it, so it touches no receivable,
no payable and no tax -- Dr the account the money went to, Cr the one it left.

It posts on save, as a receipt or an expense does: the money has already
moved by the time anybody records it, so there is nothing to approve. A
mistake is cancelled with a reason and a mirror journal, never edited.
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


class ContraKind(StrEnum):
    """Which way the money went. Derived from the two accounts, never typed."""

    #: Cash paid into a bank account.
    DEPOSIT = "DEPOSIT"
    #: Cash drawn out of a bank account.
    WITHDRAWAL = "WITHDRAWAL"
    #: One bank account to another.
    BANK_TRANSFER = "BANK_TRANSFER"
    #: One cash account to another -- the counter to petty cash.
    CASH_TRANSFER = "CASH_TRANSFER"


class ContraStatus(StrEnum):
    """Posted on save; cancelled by a mirror journal."""

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class ContraVoucher(BaseEntity):
    """One movement of money between two of the firm's own accounts."""

    __tablename__ = "contra_vouchers"
    __table_args__ = (
        UniqueConstraint("firm_id", "voucher_number", name="UQ_contra_vouchers_number"),
        CheckConstraint("amount > 0", name="CK_contra_vouchers_amount_positive"),
        CheckConstraint(
            "from_account_id <> to_account_id",
            name="CK_contra_vouchers_distinct_accounts",
        ),
        Index("IX_contra_vouchers_firm_date", "firm_id", "voucher_date"),
        Index("IX_contra_vouchers_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    voucher_number: Mapped[str] = mapped_column(String(60), nullable=False)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Derived from the two accounts at save and kept, so the register reads
    #: what the voucher was even after an account is renamed or regrouped.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Credited: where the money left.
    from_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Debited: where the money arrived.
    to_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The deposit slip, cheque or transfer reference.
    reference: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ContraStatus.POSTED.value,
        server_default=ContraStatus.POSTED.value,
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The mirror that cancelled it.
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
    cancel_reason: Mapped[str | None] = mapped_column(Text())
