"""SQLAlchemy models for the multi-industry business profile framework."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
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


class AttributeDefinition(BaseEntity):
    """Define reusable product-extension attributes for future modules."""

    __tablename__ = "attribute_definitions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
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
