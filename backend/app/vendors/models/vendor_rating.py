"""People's opinion of a supplier, kept apart from the figures (BUY-15).

The supplier performance report already computes what the documents can say:
on-time delivery, short and rejected supply, price movement. What it cannot
say is that a supplier is slow to answer the phone or sends invoices that
never match the challan. That is an opinion, so it is recorded as one -- by a
named person, on five criteria scored 1 to 5, with a remark -- and never mixed
into the computed figures.

One live rating per person per supplier: rating again replaces your own, and
the old one stays on file as history.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType

#: The five things a buyer judges a supplier on, as ERPNext's supplier
#: scorecard and Busy's vendor rating do.
RATING_CRITERIA = ("quality", "delivery", "price", "communication", "paperwork")


class VendorRating(BaseEntity):
    """One person's scores for one supplier."""

    __tablename__ = "vendor_ratings"
    __table_args__ = (
        *(
            CheckConstraint(
                f"{name} BETWEEN 1 AND 5", name=f"CK_vendor_ratings_{name}_range"
            )
            for name in RATING_CRITERIA
        ),
        Index(
            "UQ_vendor_ratings_rater_active",
            "firm_id",
            "vendor_id",
            "rated_by",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: Who gave the scores -- a user id from the platform store.
    rated_by: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    rated_on: Mapped[date] = mapped_column(Date, nullable=False)
    quality: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    communication: Mapped[int] = mapped_column(Integer, nullable=False)
    paperwork: Mapped[int] = mapped_column(Integer, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
