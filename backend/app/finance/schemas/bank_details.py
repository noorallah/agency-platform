"""Request and response contracts for the firm's bank details (ACC-4)."""

import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Four letters for the bank, a zero, six characters for the branch (RBI).
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
#: Indian account numbers run from 9 to 18 digits; a few banks use letters.
_ACCOUNT_NUMBER = re.compile(r"^[0-9A-Z]{6,34}$")


class BankAccountKind(StrEnum):
    """What kind of account the bank holds."""

    CURRENT = "CURRENT"
    SAVINGS = "SAVINGS"
    CASH_CREDIT = "CASH_CREDIT"
    OVERDRAFT = "OVERDRAFT"


class BankAccountDetailsWrite(BaseModel):
    """A bank ledger account's details, saved as a whole."""

    model_config = ConfigDict(extra="forbid")

    bank_name: str = Field(min_length=1, max_length=150)
    account_name: str = Field(min_length=1, max_length=150)
    account_number: str = Field(min_length=1, max_length=64)
    ifsc: str | None = Field(default=None, max_length=16)
    branch: str | None = Field(default=None, max_length=120)
    account_kind: BankAccountKind | None = None
    swift_code: str | None = Field(default=None, max_length=16)
    upi_id: str | None = Field(default=None, max_length=120)
    print_on_documents: bool = False

    @field_validator("bank_name", "account_name")
    @classmethod
    def strip_names(cls, value: str) -> str:
        """Refuse a name that is only spaces."""
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("account_number")
    @classmethod
    def normalise_number(cls, value: str) -> str:
        """Drop spaces and dashes, and refuse anything else."""
        value = re.sub(r"[\s-]", "", value).upper()
        if not _ACCOUNT_NUMBER.match(value):
            raise ValueError("must be 6 to 34 letters or digits")
        return value

    @field_validator("ifsc")
    @classmethod
    def check_ifsc(cls, value: str | None) -> str | None:
        """Accept an RBI IFSC: four letters, a zero, six characters."""
        if value is None or not value.strip():
            return None
        value = value.strip().upper()
        if not _IFSC.match(value):
            raise ValueError("must be 11 characters, like HDFC0001234")
        return value

    @field_validator("branch", "swift_code", "upi_id")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        """Store an empty box as nothing."""
        if value is None:
            return None
        return value.strip() or None


class BankAccountDetailsResponse(BaseModel):
    """One bank ledger account's details; the number masked where withheld."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ledger_account_id: UUID
    ledger_account_code: str
    ledger_account_name: str
    bank_name: str
    account_name: str
    account_number: str
    #: True when ``account_number`` shows only its last four characters.
    masked: bool = False
    ifsc: str | None
    branch: str | None
    account_kind: str | None
    swift_code: str | None
    upi_id: str | None
    print_on_documents: bool
    version: int
    updated_at: datetime
