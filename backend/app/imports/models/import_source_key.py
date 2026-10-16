"""An old software's number kept against our record (Swathi plan, gap G2)."""

from uuid import UUID

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ImportSourceKey(BaseEntity):
    """One record brought in from another program, by that program's number.

    A conversion from Swathi, Tally or Marg is run more than once while a firm
    migrates, and a second run must recognise a customer, product or bill it
    already brought in and skip it rather than duplicate it. The old number is
    kept here rather than on each module's table, so one lookup serves every
    import. ``record_id`` names our row and carries no foreign key, because it
    points at a different table per ``subject``.
    """

    __tablename__ = "import_source_keys"
    __table_args__ = (
        Index(
            "UQ_import_source_keys_firm_system_subject_key_active",
            "firm_id",
            "source_system",
            "subject",
            "source_key",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema. Carried
    #: because `firm_shared` holds many firms, and two of them may each have a
    #: customer numbered 101 in the same old program.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The program the record came from: SWATHI, TALLY, MARG ...
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    #: What kind of record: CUSTOMER, PRODUCT, VENDOR, SALES_INVOICE ...
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    #: The old program's own number for it, as that program wrote it.
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Our row. No foreign key: the table depends on ``subject``.
    record_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
