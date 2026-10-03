"""Named price levels: Retail, Wholesale, Dealer (SEL-9, decision A89).

A distributor sells one product at several prices by who is buying: the shop
on the corner pays retail, the sub-dealer pays dealer. Tally calls these
price levels and Busy and Marg the same; a product carries a rate per level,
and a customer -- or the group it belongs to -- is put on one.

These are **prices**, not rates off the price, so they sit beside the price
lists rather than inside them: a list says "ten percent off" and follows a
price revision by itself, a level says "dealers pay 80" and is revised as a
price is. Which price a line starts at is decided in
``app/pricing/services/unit_price.py``: a fixed rate on a price list for this
customer, then the customer's level, then the product's own selling price.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class PriceLevel(BaseEntity):
    """One named level a firm prices by."""

    __tablename__ = "price_levels"
    __table_args__ = (
        Index(
            "UQ_price_levels_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ProductPriceLevel(BaseEntity):
    """One product's price at one level."""

    __tablename__ = "product_price_levels"
    __table_args__ = (
        Index(
            "UQ_product_price_levels_level_product_active",
            "price_level_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_product_price_levels_product", "firm_id", "product_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    price_level_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("price_levels.id", ondelete="CASCADE"), nullable=False
    )
    #: The price, before tax, in the product's sales unit.
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


__all__ = ["PriceLevel", "ProductPriceLevel"]
