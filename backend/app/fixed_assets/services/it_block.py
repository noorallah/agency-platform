"""The Income-tax block schedule (s.32, PG-13): a view that posts nothing.

Income tax does not depreciate an asset; it depreciates a **block** -- every
asset carrying the same rate -- on its written-down value:

* opening WDV + additions - sale proceeds of what left the block, then
* depreciation at the block rate, **half** the rate on an addition put to use
  for less than 180 days in the year (the second proviso to s.32(1)(ii)).

Proceeds beyond what the block holds leave it at nil, and the excess is a
short-term capital gain (s.50) with no depreciation that year.

The years are the firm's own: the schedule is replayed year by year from the
earliest asset to the one asked for, each year starting on the same day and
month as that one. An opening asset joins its block's opening WDV in the year
after its ``opening_as_of``, at its own Income-tax WDV.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.core.utils.money import ZERO, quantize_ledger

#: Days of use below which an addition takes half the rate.
HALF_RATE_BELOW_DAYS = 180
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class BlockAsset:
    """One asset as the Income-tax book sees it."""

    block_rate: Decimal
    class_name: str
    put_to_use_date: date
    cost: Decimal
    #: The day an opening asset joins the block's opening WDV, or None for an
    #: asset bought here, which is an addition in its year.
    opening_from: date | None = None
    opening_wdv: Decimal = ZERO
    disposed_on: date | None = None
    sale_amount: Decimal = ZERO


@dataclass
class ItBlockRow:
    """One block's movement over one financial year."""

    block_rate: Decimal
    class_names: list[str] = field(default_factory=list)
    opening_wdv: Decimal = ZERO
    #: Put to use for 180 days or more in the year: the full rate.
    additions_full_rate: Decimal = ZERO
    #: Put to use for less than 180 days in the year: half the rate.
    additions_half_rate: Decimal = ZERO
    additions: Decimal = ZERO
    #: Sale proceeds of what left the block.
    disposals: Decimal = ZERO
    depreciation_full_rate: Decimal = ZERO
    depreciation_half_rate: Decimal = ZERO
    depreciation: Decimal = ZERO
    closing_wdv: Decimal = ZERO
    short_term_capital_gain: Decimal = ZERO


def year_start(on: date, anchor: date) -> date:
    """Return the start of the firm's year holding ``on``."""
    start = anchor.replace(year=on.year)
    return start if start <= on else anchor.replace(year=on.year - 1)


def year_end(start: date) -> date:
    """Return the last day of the year starting ``start``."""
    return date.fromordinal(start.replace(year=start.year + 1).toordinal() - 1)


def it_block_schedule(
    assets: list[BlockAsset], *, year_starts_on: date
) -> list[ItBlockRow]:
    """Return each block's movement over the year starting ``year_starts_on``.

    Args:
        assets: Every asset the firm holds or held, opening ones included.
        year_starts_on: The first day of the financial year asked for.

    Returns:
        One row per block rate with any movement or balance, highest rate
        first; every amount rounded to the paisa.

    """
    by_rate: dict[Decimal, list[BlockAsset]] = defaultdict(list)
    for asset in assets:
        if asset.block_rate > ZERO:
            by_rate[asset.block_rate].append(asset)
    rows: list[ItBlockRow] = []
    for rate in sorted(by_rate, reverse=True):
        members = by_rate[rate]
        first = min(
            year_start(asset.opening_from or asset.put_to_use_date, year_starts_on)
            for asset in members
        )
        wdv = ZERO
        start = first
        row = ItBlockRow(block_rate=rate)
        while start <= year_starts_on:
            row = _replay_year(rate, members, start=start, opening=wdv)
            wdv = row.closing_wdv
            start = start.replace(year=start.year + 1)
        if any(
            value != ZERO
            for value in (
                row.opening_wdv,
                row.additions,
                row.disposals,
                row.closing_wdv,
            )
        ):
            row.class_names = sorted({asset.class_name for asset in members})
            rows.append(row)
    return rows


def _replay_year(
    rate: Decimal, members: list[BlockAsset], *, start: date, opening: Decimal
) -> ItBlockRow:
    """Return one block's year, starting from the WDV it closed the last at."""
    end = year_end(start)
    row = ItBlockRow(block_rate=rate, opening_wdv=opening)
    for asset in members:
        if asset.opening_from is not None:
            if start <= asset.opening_from <= end:
                row.opening_wdv += asset.opening_wdv
        elif start <= asset.put_to_use_date <= end:
            used = (end - asset.put_to_use_date).days + 1
            if used < HALF_RATE_BELOW_DAYS:
                row.additions_half_rate += asset.cost
            else:
                row.additions_full_rate += asset.cost
        if asset.disposed_on is not None and start <= asset.disposed_on <= end:
            row.disposals += asset.sale_amount
    row.additions = row.additions_full_rate + row.additions_half_rate
    full_base = row.opening_wdv + row.additions_full_rate - row.disposals
    half_base = row.additions_half_rate
    if full_base < ZERO:
        half_base += full_base
        full_base = ZERO
    if half_base < ZERO:
        # The proceeds took more than the block held: it is nil, nothing is
        # depreciated, and the excess is a short-term capital gain.
        row.short_term_capital_gain = quantize_ledger(-half_base)
        row.closing_wdv = ZERO
    else:
        row.depreciation_full_rate = quantize_ledger(full_base * rate / HUNDRED)
        row.depreciation_half_rate = quantize_ledger(half_base * rate / 2 / HUNDRED)
        row.depreciation = row.depreciation_full_rate + row.depreciation_half_rate
        row.closing_wdv = quantize_ledger(
            row.opening_wdv + row.additions - row.disposals - row.depreciation
        )
    for name in (
        "opening_wdv",
        "additions_full_rate",
        "additions_half_rate",
        "additions",
        "disposals",
    ):
        setattr(row, name, quantize_ledger(getattr(row, name)))
    return row
