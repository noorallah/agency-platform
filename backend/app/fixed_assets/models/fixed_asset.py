"""Fixed assets: classes, the register and depreciation (PG-13, backlog 86 #7)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType

_MONEY = Numeric(18, 2)
_RATE = Numeric(9, 4)


class AssetClass(BaseEntity):
    """A kind of asset and how it is depreciated in each book.

    The Companies Act book (Schedule II) uses ``depreciation_method`` -- ``SLM``
    on the useful life (or a rate), or ``WDV`` at a rate -- down to the
    residual value. The Income-tax book (s.32) pools every asset of a rate into
    one block depreciated at ``it_block_rate_percent``. The three accounts are
    overrides; left empty, the firm's control accounts for fixed-asset cost,
    accumulated depreciation and depreciation expense are used.
    """

    __tablename__ = "asset_classes"
    __table_args__ = (
        Index(
            "UQ_asset_classes_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: ``SLM`` or ``WDV``.
    depreciation_method: Mapped[str] = mapped_column(String(10), nullable=False)
    #: A year's depreciation, percent: of cost under SLM, of the written-down
    #: value under WDV. Under SLM a useful life takes precedence.
    rate_percent: Mapped[Decimal | None] = mapped_column(_RATE)
    useful_life_years: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    #: What is left at the end of the life, percent of cost (Schedule II: 5).
    residual_percent: Mapped[Decimal] = mapped_column(
        _RATE, nullable=False, default=0, server_default="0"
    )
    #: The Income-tax block rate (15 plant, 10 furniture, 40 computers).
    it_block_rate_percent: Mapped[Decimal] = mapped_column(
        _RATE, nullable=False, default=0, server_default="0"
    )
    asset_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    accumulated_depreciation_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    depreciation_expense_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    description: Mapped[str | None] = mapped_column(Text)


class FixedAsset(BaseEntity):
    """One asset on the register.

    Raised by approving a purchase bill whose line is marked capital goods, or
    typed by hand -- an asset the firm already held when it started here (an
    *opening* asset, with the depreciation charged before ``opening_as_of``)
    or one bought outside a bill. ``ACTIVE`` until disposed; the status moves
    only through the disposal endpoint.
    """

    __tablename__ = "fixed_assets"
    __table_args__ = (
        Index("IX_fixed_assets_firm_class", "firm_id", "asset_class_id"),
        Index("IX_fixed_assets_firm_status", "firm_id", "status"),
        Index("IX_fixed_assets_invoice", "purchase_invoice_id"),
        Index(
            "UQ_fixed_assets_number_active",
            "firm_id",
            "asset_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    asset_number: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_class_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("asset_classes.id", ondelete="RESTRICT"), nullable=False
    )
    #: The bill and line that raised it, as bare ids; empty when typed by hand.
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(UUIDType())
    purchase_invoice_line_id: Mapped[UUID | None] = mapped_column(UUIDType())
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Depreciation runs from this day in both books.
    put_to_use_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=1, server_default="1"
    )
    cost: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    residual_value: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    #: Companies Act depreciation charged before the firm started here, up to
    #: and including ``opening_as_of``. Zero for an asset bought here.
    opening_accumulated_depreciation: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    opening_as_of: Mapped[date | None] = mapped_column(Date)
    #: The asset's Income-tax written-down value at ``opening_as_of``; empty
    #: takes cost less the opening depreciation.
    opening_it_wdv: Mapped[Decimal | None] = mapped_column(_MONEY)
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    location: Mapped[str | None] = mapped_column(String(200))
    #: ``ACTIVE`` or ``DISPOSED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    disposed_on: Mapped[date | None] = mapped_column(Date)
    sale_amount: Mapped[Decimal | None] = mapped_column(_MONEY)
    #: ``CASH`` or ``BANK``: where the sale money went.
    disposal_method: Mapped[str | None] = mapped_column(String(10))
    disposal_reason: Mapped[str | None] = mapped_column(Text)
    #: Sale money less book value: positive a gain, negative a loss.
    disposal_gain_loss: Mapped[Decimal | None] = mapped_column(_MONEY)
    disposal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class DepreciationRun(BaseEntity):
    """One posting of Companies Act depreciation for a period.

    ``PERIODIC`` runs cover every active asset for the period and never
    overlap; a ``DISPOSAL`` run charges one asset up to the day it was sold.
    ``POSTED`` until cancelled, which reverses its journal.
    """

    __tablename__ = "depreciation_runs"
    __table_args__ = (
        Index("IX_depreciation_runs_firm_period", "firm_id", "period_from"),
        Index(
            "UQ_depreciation_runs_number_active",
            "firm_id",
            "run_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    run_number: Mapped[str] = mapped_column(String(30), nullable=False)
    #: ``PERIODIC`` or ``DISPOSAL``.
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)
    #: ``COMPANIES_ACT``: the only book that posts.
    book: Mapped[str] = mapped_column(String(20), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    #: ``POSTED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")
    total_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=0, server_default="0"
    )
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class DepreciationRunLine(BaseEntity):
    """What one run charged one asset, and over which days."""

    __tablename__ = "depreciation_run_lines"
    __table_args__ = (
        Index("IX_depreciation_run_lines_run", "depreciation_run_id"),
        Index("IX_depreciation_run_lines_asset", "fixed_asset_id", "to_date"),
    )

    depreciation_run_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("depreciation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    fixed_asset_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("fixed_assets.id", ondelete="RESTRICT"), nullable=False
    )
    asset_class_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("asset_classes.id", ondelete="RESTRICT"), nullable=False
    )
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Book value at ``from_date``, before this charge.
    opening_book_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
