"""The firm's own list of reasons stock is adjusted or written off (STK-7)."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class StockAdjustmentReason(BaseEntity):
    """One reason stock left, or was corrected, tied to the account it costs.

    Decision A104. The six reasons the code always knew -- damage, expiry,
    loss, internal use, staff, display -- are system rows a firm may rename
    or point at another account but not delete; a firm adds its own beside
    them. A write-off names one and its journal lands in the reason's account,
    or, where none is set, where that reason always landed.
    """

    __tablename__ = "stock_adjustment_reasons"
    __table_args__ = (
        Index(
            "UQ_stock_adjustment_reasons_code_active",
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
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: The account the cost lands in. Null: the inventory adjustment account,
    #: or for a system issue reason its own expense (STK-3).
    ledger_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
