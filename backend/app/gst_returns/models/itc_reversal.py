"""Input tax credit reversed and reclaimed under rule 37 (backlog 78 row 4).

A buyer who has not paid a supplier the value and tax of a bill within 180
days of its date must reverse the credit taken on the unpaid part, and may
claim it back when the bill is paid (CGST rule 37, as amended from 1 October
2022). Each row here is one such movement on one bill: a REVERSAL, or a
RECLAIM of some of what was reversed. What stands reversed on a bill is the
sum of its reversals less its reclaims -- never a column of its own -- and
each movement carries the journal that moved the credit, so the books and
GSTR-3B read the same thing: reversals in 4(B)(2), reclaims in 4(A)(5) and
4(D)(1) (CBIC circular 170/02/2022).
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ItcMovement(StrEnum):
    """Which way the credit moved."""

    REVERSAL = "REVERSAL"
    RECLAIM = "RECLAIM"


class ItcReversal(BaseEntity):
    """One reversal of a bill's credit, or one reclaim of it."""

    __tablename__ = "itc_reversals"
    __table_args__ = (
        CheckConstraint(
            "movement IN ('REVERSAL', 'RECLAIM')",
            name="CK_itc_reversals_movement",
        ),
        Index("IX_itc_reversals_firm_date", "firm_id", "movement_date"),
        Index("IX_itc_reversals_bill", "purchase_invoice_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    movement: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The day the movement is reported: the 3B period it falls in.
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: What the bill still owed when this was worked out, and its total.
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    bill_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    igst: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    cgst: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    sgst: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    cess: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
