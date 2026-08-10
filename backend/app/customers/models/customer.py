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
    area: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(24), nullable=False)
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
