"""Goods types: what a line of goods is, and how its products are tracked.

Medicine, Food, Paint, Electronics. A goods type carries the tracking
switches a new product of that line starts with (backlog 89). Not
``product_type``, which already means stock, service or bundle.

Kept the way custom fields are: a row without ``firm_id`` is the platform's
shared catalogue, offered to every firm and read-only to them; a row with one
is that firm's own. Which types a firm trades in, and the tax defaults it
gives a new product of each, is ``firm_goods_types`` -- a tax group is the
firm's own code, so it cannot sit on a row several firms share.

General is the absence of a type: a category or a product whose
``goods_type_id`` is null tracks nothing and requires nothing.
"""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class GoodsType(BaseEntity):
    """One line of goods and the tracking its products start with."""

    __tablename__ = "goods_types"
    __table_args__ = (
        # A firm's code is its own; the shared catalogue's codes are unique
        # among themselves. The service also keeps a firm's code clear of the
        # shared ones, which no single index can say.
        Index(
            "UQ_goods_types_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false AND firm_id IS NOT NULL"),
            sqlite_where=text("is_deleted = 0 AND firm_id IS NOT NULL"),
        ),
        Index(
            "UQ_goods_types_shared_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false AND firm_id IS NULL"),
            sqlite_where=text("is_deleted = 0 AND firm_id IS NULL"),
        ),
    )

    #: The firm whose own type this is; null for the shared catalogue.
    firm_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    track_batch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_expiry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_manufacturing_date: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_serial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    track_warranty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class FirmGoodsType(BaseEntity):
    """One goods type a firm trades in, with its defaults for a new product."""

    __tablename__ = "firm_goods_types"
    __table_args__ = (
        Index(
            "UQ_firm_goods_types_firm_type_active",
            "firm_id",
            "goods_type_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    goods_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "goods_types.id",
            name="FK_firm_goods_types_goods_type_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    #: Filled into a new product of this type, where the person can change
    #: them; never written over a product that has its own.
    default_hsn_sac: Mapped[str | None] = mapped_column(String(20))
    default_tax_profile_group_code: Mapped[str | None] = mapped_column(String(50))
