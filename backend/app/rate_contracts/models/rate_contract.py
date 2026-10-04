"""Rate contracts (blanket orders) with a supplier (PG-9, backlog 86 #2)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class RateContract(BaseEntity):
    """An agreement with one supplier: these items, at these rates, for a period.

    ``DRAFT`` while it is typed, ``ACTIVE`` once approved, ``CLOSED`` when
    ended by hand, ``CANCELLED`` when called off. *Expired* is never stored:
    an active contract whose ``valid_to`` has passed reads as ``EXPIRED``.
    The status moves only through the transition endpoints.
    """

    __tablename__ = "rate_contracts"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "contract_number",
            name="UQ_rate_contracts_firm_contract_number",
        ),
        Index("IX_rate_contracts_firm_vendor_status", "firm_id", "vendor_id", "status"),
        Index("IX_rate_contracts_firm_valid_from", "firm_id", "valid_from"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    contract_number: Mapped[str] = mapped_column(String(60), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    #: The supplier's own reference for the agreement, if any.
    reference: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    #: ``DRAFT``, ``ACTIVE``, ``CLOSED`` or ``CANCELLED``; never ``EXPIRED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID | None] = mapped_column(UUIDType())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class RateContractLine(BaseEntity):
    """One product on a contract, its agreed rate and how much was agreed.

    What has been drawn against it is never stored: it is the sum of the
    approved, uncancelled purchase order lines that name this line.
    """

    __tablename__ = "rate_contract_lines"
    __table_args__ = (
        UniqueConstraint(
            "contract_id", "line_number", name="UQ_rate_contract_lines_contract_line"
        ),
        Index("IX_rate_contract_lines_contract", "contract_id"),
        Index("IX_rate_contract_lines_firm_product", "firm_id", "product_id"),
    )

    contract_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("rate_contracts.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    #: The unit the rate is per; an order line in another unit is not priced
    #: from the contract. Defaults to the product's purchase unit.
    uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The total agreed, if any; null is a rate agreement with no quantity.
    contracted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    notes: Mapped[str | None] = mapped_column(Text)
