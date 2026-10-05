"""Validated request and response contracts for customer management."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.core.validation import normalize_tan, validate_email, validate_phone
from app.customers.gst_registration import GstRegistrationType


class CustomerType(StrEnum):
    """Supported customer legal classifications."""

    INDIVIDUAL = "INDIVIDUAL"
    BUSINESS = "BUSINESS"


class CustomerStatus(StrEnum):
    """Supported customer lifecycle statuses."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ON_HOLD = "ON_HOLD"
    #: A new outlet waiting for the office (SEL-15): takes quotations and
    #: orders, is not billed until somebody with CUSTOMER_APPROVE approves it.
    PENDING = "PENDING"


class CustomerReceivableTransactionType(StrEnum):
    """Supported receivable transaction categories."""

    OPENING_BALANCE = "OPENING_BALANCE"
    #: One bill the customer owed at cutover (`CustomerOpeningBill`). Its own
    #: type rather than OPENING_BALANCE because that one is the master's single
    #: figure and is rewritten whole when the figure is revised -- the rows
    #: of that type are deleted and their journals mirrored -- which must never
    #: touch a bill. System-managed like OPENING_BALANCE.
    OPENING_BILL = "OPENING_BILL"
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"
    ADVANCE_RECEIPT = "ADVANCE_RECEIPT"
    ADVANCE_APPLY = "ADVANCE_APPLY"
    CREDIT_NOTE = "CREDIT_NOTE"
    #: More charged on an invoice after it was billed (backlog 77 row 5). It
    #: raises what the customer owes exactly as the invoice did.
    DEBIT_NOTE = "DEBIT_NOTE"
    REFUND = "REFUND"
    #: Tax collected at source on a receipt. It raises what the buyer owes,
    #: the same shape as an invoice, because the buyer owes it **on top of**
    #: the money they have just paid -- taking it out of that money would
    #: leave the firm short by the tax on every collection.
    TCS = "TCS"
    #: What the firm charged the customer for a cheque of theirs that
    #: bounced (ACC-2). Owed on top, like TCS, and outside GST.
    CHEQUE_RETURN_CHARGE = "CHEQUE_RETURN_CHARGE"
    #: Loyalty credit spent against a bill. It reduces what the customer owes
    #: exactly as a receipt does -- the firm has been paid, in credit it
    #: already owed rather than in cash. Its own type rather than RECEIPT
    #: because a statement saying "receipt" for points spent tells the reader
    #: money arrived when none did.
    LOYALTY = "LOYALTY"
    #: A debt the firm has given up collecting -- a party adjustment's
    #: write-off (backlog 74 row 2). It reduces what the customer owes as a
    #: receipt does, without money, and its journal debits bad debts.
    WRITE_OFF = "WRITE_OFF"
    #: What the customer owes settled by what the firm owes the same business
    #: as a supplier -- a party adjustment's set-off. Its journal debits the
    #: payable rather than cash.
    SET_OFF = "SET_OFF"
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
    tan_number: str | None = Field(default=None, max_length=10)
    #: How the buyer stands under GST; blank is read off the GSTIN.
    gst_registration_type: GstRegistrationType | None = None
    #: The account manager, a member of the firm; blank leaves documents to
    #: the territory's salesperson (backlog 67 row 2).
    salesman_id: UUID | None = None
    #: Who collects this customer's dues, a member of the firm (SG-8); blank
    #: leaves collection to the account manager.
    collector_id: UUID | None = None
    #: The price level the customer buys at (SEL-9); blank takes the group's.
    price_level_id: UUID | None = None
    #: Percent off a bill paid within the days of its date (SEL-14); blank
    #: days take the firm's terms, zero days refuse them.
    cash_discount_days: int | None = Field(default=None, ge=0, le=365)
    cash_discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    #: The same business as a supplier (ACC-11): one combined statement, and
    #: a set-off between the two preselected.
    linked_vendor_id: UUID | None = None
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
    #: Messaging (backlog 51): no payment reminders to this customer.
    no_reminders: bool = False
    #: Days of shelf life goods must have left on reaching this customer
    #: (backlog 79 row 6). Needs the firm's EXPIRY_TRACKING feature.
    minimum_shelf_life_days: int | None = Field(default=None, ge=1, le=3650)
    #: Which batch trade rate this buyer takes (PG-14): RETAILER the price to
    #: retailer, STOCKIST the price to stockist; blank or OTHER neither.
    trade_class: Literal["RETAILER", "STOCKIST", "OTHER"] | None = None
    #: Tried first when an event offers it; blank follows the firm's order.
    preferred_channel: Literal["EMAIL", "WHATSAPP", "SMS"] | None = None
    #: The customer agreed to WhatsApp messages. The server records when.
    whatsapp_opt_in: bool = False
    addresses: list[CustomerAddressInput] = Field(default_factory=list, max_length=50)
    contacts: list[CustomerContactInput] = Field(default_factory=list, max_length=50)
    #: The customer's custom fields, as the business profile defines them.
    #: Replaced whole when sent; an update that omits them leaves them alone.
    attributes: list[AttributeValueInput] = Field(default_factory=list, max_length=300)

    @field_validator("code", "gst_number", "pan_number", "currency_code", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str | None) -> str | None:
        """Normalize optional and required business identifiers."""
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("tan_number", mode="before")
    @classmethod
    def _tan(cls, value: str | None) -> str | None:
        """Check a TAN's format; a blank one is no TAN."""
        return normalize_tan(value)

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

    #: Blank takes the next code from the firm's series (MST-5).
    code: str | None = Field(  # type: ignore[assignment]
        default=None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$"
    )


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
    tan_number: str | None = None
    gst_registration_type: str | None = None
    salesman_id: UUID | None = None
    collector_id: UUID | None = None
    price_level_id: UUID | None = None
    cash_discount_days: int | None = None
    cash_discount_percent: Decimal | None = None
    linked_vendor_id: UUID | None = None
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
    no_reminders: bool = False
    #: The firm's built-in walk-in customer (SG-2); never writable.
    is_cash_sale: bool = False
    minimum_shelf_life_days: int | None = None
    trade_class: str | None = None
    preferred_channel: str | None = None
    whatsapp_opt_in: bool = False
    whatsapp_opt_in_at: datetime | None = None
    created_by: UUID | None
    created_at: datetime
    updated_by: UUID | None
    updated_at: datetime
    is_deleted: bool
    deleted_at: datetime | None
    addresses: list[CustomerAddressResponse]
    contacts: list[CustomerContactResponse]
    attributes: list[AttributeValueResponse] = Field(default_factory=list)


class CustomerIdentityHolder(CustomerSchema):
    """Another live customer holding the same GSTIN or PAN (decision A7)."""

    id: UUID
    code: str
    name: str
    gst_number: str | None = None
    pan_number: str | None = None


class CustomerIdentityCheck(CustomerSchema):
    """Who else holds a GSTIN or PAN, asked before a save (decision A7).

    A repeat is allowed -- one company is often several accounts -- so this
    warns rather than refuses; ``message`` is the sentence to show.
    """

    holders: list[CustomerIdentityHolder]
    message: str | None = None


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
    #: The firm's cash discount terms and overdue interest (SEL-14).
    cash_discount_days: int | None = None
    cash_discount_percent: Decimal | None = None
    overdue_interest_rate: Decimal = Decimal("0")
    interest_grace_days: int = 0
    is_configured: bool


class CreditControlSettingsWrite(CustomerSchema):
    """Replace the firm's credit policy."""

    enforcement: CreditEnforcement
    warn_at_percent: Decimal = Field(ge=Decimal("1"), le=Decimal("500"))
    block_at_percent: Decimal = Field(ge=Decimal("1"), le=Decimal("500"))
    #: Absent keeps the firm's own (SEL-14), as do the three below. Sent with
    #: null days, the firm offers no cash discount.
    cash_discount_days: int | None = Field(default=None, ge=0, le=365)
    cash_discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    overdue_interest_rate: Decimal | None = Field(
        default=None, ge=0, le=60, max_digits=7, decimal_places=4
    )
    interest_grace_days: int | None = Field(default=None, ge=0, le=365)

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
    #: The price level everyone in the segment buys at (SEL-9).
    price_level_id: UUID | None = None
    is_active: bool = True


class CustomerGroupResponse(CustomerSchema):
    """Expose one stored customer segment."""

    id: UUID
    code: str
    name: str
    description: str | None
    default_discount_percent: Decimal
    price_level_id: UUID | None = None
    is_active: bool
    version: int
