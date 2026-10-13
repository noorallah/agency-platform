"""The brands a supplier may sell (backlog 129, row M11)."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class VendorBrand(BaseEntity):
    """One brand one supplier may sell.

    A link and nothing else: the list is replaced whole, and a brand taken
    off the list is a row removed, so the key is not partial. A supplier
    with no row here is not limited to any brand.
    """

    __tablename__ = "vendor_brands"
    __table_args__ = (
        Index("UQ_vendor_brands_vendor_brand", "vendor_id", "brand_id", unique=True),
        Index("IX_vendor_brands_brand_id", "brand_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="CASCADE", name="FK_vendor_brands_vendor_id"),
        nullable=False,
    )
    brand_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("brands.id", ondelete="CASCADE", name="FK_vendor_brands_brand_id"),
        nullable=False,
    )
