"""Companies Act depreciation for one asset over a span of days (PG-13).

Schedule II, as Tally and ERPNext apply it:

* **SLM** -- a year's charge is ``(cost - residual) / useful life``; with no
  life, ``cost x rate``. The same every year.
* **WDV** -- a year's charge is ``rate x written-down value`` at the start of
  the span. With no rate the Schedule II formula derives one from the life:
  ``1 - (residual / cost) ** (1 / life)``.

A part year is charged **pro rata by days**, over a 365-day year, and the
charge never takes the book value below the residual value. Each charge is
rounded to the paisa on its own (``quantize_ledger``): the run's journal is the
sum of what was charged, not a figure rounded after summing.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.utils.money import ZERO, quantize_ledger

#: Days in the year a part-year charge is divided by.
YEAR_DAYS = Decimal("365")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class ChargeBasis:
    """What a charge is worked out from: the asset and its class's rule."""

    method: str
    cost: Decimal
    residual_value: Decimal
    rate_percent: Decimal | None
    useful_life_years: Decimal | None


def days_between(first: date, last: date) -> int:
    """Return the days from ``first`` to ``last``, both counted."""
    return (last - first).days + 1


def wdv_rate(basis: ChargeBasis) -> Decimal:
    """Return the WDV rate, percent: the class's, or derived from the life.

    Returns zero where neither can be had (no rate, and no life or no residual
    to derive one from), so such an asset is charged nothing rather than
    guessed at.
    """
    if basis.rate_percent is not None:
        return basis.rate_percent
    life = basis.useful_life_years
    if not life or life <= ZERO or basis.cost <= ZERO or basis.residual_value <= ZERO:
        return ZERO
    left = float(basis.residual_value / basis.cost) ** (1 / float(life))
    return (Decimal(str(1 - left)) * HUNDRED).quantize(Decimal("0.0001"))


def annual_slm(basis: ChargeBasis) -> Decimal:
    """Return a full year's straight-line charge."""
    life = basis.useful_life_years
    if life and life > ZERO:
        return (basis.cost - basis.residual_value) / life
    if basis.rate_percent is not None:
        return basis.cost * basis.rate_percent / HUNDRED
    return ZERO


def charge_for(basis: ChargeBasis, *, book_value: Decimal, days: int) -> Decimal:
    """Return the depreciation for ``days`` on an asset worth ``book_value``.

    Args:
        basis: The asset's cost, residual value and its class's rule.
        book_value: What the asset is carried at when the span starts:
            cost less every charge before it, opening depreciation included.
        days: Days in the span, both ends counted.

    Returns:
        The charge, rounded to the paisa, never taking the book value below
        the residual value and never negative.

    """
    room = book_value - basis.residual_value
    if days <= 0 or room <= ZERO:
        return ZERO
    if basis.method == "WDV":
        yearly = book_value * wdv_rate(basis) / HUNDRED
    else:
        yearly = annual_slm(basis)
    amount = quantize_ledger(yearly * Decimal(days) / YEAR_DAYS)
    return max(ZERO, min(amount, quantize_ledger(room)))
