"""Staff advance request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.staff_advances.models import StaffAdvanceKind


class StaffAdvanceSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class EmployeeCreate(StaffAdvanceSchema):
    """Open an account for one employee under Staff Advances."""

    name: str = Field(min_length=1, max_length=100)


class EmployeeRecord(StaffAdvanceSchema):
    """One employee's account and what he still owes.

    ``advanced`` and ``recovered`` are everything posted to the account,
    whoever posted it; ``owes`` is the first less the second, and is negative
    where more was taken back than was given.
    """

    account_id: UUID
    code: str
    name: str
    is_active: bool
    advanced: Decimal
    recovered: Decimal
    owes: Decimal


class StaffAdvanceAccountRecord(StaffAdvanceSchema):
    """One ledger account a staff advance form may offer."""

    id: UUID
    code: str
    name: str
    #: ``CASH`` or ``BANK`` for a money account; absent for an expense account.
    kind: str | None = None


class StaffAdvanceAccountChoices(StaffAdvanceSchema):
    """What the forms offer.

    ``money_accounts`` pay an advance and receive one paid back;
    ``salary_accounts`` are the expense accounts a recovery out of salary may
    be booked to.
    """

    money_accounts: list[StaffAdvanceAccountRecord]
    salary_accounts: list[StaffAdvanceAccountRecord]


class StaffAdvanceCreate(StaffAdvanceSchema):
    """Record one advance to an employee, or one recovery."""

    kind: StaffAdvanceKind
    entry_date: date
    employee_account_id: UUID
    #: An advance: the cash or bank account paid from. A recovery: the expense
    #: account the salary is booked to, or the money account it was paid into.
    other_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    narration: str | None = Field(default=None, max_length=2000)
    #: Sent ``true`` by a screen whose user answered *Save anyway?*: an
    #: advance out of a cash account that holds less is asked about first.
    cash_below_zero_confirmed: bool = False


class StaffAdvanceCancelRequest(StaffAdvanceSchema):
    """Say why an entry is being taken back. A reason is required."""

    reason: str = Field(min_length=1, max_length=500)


class StaffAdvanceResponse(StaffAdvanceSchema):
    """Return one entry with the accounts it names."""

    id: UUID
    entry_number: str
    entry_date: date
    kind: str
    employee_account_id: UUID
    employee_name: str
    other_account_id: UUID
    other_account_code: str
    other_account_name: str
    #: ``SALARY`` where a recovery was booked to an expense account, ``MONEY``
    #: where the other side is cash or a bank account.
    other_side: str
    amount: Decimal
    narration: str | None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    cancel_reason: str | None
    cancelled_at: datetime | None
    version: int


__all__ = [
    "EmployeeCreate",
    "EmployeeRecord",
    "StaffAdvanceAccountChoices",
    "StaffAdvanceAccountRecord",
    "StaffAdvanceCancelRequest",
    "StaffAdvanceCreate",
    "StaffAdvanceResponse",
    "StaffAdvanceSchema",
]
