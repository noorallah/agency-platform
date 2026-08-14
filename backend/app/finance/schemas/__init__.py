"""Validated request and response contracts for the finance module."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MONEY = Decimal("0.01")


class AccountTypeEnum(StrEnum):
    """Supported ledger account classifications."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"
    MEMO = "MEMO"
    CONTROL = "CONTROL"


class PeriodStatusEnum(StrEnum):
    """Supported accounting period statuses."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class JournalStatusEnum(StrEnum):
    """Supported journal entry statuses."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    REJECTED = "REJECTED"


class PostingStatusEnum(StrEnum):
    """Supported general-ledger posting statuses."""

    PENDING = "PENDING"
    POSTED = "POSTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FinanceSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


CodeField = Field(max_length=20, min_length=1, pattern=r"^[A-Z0-9_-]+$")
NameField = Field(max_length=100, min_length=1)


class FinancialYearCreate(FinanceSchema):
    """Create one financial year."""

    code: str = CodeField
    name: str = NameField
    starts_on: date
    ends_on: date
    description: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Reject a year whose end does not follow its start."""
        if self.ends_on <= self.starts_on:
            raise ValueError("Financial year must end after it starts.")
        return self


class FinancialYearUpdate(FinanceSchema):
    """Apply a partial financial year update."""

    name: str | None = Field(default=None, max_length=100, min_length=1)
    starts_on: date | None = None
    ends_on: date | None = None
    description: str | None = None
    is_active: bool | None = None
    is_locked: bool | None = None


class FinancialYearResponse(FinanceSchema):
    """Return one financial year."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    description: str | None
    is_active: bool
    is_locked: bool
    version: int


class AccountingPeriodCreate(FinanceSchema):
    """Create one accounting period inside a financial year."""

    financial_year_id: UUID
    period_number: int = Field(ge=1, le=24)
    code: str = CodeField
    name: str = NameField
    starts_on: date
    ends_on: date
    description: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Reject a period whose end does not follow its start."""
        if self.ends_on <= self.starts_on:
            raise ValueError("Accounting period must end after it starts.")
        return self


class AccountingPeriodUpdate(FinanceSchema):
    """Apply a partial accounting period update."""

    name: str | None = Field(default=None, max_length=100, min_length=1)
    starts_on: date | None = None
    ends_on: date | None = None
    status: PeriodStatusEnum | None = None
    description: str | None = None


class AccountingPeriodResponse(FinanceSchema):
    """Return one accounting period."""

    id: UUID
    firm_id: UUID
    financial_year_id: UUID
    period_number: int
    code: str
    name: str
    starts_on: date
    ends_on: date
    status: PeriodStatusEnum
    description: str | None
    version: int


class AccountGroupCreate(FinanceSchema):
    """Create one account group."""

    code: str = CodeField
    name: str = NameField
    account_type: AccountTypeEnum
    parent_group_id: UUID | None = None
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class AccountGroupUpdate(FinanceSchema):
    """Apply a partial account group update."""

    name: str | None = Field(default=None, max_length=100, min_length=1)
    parent_group_id: UUID | None = None
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AccountGroupResponse(FinanceSchema):
    """Return one account group."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    account_type: AccountTypeEnum
    parent_group_id: UUID | None
    description: str | None
    sort_order: int
    is_active: bool
    version: int


class LedgerAccountCreate(FinanceSchema):
    """Create one ledger account."""

    account_group_id: UUID
    code: str = CodeField
    name: str = NameField
    account_type: AccountTypeEnum
    description: str | None = None
    #: Which statement the account belongs on. Omit both and they follow the
    #: account type, which is what they describe: income and expenses make the
    #: profit and loss, everything else sits on the balance sheet. They were
    #: plain defaults of `True` / `False`, so every account created without
    #: them -- the whole seeded chart, Sales and Purchases included -- claimed
    #: to be a balance sheet account and no part of the profit and loss.
    is_balance_sheet: bool | None = None
    is_profit_loss: bool | None = None
    requires_cost_center: bool = False
    requires_profit_center: bool = False
    is_active: bool = True


class LedgerAccountUpdate(FinanceSchema):
    """Apply a partial ledger account update."""

    name: str | None = Field(default=None, max_length=100, min_length=1)
    account_group_id: UUID | None = None
    description: str | None = None
    is_balance_sheet: bool | None = None
    is_profit_loss: bool | None = None
    requires_cost_center: bool | None = None
    requires_profit_center: bool | None = None
    is_active: bool | None = None


class LedgerAccountResponse(FinanceSchema):
    """Return one ledger account."""

    id: UUID
    firm_id: UUID
    account_group_id: UUID
    code: str
    name: str
    account_type: AccountTypeEnum
    description: str | None
    is_balance_sheet: bool
    is_profit_loss: bool
    requires_cost_center: bool
    requires_profit_center: bool
    is_active: bool
    version: int


class CostCenterCreate(FinanceSchema):
    """Create one cost centre."""

    code: str = CodeField
    name: str = NameField
    description: str | None = None
    is_active: bool = True


class CostCenterUpdate(FinanceSchema):
    """Apply a partial cost centre update."""

    name: str | None = Field(default=None, max_length=100, min_length=1)
    description: str | None = None
    is_active: bool | None = None


class CostCenterResponse(FinanceSchema):
    """Return one cost centre."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    version: int


class ProfitCenterCreate(FinanceSchema):
    """Create one profit centre."""

    code: str = CodeField
    name: str = NameField
    description: str | None = None
    is_active: bool = True


class ProfitCenterUpdate(FinanceSchema):
    """Apply a partial profit centre update."""

    name: str | None = Field(default=None, max_length=100, min_length=1)
    description: str | None = None
    is_active: bool | None = None


class ProfitCenterResponse(FinanceSchema):
    """Return one profit centre."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    version: int


class JournalTypeCreate(FinanceSchema):
    """Create one journal type."""

    code: str = CodeField
    name: str = NameField
    description: str | None = None
    is_active: bool = True


class JournalTypeResponse(FinanceSchema):
    """Return one journal type."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    version: int


class VoucherTypeCreate(FinanceSchema):
    """Create one voucher type."""

    code: str = CodeField
    name: str = NameField
    description: str | None = None
    is_active: bool = True


class VoucherTypeResponse(FinanceSchema):
    """Return one voucher type."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    version: int


class JournalLineInput(FinanceSchema):
    """Submit one debit or credit leg of a journal entry."""

    ledger_account_id: UUID
    debit_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18)
    credit_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18)
    cost_center_id: UUID | None = None
    profit_center_id: UUID | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_single_side(self) -> Self:
        """Require exactly one populated side on every line."""
        debit = self.debit_amount.quantize(MONEY)
        credit = self.credit_amount.quantize(MONEY)
        if debit > 0 and credit > 0:
            raise ValueError("A journal line cannot be both a debit and a credit.")
        if debit == 0 and credit == 0:
            raise ValueError("A journal line must carry a debit or a credit amount.")
        return self


class JournalLineResponse(FinanceSchema):
    """Return one journal line."""

    id: UUID
    journal_entry_id: UUID
    ledger_account_id: UUID
    cost_center_id: UUID | None
    profit_center_id: UUID | None
    line_number: int
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None


class JournalEntryCreate(FinanceSchema):
    """Create one balanced journal entry."""

    journal_type_id: UUID
    voucher_type_id: UUID
    accounting_period_id: UUID
    journal_date: date
    reference_number: str = Field(max_length=50, min_length=1)
    description: str | None = None
    remarks: str | None = None
    lines: list[JournalLineInput] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_balanced(self) -> Self:
        """Require total debits to equal total credits."""
        debit = sum((line.debit_amount for line in self.lines), Decimal("0"))
        credit = sum((line.credit_amount for line in self.lines), Decimal("0"))
        if debit.quantize(MONEY) != credit.quantize(MONEY):
            raise ValueError(
                f"Journal entry is not balanced: debit {debit}, credit {credit}."
            )
        return self


class JournalEntryUpdate(FinanceSchema):
    """Apply a partial journal entry update while it remains a draft."""

    description: str | None = None
    remarks: str | None = None
    journal_date: date | None = None


class JournalEntryResponse(FinanceSchema):
    """Return one journal entry with its lines."""

    id: UUID
    firm_id: UUID
    journal_type_id: UUID
    voucher_type_id: UUID
    accounting_period_id: UUID
    journal_date: date
    reference_number: str
    description: str | None
    remarks: str | None
    status: JournalStatusEnum
    posted_at: datetime | None
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool
    source_module: str | None
    source_id: UUID | None
    reversal_of_id: UUID | None
    version: int
    lines: list[JournalLineResponse]


class JournalEntryReverse(FinanceSchema):
    """Reverse a posted journal entry under a new reference."""

    reference_number: str = Field(max_length=50, min_length=1)
    accounting_period_id: UUID | None = None
    journal_date: date | None = None


class JournalEntryFilters(FinanceSchema):
    """Filter the journal entry list."""

    accounting_period_id: UUID | None = None
    journal_type_id: UUID | None = None
    status: JournalStatusEnum | None = None
    source_module: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class LedgerBalanceResponse(FinanceSchema):
    """Return the stored balance of one account for one period."""

    id: UUID
    firm_id: UUID
    ledger_account_id: UUID
    accounting_period_id: UUID
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal
    updated_at: datetime


class GLPostingResponse(FinanceSchema):
    """Return one general-ledger posting record."""

    id: UUID
    firm_id: UUID
    journal_entry_id: UUID
    journal_line_id: UUID
    ledger_account_id: UUID
    accounting_period_id: UUID
    posting_date: datetime
    debit_amount: Decimal
    credit_amount: Decimal
    status: PostingStatusEnum
    error_message: str | None


class TrialBalanceLine(FinanceSchema):
    """Return one account row of a trial balance."""

    ledger_account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountTypeEnum
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal


class TrialBalanceReport(FinanceSchema):
    """Return a trial balance for one accounting period."""

    accounting_period_id: UUID
    generated_at: datetime
    lines: list[TrialBalanceLine]
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool


class GeneralLedgerLine(FinanceSchema):
    """Return one movement row of a general-ledger statement.

    Dated by the journal date, not by when someone pressed Post. A ledger
    statement is a record of when business happened; ``GLPosting.posting_date``
    is the wall clock at the moment of posting and belongs to the audit trail.
    """

    journal_entry_id: UUID
    journal_date: date
    reference_number: str
    description: str | None
    debit_amount: Decimal
    credit_amount: Decimal
    running_balance: Decimal


class GeneralLedgerReport(FinanceSchema):
    """Return a general-ledger statement for one account."""

    ledger_account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountTypeEnum
    accounting_period_id: UUID
    opening_balance: Decimal
    total_debit: Decimal
    total_credit: Decimal
    closing_balance: Decimal
    lines: list[GeneralLedgerLine]


class ProfitLossLine(FinanceSchema):
    """Return one income or expense account's contribution to the result.

    Both figures are the account's own movement in its natural direction --
    income counted on the credit side, expenses on the debit -- so a positive
    number always means "this much income" or "this much cost", whichever
    section the line is in. A contra account such as sales returns runs the
    other way and reports negative, which is what it does to the result.
    """

    ledger_account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountTypeEnum
    period_amount: Decimal
    year_to_date_amount: Decimal


class ProfitLossReport(FinanceSchema):
    """Return the profit and loss for one period and the year it belongs to.

    Two columns, because one on its own is the wrong answer half the time: a
    month is what somebody asks about, and the year to date is what tells them
    whether the month was normal.

    There is no `is_profit` flag. Whether the books balance is a claim about
    the ledger and belongs to the server, but profit against loss is only the
    sign of a number that is already here, and a second field carrying it is a
    second thing to keep in step.
    """

    accounting_period_id: UUID
    financial_year_id: UUID
    generated_at: datetime
    income: list[ProfitLossLine]
    expenses: list[ProfitLossLine]
    total_income: Decimal
    total_expense: Decimal
    net_profit: Decimal
    year_to_date_income: Decimal
    year_to_date_expense: Decimal
    year_to_date_net_profit: Decimal


class AccountSummary(FinanceSchema):
    """Return one aggregated account balance row."""

    ledger_account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountTypeEnum
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal


__all__ = [
    "AccountGroupCreate",
    "AccountGroupResponse",
    "AccountGroupUpdate",
    "AccountSummary",
    "AccountTypeEnum",
    "AccountingPeriodCreate",
    "AccountingPeriodResponse",
    "AccountingPeriodUpdate",
    "CostCenterCreate",
    "CostCenterResponse",
    "CostCenterUpdate",
    "FinancialYearCreate",
    "FinancialYearResponse",
    "FinancialYearUpdate",
    "GLPostingResponse",
    "GeneralLedgerLine",
    "GeneralLedgerReport",
    "JournalEntryCreate",
    "JournalEntryFilters",
    "JournalEntryResponse",
    "JournalEntryReverse",
    "JournalEntryUpdate",
    "JournalLineInput",
    "JournalLineResponse",
    "JournalStatusEnum",
    "JournalTypeCreate",
    "JournalTypeResponse",
    "LedgerAccountCreate",
    "LedgerAccountResponse",
    "LedgerAccountUpdate",
    "LedgerBalanceResponse",
    "PeriodStatusEnum",
    "PostingStatusEnum",
    "ProfitCenterCreate",
    "ProfitCenterResponse",
    "ProfitCenterUpdate",
    "ProfitLossLine",
    "ProfitLossReport",
    "TrialBalanceLine",
    "TrialBalanceReport",
    "VoucherTypeCreate",
    "VoucherTypeResponse",
]
