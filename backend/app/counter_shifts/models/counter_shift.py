"""A cashier's shift at the counter (backlog 87 #7, SG-7).

A till is opened with a float, takes money all day and is counted when the
cashier goes home -- Tally's *POS register*, Marg and Busy's *shift closing*,
ERPNext's *POS opening and closing entry*. The firm had bills and tenders and
nowhere to say whose drawer the cash went into or whether it was all there.

**What the drawer should hold is derived, never incremented**
(`app/counter_shifts/services`): the float plus the cash tenders of the bills
approved in the shift whose receipts still stand. A counter kept on the row
would be a second copy of the receipts, wrong the first time one is reversed.
Only the close writes it down -- `expected_cash` is the figure the count was
judged against that evening, a snapshot the books must keep.

**One open shift per cashier**, held by `UQ_counter_shifts_open_cashier`
rather than by a read: two tills opened in the same second would each see
none. The service checks first, for the message.

**Shifts are optional.** A bill approved by somebody with no open shift is
stamped with none and posts exactly as it always did; a one-person firm that
never counts a drawer is not asked to, and one that hires a cashier later
starts opening shifts the day it wants to.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class CounterShiftStatus(StrEnum):
    """Whether the till is still taking money."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class CounterShift(BaseEntity):
    """Store one cashier's shift: the float, and the count it closed on."""

    __tablename__ = "counter_shifts"
    __table_args__ = (
        UniqueConstraint("firm_id", "shift_number", name="UQ_counter_shifts_number"),
        # Named by the metadata convention: CK_counter_shifts_<name>.
        CheckConstraint("opening_float >= 0", name="opening_float_not_negative"),
        CheckConstraint(
            "counted_cash IS NULL OR counted_cash >= 0",
            name="counted_cash_not_negative",
        ),
        Index(
            "UQ_counter_shifts_open_cashier",
            "firm_id",
            "cashier_id",
            unique=True,
            postgresql_where=text("status = 'OPEN' AND is_deleted = false"),
            sqlite_where=text("status = 'OPEN' AND is_deleted = 0"),
        ),
        Index("IX_counter_shifts_firm_opened", "firm_id", "opened_at"),
    )

    #: The owning firm. No foreign key: `firms` lives only in the platform
    #: store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "branches.id", ondelete="RESTRICT", name="FK_counter_shifts_branch_id"
        ),
        nullable=False,
    )
    #: Whose till it is. A platform user id, so no foreign key.
    cashier_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    #: The cash account the till's money is booked to, and the one a shortage
    #: or an excess is posted against. The firm's cash control account unless
    #: the shift named another.
    cash_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "ledger_accounts.id",
            ondelete="RESTRICT",
            name="FK_counter_shifts_cash_account_id",
        ),
        nullable=False,
    )
    #: ``SHIFT-000123``: the firm's running number, and the reference of the
    #: journal a difference posts.
    shift_number: Mapped[str] = mapped_column(String(30), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: The cash put in the drawer to give change from.
    opening_float: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=CounterShiftStatus.OPEN.value,
        server_default=CounterShiftStatus.OPEN.value,
    )
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: Who closed it: the cashier, or whoever may approve sales. A platform
    #: user id, so no foreign key.
    closed_by: Mapped[UUID | None] = mapped_column(UUIDType())
    #: What was in the drawer when it was counted.
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    #: What the drawer should have held when it was counted: a snapshot taken
    #: at the close, the one figure here that is stored rather than derived.
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    #: Counted less expected: negative is short, positive is over.
    difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    #: The journal the difference posted; NULL when the drawer was exact.
    difference_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "journal_entries.id",
            ondelete="RESTRICT",
            name="FK_counter_shifts_difference_journal_entry_id",
        ),
    )
    closing_note: Mapped[str | None] = mapped_column(Text())
