"""Finance API schemas - Pydantic models for request/response validation."""

from decimal import Decimal
from datetime import datetime
from uuid import UUID
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, validator


class AccountTypeEnum(str, Enum):
    """GL Account types."""
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"
    MEMO = "MEMO"
    CONTROL = "CONTROL"


class PeriodStatusEnum(str, Enum):
    """Accounting period status."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class JournalStatusEnum(str, Enum):
    """Journal entry status."""
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class PostingStatusEnum(str, Enum):
    """GL posting status."""
    PENDING = "PENDING"
    POSTED = "POSTED"
    ERROR = "ERROR"


# Financial Year Schema
class FinancialYearCreate(BaseModel):
    financial_year_code: str
    financial_year_name: str
    financial_year_start: datetime
    financial_year_end: datetime
    is_active: bool = True
    description: Optional[str] = None


class FinancialYearUpdate(BaseModel):
    financial_year_name: Optional[str] = None
    financial_year_start: Optional[datetime] = None
    financial_year_end: Optional[datetime] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class FinancialYearResponse(BaseModel):
    id: UUID
    firm_id: UUID
    financial_year_code: str
    financial_year_name: str
    financial_year_start: datetime
    financial_year_end: datetime
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


# Accounting Period Schema
class AccountingPeriodCreate(BaseModel):
    financial_year_id: UUID
    period_code: str
    period_name: str
    period_start: datetime
    period_end: datetime
    status: PeriodStatusEnum = PeriodStatusEnum.OPEN
    description: Optional[str] = None


class AccountingPeriodUpdate(BaseModel):
    period_name: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    status: Optional[PeriodStatusEnum] = None
    description: Optional[str] = None


class AccountingPeriodResponse(BaseModel):
    id: UUID
    financial_year_id: UUID
    period_code: str
    period_name: str
    period_start: datetime
    period_end: datetime
    status: PeriodStatusEnum
    description: Optional[str]

    class Config:
        from_attributes = True


# Account Group Schema
class AccountGroupCreate(BaseModel):
    account_group_code: str
    account_group_name: str
    account_type: AccountTypeEnum
    parent_group_id: Optional[UUID] = None
    description: Optional[str] = None


class AccountGroupResponse(BaseModel):
    id: UUID
    account_group_code: str
    account_group_name: str
    account_type: str
    parent_group_id: Optional[UUID]
    description: Optional[str]

    class Config:
        from_attributes = True


# Ledger Account Schema
class LedgerAccountCreate(BaseModel):
    account_group_id: UUID
    account_code: str
    account_name: str
    account_type: AccountTypeEnum
    is_active: bool = True
    requires_cost_center: bool = False
    requires_profit_center: bool = False
    description: Optional[str] = None


class LedgerAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    is_active: Optional[bool] = None
    requires_cost_center: Optional[bool] = None
    requires_profit_center: Optional[bool] = None
    description: Optional[str] = None


class LedgerAccountResponse(BaseModel):
    id: UUID
    account_group_id: UUID
    account_code: str
    account_name: str
    account_type: str
    is_active: bool
    requires_cost_center: bool
    requires_profit_center: bool
    description: Optional[str]

    class Config:
        from_attributes = True


# Cost Center Schema
class CostCenterCreate(BaseModel):
    cost_center_code: str
    cost_center_name: str
    is_active: bool = True
    description: Optional[str] = None


class CostCenterResponse(BaseModel):
    id: UUID
    cost_center_code: str
    cost_center_name: str
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


# Profit Center Schema
class ProfitCenterCreate(BaseModel):
    profit_center_code: str
    profit_center_name: str
    is_active: bool = True
    description: Optional[str] = None


class ProfitCenterResponse(BaseModel):
    id: UUID
    profit_center_code: str
    profit_center_name: str
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


# Journal Type Schema
class JournalTypeCreate(BaseModel):
    journal_type_code: str
    journal_type_name: str
    is_active: bool = True
    description: Optional[str] = None


class JournalTypeResponse(BaseModel):
    id: UUID
    journal_type_code: str
    journal_type_name: str
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


# Voucher Type Schema
class VoucherTypeCreate(BaseModel):
    voucher_type_code: str
    voucher_type_name: str
    is_active: bool = True
    description: Optional[str] = None


class VoucherTypeResponse(BaseModel):
    id: UUID
    voucher_type_code: str
    voucher_type_name: str
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


# Journal Line Schema (for entry/response)
class JournalLineSchema(BaseModel):
    ledger_account_id: UUID
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    cost_center_id: Optional[UUID] = None
    profit_center_id: Optional[UUID] = None
    description: Optional[str] = None

    @validator("debit_amount", "credit_amount", pre=True)
    def quantize_decimal(cls, v):
        if v is None:
            return Decimal("0")
        val = Decimal(str(v))
        return val.quantize(Decimal("0.01"))


# Journal Entry Schema
class JournalEntryCreate(BaseModel):
    journal_type_id: UUID
    voucher_type_id: UUID
    accounting_period_id: UUID
    journal_date: datetime
    reference_number: str
    description: str
    lines: list[JournalLineSchema]
    remarks: Optional[str] = None

    @validator("lines")
    def validate_lines(cls, v):
        if len(v) < 2:
            raise ValueError("Journal entry must have at least 2 lines (1 debit, 1 credit)")
        return v


class JournalEntryUpdate(BaseModel):
    description: Optional[str] = None
    remarks: Optional[str] = None


class JournalEntryResponse(BaseModel):
    id: UUID
    journal_type_id: UUID
    voucher_type_id: UUID
    accounting_period_id: UUID
    journal_date: datetime
    reference_number: str
    description: str
    status: JournalStatusEnum
    remarks: Optional[str]
    total_debit: Decimal
    total_credit: Decimal
    source_module: Optional[str]
    source_id: Optional[UUID]
    created_by: UUID
    created_at: datetime
    modified_at: datetime

    class Config:
        from_attributes = True


# Ledger Balance Schema
class LedgerBalanceResponse(BaseModel):
    ledger_account_id: UUID
    accounting_period_id: UUID
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal
    last_updated: datetime

    class Config:
        from_attributes = True


# GL Posting Schema
class GLPostingResponse(BaseModel):
    id: UUID
    journal_entry_id: UUID
    ledger_account_id: UUID
    accounting_period_id: UUID
    debit_amount: Decimal
    credit_amount: Decimal
    posting_date: datetime

    class Config:
        from_attributes = True


# Trial Balance Report Schema
class TrialBalanceLineSchema(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    debit_balance: Decimal
    credit_balance: Decimal
    closing_balance: Decimal


class TrialBalanceReportSchema(BaseModel):
    accounting_period_id: UUID
    as_of: datetime
    lines: list[TrialBalanceLineSchema]
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool


# GL Detail Report Schema
class GLDetailLineSchema(BaseModel):
    posting_date: Optional[datetime]
    reference: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


class GeneralLedgerReportSchema(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    opening_balance: Decimal
    closing_balance: Decimal
    total_debit: Decimal
    total_credit: Decimal
    lines: list[GLDetailLineSchema]


# Account Summary Schema
class AccountSummarySchema(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    account_type: str
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal


# Customer Ledger Schema
class CustomerLedgerSchema(BaseModel):
    customer_id: UUID
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal
    ageing_0_30: Decimal
    ageing_31_60: Decimal
    ageing_61_90: Decimal
    ageing_90_plus: Decimal


# Vendor Ledger Schema
class VendorLedgerSchema(BaseModel):
    vendor_id: UUID
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal
    ageing_0_30: Decimal
    ageing_31_60: Decimal
    ageing_61_90: Decimal
    ageing_90_plus: Decimal
