"""A person's saved layout of an analysis screen (RPT-1, decision A121).

"Product by month for the North route, net of returns, with margin" is set up
once and opened again by name. A layout is the screen's own settings --
dimensions, basis, filters, period kind -- held as one JSON object the
desktop owns: nothing on the server reads inside it, so a setting the screen
adds later needs no migration. It is per person, per firm and per report;
the firm is the store's, and the person is a bare id because ``users`` lives
only in the platform store.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ReportLayout(BaseEntity):
    """One named layout of one report, kept by one person in one firm."""

    __tablename__ = "report_layouts"
    __table_args__ = (
        Index(
            "UQ_report_layouts_name_active",
            "firm_id",
            "user_id",
            "report_code",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    report_code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
