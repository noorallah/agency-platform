"""Principals and brands (MST-1, decision A118)."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Principal(BaseEntity):
    """The company whose agency the firm holds -- a distributor's principal.

    Usually also a supplier, so it may name the vendor the firm buys from.
    """

    __tablename__ = "principals"
    __table_args__ = (
        Index(
            "UQ_principals_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Brand(BaseEntity):
    """A brand the firm sells, under the principal that owns it."""

    __tablename__ = "brands"
    __table_args__ = (
        Index(
            "UQ_brands_name_active",
            "firm_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    principal_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("principals.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
