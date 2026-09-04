"""Request and response models for proforma invoices."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProformaSchema(BaseModel):
    """Shared configuration for every proforma payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ProformaStatusEnum(StrEnum):
    """Where a proforma stands."""

    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"


class ProformaCreate(ProformaSchema):
    """Raise a proforma from an approved sales order.

    The lines are not sent: they are snapshotted from the order, which is the
    whole point of the document. A caller that could name its own lines could
    state a price the order never agreed, and the customer would be paying
    against a figure nothing backs.
    """

    sales_order_id: UUID
    proforma_date: date
    valid_until: date | None = None
    proforma_number: str | None = Field(default=None, max_length=60)
    customer_reference: str | None = Field(default=None, max_length=80)
    payment_terms: str | None = Field(default=None, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=200)
    remarks: str | None = None
    #: The proforma this one replaces, where it is a revision.
    supersedes_id: UUID | None = None


class ProformaUpdate(ProformaSchema):
    """Amend a draft proforma.

    Every field is optional and the service dumps with ``exclude_unset``, so an
    omitted field means *leave it alone* -- a write model that dumps in full
    turns an omission into an instruction, which has shipped in this repo often
    enough to be a rule.

    The lines and the order are not among them: re-stating the deal means
    raising a new proforma against a corrected order, not editing the
    statement.
    """

    proforma_date: date | None = None
    valid_until: date | None = None
    customer_reference: str | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    remarks: str | None = None


class ProformaLineResponse(ProformaSchema):
    """One line of a proforma, as it was snapshotted."""

    id: UUID
    line_number: int
    product_id: UUID
    product_code: str | None = None
    product_name: str | None = None
    description: str | None = None
    quantity: Decimal
    free_quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    bill_discount_amount: Decimal
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal


class ProformaResponse(ProformaSchema):
    """A proforma and everything it states."""

    id: UUID
    proforma_number: str
    proforma_date: date
    valid_until: date | None = None
    status: ProformaStatusEnum
    customer_id: UUID
    customer_name: str | None = None
    branch_id: UUID
    sales_order_id: UUID
    sales_order_number: str | None = None
    customer_reference: str | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    currency_code: str | None = None
    remarks: str | None = None
    line_discount_total: Decimal
    bill_discount_amount: Decimal
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    issued_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    supersedes_id: UUID | None = None
    #: Said on the document rather than left to be known. A proforma is not a
    #: tax invoice: no input credit can be claimed against it and no tax is
    #: payable on it, and a customer's accounts clerk holding a printout has
    #: no other way to tell.
    is_tax_invoice: bool = False
    lines: list[ProformaLineResponse] = Field(default_factory=list)
    version: int = 0


class ProformaCancel(ProformaSchema):
    """Withdraw a proforma, saying why."""

    reason: str = Field(min_length=1, max_length=500)


class ProformaRegisterRecord(ProformaSchema):
    """One proforma, as the register lists it."""

    proforma_id: UUID
    proforma_number: str
    proforma_date: date
    valid_until: date | None
    customer_id: UUID
    customer_name: str
    sales_order_id: UUID
    sales_order_number: str
    grand_total: Decimal
    status: ProformaStatusEnum


class ProformaOutstandingRecord(ProformaSchema):
    """An issued proforma the customer is still arranging payment against.

    Superseded ones are left out: a revision replaced them, and a buyer
    holding two figures for one order is the confusion the `supersedes_id`
    chain exists to prevent.

    `days_to_expiry` goes negative once the stated prices have run out --
    reported rather than filtered away, because a figure somebody is still
    acting on is exactly the one worth knowing has lapsed.
    """

    proforma_id: UUID
    proforma_number: str
    proforma_date: date
    valid_until: date | None
    days_to_expiry: int | None
    customer_id: UUID
    customer_name: str
    sales_order_number: str
    grand_total: Decimal
