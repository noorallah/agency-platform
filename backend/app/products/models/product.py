"""Firm-scoped product, category, and dynamic-attribute persistence models."""

from collections.abc import Iterable
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship
from sqlalchemy.orm.attributes import flag_modified

from app.business.models import AttributeEntityType, AttributeValueBase
from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ProductCategory(BaseEntity):
    """Represent a hierarchical firm category tree for products."""

    __tablename__ = "product_categories"
    __table_args__ = (
        Index(
            "UQ_product_categories_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "UQ_product_categories_firm_name_parent_active",
            "firm_id",
            "name",
            "parent_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
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
    #: Goods of this category wait in quarantine on receipt until passed
    #: (BUY-9).
    #: Expiry rules (STK-5), each overriding the firm's:
    #: stop selling this many days before expiry, alert this many days
    #: before, and send back to the supplier this many days before.
    expiry_stop_sale_days: Mapped[int | None] = mapped_column(Integer)
    expiry_alert_days: Mapped[int | None] = mapped_column(Integer)
    expiry_return_days: Mapped[int | None] = mapped_column(Integer)
    inspection_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: The goods type a new product filed here takes and stores (backlog
    #: 89). Null is General; a sub-category without one takes its parent's.
    #: Changing it reaches products created afterwards only.
    goods_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "goods_types.id",
            name="FK_product_categories_goods_type_id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    children: Mapped[list["ProductCategory"]] = relationship(
        back_populates="parent",
        cascade="save-update, merge",
    )
    #: The trade licences a buyer and seller must hold to trade what this
    #: category holds -- all Schedule H medicines, say (backlog 54). Every
    #: one is asked for (backlog 152); a sub-category naming none inherits
    #: its parent's.
    licence_requirements: Mapped[list["ProductCategoryLicenceRequirement"]] = (
        relationship(
            cascade="all, delete-orphan",
            lazy="selectin",
            order_by="ProductCategoryLicenceRequirement.position",
        )
    )

    @property
    def required_licence_type_ids(self) -> list[UUID]:
        """Return the licence types this category's goods need, in order."""
        return [row.licence_type_id for row in self.licence_requirements]

    @required_licence_type_ids.setter
    def required_licence_type_ids(self, licence_type_ids: Iterable[UUID]) -> None:
        """Replace the list, keeping the rows of the types that stay."""
        _replace_requirements(self, licence_type_ids, ProductCategoryLicenceRequirement)

    parent: Mapped["ProductCategory | None"] = relationship(
        back_populates="children",
        remote_side="ProductCategory.id",
    )


class Product(BaseEntity):
    """Represent one configurable product core master row."""

    __tablename__ = "products"
    __table_args__ = (
        Index(
            "UQ_products_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_products_firm_name", "firm_id", "name"),
        Index("IX_products_firm_status", "firm_id", "status"),
        Index("IX_products_firm_barcode", "firm_id", "barcode"),
        Index("IX_products_firm_qr_code", "firm_id", "qr_code"),
        Index("IX_products_firm_tax_group_code", "firm_id", "tax_profile_group_code"),
        Index("IX_products_firm_goods_type", "firm_id", "goods_type_id"),
        Index(
            "UQ_products_firm_barcode_active",
            "firm_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL AND is_deleted IS FALSE"),
            sqlite_where=text("barcode IS NOT NULL AND is_deleted = 0"),
        ),
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
    #: The goods type taken from the category when the product was filed
    #: there, and stored so a report by goods type reads this row alone
    #: (backlog 89). Null is General. Moving the product to another category
    #: is the only thing that changes it.
    goods_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "goods_types.id",
            name="FK_products_goods_type_id",
            ondelete="RESTRICT",
        ),
    )
    #: The unit set its units were copied from when it was created, kept for
    #: reference only (backlog 89): the units and the conversion rule are the
    #: product's own and nothing reads the set again.
    unit_set_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("unit_sets.id", name="FK_products_unit_set_id", ondelete="SET NULL"),
    )
    unit: Mapped[str | None] = mapped_column(String(20))
    brand: Mapped[str | None] = mapped_column(String(120))
    #: The brand row (MST-1); ``brand`` keeps its name in step.
    brand_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("brands.id", ondelete="RESTRICT")
    )
    model: Mapped[str | None] = mapped_column(String(120))
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    tax_profile_group_code: Mapped[str | None] = mapped_column(String(50), index=True)
    #: Whether tax paid buying it may be claimed as input credit (backlog 78
    #: row 1): ELIGIBLE, BLOCKED (s.17(5)) or INELIGIBLE. The default a
    #: purchase bill line takes; the line can say otherwise.
    itc_eligibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ELIGIBLE", server_default="ELIGIBLE"
    )
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
        ForeignKey(
            "uoms.id", name="FK_products_minimum_sales_uoms", ondelete="RESTRICT"
        ),
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
    #: The supplier this product is normally bought from (decision A18).
    #: Reorder raises its draft orders with it, and falls back to the one last
    #: billed where none is set or the one set has gone.
    preferred_vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), index=True
    )
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    #: The lowest net rate this product may be sold at, per stock unit -- the
    #: unit its moving average cost is kept in. A sale below it (or below
    #: cost) warns or is refused by the firm's `price_floor_settings`
    #: (BACKLOG 64 row 2). None sets no minimum.
    minimum_selling_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Bought and stocked but never sold -- packing material, consumables
    #: (STK-17). Every new sales line naming it is refused.
    not_for_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Days from manufacture to expiry (STK-18). A receipt that types only the
    #: manufacturing date gets its expiry from this; None fills nothing.
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    #: Which batch the goods leave from: FEFO, FIFO or PICK (STK-11). None
    #: is earliest expiry, as every product followed before.
    issue_rule: Mapped[str | None] = mapped_column(String(10))
    remarks: Mapped[str | None] = mapped_column(Text)
    track_batch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_lot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_serial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_expiry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_manufacturing_date: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_warranty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_negative_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    require_batch_on_receipt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Expiry rules (STK-5), each overriding the category's and the firm's:
    #: stop selling this many days before expiry, alert this many days
    #: before, and send back to the supplier this many days before.
    expiry_stop_sale_days: Mapped[int | None] = mapped_column(Integer)
    expiry_alert_days: Mapped[int | None] = mapped_column(Integer)
    expiry_return_days: Mapped[int | None] = mapped_column(Integer)
    #: Promotional stock (BUY-1): received, given away and counted, but never
    #: sold at a price.
    free_issue_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Received goods wait in quarantine until somebody passes them (BUY-9).
    #: True on the product or on its category is enough.
    inspection_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    require_batch_on_issue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    require_serial_on_receipt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    require_serial_on_issue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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
    #: The trade licences this product needs, overriding its category's; an
    #: empty list takes the category's (backlog 54). Every one is asked for
    #: (backlog 152).
    licence_requirements: Mapped[list["ProductLicenceRequirement"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductLicenceRequirement.position",
    )

    @property
    def required_licence_type_ids(self) -> list[UUID]:
        """Return the licence types this product itself names, in order."""
        return [row.licence_type_id for row in self.licence_requirements]

    @required_licence_type_ids.setter
    def required_licence_type_ids(self, licence_type_ids: Iterable[UUID]) -> None:
        """Replace the list, keeping the rows of the types that stay."""
        _replace_requirements(self, licence_type_ids, ProductLicenceRequirement)


class ProductLicenceRequirement(BaseEntity):
    """One trade licence a product needs; a product may name several."""

    __tablename__ = "product_licence_requirements"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "licence_type_id",
            name="UQ_product_licence_requirements_product_type",
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    licence_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("trade_licence_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: Where it stands in the list as the firm typed it.
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class ProductCategoryLicenceRequirement(BaseEntity):
    """One trade licence a category's goods need; it may name several."""

    __tablename__ = "product_category_licence_requirements"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "licence_type_id",
            name="UQ_product_category_licence_requirements_category_type",
        ),
    )

    category_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("product_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    licence_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("trade_licence_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: Where it stands in the list as the firm typed it.
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


def _replace_requirements(
    owner: Product | ProductCategory,
    licence_type_ids: Iterable[UUID],
    model: type[ProductLicenceRequirement] | type[ProductCategoryLicenceRequirement],
) -> None:
    """Make ``owner`` need exactly these licence types, in this order.

    A type that stays keeps its row, so one flush never deletes and inserts
    the same pair. Where the list really moves, the owner's row is written
    too: its ``version`` is what tells a second editor the record changed,
    and a change to the list alone touches no column of it.
    """
    wanted = list(dict.fromkeys(licence_type_ids))
    if wanted == owner.required_licence_type_ids:
        return
    kept = {row.licence_type_id: row for row in owner.licence_requirements}
    rows = [kept.get(type_id) or model(licence_type_id=type_id) for type_id in wanted]
    for position, row in enumerate(rows):
        row.position = position
    owner.licence_requirements = rows  # type: ignore[assignment]
    if object_session(owner) is not None:
        # Read first: an expired attribute cannot be flagged.
        owner.updated_by = owner.updated_by
        flag_modified(owner, "updated_by")


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


class ProductAttributeValue(AttributeValueBase):
    """Store one configurable attribute value for a product."""

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

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.PRODUCT
    OWNER_COLUMN: ClassVar[str] = "product_id"

    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
