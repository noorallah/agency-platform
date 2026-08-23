"""What a firm has agreed to charge, and to whom.

A product carries one `selling_price`, and `customers.default_discount_percent`
lets a firm say one customer is on a blanket rate. Neither can express the
ordinary arrangement in distribution: *this* customer, or everyone on *this*
route, gets a particular rate on a particular product, from a particular date.

A price list holds **rates off the product's price**, not prices of its own.
That is the decision the shape rests on: a firm revises a product's price once
and every arrangement built on it follows, where a list of absolute prices
would silently keep charging last year's figure until somebody edited every
row.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
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


class PriceList(BaseEntity):
    """One named arrangement, scoped to who it applies to and when.

    Scope is deliberately two nullable keys rather than a type-and-id pair:
    `customer_id` names one shop, `territory_id` names everyone on a round,
    and both NULL is the firm's own standing arrangement. A query for "the
    lists that could apply here" is then three equality tests, and the
    specificity order falls out of which key is filled.

    Effective-dated for the reason `uom_conversion_rules` and `tax_profiles`
    are: a rate agreed in April must still explain an April document after the
    arrangement changes in September. A list is superseded by dating it, never
    by editing the rate.
    """

    __tablename__ = "price_lists"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_price_lists_firm_code"),
        Index("IX_price_lists_firm_status", "firm_id", "status"),
        Index("IX_price_lists_customer", "firm_id", "customer_id"),
        Index("IX_price_lists_territory", "firm_id", "territory_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    #: One shop. NULL with `territory_id` NULL means the whole firm.
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    #: Everyone on a round or under a branch of the hierarchy.
    territory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )


class PriceListItem(BaseEntity):
    """One product's rate on one list.

    A rate rather than a price, per the module docstring. `discount_percent`
    is what comes off `products.selling_price` -- or off whatever price the
    document line carries, since the line is where the price is stated and the
    list has no opinion about how it got there.
    """

    __tablename__ = "price_list_items"
    __table_args__ = (
        UniqueConstraint(
            "price_list_id", "product_id", name="UQ_price_list_items_list_product"
        ),
        Index("IX_price_list_items_list", "price_list_id"),
        Index("IX_price_list_items_product", "firm_id", "product_id"),
    )

    price_list_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("price_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
