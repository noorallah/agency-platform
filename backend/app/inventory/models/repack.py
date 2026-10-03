"""Repacking and bulk breaking: one product into others (STK-4)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Repack(BaseEntity):
    """Goods consumed and goods produced in one warehouse (decision A114).

    A 25 kg bag becomes 25 packs: the bag leaves at what it was carried at,
    the packs arrive carrying that value in proportion, and what was lost in
    the breaking is written to the inventory adjustment account.
    """

    __tablename__ = "repacks"
    __table_args__ = (Index("IX_repacks_firm_date", "firm_id", "repack_date"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    repack_number: Mapped[str] = mapped_column(String(60), nullable=False)
    repack_date: Mapped[date] = mapped_column(Date, nullable=False)
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    #: Share of the consumed value lost in the breaking, written off.
    wastage_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=0, server_default="0"
    )
    consumed_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default="0"
    )
    wastage_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default="0"
    )
    #: ``POSTED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class RepackLine(BaseEntity):
    """One product consumed or produced, and the movement that did it."""

    __tablename__ = "repack_lines"
    __table_args__ = (Index("IX_repack_lines_repack", "repack_id"),)

    repack_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("repacks.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: ``CONSUME`` or ``PRODUCE``.
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT")
    )
    #: In the product's stock unit.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: What the line moved at: the average for a consume line, the share
    #: carried for a produce line.
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default="0"
    )
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
