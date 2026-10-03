"""The firm's ledger names as its CA keeps them in Tally (MSG-5)."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class TallyLedgerMapping(BaseEntity):
    """What one of our accounts is called in the CA's Tally, and its group.

    An account with no row is exported under its own name, in the group its
    type and purpose suggest (decision A135).
    """

    __tablename__ = "tally_ledger_mappings"
    __table_args__ = (
        Index(
            "UQ_tally_ledger_mappings_account_active",
            "firm_id",
            "ledger_account_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    tally_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tally_parent: Mapped[str | None] = mapped_column(String(200))
