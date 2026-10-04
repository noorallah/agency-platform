"""Contracts for fixed assets (PG-13, backlog 86 #7)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FixedAssetSchema(BaseModel):
    """Base contract: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


def _rate(default: Decimal | None) -> Any:  # noqa: ANN401 -- a pydantic Field
    """Return a percent field from 0 to 100."""
    return Field(default=default, ge=0, le=100, max_digits=9, decimal_places=4)


# -- classes -------------------------------------------------------------------
class AssetClassCreate(FixedAssetSchema):
    """A kind of asset and how each book depreciates it.

    ``SLM`` needs a useful life or a rate; ``WDV`` a rate, or a life and a
    residual percent to derive one from. The three accounts are overrides of
    the firm's fixed-asset control accounts; left out, those are used.
    """

    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    depreciation_method: Literal["SLM", "WDV"]
    rate_percent: Decimal | None = _rate(None)
    useful_life_years: Decimal | None = Field(
        default=None, gt=0, le=200, max_digits=6, decimal_places=2
    )
    residual_percent: Decimal = _rate(Decimal("5"))
    it_block_rate_percent: Decimal = _rate(Decimal("0"))
    asset_account_id: UUID | None = None
    accumulated_depreciation_account_id: UUID | None = None
    depreciation_expense_account_id: UUID | None = None
    is_active: bool = True
    description: str | None = Field(default=None, max_length=2000)


class AssetClassUpdate(FixedAssetSchema):
    """Change a class; a field left out is left alone, ``null`` clears it.

    A change applies to depreciation charged from now on; what was charged
    stands.
    """

    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    depreciation_method: Literal["SLM", "WDV"] | None = None
    rate_percent: Decimal | None = _rate(None)
    useful_life_years: Decimal | None = Field(
        default=None, gt=0, le=200, max_digits=6, decimal_places=2
    )
    residual_percent: Decimal | None = _rate(None)
    it_block_rate_percent: Decimal | None = _rate(None)
    asset_account_id: UUID | None = None
    accumulated_depreciation_account_id: UUID | None = None
    depreciation_expense_account_id: UUID | None = None
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=2000)


class AssetClassResponse(FixedAssetSchema):
    """One asset class."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    code: str
    name: str
    depreciation_method: str
    rate_percent: Decimal | None
    useful_life_years: Decimal | None
    residual_percent: Decimal
    it_block_rate_percent: Decimal
    asset_account_id: UUID | None
    accumulated_depreciation_account_id: UUID | None
    depreciation_expense_account_id: UUID | None
    is_active: bool
    description: str | None
    version: int


# -- assets --------------------------------------------------------------------
class FixedAssetCreate(FixedAssetSchema):
    """Put an asset on the register by hand.

    For one bought on a supplier bill, mark the bill line capital goods
    instead: approving the bill raises the asset. Typing one here books
    nothing -- its cost reached the ledger by the journal or the opening
    balance that brought it. An **opening** asset gives ``opening_as_of``:
    the depreciation charged up to that day, and its Income-tax WDV then.
    """

    name: str = Field(min_length=1, max_length=200)
    asset_class_id: UUID
    acquisition_date: date
    #: Left out, the acquisition date.
    put_to_use_date: date | None = None
    quantity: Decimal = Field(
        default=Decimal("1"), gt=0, max_digits=18, decimal_places=4
    )
    cost: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    #: Left out, the class's residual percent of cost.
    residual_value: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    opening_accumulated_depreciation: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=2
    )
    opening_as_of: date | None = None
    opening_it_wdv: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    location: str | None = Field(default=None, max_length=200)
    remarks: str | None = Field(default=None, max_length=2000)


class FixedAssetUpdate(FixedAssetSchema):
    """Change an active asset; a field left out is left alone.

    What depreciation is worked out from -- class, dates, cost, residual and
    the opening figures -- is fixed once a run has charged the asset. The
    status moves only by disposal.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_class_id: UUID | None = None
    acquisition_date: date | None = None
    put_to_use_date: date | None = None
    cost: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    residual_value: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    opening_accumulated_depreciation: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    opening_as_of: date | None = None
    opening_it_wdv: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    branch_id: UUID | None = None
    location: str | None = Field(default=None, max_length=200)
    remarks: str | None = Field(default=None, max_length=2000)


class FixedAssetDispose(FixedAssetSchema):
    """Sell or scrap an asset.

    Depreciation is charged up to ``disposal_date`` first. ``sale_amount``
    zero is a scrapping; otherwise the money is debited to the firm's cash or
    bank account by ``method``, as a payment's is.
    """

    disposal_date: date
    sale_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    method: Literal["CASH", "BANK"] = "BANK"
    reason: str = Field(min_length=1, max_length=1000)


class FixedAssetResponse(FixedAssetSchema):
    """One asset on the register, with where it stands."""

    id: UUID
    asset_number: str
    name: str
    asset_class_id: UUID
    asset_class_code: str
    asset_class_name: str
    purchase_invoice_id: UUID | None
    purchase_invoice_line_id: UUID | None
    purchase_invoice_number: str | None
    vendor_id: UUID | None
    acquisition_date: date
    put_to_use_date: date
    quantity: Decimal
    cost: Decimal
    residual_value: Decimal
    opening_accumulated_depreciation: Decimal
    opening_as_of: date | None
    opening_it_wdv: Decimal | None
    #: Opening depreciation plus every live charge (up to ``as_of`` if asked).
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    #: The last day depreciation has been charged to, if any.
    depreciated_to: date | None
    branch_id: UUID | None
    location: str | None
    status: str
    disposed_on: date | None
    sale_amount: Decimal | None
    disposal_method: str | None
    disposal_reason: str | None
    disposal_gain_loss: Decimal | None
    disposal_journal_entry_id: UUID | None
    remarks: str | None
    version: int


class ScheduleEntry(FixedAssetSchema):
    """One span of depreciation on an asset: charged, or still to come."""

    from_date: date
    to_date: date
    days: int
    opening_book_value: Decimal
    amount: Decimal
    accumulated_depreciation: Decimal
    closing_book_value: Decimal
    #: The run that charged it; None on a projected span.
    depreciation_run_id: UUID | None = None
    run_number: str | None = None
    projected: bool = False


class FixedAssetSchedule(FixedAssetSchema):
    """An asset's Companies Act depreciation: what was charged, then by year."""

    fixed_asset_id: UUID
    asset_number: str
    depreciation_method: str
    cost: Decimal
    residual_value: Decimal
    opening_accumulated_depreciation: Decimal
    charged: list[ScheduleEntry]
    #: Each remaining financial year until the residual value is reached,
    #: worked out on today's class settings. Empty once disposed.
    projected: list[ScheduleEntry]


# -- runs ----------------------------------------------------------------------
class DepreciationRunCreate(FixedAssetSchema):
    """Charge Companies Act depreciation on every active asset for a period."""

    period_from: date
    period_to: date
    book: Literal["COMPANIES_ACT"] = "COMPANIES_ACT"
    remarks: str | None = Field(default=None, max_length=2000)


class DepreciationRunCancel(FixedAssetSchema):
    """Why a run is being taken back."""

    reason: str = Field(min_length=1, max_length=1000)


class DepreciationRunLineResponse(FixedAssetSchema):
    """What a run charged one asset."""

    id: UUID
    fixed_asset_id: UUID
    asset_number: str
    asset_name: str
    asset_class_id: UUID
    from_date: date
    to_date: date
    days: int
    opening_book_value: Decimal
    amount: Decimal


class DepreciationRunResponse(FixedAssetSchema):
    """One depreciation run and its lines."""

    id: UUID
    run_number: str
    run_type: str
    book: str
    period_from: date
    period_to: date
    status: str
    total_amount: Decimal
    journal_entry_id: UUID | None
    reversal_journal_entry_id: UUID | None
    posted_at: datetime | None
    remarks: str | None
    cancel_reason: str | None
    version: int
    lines: list[DepreciationRunLineResponse]


# -- the Income-tax block schedule ---------------------------------------------
class ItBlockScheduleRow(FixedAssetSchema):
    """One block's movement over the year (s.32), as Form 3CD clause 18 lists it."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    block_rate: Decimal
    class_names: list[str]
    opening_wdv: Decimal
    additions_full_rate: Decimal
    additions_half_rate: Decimal
    additions: Decimal
    disposals: Decimal
    depreciation_full_rate: Decimal
    depreciation_half_rate: Decimal
    depreciation: Decimal
    closing_wdv: Decimal
    short_term_capital_gain: Decimal


class ItBlockSchedule(FixedAssetSchema):
    """The Income-tax block schedule of one financial year."""

    financial_year_id: UUID
    starts_on: date
    ends_on: date
    blocks: list[ItBlockScheduleRow]
