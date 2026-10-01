"""A GST return the firm says it filed on the portal (backlog 63 item 4).

Filing happens on the GST portal, never here, so the platform cannot know a
return was filed unless somebody says so. The tax calendar on Home needs to:
without it a GSTR-1 filed on the 10th would read as late from the 12th for
ever. One row per firm, return and month, kept with the date filed and the
acknowledgement (ARN) the portal gave; withdrawing it soft-deletes the row.

GSTR-3B is also settled by recording the month's GST payment (``gst_payments``),
which is how most firms will close it; a row here covers a nil return, or one
whose tax was paid outside the platform.
"""

from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class GstReturnType(StrEnum):
    """The returns the calendar follows."""

    GSTR1 = "GSTR1"
    GSTR3B = "GSTR3B"


class GstReturnFiling(BaseEntity):
    """One return, for one month, filed on the portal."""

    __tablename__ = "gst_return_filings"
    __table_args__ = (
        # A return is filed once a month; saying so twice would be a second
        # answer to the same question.
        Index(
            "UQ_gst_return_filings_firm_type_period_active",
            "firm_id",
            "return_type",
            "return_period",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: ``GSTR1`` or ``GSTR3B``.
    return_type: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The return month, ``YYYY-MM``.
    return_period: Mapped[str] = mapped_column(String(7), nullable=False)
    filed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: The portal's acknowledgement reference number, where it was kept.
    arn: Mapped[str | None] = mapped_column(String(30))
    remarks: Mapped[str | None] = mapped_column(Text)


__all__ = ["GstReturnFiling", "GstReturnType"]
