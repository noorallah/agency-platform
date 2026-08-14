"""Firm-scoped finance persistence models for the general ledger.

The module covers the accounting calendar (financial years and periods), the
chart of accounts (groups, ledger accounts, cost and profit centres), the
double-entry journal (entries, lines, and their posting audit trail), and the
derived balance tables used by reporting.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class AccountType(StrEnum):
    """Classify a ledger account for reporting and balance direction."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"
    MEMO = "MEMO"
    CONTROL = "CONTROL"


#: Account types whose balance increases on the debit side.
DEBIT_BALANCE_ACCOUNT_TYPES = frozenset({AccountType.ASSET, AccountType.EXPENSE})

#: Account types the profit and loss is drawn from.
#:
#: The type rather than the `is_profit_loss` flag on the account: the type is
#: structural and already decides which side an account increases on, while the
#: flag is a column somebody has to set and every account in the seeded demo
#: firm carries it as `False`, Sales and Purchases included.
PROFIT_LOSS_ACCOUNT_TYPES = frozenset({AccountType.INCOME, AccountType.EXPENSE})


class PeriodStatus(StrEnum):
    """Describe whether an accounting period accepts new postings."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class JournalStatus(StrEnum):
    """Track the lifecycle of a journal entry."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    REJECTED = "REJECTED"


class PostingStatus(StrEnum):
    """Track the outcome of posting one journal line to the ledger."""

    PENDING = "PENDING"
    POSTED = "POSTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FinancialYear(BaseEntity):
    """Represent one fiscal year owned by a firm."""

    __tablename__ = "financial_years"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_financial_years_firm_code"),
        Index("IX_financial_years_firm_active", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    periods: Mapped[list["AccountingPeriod"]] = relationship(
        back_populates="financial_year", cascade="save-update, merge"
    )


class AccountingPeriod(BaseEntity):
    """Represent one posting period inside a financial year."""

    __tablename__ = "accounting_periods"
    __table_args__ = (
        UniqueConstraint(
            "financial_year_id",
            "period_number",
            name="UQ_accounting_periods_year_number",
        ),
        # Scoped to the year, like the number above. It was scoped to the firm,
        # which contradicted it: a period's code identifies it *within* its
        # year, and the seeder writes P01..P12 for every year, so a firm could
        # never hold a second financial year at all -- no year-end, no
        # comparatives, no prior-year reporting.
        UniqueConstraint(
            "financial_year_id", "code", name="UQ_accounting_periods_year_code"
        ),
        Index("IX_accounting_periods_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    financial_year_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("financial_years.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PeriodStatus.OPEN.value
    )
    description: Mapped[str | None] = mapped_column(Text)

    financial_year: Mapped[FinancialYear] = relationship(back_populates="periods")


class AccountGroup(BaseEntity):
    """Group ledger accounts for classification and report rollups."""

    __tablename__ = "account_groups"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_account_groups_firm_code"),
        Index("IX_account_groups_firm_type", "firm_id", "account_type"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_group_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("account_groups.id", ondelete="RESTRICT")
    )
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    accounts: Mapped[list["LedgerAccount"]] = relationship(
        back_populates="account_group"
    )


class LedgerAccount(BaseEntity):
    """Represent one general-ledger account in the chart of accounts."""

    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_ledger_accounts_firm_code"),
        Index("IX_ledger_accounts_firm_type", "firm_id", "account_type"),
        Index("IX_ledger_accounts_firm_active", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    account_group_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("account_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_balance_sheet: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_profit_loss: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    requires_cost_center: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    requires_profit_center: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    account_group: Mapped[AccountGroup] = relationship(back_populates="accounts")
    balances: Mapped[list["LedgerBalance"]] = relationship(
        back_populates="ledger_account"
    )
    journal_lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="ledger_account"
    )


class CostCenter(BaseEntity):
    """Represent a cost centre used to attribute expenditure."""

    __tablename__ = "cost_centers"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_cost_centers_firm_code"),
        Index("IX_cost_centers_firm_active", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ProfitCenter(BaseEntity):
    """Represent a profit centre used to attribute revenue."""

    __tablename__ = "profit_centers"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_profit_centers_firm_code"),
        Index("IX_profit_centers_firm_active", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class JournalType(BaseEntity):
    """Classify journals such as sales, purchase, or general."""

    __tablename__ = "journal_types"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_journal_types_firm_code"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class VoucherType(BaseEntity):
    """Classify vouchers such as invoice, receipt, or payment."""

    __tablename__ = "voucher_types"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_voucher_types_firm_code"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class JournalEntry(BaseEntity):
    """Represent one balanced double-entry journal voucher."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "reference_number", name="UQ_journal_entries_firm_reference"
        ),
        Index("IX_journal_entries_firm_status", "firm_id", "status"),
        Index("IX_journal_entries_firm_period", "firm_id", "accounting_period_id"),
        Index("IX_journal_entries_source", "source_module", "source_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    journal_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    voucher_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("voucher_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accounting_period_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("accounting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    journal_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_number: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JournalStatus.DRAFT.value
    )
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    total_debit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_credit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    is_balanced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    source_module: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[UUID | None] = mapped_column(UUIDType())
    reversal_of_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="JournalLine.line_number",
    )


class JournalLine(BaseEntity):
    """Represent one debit or credit leg of a journal entry."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        UniqueConstraint(
            "journal_entry_id", "line_number", name="UQ_journal_lines_entry_line"
        ),
        Index("IX_journal_lines_account", "ledger_account_id"),
    )

    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cost_center_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("cost_centers.id", ondelete="RESTRICT")
    )
    profit_center_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("profit_centers.id", ondelete="RESTRICT")
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    description: Mapped[str | None] = mapped_column(Text)

    journal_entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    ledger_account: Mapped[LedgerAccount] = relationship(back_populates="journal_lines")


class LedgerBalance(BaseEntity):
    """Hold the derived balance of one ledger account for one period."""

    __tablename__ = "ledger_balances"
    __table_args__ = (
        UniqueConstraint(
            "ledger_account_id",
            "accounting_period_id",
            name="UQ_ledger_balances_account_period",
        ),
        Index("IX_ledger_balances_firm_period", "firm_id", "accounting_period_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accounting_period_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("accounting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    period_debit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    period_credit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )

    ledger_account: Mapped[LedgerAccount] = relationship(back_populates="balances")


class GLPosting(BaseEntity):
    """Record one journal line as it was posted to the general ledger."""

    __tablename__ = "gl_postings"
    __table_args__ = (
        Index("IX_gl_postings_firm_period", "firm_id", "accounting_period_id"),
        Index("IX_gl_postings_account", "ledger_account_id", "accounting_period_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    journal_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accounting_period_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("accounting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    posting_date: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PostingStatus.POSTED.value
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    posted_by: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)


class CustomerLedger(BaseEntity):
    """Hold derived receivable totals for one customer and period."""

    __tablename__ = "customer_ledgers"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "customer_id",
            "accounting_period_id",
            name="UQ_customer_ledgers_firm_customer_period",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    accounting_period_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("accounting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    days_overdue: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class VendorLedger(BaseEntity):
    """Hold derived payable totals for one vendor and period."""

    __tablename__ = "vendor_ledgers"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "vendor_id",
            "accounting_period_id",
            name="UQ_vendor_ledgers_firm_vendor_period",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    accounting_period_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("accounting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    days_overdue: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class FirmControlAccount(BaseEntity):
    """Map a document-posting purpose onto the account a firm posts it to.

    Which account a firm's receivables or cost of goods sold lands in is that
    firm's decision, and it differs between firms sharing a chart of accounts.
    Keeping it in data lets the posting rules stay in code; the previous attempt
    guessed accounts by matching on their name and was removed.
    """

    __tablename__ = "firm_control_accounts"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "purpose", name="UQ_firm_control_accounts_firm_purpose"
        ),
        Index("IX_firm_control_accounts_firm", "firm_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
