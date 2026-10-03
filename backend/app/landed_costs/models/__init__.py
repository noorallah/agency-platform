"""Landed cost vouchers, their charges and how they were spread (BUY-16)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class LandedCostVoucher(BaseEntity):
    """Freight, loading or clearing spread over completed receipts (A129).

    The charge's own bill is booked to *Expenses Included in Valuation*; the
    voucher moves it into the goods -- the share still on hand into stock,
    revaluing its average, and the share already sold into cost of goods
    sold.
    """

    __tablename__ = "landed_cost_vouchers"
    __table_args__ = (
        Index("IX_landed_cost_vouchers_firm_date", "firm_id", "voucher_date"),
        Index(
            "UQ_landed_cost_vouchers_number_active",
            "firm_id",
            "voucher_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    voucher_number: Mapped[str] = mapped_column(String(60), nullable=False)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: ``VALUE``, ``QUANTITY`` or ``WEIGHT``.
    basis: Mapped[str] = mapped_column(String(20), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    inventory_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    cogs_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    #: ``POSTED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class LandedCostCharge(BaseEntity):
    """One charge on a voucher: what it was for and whose bill it was."""

    __tablename__ = "landed_cost_charges"
    __table_args__ = (Index("IX_landed_cost_charges_voucher", "voucher_id"),)

    voucher_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("landed_cost_vouchers.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The transporter, clearing agent or other party that billed it.
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    #: The bill's number, as the party wrote it.
    bill_reference: Mapped[str | None] = mapped_column(String(100))


class LandedCostAllocation(BaseEntity):
    """The share of a voucher one receipt line carried."""

    __tablename__ = "landed_cost_allocations"
    __table_args__ = (
        Index("IX_landed_cost_allocations_voucher", "voucher_id"),
        Index("IX_landed_cost_allocations_receipt", "goods_receipt_id"),
    )

    voucher_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("landed_cost_vouchers.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    goods_receipt_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("goods_receipts.id", ondelete="RESTRICT"), nullable=False
    )
    goods_receipt_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("goods_receipt_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    #: Received, in the stock unit.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: What the basis measured: value, quantity or weight.
    basis_measure: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    inventory_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cogs_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventory_transactions.id", ondelete="SET NULL")
    )
