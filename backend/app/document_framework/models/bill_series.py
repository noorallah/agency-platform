"""A bill series per company (backlog 157, PRT-7).

`docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md` is the reference. A firm's
sales bills take one series, GENERAL, unless the firm switches on a series
per company; then a bill of one company's goods takes that company's prefix.
The counter is keyed on the prefix and the financial year, never on the
company or the rule, so two companies sharing a prefix share one running
number and no number is issued twice.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType

#: The firm numbers every sales bill from its one series.
ONE_SERIES = "ONE_SERIES"
#: A bill of one company's goods takes that company's prefix.
BY_COMPANY = "BY_COMPANY"

#: The prefix the general series is counted under.
GENERAL_SERIES = "GENERAL"


class BillSeriesSettings(BaseEntity):
    """Which series a firm's sales bills take; one row per firm.

    A firm with no row reads as ``ONE_SERIES``. ``series_driver`` is text,
    not a switch, so a later level (brand, goods type, product) is a value
    and a prefix column on that level's master, with no table reshaped.
    """

    __tablename__ = "bill_series_settings"
    __table_args__ = (UniqueConstraint("firm_id", name="UQ_bill_series_settings_firm"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    series_driver: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ONE_SERIES, server_default=ONE_SERIES
    )


class BillSeriesCounter(BaseEntity):
    """The next number of one bill series in one financial year.

    The unique key is not partial, so a retired row is revived and never
    duplicated (the lesson of D-CFG-7). It is read ``with_for_update``: it
    guards the next number, which optimistic ``version`` cannot.
    """

    __tablename__ = "bill_series_counters"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "prefix",
            "financial_year",
            name="UQ_bill_series_counters_firm_prefix_year",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    financial_year: Mapped[str] = mapped_column(String(20), nullable=False)
    next_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
