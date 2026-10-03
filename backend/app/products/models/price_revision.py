"""Dated price revisions for a product (MST-2, decision A119)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ProductPriceRevision(BaseEntity):
    """New rates for a product from a date, kept with every earlier one.

    A document reads the revision in force on its own date -- the latest
    dated on or before it -- and falls back to the product's own price before
    the first. A blank price in a revision leaves that price as it was.
    """

    __tablename__ = "product_price_revisions"
    __table_args__ = (
        Index(
            "UQ_product_price_revisions_dated_active",
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
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    remarks: Mapped[str | None] = mapped_column(Text)
