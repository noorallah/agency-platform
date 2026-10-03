"""A firm's settings for TDS on the purchase of goods, section 194Q (ACC-8).

A buyer whose turnover passed ten crore rupees in the previous year deducts
0.1% on what it buys from one supplier past fifty lakh in the year (5% where
the supplier gave no PAN, section 206AA). Whether the turnover test is met is
a fact only the firm knows, so the section is **off until the firm says so**;
the threshold and rates are kept here because each Finance Act may move them.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Numeric, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Tds194QSettings(BaseEntity):
    """One firm's 194Q switch, threshold and rates."""

    __tablename__ = "tds_194q_settings"
    __table_args__ = (UniqueConstraint("firm_id", name="UQ_tds_194q_settings_firm"),)

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: Purchases from one supplier in the year past which the tax applies.
    threshold_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("5000000"),
        server_default="5000000",
    )
    #: Percent on the excess where the supplier's PAN is known.
    rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("0.1"), server_default="0.1"
    )
    #: Percent where it is not (section 206AA).
    rate_without_pan_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("5"), server_default="5"
    )
