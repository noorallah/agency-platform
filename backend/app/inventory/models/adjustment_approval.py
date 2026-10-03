"""Value limits on stock adjustments, and the requests above them (STK-8)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class RoleStockAdjustmentLimit(BaseEntity):
    """The largest stock adjustment one role may post, in one firm (A108).

    The pattern of ``role_purchase_approval_limits``: a person's limit is the
    largest among their roles that have one; somebody none of whose roles has
    one is not limited, so a firm that sets none behaves as before.
    """

    __tablename__ = "role_stock_adjustment_limits"
    __table_args__ = (
        Index(
            "UQ_role_stock_adjustment_limits_role_active",
            "firm_id",
            "role_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(String(100), nullable=False)
    #: The stock value an adjustment or write-off may move, at average cost.
    max_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class StockAdjustmentRequest(BaseEntity):
    """An adjustment or write-off above its author's limit, waiting (A108).

    The request is kept as it was typed and posted unchanged by whoever
    approves it, through the same service a direct post uses.
    """

    __tablename__ = "stock_adjustment_requests"
    __table_args__ = (
        Index("IX_stock_adjustment_requests_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: ``ADJUSTMENT`` or ``WRITE_OFF``.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: What it moves at the product's average cost when it was asked for.
    estimated_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The adjustment or write-off exactly as typed.
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    #: ``PENDING``, ``APPROVED`` or ``REJECTED``.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="PENDING"
    )
    decided_by: Mapped[UUID | None] = mapped_column(UUIDType())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_remarks: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
