"""A saved mapping of a file's headings onto an import's template (B3)."""

from uuid import UUID

from sqlalchemy import JSON, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ImportMapping(BaseEntity):
    """How one firm reads one kind of file from one source, by name.

    A firm moving from Tally, Marg or Busy exports the same report many times
    while it migrates; the mapping it worked out the first time is kept, as
    Zoho's import keeps "these selections for future imports". ``mapping`` is
    configuration -- file heading to template column, or null to leave it out
    -- not data about any record, so it is held as JSON.
    """

    __tablename__ = "import_mappings"
    __table_args__ = (
        Index(
            "UQ_import_mappings_firm_kind_name_active",
            "firm_id",
            "kind",
            "name",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: Which import: products, customers, vendors, customer-opening-bills,
    #: vendor-opening-bills or opening-stock.
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mapping: Mapped[dict[str, str | None]] = mapped_column(JSON, nullable=False)
