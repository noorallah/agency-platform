"""What one supplier sells of one product, dated (BUY-4, decision A101)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SupplierProduct(BaseEntity):
    """One dated catalogue row: a supplier's name, code and terms for a product.

    Rows are never overwritten. A new price or pack is a new row from its own
    ``effective_from``, so the history of what a supplier charged stays where
    a buyer can read it; the row in force on a date is the latest one dated on
    or before it. A row typed in error is deleted, not corrected.
    """

    __tablename__ = "supplier_products"
    __table_args__ = (
        Index(
            "IX_supplier_products_vendor_product",
            "firm_id",
            "vendor_id",
            "product_id",
            "effective_from",
        ),
        Index(
            "UQ_supplier_products_dated_active",
            "vendor_id",
            "product_id",
            "effective_from",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    #: What the supplier calls it, as their invoice prints it.
    supplier_product_code: Mapped[str | None] = mapped_column(String(120))
    supplier_product_name: Mapped[str | None] = mapped_column(String(200))
    #: Their price per purchase unit. A supplier price list's fixed rate still
    #: outranks it; it outranks the product's own purchase price.
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: Units per pack or case, as they ship it.
    pack_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    minimum_order_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: They ship only in multiples of this (BUY-5): 115 of a multiple of 20
    #: suggests 120.
    order_multiple: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
