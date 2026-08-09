"""Enterprise UOM, conversion, and packaging persistence models."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Uom(BaseEntity):
    """Define one reusable unit of measure."""

    __tablename__ = "uoms"
    __table_args__ = (
        UniqueConstraint("code", name="UQ_uoms_code"),
        Index("IX_uoms_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(30))
    dimension: Mapped[str] = mapped_column(
        String(30), nullable=False, default="COUNT", server_default="COUNT"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    is_decimal_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class UomGroup(BaseEntity):
    """Group related UOMs for conversions and product assignment."""

    __tablename__ = "uom_groups"
    __table_args__ = (
        UniqueConstraint("code", name="UQ_uom_groups_code"),
        Index("IX_uom_groups_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )


class UomGroupUnit(BaseEntity):
    """Map UOMs into UOM groups with base-unit selection."""

    __tablename__ = "uom_group_units"
    __table_args__ = (
        UniqueConstraint("uom_group_id", "uom_id", name="UQ_uom_group_units_group_uom"),
        Index("IX_uom_group_units_group", "uom_group_id"),
    )

    uom_group_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("uom_groups.id", ondelete="RESTRICT"), nullable=False
    )
    uom_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"), nullable=False
    )
    is_base: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    display_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )


class PackagingType(BaseEntity):
    """Define one packaging type token (box/carton/pallet/etc.)."""

    __tablename__ = "packaging_types"
    __table_args__ = (
        UniqueConstraint("code", name="UQ_packaging_types_code"),
        Index("IX_packaging_types_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )


class ConversionRule(BaseEntity):
    """Versioned UOM conversion rule with historical effectivity."""

    __tablename__ = "uom_conversion_rules"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "product_id",
            "from_uom_id",
            "to_uom_id",
            "version",
            name="UQ_uom_conversion_rules_unique_version",
        ),
        Index("IX_uom_conversion_rules_firm", "firm_id"),
        Index("IX_uom_conversion_rules_product", "product_id"),
        Index("IX_uom_conversion_rules_effective", "effective_from", "effective_to"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    product_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT")
    )
    from_uom_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_uom_conversion_rules_from_uoms", ondelete="RESTRICT"),
        nullable=False,
    )
    to_uom_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_uom_conversion_rules_to_uoms", ondelete="RESTRICT"),
        nullable=False,
    )
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    rounding_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="HALF_UP", server_default="HALF_UP"
    )
    precision_scale: Mapped[int] = mapped_column(
        nullable=False, default=4, server_default="4"
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    reason: Mapped[str | None] = mapped_column(Text)


class BusinessProfileUomDefault(BaseEntity):
    """Default UOM behavior by business profile (and optional firm override)."""

    __tablename__ = "business_profile_uom_defaults"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "business_profile_id",
            name="UQ_business_profile_uom_defaults_firm_profile",
        ),
        Index("IX_business_profile_uom_defaults_profile", "business_profile_id"),
    )

    firm_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), index=True
    )
    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    base_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_business_profile_uom_defaults_base_uoms", ondelete="RESTRICT"),
    )
    inventory_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_business_profile_uom_defaults_inventory_uoms",
            ondelete="RESTRICT",
        ),
    )
    purchase_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_business_profile_uom_defaults_purchase_uoms",
            ondelete="RESTRICT",
        ),
    )
    sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_business_profile_uom_defaults_sales_uoms",
            ondelete="RESTRICT",
        ),
    )
    allow_fraction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_decimal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class IndustryTemplate(BaseEntity):
    """Store reusable industry UOM/packaging templates."""

    __tablename__ = "uom_industry_templates"
    __table_args__ = (
        UniqueConstraint("code", name="UQ_uom_industry_templates_code"),
        Index("IX_uom_industry_templates_industry", "industry_type"),
        Index("IX_uom_industry_templates_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    industry_type: Mapped[str] = mapped_column(String(60), nullable=False)
    template_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class ProductUomConfig(BaseEntity):
    """Store extended per-product UOM and physical configuration."""

    __tablename__ = "product_uom_configs"
    __table_args__ = (
        UniqueConstraint("firm_id", "product_id", name="UQ_product_uom_configs_firm_product"),
        Index("IX_product_uom_configs_firm_product", "firm_id", "product_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    base_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_product_uom_configs_base_uoms", ondelete="RESTRICT"),
    )
    inventory_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_product_uom_configs_inventory_uoms", ondelete="RESTRICT"),
    )
    purchase_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_product_uom_configs_purchase_uoms", ondelete="RESTRICT"),
    )
    sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_product_uom_configs_sales_uoms", ondelete="RESTRICT"),
    )
    default_receiving_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_product_uom_configs_default_receiving_uoms",
            ondelete="RESTRICT",
        ),
    )
    default_dispatch_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_product_uom_configs_default_dispatch_uoms",
            ondelete="RESTRICT",
        ),
    )
    minimum_sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_product_uom_configs_minimum_sales_uoms",
            ondelete="RESTRICT",
        ),
    )
    allow_fraction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_decimal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    length: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    width: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    height: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))


class ProductPackagingLevel(BaseEntity):
    """Store unlimited product packaging hierarchy levels."""

    __tablename__ = "product_packaging_levels"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "product_id",
            "level_name",
            name="UQ_product_packaging_levels_product_level_name",
        ),
        Index("IX_product_packaging_levels_product", "firm_id", "product_id"),
        Index("IX_product_packaging_levels_parent", "parent_level_id"),
        Index("IX_product_packaging_levels_barcode", "barcode"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    parent_level_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("product_packaging_levels.id", ondelete="RESTRICT")
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
    )
    uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    level_name: Mapped[str] = mapped_column(String(120), nullable=False)
    conversion_to_base_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, default=Decimal("1"), server_default="1"
    )
    barcode: Mapped[str | None] = mapped_column(String(120))
    qr_code: Mapped[str | None] = mapped_column(String(300))
    gtin: Mapped[str | None] = mapped_column(String(30))
    ean: Mapped[str | None] = mapped_column(String(30))
    upc: Mapped[str | None] = mapped_column(String(30))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    length: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    width: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    height: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    display_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
