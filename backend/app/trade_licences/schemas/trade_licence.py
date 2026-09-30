"""Validated contracts for trade licences (backlog 54)."""

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TradeLicenceSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LicenceHolderType(StrEnum):
    """Who holds a licence."""

    FIRM = "FIRM"
    CUSTOMER = "CUSTOMER"
    VENDOR = "VENDOR"


class LicenceStanding(StrEnum):
    """Where a licence stands on a given day, derived and never stored."""

    VALID = "VALID"
    #: Valid, and runs out within the warning window.
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    NOT_YET_VALID = "NOT_YET_VALID"
    #: A type that expires, recorded without a valid-to date -- the case the
    #: register's migration leaves for numbers copied from the old fields.
    NO_EXPIRY_RECORDED = "NO_EXPIRY_RECORDED"


class TradeLicenceTypeWrite(TradeLicenceSchema):
    """Create or replace one licence type."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    form_numbers: str | None = Field(default=None, max_length=120)
    expires: bool = True
    is_active: bool = True
    description: str | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, value: str) -> str:
        """Keep codes in capitals, as every other master's are."""
        return value.strip().upper()


class TradeLicenceTypeResponse(TradeLicenceSchema):
    """One licence type."""

    id: UUID
    version: int
    code: str
    name: str
    form_numbers: str | None
    expires: bool
    is_active: bool
    description: str | None


class TradeLicenceWrite(TradeLicenceSchema):
    """Record, or replace, one licence."""

    licence_type_id: UUID
    holder_type: LicenceHolderType
    branch_id: UUID | None = None
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    licence_number: str = Field(min_length=1, max_length=80)
    issued_by: str | None = Field(default=None, max_length=200)
    valid_from: date | None = None
    valid_to: date | None = None
    premises: str | None = Field(default=None, max_length=250)
    remarks: str | None = None

    @field_validator("licence_number", mode="before")
    @classmethod
    def _number(cls, value: str) -> str:
        """Trim the number; it is compared as printed."""
        return value.strip().upper()

    @model_validator(mode="after")
    def _holder_and_dates(self) -> "TradeLicenceWrite":
        """Name exactly the holder the type says, and an ordered validity."""
        if self.holder_type is LicenceHolderType.CUSTOMER:
            if self.customer_id is None:
                raise ValueError("A customer's licence names the customer.")
            if self.vendor_id is not None or self.branch_id is not None:
                raise ValueError("A customer's licence names only the customer.")
        elif self.holder_type is LicenceHolderType.VENDOR:
            if self.vendor_id is None:
                raise ValueError("A vendor's licence names the vendor.")
            if self.customer_id is not None or self.branch_id is not None:
                raise ValueError("A vendor's licence names only the vendor.")
        elif self.customer_id is not None or self.vendor_id is not None:
            raise ValueError(
                "The firm's own licence names at most a branch, never a "
                "customer or a vendor."
            )
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("A licence cannot run out before it starts.")
        return self


class TradeLicenceResponse(TradeLicenceSchema):
    """One licence, with its type and holder named and where it stands today."""

    id: UUID
    version: int
    licence_type_id: UUID
    licence_type_code: str
    licence_type_name: str
    holder_type: LicenceHolderType
    branch_id: UUID | None
    customer_id: UUID | None
    vendor_id: UUID | None
    #: The firm's name for the holder -- the branch (or "Firm"), customer or
    #: vendor -- so a list across holders reads without a second lookup.
    holder_name: str
    licence_number: str
    issued_by: str | None
    valid_from: date | None
    valid_to: date | None
    premises: str | None
    remarks: str | None
    standing: LicenceStanding
    #: Days until it runs out, negative once it has; null with no valid-to.
    days_to_expiry: int | None
