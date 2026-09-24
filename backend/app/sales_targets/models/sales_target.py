"""What a firm expects a salesman or a round to sell, and over what period.

The by-salesman and by-territory reports have always answered "how much" and
never "how much against what", because there was nothing to measure them
against. A target is that missing half.

Two things are deliberately configuration rather than a decision baked in.

**What counts** -- `basis` is INVOICED or COLLECTED, because firms genuinely
differ: one measures a salesman on what they sold, another on what they got
paid for. Commission here is earned on money collected, so a firm running both
can align them or not, as it chooses.

**Who it is for** -- a target names a salesman, a territory, or neither, and
neither means the firm as a whole. Both nullable rather than a type-and-id
pair, which is the shape `price_lists` already uses for the same question.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SalesTarget(BaseEntity):
    """One expectation, for one period, of one salesman or round."""

    __tablename__ = "sales_targets"
    __table_args__ = (
        # One live target per scope, basis and period start. A second would
        # leave two answers to "did they make it", and no report could choose
        # between them.
        #
        # It was a plain `UniqueConstraint` over
        # (firm_id, salesman_id, territory_id, period_start), which held in
        # two directions at once and in neither of them well (D-TER-16):
        #
        # - both scope columns are nullable and neither PostgreSQL nor SQLite
        #   equates two NULLs, so it held **nothing at all** for a target with
        #   a blank scope -- which is most of them, since a target naming only
        #   a person leaves the territory blank and the firm's own number
        #   leaves both. `coalesce` onto the nil UUID gives the two scopes a
        #   value the key can compare;
        # - it covered deleted rows, so a withdrawn target kept its period for
        #   ever, and the service -- which filters `is_deleted` -- let the
        #   replacement through to a bare 409 from the database;
        # - and it left `basis` out, while the service deliberately allows one
        #   INVOICED and one COLLECTED target over the same days, because what
        #   was billed and what was collected are different numbers a firm may
        #   set both of.
        #
        # It still cannot express **overlap**, which is what `_assert_free`
        # checks and what D-TER-2 was about; the service check stays
        # authoritative, and this is the backstop for two requests that both
        # read before either commits. The same division `UQ_commission_payouts
        # _period_active` already draws.
        Index(
            "UQ_sales_targets_scope_period_active",
            "firm_id",
            text("coalesce(salesman_id, '00000000-0000-0000-0000-000000000000')"),
            text("coalesce(territory_id, '00000000-0000-0000-0000-000000000000')"),
            "basis",
            "period_start",
            unique=True,
            # Both dialects: with only the PostgreSQL clause SQLite ignores it
            # and `create_all` builds an unconditional unique index -- stricter
            # than intended, and the unit suite is what would then be believed.
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
        CheckConstraint(
            "period_end >= period_start", name="CK_sales_targets_period_order"
        ),
        CheckConstraint("target_amount >= 0", name="CK_sales_targets_amount"),
        Index("IX_sales_targets_firm_period", "firm_id", "period_start"),
        Index("IX_sales_targets_firm_salesman", "firm_id", "salesman_id"),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store. `price_lists` and `commission_rules` are the
    #: precedent.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: Null on both means the firm's own number for the period.
    salesman_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    territory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )
    #: The window this target covers, given rather than derived: a firm's
    #: quarter does not always start where the calendar's does, and a period
    #: computed from a name would be wrong for every firm whose year starts in
    #: April.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    #: MONTHLY, QUARTERLY or YEARLY. A label for reading and grouping; the
    #: dates above are what is actually measured.
    period_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MONTHLY", server_default="MONTHLY"
    )
    #: INVOICED or COLLECTED -- what a firm counts as having been sold.
    basis: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INVOICED", server_default="INVOICED"
    )
    target_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
