"""A bank's statement, and which of its lines the books account for (ACC-1).

Decision A125. A statement is imported against one bank ledger account; each
line is a deposit or a withdrawal on a date. Reconciling ties a line to the
**postings on that bank account** -- the journal lines a receipt, a payment,
a contra voucher, an expense or a hand journal wrote there -- rather than to
any one kind of document, so every way money reaches the books is matched
the same way, as Tally does on its bank ledger. A line may account for
several postings (one deposit slip of three cheques); a posting is matched at
most once. The date the bank cleared a posting is the date of the line that
matched it: a cleared date is never typed, so it cannot disagree with the
statement.
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
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class StatementLineStatus(StrEnum):
    """Whether the books account for a statement line yet."""

    UNMATCHED = "UNMATCHED"
    MATCHED = "MATCHED"


class BankStatement(BaseEntity):
    """One statement file imported against one bank account."""

    __tablename__ = "bank_statements"
    __table_args__ = (
        Index("IX_bank_statements_firm_account", "firm_id", "ledger_account_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    #: What the person called it, or the file's name.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BankStatementLine(BaseEntity):
    """One line of a statement: money in or out of the account on a day."""

    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        Index("IX_bank_statement_lines_statement", "statement_id"),
        Index(
            "IX_bank_statement_lines_account_date",
            "firm_id",
            "ledger_account_id",
            "line_date",
        ),
        CheckConstraint(
            "(withdrawal > 0 AND deposit = 0) OR (deposit > 0 AND withdrawal = 0)",
            name="CK_bank_statement_lines_one_side",
        ),
    )

    statement_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("bank_statements.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    ledger_account_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    line_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Cheque number, UTR or the bank's own reference.
    reference: Mapped[str | None] = mapped_column(String(120))
    withdrawal: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    deposit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The running balance the bank printed, where it printed one.
    balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=StatementLineStatus.UNMATCHED.value,
        server_default=StatementLineStatus.UNMATCHED.value,
    )


class BankReconciliationMatch(BaseEntity):
    """One posting on the bank account, accounted for by one statement line."""

    __tablename__ = "bank_reconciliation_matches"
    __table_args__ = (
        # A posting clears once.
        Index(
            "UQ_bank_reconciliation_matches_posting_active",
            "gl_posting_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_bank_reconciliation_matches_line", "statement_line_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    statement_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("bank_statement_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    gl_posting_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("gl_postings.id", ondelete="RESTRICT"), nullable=False
    )
    #: The day the bank cleared it: the statement line's date.
    cleared_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: ``AUTO`` when the matcher chose it, ``MANUAL`` when a person did.
    matched_how: Mapped[str] = mapped_column(String(10), nullable=False)
