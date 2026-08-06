"""Firm-scoped product, category, and dynamic-attribute persistence models."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ProductCategory(BaseEntity):
    """Represent a hierarchical firm category tree for products."""

    __tablename__ = "product_categories"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_product_categories_firm_code"),
        UniqueConstraint(
            "firm_id",
            "name",
            "parent_id",
            name="UQ_product_categories_firm_name_parent",
        ),
        Index("IX_product_categories_firm_parent", "firm_id", "parent_id"),
        Index("IX_product_categories_firm_path", "firm_id", "path"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("product_categories.id", ondelete="RESTRICT")
    )
    level: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    children: Mapped[list["ProductCategory"]] = relationship(
        back_populates="parent",
        cascade="save-update, merge",
    )
    parent: Mapped["ProductCategory | None"] = relationship(
        back_populates="children",
        remote_side="ProductCategory.id",
    )


class Product(BaseEntity):
    """Represent one configurable product core master row."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_products_firm_code"),
        Index("IX_products_firm_name", "firm_id", "name"),
        Index("IX_products_firm_status", "firm_id", "status"),
        Index("IX_products_firm_barcode", "firm_id", "barcode"),
        Index("IX_products_firm_qr_code", "firm_id", "qr_code"),
        Index("IX_products_firm_tax_group_code", "firm_id", "tax_profile_group_code"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(120))
    qr_code: Mapped[str | None] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(String(30), nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("product_categories.id", ondelete="RESTRICT")
    )
    sub_category_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("product_categories.id", ondelete="RESTRICT")
    )
    unit: Mapped[str | None] = mapped_column(String(20))
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    tax_profile_group_code: Mapped[str | None] = mapped_column(String(50), index=True)
    base_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_products_base_uoms", ondelete="RESTRICT"),
        index=True,
    )
    inventory_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_products_inventory_uoms", ondelete="RESTRICT"),
    )
    purchase_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_products_purchase_uoms", ondelete="RESTRICT"),
    )
    sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_products_sales_uoms", ondelete="RESTRICT"),
    )
    default_receiving_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_products_default_receiving_uoms",
            ondelete="RESTRICT",
        ),
    )
    default_dispatch_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "uoms.id",
            name="FK_products_default_dispatch_uoms",
            ondelete="RESTRICT",
        ),
    )
    minimum_sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_products_minimum_sales_uoms", ondelete="RESTRICT"),
    )
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    length: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    width: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    height: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    allow_fraction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_decimal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
    track_batch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    track_lot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    track_serial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    track_expiry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    track_manufacturing_date: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    track_warranty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    require_batch_on_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    require_batch_on_issue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    require_serial_on_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    require_serial_on_issue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    attributes: Mapped[list["ProductAttributeValue"]] = relationship(
        back_populates="product",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Product.id == ProductAttributeValue.product_id,
            ProductAttributeValue.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="ProductAttributeValue.created_at",
    )
    media: Mapped[list["ProductMedia"]] = relationship(
        back_populates="product",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Product.id == ProductMedia.product_id,
            ProductMedia.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="ProductMedia.created_at",
    )


class ProductAttributeValue(BaseEntity):
    """Store one dynamic attribute value assigned to a product."""

    __tablename__ = "product_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "attribute_definition_id",
            name="UQ_product_attribute_values_product_attribute",
        ),
        Index("IX_product_attribute_values_firm_text", "firm_id", "value_text"),
        Index("IX_product_attribute_values_firm_number", "firm_id", "value_number"),
        Index("IX_product_attribute_values_firm_date", "firm_id", "value_date"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attribute_definition_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("attribute_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    value_date: Mapped[date | None] = mapped_column(Date)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)

    product: Mapped[Product] = relationship(back_populates="attributes")


class ProductMedia(BaseEntity):
    """Store product images, attachments, and reference documents."""

    __tablename__ = "product_media"
    __table_args__ = (
        Index("IX_product_media_firm_kind", "firm_id", "media_kind"),
        Index("IX_product_media_product_primary", "product_id", "is_primary"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    media_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    file_size_bytes: Mapped[int | None] = mapped_column()

    product: Mapped[Product] = relationship(back_populates="media")
