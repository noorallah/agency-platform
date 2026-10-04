"""Contracts for rate contracts and the orders released against them (PG-9)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RateContractSchema(BaseModel):
    """Base contract: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class RateContractLineWrite(RateContractSchema):
    """One product on the contract and its agreed terms."""

    product_id: UUID
    rate: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=9, decimal_places=4
    )
    #: Blank takes the product's purchase unit.
    uom_id: UUID | None = None
    #: Blank is a rate agreement with no quantity to draw down.
    contracted_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    notes: str | None = Field(default=None, max_length=500)


class RateContractCreate(RateContractSchema):
    """Type a draft contract: the whole document."""

    vendor_id: UUID
    valid_from: date
    valid_to: date
    reference: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[RateContractLineWrite] = Field(min_length=1, max_length=500)


class RateContractUpdate(RateContractSchema):
    """Change a draft contract; a field left out is left alone."""

    vendor_id: UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    reference: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    #: Replaces the lines whole when sent, reconciled on line number.
    lines: list[RateContractLineWrite] | None = Field(
        default=None, min_length=1, max_length=500
    )


class RateContractCancel(RateContractSchema):
    """Why a contract is called off."""

    reason: str = Field(min_length=1, max_length=1000)


class RateContractLineResponse(RateContractSchema):
    """One contract line, with what has been drawn against it."""

    id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    uom_id: UUID | None
    rate: Decimal
    discount_percent: Decimal
    contracted_quantity: Decimal | None
    #: Summed from approved, uncancelled order lines on every read.
    drawn_quantity: Decimal
    #: Contracted less drawn, never below zero; null with no quantity agreed.
    remaining_quantity: Decimal | None
    notes: str | None


class RateContractResponse(RateContractSchema):
    """One rate contract and its lines."""

    id: UUID
    contract_number: str
    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    valid_from: date
    valid_to: date
    reference: str | None
    notes: str | None
    #: ``DRAFT``, ``ACTIVE``, ``EXPIRED`` (active, past ``valid_to``; derived),
    #: ``CLOSED`` or ``CANCELLED``.
    status: str
    approved_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    version: int
    lines: list[RateContractLineResponse]


class RateContractReleaseResponse(RateContractSchema):
    """One purchase order line drawing on the contract."""

    purchase_order_id: UUID
    po_number: str
    purchase_date: date
    order_status: str
    #: Whether the line counts in the drawn quantity: the order is approved
    #: or later and not cancelled.
    counts_as_drawn: bool
    purchase_order_line_id: UUID
    line_number: int
    rate_contract_line_id: UUID
    product_id: UUID
    ordered_quantity: Decimal
    unit_price: Decimal
