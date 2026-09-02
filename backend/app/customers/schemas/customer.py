"""Validated request and response contracts for customer management."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import validate_email, validate_phone


class CustomerType(StrEnum):
    """Supported customer legal classifications."""

    INDIVIDUAL = "INDIVIDUAL"
    BUSINESS = "BUSINESS"


class CustomerStatus(StrEnum):
    """Supported customer lifecycle statuses."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ON_HOLD = "ON_HOLD"


class CustomerReceivableTransactionType(StrEnum):
    """Supported receivable transaction categories."""

    OPENING_BALANCE = "OPENING_BALANCE"
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"
    ADVANCE_RECEIPT = "ADVANCE_RECEIPT"
    ADVANCE_APPLY = "ADVANCE_APPLY"
    CREDIT_NOTE = "CREDIT_NOTE"
    REFUND = "REFUND"
    #: Undoes an earlier transaction by its exact deltas. It is not a category
    #: of business event -- it is the record of one being taken back -- so it
    #: carries no rule of its own and cannot be posted directly.
    REVERSAL = "REVERSAL"


class AddressType(StrEnum):
    """Supported customer address classifications."""

    BILLING = "BILLING"
    SHIPPING = "SHIPPING"
    OFFICE = "OFFICE"
    HOME = "HOME"
    OTHER = "OTHER"


class CreditEnforcement(StrEnum):
    """What a firm wants to happen when a customer nears their limit."""

    OFF = "OFF"
    WARN = "WARN"
    BLOCK = "BLOCK"


class CreditStatus(StrEnum):
    """Where one document leaves a customer against their limit."""

    OK = "OK"
    WARNING = "WARNING"
    BREACH = "BREACH"


class CustomerSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CustomerAddressInput(CustomerSchema):
    """Create or replace one customer address."""

    id: UUID | None = None
    address_type: AddressType
    address_line1: str = Field(min_length=1, max_length=250)
    address_line2: str | None = Field(default=None, max_length=250)
    area: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=1, max_length=24)
    # Where the address is, in the shared geography masters. Optional: a firm
    # with no masters must still be able to record an address, and an older
    # client sends none of these. Where they are given the service derives the
    # text above from them, so the two cannot drift apart.
    country_id: UUID | None = None
    state_id: UUID | None = None
    district_id: UUID | None = None
    city_id: UUID | None = None
    postal_code_id: UUID | None = None
    locality_id: UUID | None = None
    is_default_billing: bool = False
    is_default_shipping: bool = False

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        """Normalize the country identifier."""
        return value.strip().upper()


class CustomerContactInput(CustomerSchema):
    """Create or replace one customer contact person."""

    id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    designation: str | None = Field(default=None, max_length=100)
    mobile: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    department: str | None = Field(default=None, max_length=100)
    is_primary: bool = False

    @field_validator("mobile")
    @classmethod
    def normalize_mobile(cls, value: str | None) -> str | None:
        """Validate an optional E.164 contact number."""
        return validate_phone(value) if value else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """Validate and normalize an optional email."""
        return validate_email(value) if value else None


class CustomerWrite(CustomerSchema):
    """Fields shared by create and complete update requests."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    customer_type: CustomerType
    #: The commercial segment this shop is in, if the firm groups them. Not
    #: the same question as `customer_type`, which is a legal classification.
    customer_group_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    gst_number: str | None = Field(default=None, max_length=32)
    pan_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=20)
    alternate_phone: str | None = Field(default=None, max_length=20)
    website: str | None = Field(default=None, max_length=500)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18)
    #: The standing discount a document line starts at. Overridable there.
    default_discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=9, decimal_places=4
    )
    opening_balance: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("-9999999999999999.99"),
        le=Decimal("9999999999999999.99"),
        max_digits=18,
    )
    payment_terms_days: int = Field(default=0, ge=0, le=3650)
    currency_code: str = Field(min_length=3, max_length=3)
    status: CustomerStatus = CustomerStatus.ACTIVE
    notes: str | None = None
    addresses: list[CustomerAddressInput] = Field(default_factory=list, max_length=50)
    contacts: list[CustomerContactInput] = Field(default_factory=list, max_length=50)

    @field_validator("code", "gst_number", "pan_number", "currency_code", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str | None) -> str | None:
        """Normalize optional and required business identifiers."""
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("name", "display_name", mode="before")
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        """Trim customer names before validation and persistence."""
        return value.strip() if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """Validate an optional primary email."""
        return validate_email(value) if value else None

    @field_validator("phone", "alternate_phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """Validate optional E.164 customer numbers."""
        return validate_phone(value) if value else None

    @model_validator(mode="after")
    def validate_nested_defaults(self) -> "CustomerWrite":
        """Ensure address and contact defaults remain unambiguous."""
        if sum(address.is_default_billing for address in self.addresses) > 1:
            raise ValueError("Only one default billing address is allowed.")
        if sum(address.is_default_shipping for address in self.addresses) > 1:
            raise ValueError("Only one default shipping address is allowed.")
        if sum(contact.is_primary for contact in self.contacts) > 1:
            raise ValueError("Only one primary contact is allowed.")
        return self


class CustomerCreate(CustomerWrite):
    """Create a customer and its initial child records."""


class CustomerUpdate(CustomerWrite):
    """Completely replace editable customer data and child records."""


class CustomerImportRequest(CustomerSchema):
    """Batch of validated customer records imported atomically."""

    records: list[CustomerCreate] = Field(min_length=1, max_length=1000)


class CustomerAddressResponse(CustomerAddressInput):
    """Expose one persisted customer address."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class CustomerContactResponse(CustomerContactInput):
    """Expose one persisted customer contact."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class CustomerResponse(CustomerSchema):
    """Expose a complete customer record."""

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    code: str
    customer_type: CustomerType
    customer_group_id: UUID | None
    name: str
    display_name: str
    gst_number: str | None
    pan_number: str | None
    email: str | None
    phone: str | None
    alternate_phone: str | None
    website: str | None
    credit_limit: Decimal
    default_discount_percent: Decimal
    opening_balance: Decimal
    payment_terms_days: int
    currency_code: str
    current_outstanding: Decimal
    unapplied_advance_balance: Decimal
    status: CustomerStatus
    notes: str | None
    created_by: UUID | None
    created_at: datetime
    updated_by: UUID | None
    updated_at: datetime
    is_deleted: bool
    deleted_at: datetime | None
    addresses: list[CustomerAddressResponse]
    contacts: list[CustomerContactResponse]


class CustomerSummary(CustomerSchema):
    """Expose aggregate customer counts and credit totals."""

    total: int
    active: int
    inactive: int
    on_hold: int
    deleted: int
    total_credit_limit: Decimal
    total_opening_balance: Decimal
    total_current_outstanding: Decimal
    total_unapplied_advance: Decimal


class CustomerListFilters(CustomerSchema):
    """Validated collection filters shared by routes and services."""

    status: CustomerStatus | None = None
    customer_type: CustomerType | None = None
    firm_id: UUID | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    created_from: date | None = None
    created_to: date | None = None
    include_deleted: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> "CustomerListFilters":
        """Reject inverted creation-date filters."""
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must not be after created_to.")
        return self


class CustomerReceivableTransactionCreate(CustomerSchema):
    """Create one customer receivable transaction entry."""

    transaction_type: CustomerReceivableTransactionType
    transaction_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reference_type: str | None = Field(default=None, max_length=40)
    reference_id: UUID | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None


class CustomerReceivableTransactionResponse(CustomerSchema):
    """Expose one customer receivable transaction."""

    id: UUID
    customer_id: UUID
    firm_id: UUID
    transaction_type: CustomerReceivableTransactionType
    transaction_date: date
    amount: Decimal
    outstanding_delta: Decimal
    advance_delta: Decimal
    outstanding_after: Decimal
    advance_after: Decimal
    reference_type: str | None
    reference_id: UUID | None
    reference_number: str | None
    #: The journal this movement posted, where it posted one. Null on the
    #: older paths through this table, which write no journal at all.
    journal_entry_id: UUID | None
    remarks: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerReceivableSummary(CustomerSchema):
    """Expose customer-level receivable and advance balances."""

    customer_id: UUID
    customer_name: str
    outstanding: Decimal
    unapplied_advance: Decimal
    net_position: Decimal


class CreditStatusResponse(CustomerSchema):
    """Report where one customer stands against their credit limit."""

    customer_id: UUID
    customer_name: str
    enforcement: CreditEnforcement
    status: CreditStatus
    limit: Decimal
    exposure: Decimal
    available: Decimal
    used_percent: Decimal
    warn_at_percent: Decimal
    block_at_percent: Decimal
    would_block: bool
    message: str | None


class CreditControlSettingsResponse(CustomerSchema):
    """Expose the firm's credit policy."""

    enforcement: CreditEnforcement
    warn_at_percent: Decimal
    block_at_percent: Decimal
    is_configured: bool


class CreditControlSettingsWrite(CustomerSchema):
    """Replace the firm's credit policy."""

    enforcement: CreditEnforcement
    warn_at_percent: Decimal = Field(ge=Decimal("1"), le=Decimal("500"))
    block_at_percent: Decimal = Field(ge=Decimal("1"), le=Decimal("500"))

    @model_validator(mode="after")
    def _warn_before_block(self) -> "CreditControlSettingsWrite":
        """Keep the warning ahead of the block.

        A warning threshold above the blocking one can never fire: the document
        is refused before it is ever reached, so the firm would believe it had
        a warning stage it does not have.
        """
        if self.warn_at_percent > self.block_at_percent:
            raise ValueError(
                "Warning threshold must not be above the blocking threshold."
            )
        return self


class CustomerGroupWrite(CustomerSchema):
    """Create or replace one customer segment."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    #: What everyone in the segment is normally given. Zero means no
    #: arrangement, matching how the customer's own standing rate reads.
    default_discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=9, decimal_places=4
    )
    is_active: bool = True


class CustomerGroupResponse(CustomerSchema):
    """Expose one stored customer segment."""

    id: UUID
    code: str
    name: str
    description: str | None
    default_discount_percent: Decimal
    is_active: bool
    version: int
