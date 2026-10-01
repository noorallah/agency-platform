"""Expense request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import normalize_pan
from app.finance.tds import check_tds


class ExpenseSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ExpenseCreate(ExpenseSchema):
    """Record one amount the firm has already spent."""

    expense_date: date
    expense_account_id: UUID
    paid_from_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payee: str | None = Field(default=None, max_length=200)
    reference: str | None = Field(default=None, max_length=120)
    narration: str | None = Field(default=None, max_length=2000)
    #: Tax deducted at source out of ``amount`` (backlog 53.1): rent, fees and
    #: transport commonly carry it. The expense is the whole ``amount``; the
    #: money paid out is the rest. Blank or 0 means nothing was deducted.
    tds_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    tds_section: str | None = Field(default=None, max_length=10)
    #: The payee's PAN, which the TDS return names the deductee by.
    payee_pan: str | None = Field(default=None, max_length=10)

    @field_validator("payee_pan")
    @classmethod
    def _pan(cls, value: str | None) -> str | None:
        return normalize_pan(value)

    @model_validator(mode="after")
    def _tds_can_be_filed(self) -> "ExpenseCreate":
        """Refuse a deduction that the quarterly return could not carry."""
        if self.tds_section is not None:
            self.tds_section = self.tds_section.strip().upper() or None
        check_tds(self.amount, self.tds_amount, self.tds_section)
        if (self.tds_amount or 0) > 0 and not (self.payee and self.payee.strip()):
            raise ValueError(
                "Name the payee: the TDS return lists every deduction by deductee."
            )
        return self


class ExpenseCancelRequest(ExpenseSchema):
    """Say why an expense is being taken back. A reason is required."""

    reason: str = Field(min_length=1, max_length=500)


class ExpenseResponse(ExpenseSchema):
    """Return one expense with the accounts it names."""

    id: UUID
    expense_number: str
    expense_date: date
    expense_account_id: UUID
    expense_account_code: str
    expense_account_name: str
    paid_from_account_id: UUID
    paid_from_account_code: str
    paid_from_account_name: str
    amount: Decimal
    tds_amount: Decimal = Decimal("0")
    tds_section: str | None = None
    payee_pan: str | None = None
    #: What left the cash or bank account: ``amount - tds_amount``.
    paid_amount: Decimal | None = None
    payee: str | None
    reference: str | None
    narration: str | None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    cancel_reason: str | None
    cancelled_at: datetime | None
    version: int


class ExpenseAccountRecord(ExpenseSchema):
    """One ledger account the expense form may offer."""

    id: UUID
    code: str
    name: str


class ExpenseAccountChoices(ExpenseSchema):
    """What the expense form offers: what it was for, and where it came from.

    ``expense_accounts`` are the firm's EXPENSE accounts that no document posts
    to; ``paid_from_accounts`` are its cash, bank and other money accounts.
    """

    expense_accounts: list[ExpenseAccountRecord]
    paid_from_accounts: list[ExpenseAccountRecord]


__all__ = [
    "ExpenseAccountChoices",
    "ExpenseAccountRecord",
    "ExpenseCancelRequest",
    "ExpenseCreate",
    "ExpenseResponse",
    "ExpenseSchema",
]
