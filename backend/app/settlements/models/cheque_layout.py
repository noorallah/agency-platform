"""Where a bank's cheque leaf takes its print (ACC-12, decision A66).

Every Indian bank prints its cheques to the CTS-2010 standard, so the date
boxes, the payee line, the amount in words and the amount box sit in the same
places on every leaf -- give or take the millimetre or two by which a bank's
printer and the firm's own printer disagree. That difference is all a firm
records here, per bank account it pays from, after one test print. Tally keeps
the same thing on the bank ledger.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class ChequeLayout(BaseEntity):
    """One bank account's printing offsets and A/c Payee choice."""

    __tablename__ = "cheque_layouts"
    __table_args__ = (
        Index(
            "UQ_cheque_layouts_account_active",
            "firm_id",
            "ledger_account_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: The bank ledger account whose cheque book this describes.
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Millimetres to move everything right (positive) or left (negative).
    offset_x_mm: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Millimetres to move everything down (positive) or up (negative).
    offset_y_mm: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Print the two crossing lines and "A/c Payee" -- on by default, as
    #: almost every business cheque is crossed.
    print_ac_payee: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
