"""SQLAlchemy models for the multi-industry business profile framework."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar, cast
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class BusinessProfile(BaseEntity):
    """Define one industry/business operating profile."""

    __tablename__ = "business_profiles"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    industry_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    default_settings: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class BusinessFeature(BaseEntity):
    """Define one configurable framework feature flag."""

    __tablename__ = "business_features"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    default_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Whether anything in the codebase actually implements this feature.
    #:
    #: Distinct from ``is_active``, which is a choice an administrator makes.
    #: This is a statement of fact: seven catalogue entries -- IMEI,
    #: PRESCRIPTION_REQUIRED, RECIPE_MANAGEMENT, KITCHEN_MANAGEMENT,
    #: COMMISSION, SERVICE_CONTRACTS and PROJECT_MANAGEMENT -- had no backing
    #: code in either application, so enabling one promised a customer
    #: something that could never happen. They stay in the catalogue as
    #: roadmap, and this flag stops them being switched on.
    is_implemented: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class BusinessModule(BaseEntity):
    """Define one configurable module in the ERP workspace."""

    __tablename__ = "business_modules"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ui_route: Mapped[str | None] = mapped_column(String(100))
    default_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ProfileFeature(BaseEntity):
    """Store per-profile feature enablement and optional configuration."""

    __tablename__ = "profile_features"
    __table_args__ = (UniqueConstraint("business_profile_id", "feature_id"),)

    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id"), nullable=False
    )
    feature_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_features.id"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSON)


class ProfileModule(BaseEntity):
    """Store per-profile module visibility and workflow configuration."""

    __tablename__ = "profile_modules"
    __table_args__ = (UniqueConstraint("business_profile_id", "module_id"),)

    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id"), nullable=False
    )
    module_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_modules.id"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSON)


class AttributeEntityType(StrEnum):
    """Name the records a custom attribute can extend.

    Adding a member here plus a call to ``AttributeService`` is all a module
    needs to gain configurable fields; no schema change is required.
    """

    PRODUCT = "PRODUCT"
    CUSTOMER = "CUSTOMER"
    VENDOR = "VENDOR"
    BRANCH = "BRANCH"
    WAREHOUSE = "WAREHOUSE"


class AttributeDataType(StrEnum):
    """Supported value types for a custom attribute."""

    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"


class AttributeDefinition(BaseEntity):
    """Define one configurable field that extends a record for some industry.

    A definition is scoped by ``entity_type`` (which record it extends) and
    optionally by ``applicable_business_profile_id`` (which industries see it),
    so a pharmacy firm can carry a drug-licence field that a food firm does not.
    """

    __tablename__ = "attribute_definitions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=AttributeEntityType.PRODUCT.value,
        server_default=AttributeEntityType.PRODUCT.value,
        index=True,
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    default_value: Mapped[str | None] = mapped_column(Text)
    validation_rule: Mapped[dict[str, object] | None] = mapped_column(JSON)
    applicable_category: Mapped[str | None] = mapped_column(String(100))
    applicable_business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class CategoryAttributeRule(BaseEntity):
    """Define category-scoped mandatory-attribute rules by business profile."""

    __tablename__ = "category_attribute_rules"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "category_code",
            "attribute_definition_id",
        ),
    )

    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id")
    )
    category_code: Mapped[str] = mapped_column(String(100), nullable=False)
    attribute_definition_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("attribute_definitions.id"), nullable=False
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    validation_override: Mapped[dict[str, object] | None] = mapped_column(JSON)


class FirmBusinessProfile(BaseEntity):
    """Assign exactly one active business profile to a firm."""

    __tablename__ = "firm_business_profiles"
    __table_args__ = (UniqueConstraint("firm_id"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False
    )
    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class AttributeValueBase(BaseEntity):
    """Shared columns for a module's custom attribute values.

    Each module owns a small concrete table (``product_attribute_values``,
    ``customer_attribute_values``, …) so the value carries a real foreign key to
    its record and gets its own indexes. The behaviour stays generic:
    ``AttributeService`` is parameterised by the model, so there is still one
    implementation, one set of tests, and one form renderer.

    Values live in typed columns rather than a serialized blob so that list
    filters and reports can index and query them.
    """

    __abstract__ = True

    #: Which catalogue entries apply to this table.
    ENTITY_TYPE: ClassVar[AttributeEntityType]
    #: Name of the foreign-key column pointing at the owning record.
    OWNER_COLUMN: ClassVar[str]

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    attribute_definition_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("attribute_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    value_date: Mapped[date | None] = mapped_column(Date)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)

    @classmethod
    def owner_column(cls) -> Mapped[UUID]:
        """Return the mapped foreign-key column pointing at the owning record."""
        return cast("Mapped[UUID]", getattr(cls, cls.OWNER_COLUMN))
