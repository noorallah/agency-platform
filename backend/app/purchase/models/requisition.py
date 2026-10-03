"""Purchase requisitions: a request for goods, before any order (BUY-7)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class PurchaseRequisition(BaseEntity):
    """A branch or storeman asking for goods (decision A109).

    Raised, submitted and approved like an order, then converted into
    purchase orders -- one per supplier -- which is the point at which the
    firm commits to anybody. Its number comes from its own series.
    """

    __tablename__ = "purchase_requisitions"
    __table_args__ = (
        Index("IX_purchase_requisitions_firm_status", "firm_id", "status"),
        Index("IX_purchase_requisitions_firm_date", "firm_id", "requisition_date"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    requisition_number: Mapped[str] = mapped_column(String(60), nullable=False)
    requisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    needed_by: Mapped[date | None] = mapped_column(Date)
    #: ``DRAFT``, ``SUBMITTED``, ``APPROVED``, ``ORDERED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    remarks: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[UUID | None] = mapped_column(UUIDType())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class PurchaseRequisitionLine(BaseEntity):
    """One product asked for, and the order it went onto."""

    __tablename__ = "purchase_requisition_lines"
    __table_args__ = (
        Index("IX_purchase_requisition_lines_requisition", "requisition_id"),
    )

    requisition_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_requisitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: The supplier to order from; blank takes the product's preferred one.
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    #: Set when the line was put on an order.
    purchase_order_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_orders.id", ondelete="SET NULL")
    )
