"""A firm's settings for TDS on contracts (194C) and fees (194J) (PG-5).

One row per firm and section, kept beside the 194Q row (ACC-8) because each
Finance Act may move the rates and thresholds. No row reads as the defaults
in ``app.finance.services.tds_sections``: 194C 1% (individual or HUF) and 2%
(anybody else) past 30,000 on one bill or 1,00,000 in the year; 194J 10%
(professional) and 2% (technical) past 30,000 in the year; 20% without a PAN
(section 206AA) under either.

Unlike 194Q these are **on by default**: they apply to every firm that keeps
audited books, and a supplier is only ever proposed a deduction when its own
master names the section.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class TdsSectionSettings(BaseEntity):
    """One firm's switch, thresholds and rates for 194C or 194J."""

    __tablename__ = "tds_section_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", "section", name="UQ_tds_section_settings_firm"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: ``194C`` or ``194J``.
    section: Mapped[str] = mapped_column(String(10), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: One bill past which the tax applies whatever the year holds (194C);
    #: NULL where the section has none (194J).
    single_threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    #: The year's total past which the tax applies to all of it.
    annual_threshold_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    #: 194C: anybody but an individual or HUF. 194J: professional fees.
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    #: 194C: an individual or HUF. 194J: technical services.
    lower_rate_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    #: Where the supplier gave no PAN (section 206AA).
    rate_without_pan_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("20"), server_default="20"
    )
