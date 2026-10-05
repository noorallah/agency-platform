"""Party adjustment request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.settlements.schemas import OutstandingInvoiceRecord


class PartyAdjustmentSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PartyAdjustmentKindEnum(StrEnum):
    """Which balance moves."""

    CUSTOMER_WRITE_OFF = "CUSTOMER_WRITE_OFF"
    SUPPLIER_WRITE_BACK = "SUPPLIER_WRITE_BACK"
    SET_OFF = "SET_OFF"
    SUPPLIER_REBATE = "SUPPLIER_REBATE"
    PRINCIPAL_CLAIM = "PRINCIPAL_CLAIM"
    CUSTOMER_REBATE = "CUSTOMER_REBATE"


class PartyAdjustmentStatusEnum(StrEnum):
    """Where an adjustment has got to."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class PartyAdjustmentSideEnum(StrEnum):
    """Whose bill an allocation clears: the customer's or the supplier's."""

    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"


class PartyAdjustmentAllocationWrite(PartyAdjustmentSchema):
    """Take part of an adjustment off one open bill."""

    side: PartyAdjustmentSideEnum
    #: A sales or purchase invoice, or an opening bill, as the outstanding
    #: list names it.
    bill_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


def _one_row_per_bill(
    allocations: list[PartyAdjustmentAllocationWrite] | None,
) -> None:
    """Refuse the same bill twice in one adjustment."""
    if not allocations:
        return
    seen = {(item.side, item.bill_id) for item in allocations}
    if len(seen) != len(allocations):
        raise ValueError("A bill can appear only once in one adjustment.")


class PartyAdjustmentCreate(PartyAdjustmentSchema):
    """Draft one write-off, write-back or set-off."""

    kind: PartyAdjustmentKindEnum
    adjustment_date: date
    #: The customer, for a write-off or a set-off.
    customer_id: UUID | None = None
    #: The supplier, for a write-back or a set-off.
    vendor_id: UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    #: Required: why the balance is moving is the first thing asked of it.
    reason: str = Field(min_length=1, max_length=2000)
    adjustment_number: str | None = Field(default=None, max_length=60)
    #: Open bills it clears. Optional: what is not allocated moves the
    #: party's balance on account.
    allocations: list[PartyAdjustmentAllocationWrite] = Field(default_factory=list)
    #: The volume rebate a ``SUPPLIER_REBATE`` settles, and only then.
    rebate_agreement_id: UUID | None = None
    #: The claim a ``PRINCIPAL_CLAIM`` settles, and only then (SEL-11).
    principal_claim_id: UUID | None = None
    #: The turnover rebate a ``CUSTOMER_REBATE`` settles, and only then (SG-9).
    customer_rebate_agreement_id: UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> "PartyAdjustmentCreate":
        """Refuse a reason of blanks, the same bill twice, a stray agreement."""
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Say why the balance is being adjusted.")
        _one_row_per_bill(self.allocations)
        rebate = self.kind == PartyAdjustmentKindEnum.SUPPLIER_REBATE
        if rebate and self.rebate_agreement_id is None:
            raise ValueError("Name the rebate agreement this settles.")
        if not rebate and self.rebate_agreement_id is not None:
            raise ValueError("Only a rebate settlement names a rebate agreement.")
        claim = self.kind == PartyAdjustmentKindEnum.PRINCIPAL_CLAIM
        if claim and self.principal_claim_id is None:
            raise ValueError("Name the claim this settles.")
        if not claim and self.principal_claim_id is not None:
            raise ValueError("Only a claim settlement names a claim.")
        turnover = self.kind == PartyAdjustmentKindEnum.CUSTOMER_REBATE
        if turnover and self.customer_rebate_agreement_id is None:
            raise ValueError("Name the rebate agreement this settles.")
        if not turnover and self.customer_rebate_agreement_id is not None:
            raise ValueError(
                "Only a customer's rebate settlement names a customer rebate "
                "agreement."
            )
        return self


class PartyAdjustmentUpdate(PartyAdjustmentSchema):
    """Change a draft. Absent fields are left alone; the kind is fixed."""

    adjustment_date: date | None = None
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    allocations: list[PartyAdjustmentAllocationWrite] | None = None

    @model_validator(mode="after")
    def _shape(self) -> "PartyAdjustmentUpdate":
        """Refuse a reason of blanks and the same bill named twice."""
        if self.reason is not None:
            self.reason = self.reason.strip()
            if not self.reason:
                raise ValueError("Say why the balance is being adjusted.")
        _one_row_per_bill(self.allocations)
        return self


class PartyAdjustmentCancel(PartyAdjustmentSchema):
    """Carry why an adjustment is withdrawn."""

    reason: str = Field(min_length=1, max_length=500)


class PartyAdjustmentAllocationResponse(PartyAdjustmentSchema):
    """One bill an adjustment clears."""

    id: UUID
    side: PartyAdjustmentSideEnum
    bill_id: UUID
    bill_number: str
    bill_date: date | None
    amount: Decimal


class PartyAdjustmentResponse(PartyAdjustmentSchema):
    """Return one adjustment."""

    id: UUID
    adjustment_number: str
    adjustment_date: date
    kind: PartyAdjustmentKindEnum
    status: PartyAdjustmentStatusEnum
    customer_id: UUID | None
    customer_name: str | None
    vendor_id: UUID | None
    vendor_name: str | None
    amount: Decimal
    reason: str
    #: What the allocations take off bills, per side; the rest is on account.
    customer_allocated: Decimal
    supplier_allocated: Decimal
    #: Whether approving needs a second person holding
    #: `PARTY_ADJUSTMENT_APPROVE` -- the amount is above the firm's threshold.
    needs_second_approver: bool
    journal_entry_id: UUID | None
    reversal_journal_entry_id: UUID | None
    approved_at: datetime | None
    approved_by: UUID | None
    created_by: UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    allocations: list[PartyAdjustmentAllocationResponse]
    version: int
    rebate_agreement_id: UUID | None = None
    principal_claim_id: UUID | None = None
    customer_rebate_agreement_id: UUID | None = None


class PartyAdjustmentOpenBills(PartyAdjustmentSchema):
    """The bills an adjustment can clear, for each party it names."""

    customer_bills: list[OutstandingInvoiceRecord]
    supplier_bills: list[OutstandingInvoiceRecord]
    #: The customer's balance on account, and what the supplier's open bills
    #: add up to -- the most a write-off, write-back or set-off can move.
    customer_balance: Decimal | None
    supplier_outstanding: Decimal | None


class PartyAdjustmentSettingsResponse(PartyAdjustmentSchema):
    """A firm's limits on clearing a balance without money."""

    approval_threshold: Decimal
    rounding_limit: Decimal
    is_default: bool


class PartyAdjustmentSettingsWrite(PartyAdjustmentSchema):
    """Set the firm's limits."""

    approval_threshold: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    rounding_limit: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class PartyAdjustmentRegisterRecord(PartyAdjustmentSchema):
    """One row of the party adjustment register."""

    adjustment_id: UUID
    adjustment_number: str
    adjustment_date: date
    kind: PartyAdjustmentKindEnum
    status: PartyAdjustmentStatusEnum
    customer_name: str | None
    vendor_name: str | None
    amount: Decimal
    reason: str


__all__ = [
    "PartyAdjustmentAllocationResponse",
    "PartyAdjustmentAllocationWrite",
    "PartyAdjustmentCancel",
    "PartyAdjustmentCreate",
    "PartyAdjustmentKindEnum",
    "PartyAdjustmentOpenBills",
    "PartyAdjustmentRegisterRecord",
    "PartyAdjustmentResponse",
    "PartyAdjustmentSchema",
    "PartyAdjustmentSettingsResponse",
    "PartyAdjustmentSettingsWrite",
    "PartyAdjustmentSideEnum",
    "PartyAdjustmentStatusEnum",
    "PartyAdjustmentUpdate",
]
