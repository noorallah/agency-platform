"""Payment runs: many supplier bills paid in one go (BUY-11)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class PaymentRun(BaseEntity):
    """The bills chosen to be paid on one date (decision A110).

    A draft lists the bills and amounts; approving records one payment per
    supplier through the payment service and is the point money is booked.
    Its number comes from its own series.
    """

    __tablename__ = "payment_runs"
    __table_args__ = (Index("IX_payment_runs_firm_status", "firm_id", "status"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    run_number: Mapped[str] = mapped_column(String(60), nullable=False)
    #: The date the payments are made on.
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Bills due on or before this were proposed.
    due_by: Mapped[date | None] = mapped_column(Date)
    #: ``DRAFT``, ``APPROVED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    remarks: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[UUID | None] = mapped_column(UUIDType())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class PaymentRunLine(BaseEntity):
    """One bill in a run, and the payment that settled it."""

    __tablename__ = "payment_run_lines"
    __table_args__ = (Index("IX_payment_run_lines_run", "payment_run_id"),)

    payment_run_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("payment_runs.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    #: A purchase invoice, or a supplier opening bill when ``is_opening_bill``.
    invoice_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    is_opening_bill: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The payment approval recorded for this line's supplier.
    settlement_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("settlements.id", ondelete="SET NULL")
    )
