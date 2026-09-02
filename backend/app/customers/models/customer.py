"""Firm-scoped customer, receivable, address, and contact persistence models."""

from datetime import date
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.business.models import AttributeEntityType, AttributeValueBase
from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class CustomerGroup(BaseEntity):
    """A commercial segment a firm sells to: Retailer, Wholesaler, Institution.

    Distinct from `customers.customer_type`, which is INDIVIDUAL or BUSINESS --
    a legal classification, and the wrong thing to hang a price or an offer on.
    A firm that wants to give wholesalers a different rate needs a grouping of
    its own choosing, not a KYC field.

    One flat list rather than a hierarchy. A tree is what `sales_territories`
    already is, and a second one would leave two answers to "which group is
    this customer in" -- the mistake this codebase records as costing it four
    business-profile resolvers.
    """

    __tablename__ = "customer_groups"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_customer_groups_firm_code"),
        UniqueConstraint("firm_id", "name", name="UQ_customer_groups_firm_name"),
        Index("IX_customer_groups_firm_status", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: What everyone in this group is normally given off a line. Ranked below
    #: the customer's own standing rate, because a rate agreed with one shop is
    #: more specific than one agreed with a segment.
    default_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Customer(BaseEntity):
    """Represent one customer master owned by a firm."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_customers_firm_code"),
        UniqueConstraint("firm_id", "gst_number", name="UQ_customers_firm_gst_number"),
        UniqueConstraint("firm_id", "pan_number", name="UQ_customers_firm_pan_number"),
        Index("IX_customers_firm_name", "firm_id", "name"),
        Index("IX_customers_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The commercial segment this shop belongs to, if the firm groups them.
    #: Nullable because a firm that does not segment its customers should not
    #: be made to invent a group to hold all of them.
    customer_group_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customer_groups.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gst_number: Mapped[str | None] = mapped_column(String(32))
    pan_number: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(20))
    alternate_phone: Mapped[str | None] = mapped_column(String(20))
    website: Mapped[str | None] = mapped_column(String(500))
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: What this customer is normally given off a line, before anything is
    #: typed on a document. A standing arrangement rather than a one-off deal:
    #: whoever raises the document may override it freely, including down to
    #: nothing, and what they chose is what the line records.
    default_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    payment_terms_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    current_outstanding: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    unapplied_advance_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )

    addresses: Mapped[list["CustomerAddress"]] = relationship(
        back_populates="customer",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Customer.id == CustomerAddress.customer_id,
            CustomerAddress.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="CustomerAddress.created_at",
    )
    contacts: Mapped[list["CustomerContact"]] = relationship(
        back_populates="customer",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Customer.id == CustomerContact.customer_id,
            CustomerContact.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="CustomerContact.created_at",
    )


class CustomerAddress(BaseEntity):
    """Represent one reusable customer address."""

    __tablename__ = "customer_addresses"
    __table_args__ = (
        Index("IX_customer_addresses_customer_city", "customer_id", "city"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    address_type: Mapped[str] = mapped_column(String(20), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(250), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(250))
    # The free text is what this table has always held, and it stays: it is
    # NOT NULL, every report reads it, and a firm whose geography masters are
    # empty still has to be able to record an address. Where the keys below are
    # set the service derives it from them, so the two cannot disagree.
    area: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(24), nullable=False)
    # Where the address actually is, as ids into the shared geography masters.
    # Nullable, and nullable for good: these are added to a table with live
    # rows, an old client sends none of them, and a firm may have no masters.
    # Without them "Parrys" and "Parry's Corner" never group and a pin-code
    # search is a string match -- and there is nowhere to hang a coordinate.
    country_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT")
    )
    state_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_states.id", ondelete="RESTRICT")
    )
    district_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_districts.id", ondelete="RESTRICT")
    )
    city_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_cities.id", ondelete="RESTRICT")
    )
    postal_code_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_postal_codes.id", ondelete="RESTRICT")
    )
    locality_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_localities.id", ondelete="RESTRICT")
    )
    is_default_billing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_default_shipping: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    customer: Mapped[Customer] = relationship(back_populates="addresses")


class CustomerContact(BaseEntity):
    """Represent one customer contact person."""

    __tablename__ = "customer_contacts"

    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(100))
    mobile: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320))
    department: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class CustomerReceivableTransaction(BaseEntity):
    """Represent one immutable receivable movement for a customer."""

    __tablename__ = "customer_receivable_transactions"
    __table_args__ = (
        Index("IX_customer_ar_tx_customer_date", "customer_id", "transaction_date"),
        Index("IX_customer_ar_tx_firm_type", "firm_id", "transaction_type"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    outstanding_delta: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    advance_delta: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    outstanding_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    advance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: The journal this movement posted, where it posted one.
    #:
    #: An opening balance is the case that needs it: changing one has to
    #: mirror the entry the old figure wrote, and searching the ledger by
    #: source module would not tell an opening balance apart from the credit
    #: notes and refunds the same customer raises. Nullable because the older
    #: paths through this table still write no journal at all.
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)


class CreditControlSettings(BaseEntity):
    """Store one firm's credit-limit policy.

    ``credit_limit`` has been on every customer from the start and constrained
    nothing: it was snapshotted onto sales orders and never compared against
    anything. Whether a breach should warn or block is a firm's decision, not
    the platform's, so the policy lives here -- one row per firm, the shape
    ``tax_settings`` already uses.
    """

    __tablename__ = "credit_control_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_credit_control_settings_firm"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: OFF, WARN or BLOCK. WARN is the default: a limit that stops trade on the
    #: day it is switched on is a limit nobody switches on.
    enforcement: Mapped[str] = mapped_column(
        String(10), nullable=False, default="WARN", server_default="WARN"
    )
    #: Percentage of the limit at which a warning starts.
    warn_at_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("80"), server_default="80"
    )
    #: Percentage at which BLOCK refuses the document. Ignored under OFF and
    #: WARN, so lowering it cannot surprise a firm that has not opted in.
    block_at_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("100"), server_default="100"
    )


class CustomerAttributeValue(AttributeValueBase):
    """Store one configurable attribute value for a customer."""

    __tablename__ = "customer_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "attribute_definition_id",
            name="UQ_customer_attribute_values_owner_attribute",
        ),
        Index("IX_customer_attribute_values_firm_text", "firm_id", "value_text"),
        Index("IX_customer_attribute_values_firm_number", "firm_id", "value_number"),
        Index("IX_customer_attribute_values_firm_date", "firm_id", "value_date"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.CUSTOMER
    OWNER_COLUMN: ClassVar[str] = "customer_id"

    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
