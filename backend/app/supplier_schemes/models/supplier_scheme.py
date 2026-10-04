"""A supplier's free-goods scheme on an item (PG-11, backlog 86 #25)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SupplierScheme(BaseEntity):
    """Buy ``buy_quantity`` of a product, get ``free_quantity`` free.

    ``vendor_id`` null is a scheme from every supplier of the product (the
    manufacturer's own, say); a supplier's own scheme beats it. The free goods
    are the same product unless ``free_product_id`` names another ("free
    bucket with 10 soap"). In force from ``valid_from`` to ``valid_to``
    (open-ended when null) while ``is_active``. No versions: an edit changes
    the scheme for orders priced after it, and an order line keeps what it
    was given (``purchase_order_lines.scheme_id`` and ``scheme_name``).
    """

    __tablename__ = "supplier_schemes"
    __table_args__ = (
        Index("IX_supplier_schemes_firm_product", "firm_id", "product_id"),
        Index("IX_supplier_schemes_firm_vendor", "firm_id", "vendor_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    buy_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    free_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    free_product_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT")
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notes: Mapped[str | None] = mapped_column(Text)
