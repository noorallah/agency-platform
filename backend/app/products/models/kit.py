"""Kits and combo packs: a product made of others (STK-15)."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ProductKitComponent(BaseEntity):
    """One component of a kit, and how many go into one kit (decision A134)."""

    __tablename__ = "product_kit_components"
    __table_args__ = (
        Index(
            "UQ_product_kit_components_kit_component_active",
            "kit_product_id",
            "component_product_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    kit_product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    #: In the component's stock unit, per one kit.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
