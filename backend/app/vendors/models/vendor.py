"""Firm-scoped vendor and child persistence models."""

from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.business.models import AttributeEntityType, AttributeValueBase
from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class VendorCategory(BaseEntity):
    """Persist a reusable vendor category per firm."""

    __tablename__ = "vendor_categories"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_vendor_categories_firm_code"),
        UniqueConstraint("firm_id", "name", name="UQ_vendor_categories_firm_name"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class VendorType(BaseEntity):
    """Persist a reusable vendor type per firm."""

    __tablename__ = "vendor_types"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_vendor_types_firm_code"),
        UniqueConstraint("firm_id", "name", name="UQ_vendor_types_firm_name"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Vendor(BaseEntity):
    """Represent one vendor master owned by a firm."""

    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_vendors_firm_code"),
        UniqueConstraint("firm_id", "gstin", name="UQ_vendors_firm_gstin"),
        Index("IX_vendors_firm_name", "firm_id", "name"),
        Index("IX_vendors_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendor_categories.id", ondelete="RESTRICT")
    )
    type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendor_types.id", ondelete="RESTRICT")
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    gst_registration: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    gstin: Mapped[str | None] = mapped_column(String(32))
    pan: Mapped[str | None] = mapped_column(String(32))
    license_number: Mapped[str | None] = mapped_column(String(64))
    registration_number: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(20))
    mobile: Mapped[str | None] = mapped_column(String(20))
    remarks: Mapped[str | None] = mapped_column(Text)
    business_attributes: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    contacts: Mapped[list["VendorContact"]] = relationship(
        back_populates="vendor",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Vendor.id == VendorContact.vendor_id,
            VendorContact.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="VendorContact.created_at",
    )
    addresses: Mapped[list["VendorAddress"]] = relationship(
        back_populates="vendor",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Vendor.id == VendorAddress.vendor_id,
            VendorAddress.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="VendorAddress.created_at",
    )
    bank_accounts: Mapped[list["VendorBankAccount"]] = relationship(
        back_populates="vendor",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Vendor.id == VendorBankAccount.vendor_id,
            VendorBankAccount.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="VendorBankAccount.created_at",
    )
    tax_details: Mapped[list["VendorTaxDetail"]] = relationship(
        back_populates="vendor",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Vendor.id == VendorTaxDetail.vendor_id,
            VendorTaxDetail.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="VendorTaxDetail.created_at",
    )
    notes: Mapped[list["VendorNote"]] = relationship(
        back_populates="vendor",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Vendor.id == VendorNote.vendor_id,
            VendorNote.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="VendorNote.created_at",
    )
    attachments: Mapped[list["VendorAttachment"]] = relationship(
        back_populates="vendor",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Vendor.id == VendorAttachment.vendor_id,
            VendorAttachment.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="VendorAttachment.created_at",
    )


class VendorContact(BaseEntity):
    """Represent one vendor contact person."""

    __tablename__ = "vendor_contacts"

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100))
    designation: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    mobile: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    vendor: Mapped[Vendor] = relationship(back_populates="contacts")


class VendorAddress(BaseEntity):
    """Represent one vendor address referencing geo masters."""

    __tablename__ = "vendor_addresses"
    __table_args__ = (Index("IX_vendor_addresses_vendor_city", "vendor_id", "city_id"),)

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    address_type: Mapped[str] = mapped_column(String(20), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(250), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(250))
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
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    vendor: Mapped[Vendor] = relationship(back_populates="addresses")


class VendorBankAccount(BaseEntity):
    """Represent one vendor bank account."""

    __tablename__ = "vendor_bank_accounts"
    __table_args__ = (
        Index("IX_vendor_bank_accounts_vendor_primary", "vendor_id", "is_primary"),
    )

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False)
    ifsc: Mapped[str | None] = mapped_column(String(16))
    branch: Mapped[str | None] = mapped_column(String(120))
    upi_id: Mapped[str | None] = mapped_column(String(120))
    swift_code: Mapped[str | None] = mapped_column(String(16))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    vendor: Mapped[Vendor] = relationship(back_populates="bank_accounts")


class VendorTaxDetail(BaseEntity):
    """Represent one vendor tax detail set."""

    __tablename__ = "vendor_tax_details"
    __table_args__ = (
        Index("IX_vendor_tax_details_vendor_primary", "vendor_id", "is_primary"),
    )

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    gstin: Mapped[str | None] = mapped_column(String(32))
    pan: Mapped[str | None] = mapped_column(String(32))
    tan: Mapped[str | None] = mapped_column(String(32))
    fssai: Mapped[str | None] = mapped_column(String(32))
    drug_license: Mapped[str | None] = mapped_column(String(64))
    import_export_code: Mapped[str | None] = mapped_column(String(32))
    extra_fields: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    vendor: Mapped[Vendor] = relationship(back_populates="tax_details")


class VendorAttachment(BaseEntity):
    """Represent one vendor attachment metadata row."""

    __tablename__ = "vendor_attachments"

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    vendor: Mapped[Vendor] = relationship(back_populates="attachments")


class VendorNote(BaseEntity):
    """Represent one vendor note/history item."""

    __tablename__ = "vendor_notes"

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="GENERAL", server_default="GENERAL"
    )

    vendor: Mapped[Vendor] = relationship(back_populates="notes")


class VendorAttributeValue(AttributeValueBase):
    """Store one configurable attribute value for a vendor."""

    __tablename__ = "vendor_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "vendor_id",
            "attribute_definition_id",
            name="UQ_vendor_attribute_values_owner_attribute",
        ),
        Index("IX_vendor_attribute_values_firm_text", "firm_id", "value_text"),
        Index("IX_vendor_attribute_values_firm_number", "firm_id", "value_number"),
        Index("IX_vendor_attribute_values_firm_date", "firm_id", "value_date"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.VENDOR
    OWNER_COLUMN: ClassVar[str] = "vendor_id"

    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
