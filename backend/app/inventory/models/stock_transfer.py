"""Stock transfer as a document: dispatch, in transit, receive (STK-1)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class StockTransfer(BaseEntity):
    """Goods sent from one warehouse to another, in two steps (decision A126).

    Dispatch takes the goods off the source and puts them *in transit* at the
    destination; receipt takes them out of transit and onto the destination's
    shelf, recording what arrived short or damaged. The firm owns the goods
    the whole way, so nothing posts until a shortage is written off.
    """

    __tablename__ = "stock_transfers"
    __table_args__ = (
        Index("IX_stock_transfers_firm_date", "firm_id", "transfer_date"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    transfer_number: Mapped[str] = mapped_column(String(60), nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    from_warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    to_branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    to_warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    #: ``DRAFT``, ``DISPATCHED``, ``RECEIVED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    dispatched_on: Mapped[date | None] = mapped_column(Date)
    received_on: Mapped[date | None] = mapped_column(Date)
    vehicle_number: Mapped[str | None] = mapped_column(String(30))
    transporter_name: Mapped[str | None] = mapped_column(String(200))
    #: What left the source, at the moving average on the day it left.
    dispatched_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default="0"
    )
    #: What never arrived, written off to the inventory adjustment account.
    shortage_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default="0"
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    receipt_remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class StockTransferLine(BaseEntity):
    """One product sent, and what became of it at the other end."""

    __tablename__ = "stock_transfer_lines"
    __table_args__ = (Index("IX_stock_transfer_lines_transfer", "transfer_id"),)

    transfer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("stock_transfers.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT")
    )
    #: Sent, in the product's stock unit.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: Arrived in good order.
    received_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: Arrived, but damaged: on the shelf and blocked from sale.
    damaged_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: Never arrived.
    short_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: The moving average the goods left at.
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    remarks: Mapped[str | None] = mapped_column(String(500))
    dispatch_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
    transit_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
    receive_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
