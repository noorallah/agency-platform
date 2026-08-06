"""Finance module - Chart of Accounts, Ledger, and Journal entry engine."""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Boolean, Enum, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.database import Base
from app.core.utils.dates import utc_now


class AccountType(str, enum.Enum):
    """Account classification for GL reporting."""
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"
    MEMO = "MEMO"
    CONTROL = "CONTROL"


class PeriodStatus(str, enum.Enum):
    """Status of accounting periods."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class JournalStatus(str, enum.Enum):
    """Status of journal entries."""
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    REJECTED = "REJECTED"


class PostingStatus(str, enum.Enum):
    """Posting status for GL entries."""
    PENDING = "PENDING"
    POSTED = "POSTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FinancialYear(Base):
    """Fiscal year definition for the firm."""
    __tablename__ = "financial_years"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    year_code = Column(String(4), nullable=False)
    financial_year_start = Column(DateTime, nullable=False)
    financial_year_end = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    periods = relationship("AccountingPeriod", back_populates="financial_year", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("firm_id", "year_code", name="uq_financial_year_code"),
        Index("ix_financial_years_firm_active", "firm_id", "is_active"),
    )


class AccountingPeriod(Base):
    """Monthly/periodic division of financial year."""
    __tablename__ = "accounting_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    financial_year_id = Column(UUID(as_uuid=True), ForeignKey("financial_years.id"), nullable=False)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    period_number = Column(Integer, nullable=False)
    period_name = Column(String(50), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    status = Column(String(20), default=PeriodStatus.OPEN.value)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    financial_year = relationship("FinancialYear", back_populates="periods")

    __table_args__ = (
        UniqueConstraint("financial_year_id", "period_number", name="uq_period_number_per_year"),
        Index("ix_accounting_periods_firm_status", "firm_id", "status"),
    )


class AccountGroup(Base):
    """Account grouping for reporting and classification."""
    __tablename__ = "account_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    group_code = Column(String(20), nullable=False)
    group_name = Column(String(100), nullable=False)
    account_type = Column(String(20), nullable=False)
    parent_group_id = Column(UUID(as_uuid=True), ForeignKey("account_groups.id"), nullable=True)
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    accounts = relationship("LedgerAccount", back_populates="account_group")

    __table_args__ = (
        UniqueConstraint("firm_id", "group_code", name="uq_account_group_code"),
        Index("ix_account_groups_firm_type", "firm_id", "account_type"),
    )


class LedgerAccount(Base):
    """General Ledger account."""
    __tablename__ = "ledger_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account_group_id = Column(UUID(as_uuid=True), ForeignKey("account_groups.id"), nullable=False)
    account_code = Column(String(20), nullable=False)
    account_name = Column(String(100), nullable=False)
    account_type = Column(String(20), nullable=False)
    description = Column(String(500))
    is_balance_sheet = Column(Boolean, default=True)
    is_profit_loss = Column(Boolean, default=True)
    enable_cost_center = Column(Boolean, default=False)
    enable_profit_center = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    account_group = relationship("AccountGroup", back_populates="accounts")
    balances = relationship("LedgerBalance", back_populates="ledger_account", cascade="all, delete-orphan")
    journal_lines = relationship("JournalLine", back_populates="ledger_account")

    __table_args__ = (
        UniqueConstraint("firm_id", "account_code", name="uq_ledger_account_code"),
        Index("ix_ledger_accounts_firm_type", "firm_id", "account_type"),
        Index("ix_ledger_accounts_firm_active", "firm_id", "is_active"),
    )


class CostCenter(Base):
    """Cost center for cost allocation."""
    __tablename__ = "cost_centers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    cost_center_code = Column(String(20), nullable=False)
    cost_center_name = Column(String(100), nullable=False)
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("firm_id", "cost_center_code", name="uq_cost_center_code"),
        Index("ix_cost_centers_firm_active", "firm_id", "is_active"),
    )


class ProfitCenter(Base):
    """Profit center for profit allocation."""
    __tablename__ = "profit_centers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    profit_center_code = Column(String(20), nullable=False)
    profit_center_name = Column(String(100), nullable=False)
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("firm_id", "profit_center_code", name="uq_profit_center_code"),
        Index("ix_profit_centers_firm_active", "firm_id", "is_active"),
    )


class JournalType(Base):
    """Type of journal (Sales, Purchase, General, etc.)."""
    __tablename__ = "journal_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    journal_type_code = Column(String(20), nullable=False)
    journal_type_name = Column(String(50), nullable=False)
    description = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("firm_id", "journal_type_code", name="uq_journal_type_code"),
    )


class VoucherType(Base):
    """Type of voucher (Invoice, Receipt, Payment, etc.)."""
    __tablename__ = "voucher_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    voucher_type_code = Column(String(20), nullable=False)
    voucher_type_name = Column(String(50), nullable=False)
    description = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("firm_id", "voucher_type_code", name="uq_voucher_type_code"),
    )


class JournalEntry(Base):
    """Journal entry with multiple debit/credit lines."""
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    journal_type_id = Column(UUID(as_uuid=True), ForeignKey("journal_types.id"), nullable=False)
    voucher_type_id = Column(UUID(as_uuid=True), ForeignKey("voucher_types.id"), nullable=False)
    accounting_period_id = Column(UUID(as_uuid=True), ForeignKey("accounting_periods.id"), nullable=False)
    journal_date = Column(DateTime, nullable=False)
    reference_number = Column(String(50), nullable=False)
    description = Column(String(500))
    status = Column(String(20), default=JournalStatus.DRAFT.value)
    posted_at = Column(DateTime, nullable=True)
    total_debit = Column(Numeric(18, 2), default=0)
    total_credit = Column(Numeric(18, 2), default=0)
    is_balanced = Column(Boolean, default=False)
    source_module = Column(String(50), nullable=True)
    source_id = Column(UUID(as_uuid=True), nullable=True)
    reversal_of_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    lines = relationship("JournalLine", back_populates="journal_entry", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("firm_id", "reference_number", name="uq_journal_reference"),
        Index("ix_journal_entries_firm_status", "firm_id", "status"),
        Index("ix_journal_entries_firm_period", "firm_id", "accounting_period_id"),
        Index("ix_journal_entries_source", "source_module", "source_id"),
    )


class JournalLine(Base):
    """Individual debit or credit line in a journal entry."""
    __tablename__ = "journal_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"), nullable=False)
    ledger_account_id = Column(UUID(as_uuid=True), ForeignKey("ledger_accounts.id"), nullable=False)
    cost_center_id = Column(UUID(as_uuid=True), ForeignKey("cost_centers.id"), nullable=True)
    profit_center_id = Column(UUID(as_uuid=True), ForeignKey("profit_centers.id"), nullable=True)
    line_number = Column(Integer, nullable=False)
    debit_amount = Column(Numeric(18, 2), default=0)
    credit_amount = Column(Numeric(18, 2), default=0)
    description = Column(String(200))
    created_at = Column(DateTime, default=utc_now, nullable=False)

    journal_entry = relationship("JournalEntry", back_populates="lines")
    ledger_account = relationship("LedgerAccount", back_populates="journal_lines")

    __table_args__ = (
        Index("ix_journal_lines_account", "ledger_account_id"),
    )


class LedgerBalance(Base):
    """Running balance for each ledger account per period."""
    __tablename__ = "ledger_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ledger_account_id = Column(UUID(as_uuid=True), ForeignKey("ledger_accounts.id"), nullable=False)
    accounting_period_id = Column(UUID(as_uuid=True), ForeignKey("accounting_periods.id"), nullable=False)
    opening_balance = Column(Numeric(18, 2), default=0)
    period_debit = Column(Numeric(18, 2), default=0)
    period_credit = Column(Numeric(18, 2), default=0)
    closing_balance = Column(Numeric(18, 2), default=0)
    last_updated = Column(DateTime, default=utc_now, onupdate=utc_now)

    ledger_account = relationship("LedgerAccount", back_populates="balances")

    __table_args__ = (
        UniqueConstraint("ledger_account_id", "accounting_period_id", name="uq_balance_per_period"),
        Index("ix_ledger_balances_firm_period", "firm_id", "accounting_period_id"),
    )


class GLPosting(Base):
    """Record of posting from journal to ledger (audit trail)."""
    __tablename__ = "gl_postings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"), nullable=False)
    journal_line_id = Column(UUID(as_uuid=True), ForeignKey("journal_lines.id"), nullable=False)
    ledger_account_id = Column(UUID(as_uuid=True), ForeignKey("ledger_accounts.id"), nullable=False)
    accounting_period_id = Column(UUID(as_uuid=True), ForeignKey("accounting_periods.id"), nullable=False)
    posting_date = Column(DateTime, default=utc_now)
    debit_amount = Column(Numeric(18, 2), default=0)
    credit_amount = Column(Numeric(18, 2), default=0)
    status = Column(String(20), default=PostingStatus.POSTED.value)
    error_message = Column(String(500), nullable=True)
    posted_by = Column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        Index("ix_gl_postings_firm_period", "firm_id", "accounting_period_id"),
        Index("ix_gl_postings_account", "ledger_account_id", "accounting_period_id"),
    )


class CustomerLedger(Base):
    """AR ledger - customer invoice and payment tracking."""
    __tablename__ = "customer_ledgers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    accounting_period_id = Column(UUID(as_uuid=True), ForeignKey("accounting_periods.id"), nullable=False)
    invoice_amount = Column(Numeric(18, 2), default=0)
    payment_amount = Column(Numeric(18, 2), default=0)
    outstanding_amount = Column(Numeric(18, 2), default=0)
    days_overdue = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("firm_id", "customer_id", "accounting_period_id", name="uq_customer_ledger_period"),
        Index("ix_customer_ledgers_firm", "firm_id"),
    )


class VendorLedger(Base):
    """AP ledger - vendor invoice and payment tracking."""
    __tablename__ = "vendor_ledgers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    accounting_period_id = Column(UUID(as_uuid=True), ForeignKey("accounting_periods.id"), nullable=False)
    invoice_amount = Column(Numeric(18, 2), default=0)
    payment_amount = Column(Numeric(18, 2), default=0)
    outstanding_amount = Column(Numeric(18, 2), default=0)
    days_overdue = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("firm_id", "vendor_id", "accounting_period_id", name="uq_vendor_ledger_period"),
        Index("ix_vendor_ledgers_firm", "firm_id"),
    )
