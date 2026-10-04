"""Request and response contracts for TDS challans (ACC-7)."""

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.finance.tds import TDS_SECTIONS


class DeductionKind(StrEnum):
    """The document a deduction was made on."""

    PAYMENT = "PAYMENT"
    EXPENSE = "EXPENSE"
    #: A supplier's bill that bore 194C or 194J at approval (PG-5).
    BILL = "BILL"


class DeductionRef(BaseModel):
    """One deduction a challan pays, by its document."""

    model_config = ConfigDict(extra="forbid")

    kind: DeductionKind
    id: UUID


class TdsChallanCreate(BaseModel):
    """A challan as the bank's counterfoil states it, and what it paid."""

    model_config = ConfigDict(extra="forbid")

    deposited_on: date
    #: The bank branch's BSR code: seven digits.
    bsr_code: str
    #: The bank's challan serial number: five digits.
    challan_serial: str
    section: str
    paid_from_account_id: UUID
    #: The tax on the counterfoil. Optional; given, it must equal the
    #: deductions chosen, so a slip typed wrong is caught here.
    tax_amount: Decimal | None = Field(default=None, gt=0)
    interest_amount: Decimal = Field(default=Decimal("0"), ge=0)
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    remarks: str | None = Field(default=None, max_length=1000)
    deductions: list[DeductionRef] = Field(min_length=1, max_length=5000)

    @field_validator("bsr_code")
    @classmethod
    def _bsr(cls, value: str) -> str:
        """Accept a BSR code: seven digits."""
        cleaned = value.strip()
        if not re.fullmatch(r"\d{7}", cleaned):
            raise ValueError("The BSR code is the bank branch's seven digits.")
        return cleaned

    @field_validator("challan_serial")
    @classmethod
    def _serial(cls, value: str) -> str:
        """Accept a challan serial of up to five digits, kept as five."""
        cleaned = value.strip()
        if not re.fullmatch(r"\d{1,5}", cleaned):
            raise ValueError("The challan serial number is up to five digits.")
        return cleaned.zfill(5)

    @field_validator("section")
    @classmethod
    def _section(cls, value: str) -> str:
        """Accept a section the firm files under."""
        cleaned = value.strip().upper()
        if cleaned not in TDS_SECTIONS:
            raise ValueError(
                f"{cleaned} is not a TDS section. Use one of "
                + ", ".join(TDS_SECTIONS)
                + "."
            )
        return cleaned


class TdsChallanCancel(BaseModel):
    """Why a challan is being cancelled."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class OpenDeductionRecord(BaseModel):
    """A deduction not yet paid by any live challan."""

    kind: DeductionKind
    id: UUID
    document_number: str
    document_date: date
    party_name: str
    pan: str | None
    section: str
    gross_amount: Decimal
    tds_amount: Decimal
    #: The seventh of the next month; 30 April for March.
    due_date: date


class TdsChallanItemResponse(BaseModel):
    """One deduction on a challan."""

    kind: DeductionKind
    document_id: UUID
    document_number: str
    document_date: date
    party_name: str
    pan: str | None
    tds_amount: Decimal


class TdsChallanResponse(BaseModel):
    """One challan with the deductions it paid."""

    id: UUID
    challan_number: str
    deposited_on: date
    bsr_code: str
    challan_serial: str
    #: BSR code, date as ddmmyyyy and serial: the Challan Identification
    #: Number the return files under.
    cin: str
    section: str
    section_name: str
    tax_amount: Decimal
    interest_amount: Decimal
    fee_amount: Decimal
    total_amount: Decimal
    paid_from_account_id: UUID
    paid_from_account_code: str
    paid_from_account_name: str
    remarks: str | None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    #: Deposited after the due date of its earliest deduction.
    is_late: bool
    items: list[TdsChallanItemResponse]
    created_at: datetime
    version: int
