"""Unit sets: a named template that fills a new product's units in one choice.

*Strip, box of 10* is the stock, purchase and sales units of a medicine and
the factor between its box and its strip (backlog 89). Choosing one on a new
product **copies** it: the units are written onto the product and the factor
becomes the product's own conversion rule, so a set edited later never
changes how a product already on the shelf converts.

Kept the way goods types are: a row without ``firm_id`` is the shared
catalogue, offered to every firm and read-only to them; a row with one is
that firm's own. ``unit_set_goods_types`` says which goods types a set suits,
and that tie only orders the picker -- a set tied to none is offered to every
product, and no pairing is ever refused.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType

#: The unit slots a set holds, named as the product names them.
UNIT_SLOTS = (
    "base_uom_id",
    "inventory_uom_id",
    "purchase_uom_id",
    "sales_uom_id",
    "minimum_sales_uom_id",
    "default_receiving_uom_id",
    "default_dispatch_uom_id",
)


def _unit(column: str) -> Mapped[UUID | None]:
    """Declare one optional unit slot, its key named after the column."""
    return mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name=f"FK_unit_sets_{column}", ondelete="RESTRICT"),
    )


class UnitSet(BaseEntity):
    """One template for a product's units and its pack size."""

    __tablename__ = "unit_sets"
    __table_args__ = (
        # A firm's names are its own; the shared catalogue's are unique among
        # themselves. The service keeps a firm's name clear of a shared one.
        Index(
            "UQ_unit_sets_firm_name_active",
            "firm_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false AND firm_id IS NOT NULL"),
            sqlite_where=text("is_deleted = 0 AND firm_id IS NOT NULL"),
        ),
        Index(
            "UQ_unit_sets_shared_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false AND firm_id IS NULL"),
            sqlite_where=text("is_deleted = 0 AND firm_id IS NULL"),
        ),
    )

    #: The firm whose own set this is; null for the shared catalogue.
    firm_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_uom_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("uoms.id", name="FK_unit_sets_base_uom_id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_uom_id: Mapped[UUID | None] = _unit("inventory_uom_id")
    purchase_uom_id: Mapped[UUID | None] = _unit("purchase_uom_id")
    sales_uom_id: Mapped[UUID | None] = _unit("sales_uom_id")
    minimum_sales_uom_id: Mapped[UUID | None] = _unit("minimum_sales_uom_id")
    default_receiving_uom_id: Mapped[UUID | None] = _unit("default_receiving_uom_id")
    default_dispatch_uom_id: Mapped[UUID | None] = _unit("default_dispatch_uom_id")
    allow_decimal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: One purchase unit is this many stock units; null where they are the
    #: same unit and nothing converts.
    conversion_factor: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class UnitSetGoodsType(BaseEntity):
    """One goods type a unit set suits; the pair is the whole row.

    Replaced by delete and insert when a set's types change, never soft
    deleted, so the key on the pair can be a plain one.
    """

    __tablename__ = "unit_set_goods_types"
    __table_args__ = (
        UniqueConstraint(
            "unit_set_id", "goods_type_id", name="UQ_unit_set_goods_types_pair"
        ),
    )

    unit_set_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "unit_sets.id",
            name="FK_unit_set_goods_types_unit_set_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    goods_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "goods_types.id",
            name="FK_unit_set_goods_types_goods_type_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
