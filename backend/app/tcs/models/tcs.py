"""What a seller collects from a buyer on the money the buyer pays.

Section 206C(1H) is unlike every other tax in this system, and the difference
decides the whole design: **it is charged on consideration received, not on
what was invoiced.** The statute says "at the time of receipt of such amount",
so the event that raises a liability here is a receipt, never an invoice being
approved. Putting it on the invoice -- which is what makes it look like just
another tax line -- collects it on money that may never arrive, and misses
money that arrives against an older bill.

Three more things the law says that are properties of the data, not of any one
calculation:

- **Only the excess counts.** The first fifty lakh a buyer pays in a financial
  year attracts nothing; a receipt straddling that line is charged on the part
  above it and no more.
- **The threshold is per buyer, per financial year**, and it resets. So the
  running total is scoped to both, and it is derived by summing the collections
  rather than kept as a counter -- a counter and a reversal are two chances to
  disagree, which is the rule `_resync_order_status` was rewritten for.
- **A seller below the turnover threshold collects nothing at all.** Whether a
  firm is above it is a fact the firm states, because its preceding year may
  predate its books here.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class TcsCollectionStatus(StrEnum):
    """Whether a collection still stands."""

    COLLECTED = "COLLECTED"
    #: The receipt it was charged on was reversed. The row stays rather than
    #: going away, because the quarterly return may already have reported it
    #: and a deletion leaves that filing unexplainable.
    REVERSED = "REVERSED"


class TcsSettings(BaseEntity):
    """One firm's 206C(1H) parameters.

    The rates and thresholds are columns rather than constants because a
    Finance Act sets them and has already changed them: the rate was
    concessionally 0.075% for part of 2020-21, and the section itself only
    began that October. A firm correcting a rate must not need a release.
    """

    __tablename__ = "tcs_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_tcs_settings_firm"),
        CheckConstraint("threshold_amount >= 0", name="CK_tcs_settings_threshold"),
        CheckConstraint(
            "rate_percent >= 0 AND rate_percent <= 100",
            name="CK_tcs_settings_rate",
        ),
        CheckConstraint(
            "rate_without_pan_percent >= 0 AND rate_without_pan_percent <= 100",
            name="CK_tcs_settings_rate_without_pan",
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store. `credit_control_settings` is the precedent.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: Which provision the row encodes. One section today, and the column says
    #: so rather than leaving the numbers to be recognised.
    section_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="206C_1H", server_default="206C_1H"
    )
    #: Off by default, so shipping this collects nothing from anybody until a
    #: firm says its turnover puts it in scope.
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: What one buyer may pay in a financial year before anything is collected.
    threshold_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("5000000"),
        server_default="5000000",
    )
    rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("0.1"), server_default="0.1"
    )
    #: A buyer who has not furnished a PAN is charged at the higher rate. That
    #: is section 206CC rather than 1H, but it is the same collection and
    #: belongs on the same row rather than in a second table nobody would find.
    rate_without_pan_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("1"), server_default="1"
    )
    #: What the firm turned over in the year before. Stated rather than
    #: derived: the preceding year may predate this system entirely, and a
    #: figure computed off a partial history would put a firm in or out of
    #: scope on the strength of data nobody migrated.
    preceding_year_turnover: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The turnover above which a seller is in scope at all.
    seller_turnover_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("100000000"),
        server_default="100000000",
    )


class TcsCollection(BaseEntity):
    """One receipt's worth of tax collected at source.

    Written when a receipt is recorded and mirrored when it is reversed. The
    figures that decided the amount are stored beside it -- what the buyer had
    already paid, what part of this receipt was above the threshold, the rate
    applied -- because the question asked of this table months later is "why is
    this number what it is", and re-deriving it against today's settings would
    answer about today.
    """

    __tablename__ = "tcs_collections"
    __table_args__ = (
        # One collection per receipt. A second would charge the same money
        # twice, and nothing would say which figure the buyer was given.
        UniqueConstraint("settlement_id", name="UQ_tcs_collections_settlement"),
        CheckConstraint("tcs_amount >= 0", name="CK_tcs_collections_amount"),
        CheckConstraint("taxable_amount >= 0", name="CK_tcs_collections_taxable"),
        Index("IX_tcs_collections_firm_customer", "firm_id", "customer_id"),
        Index("IX_tcs_collections_firm_year", "firm_id", "financial_year_start"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    settlement_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("settlements.id", ondelete="RESTRICT"), nullable=False
    )
    #: First day of the financial year the receipt falls in. The threshold
    #: resets with it, so it is part of the key the running total is summed
    #: over rather than something worked out from a date at read time.
    financial_year_start: Mapped[date] = mapped_column(Date, nullable=False)
    collected_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: The whole receipt, whatever part of it turned out to be chargeable.
    consideration_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    #: What the buyer had already paid this year before this receipt.
    cumulative_before: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The part of this receipt above the threshold.
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    #: True where the higher rate applied because no PAN was on record.
    without_pan: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    tcs_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TcsCollectionStatus.COLLECTED.value,
        server_default=TcsCollectionStatus.COLLECTED.value,
    )
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    receivable_transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())
