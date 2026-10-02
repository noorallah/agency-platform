"""Contracts for a customer's bank accounts and files on record (MST-4)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Schema(BaseModel):
    """Forbid undeclared fields and read from ORM rows."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CustomerBankAccountInput(_Schema):
    """One account in the list that replaces a customer's accounts."""

    bank_name: str = Field(min_length=1, max_length=150)
    account_name: str = Field(min_length=1, max_length=150)
    account_number: str = Field(min_length=4, max_length=64)
    ifsc: str | None = Field(default=None, max_length=16)
    branch: str | None = Field(default=None, max_length=120)
    upi_id: str | None = Field(default=None, max_length=120)
    is_primary: bool = False

    @field_validator("account_number", "ifsc", mode="before")
    @classmethod
    def _compact(cls, value: str | None) -> str | None:
        """Drop spaces and upper-case, so a number reads one way."""
        if value is None:
            return None
        compact = "".join(value.split()).upper()
        return compact or None


class CustomerBankAccountsWrite(_Schema):
    """The whole list of a customer's accounts; an empty list clears them."""

    accounts: list[CustomerBankAccountInput] = Field(max_length=20)


class CustomerBankAccountResponse(_Schema):
    """One account, its number masked unless the reader may change it."""

    id: UUID
    bank_name: str
    account_name: str
    account_number: str
    ifsc: str | None
    branch: str | None
    upi_id: str | None
    is_primary: bool
    #: True when ``account_number`` shows only its last four digits.
    masked: bool = False


class CustomerAttachmentWrite(_Schema):
    """One file to keep on file for a customer."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    caption: str | None = Field(default=None, max_length=200)


class CustomerAttachmentsWrite(_Schema):
    """The files to keep on record, one or more at a time."""

    files: list[CustomerAttachmentWrite] = Field(min_length=1, max_length=50)


class CustomerAttachmentResponse(_Schema):
    """One file kept on file for a customer."""

    id: UUID
    customer_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    caption: str | None
    created_at: datetime
    created_by: UUID | None
