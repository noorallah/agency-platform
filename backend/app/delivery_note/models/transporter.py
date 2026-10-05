"""The transporters a firm sends its goods with (backlog §87 #5, SG-5)."""

from uuid import UUID

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Transporter(BaseEntity):
    """One carrier: who it is and what an e-way bill asks about it.

    A delivery note that names one copies the name, the id and the usual mode
    into its own columns, so a later edit here never rewrites a note already
    raised.
    """

    __tablename__ = "transporters"
    __table_args__ = (
        Index(
            "UQ_transporters_firm_name_active",
            "firm_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: The transporter's GSTIN, where it is registered.
    gstin: Mapped[str | None] = mapped_column(String(15))
    #: The TRANSIN an unregistered transporter enrols for on the e-way bill
    #: portal: the same shape as a GSTIN, and what Part A names when there is
    #: no GSTIN.
    transporter_ref: Mapped[str | None] = mapped_column(String(15))
    phone: Mapped[str | None] = mapped_column(String(30))
    #: ROAD, RAIL, AIR or SHIP: how this carrier usually moves goods.
    default_mode: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


__all__ = ["Transporter"]
