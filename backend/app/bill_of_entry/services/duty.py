"""The duty customs assesses on one line of a Bill of Entry (PG-12 part B).

Indian customs works a line out in this order:

* **basic customs duty** (BCD) on the assessable value;
* **social welfare surcharge** (SWS), 10% of the basic duty unless the tariff
  says otherwise;
* **IGST** on the assessable value plus BCD plus SWS -- the duty is part of
  what the tax is charged on;
* **compensation cess**, where the goods attract it, typed as an amount.

An amount is worked out from its rate only when it was not typed. A typed
amount wins: customs rounds per line, and the printed figure is what was paid.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.utils.money import ZERO, quantize_ledger

#: The surcharge a line takes when no rate is typed: 10% of the basic duty.
DEFAULT_SWS_RATE = Decimal("10")

_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class LineDuty:
    """One line's duty, every amount in rupees at two decimals."""

    bcd_amount: Decimal
    sws_rate: Decimal
    sws_amount: Decimal
    igst_base: Decimal
    igst_amount: Decimal
    cess_amount: Decimal

    @property
    def customs_duty(self) -> Decimal:
        """Return the cost part: basic duty plus surcharge, which earn no credit."""
        return self.bcd_amount + self.sws_amount

    @property
    def total_duty(self) -> Decimal:
        """Return everything customs collected on the line."""
        return self.customs_duty + self.igst_amount + self.cess_amount


def _of(base: Decimal, rate: Decimal | None) -> Decimal:
    """Return ``rate`` percent of ``base``, or zero with no rate."""
    if rate is None:
        return ZERO
    return quantize_ledger(base * rate / _HUNDRED)


def compute_line_duty(
    *,
    assessable_value: Decimal,
    bcd_rate: Decimal | None = None,
    bcd_amount: Decimal | None = None,
    sws_rate: Decimal | None = None,
    sws_amount: Decimal | None = None,
    igst_rate: Decimal | None = None,
    igst_amount: Decimal | None = None,
    cess_amount: Decimal | None = None,
) -> LineDuty:
    """Work a line's duty out; a typed amount beats its rate.

    Args:
        assessable_value: The customs value of the line, in rupees.
        bcd_rate: Basic customs duty, percent of the assessable value.
        bcd_amount: Basic customs duty as printed; wins over the rate.
        sws_rate: Surcharge, percent of the basic duty; None takes 10.
        sws_amount: Surcharge as printed; wins over the rate.
        igst_rate: IGST, percent of assessable value + BCD + SWS.
        igst_amount: IGST as printed; wins over the rate.
        cess_amount: Compensation cess as printed; zero when not given.

    Returns:
        The line's duty.

    """
    assessable = quantize_ledger(assessable_value)
    bcd = (
        quantize_ledger(bcd_amount)
        if bcd_amount is not None
        else _of(assessable, bcd_rate)
    )
    surcharge_rate = DEFAULT_SWS_RATE if sws_rate is None else sws_rate
    sws = (
        quantize_ledger(sws_amount)
        if sws_amount is not None
        else _of(bcd, surcharge_rate)
    )
    base = assessable + bcd + sws
    igst = (
        quantize_ledger(igst_amount)
        if igst_amount is not None
        else _of(base, igst_rate)
    )
    cess = quantize_ledger(cess_amount) if cess_amount is not None else ZERO
    return LineDuty(
        bcd_amount=bcd,
        sws_rate=surcharge_rate,
        sws_amount=sws,
        igst_base=base,
        igst_amount=igst,
        cess_amount=cess,
    )
