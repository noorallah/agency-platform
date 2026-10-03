"""Monthly or quarterly GST filing, and what each period owes when (GST-7).

A firm with aggregate turnover up to 5 crore may join QRMP (rule 61A): it
files GSTR-1 and GSTR-3B once a quarter and pays tax every month. The firm
says so in its GST settings (``filing_frequency``, and the first quarter it
applies from); the platform never guesses, because the option is exercised
on the portal, quarter by quarter.

What changes for a quarterly period, by notification 76/2020-CT and 83/2020:

* **GSTR-1** for the quarter, due the 13th of the month after it. B2B
  invoices of months 1 and 2 may be furnished early on the **IFF** (due the
  13th of the next month, optional, up to 50 lakh a month); those are not
  repeated in the quarter's GSTR-1.
* **PMT-06** by the 25th of the next month for months 1 and 2: 35% of the
  cash paid for the last quarter (fixed sum), or the month's tax less its
  credit (self-assessment).
* **GSTR-3B** for the quarter, due the 22nd of the month after it in the
  states of category X and the 24th everywhere else.

Months before the first quarterly quarter are monthly, so a firm that joins
QRMP keeps the history it filed monthly.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.tax.services.gst_compliance import GstComplianceService

MONTHLY = "MONTHLY"
QUARTERLY = "QUARTERLY"
FIXED_SUM = "FIXED_SUM"
SELF_ASSESSMENT = "SELF_ASSESSMENT"

#: GST state codes whose quarterly GSTR-3B is due on the 22nd (category X of
#: notification 76/2020-CT): Chhattisgarh, Madhya Pradesh, Gujarat, Daman and
#: Diu, Dadra and Nagar Haveli, Maharashtra, Karnataka, Goa, Lakshadweep,
#: Kerala, Tamil Nadu, Puducherry, Andaman and Nicobar, Telangana, Andhra
#: Pradesh. Every other state and territory is due on the 24th.
DUE_ON_22ND = frozenset(
    {
        "22",
        "23",
        "24",
        "25",
        "26",
        "27",
        "29",
        "30",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
    }
)
#: Days of the month after the period each item falls due.
MONTHLY_GSTR1_DAY = 11
MONTHLY_GSTR3B_DAY = 20
QUARTERLY_GSTR1_DAY = 13
IFF_DAY = 13
PMT06_DAY = 25
#: The most B2B value one month's IFF may carry (rule 59(2) proviso).
IFF_MONTHLY_LIMIT = 5_000_000


def month_of(day: date) -> str:
    """Return the ``YYYY-MM`` month a day falls in."""
    return f"{day.year:04d}-{day.month:02d}"


def month_bounds(month: str) -> tuple[date, date]:
    """Return the first and last day of a ``YYYY-MM`` month."""
    try:
        year, number = (int(part) for part in month.split("-"))
        first = date(year, number, 1)
    except ValueError as error:
        raise ValidationError("A return period is a month, YYYY-MM.") from error
    following = date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1)
    return first, following - timedelta(days=1)


def shift(month: str, months: int) -> str:
    """Return the month ``months`` after (or before, negative) ``month``."""
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + (number - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def quarter_months(month: str) -> tuple[str, str, str]:
    """Return the three months of the quarter ``month`` falls in."""
    number = int(month.split("-")[1])
    first = shift(month, -((number - 1) % 3))
    return first, shift(first, 1), shift(first, 2)


def position_in_quarter(month: str) -> int:
    """Return 1, 2 or 3: where ``month`` falls in its quarter."""
    return (int(month.split("-")[1]) - 1) % 3 + 1


def quarter_label(month: str) -> str:
    """Name the quarter ``month`` falls in, e.g. ``Jul-Sep 2026``."""
    first, _, last = quarter_months(month)
    start, _ = month_bounds(first)
    end, _ = month_bounds(last)
    return f"{start:%b}-{end:%b} {end.year}"


def _day_after(month: str, day: int) -> date:
    """Return day ``day`` of the month after ``month``."""
    _, last = month_bounds(month)
    after = last + timedelta(days=1)
    return date(after.year, after.month, day)


@dataclass(frozen=True, slots=True)
class FilingPlan:
    """How one firm files, and the dates that follow from it."""

    frequency: str
    quarterly_from: date | None
    payment_method: str
    #: The two-digit state code of the firm's GSTIN; empty if it has none.
    state_code: str

    def is_quarterly(self, month: str) -> bool:
        """Return whether ``month`` belongs to a quarter filed quarterly."""
        if self.frequency != QUARTERLY:
            return False
        if self.quarterly_from is None:
            return True
        return quarter_months(month)[0] >= month_of(self.quarterly_from)

    def return_period(self, month: str) -> str:
        """Return the period ``month``'s returns are filed under.

        The month itself for a monthly filer; the quarter's last month for a
        quarterly one, which is how a filing and a settlement name a quarter.
        """
        return quarter_months(month)[2] if self.is_quarterly(month) else month

    def span(self, return_period: str) -> tuple[date, date]:
        """Return the first and last day a return period covers."""
        if not self.is_quarterly(return_period):
            return month_bounds(return_period)
        first, _, last = quarter_months(return_period)
        return month_bounds(first)[0], month_bounds(last)[1]

    def gstr1_due(self, return_period: str) -> date:
        """Return GSTR-1's due date: the 11th, or the 13th for a quarter."""
        if self.is_quarterly(return_period):
            return _day_after(quarter_months(return_period)[2], QUARTERLY_GSTR1_DAY)
        return _day_after(return_period, MONTHLY_GSTR1_DAY)

    def gstr3b_due(self, return_period: str) -> date:
        """Return GSTR-3B's due date: the 20th, or the 22nd / 24th by state."""
        if not self.is_quarterly(return_period):
            return _day_after(return_period, MONTHLY_GSTR3B_DAY)
        day = 22 if self.state_code in DUE_ON_22ND else 24
        return _day_after(quarter_months(return_period)[2], day)

    @staticmethod
    def iff_due(month: str) -> date:
        """Return the IFF's due date: the 13th of the next month."""
        return _day_after(month, IFF_DAY)

    @staticmethod
    def pmt06_due(month: str) -> date:
        """Return the PMT-06 deposit's due date: the 25th of the next month."""
        return _day_after(month, PMT06_DAY)

    def require_deposit_month(self, month: str) -> None:
        """Refuse a PMT-06 deposit for a month that does not take one.

        Raises:
            ValidationError: For a monthly period, or a quarter's last month,
                whose tax is paid with the quarter's GSTR-3B.

        """
        if not self.is_quarterly(month):
            raise ValidationError(
                f"{month} is filed monthly: its tax is paid with its own "
                "GSTR-3B, not on PMT-06."
            )
        if position_in_quarter(month) == 3:
            raise ValidationError(
                f"{month} is the last month of {quarter_label(month)}: its tax "
                "is paid with the quarter's GSTR-3B, not on PMT-06."
            )

    def require_settlement_period(self, return_period: str) -> None:
        """Refuse settling a quarter's first two months on their own.

        Raises:
            ValidationError: For month 1 or 2 of a quarterly quarter.

        """
        if self.is_quarterly(return_period) and position_in_quarter(return_period) < 3:
            last = quarter_months(return_period)[2]
            raise ValidationError(
                f"{return_period} is filed quarterly: {quarter_label(return_period)}"
                f" is settled as {last}, and its first two months are paid on "
                "PMT-06."
            )


class FilingFrequencyService:
    """Read how a firm files."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store."""
        self._session = session

    def plan(self, firm_id: UUID) -> FilingPlan:
        """Return the firm's filing plan from its GST settings and GSTIN."""
        settings = GstComplianceService(self._session).settings_response(firm_id)
        gstin = (
            FirmMetadataReader(self._session).get(firm_id).gst_number or ""
        ).strip()
        return FilingPlan(
            frequency=settings.filing_frequency,
            quarterly_from=settings.quarterly_from,
            payment_method=settings.qrmp_payment_method,
            state_code=gstin[:2],
        )


__all__ = [
    "FIXED_SUM",
    "IFF_MONTHLY_LIMIT",
    "MONTHLY",
    "QUARTERLY",
    "SELF_ASSESSMENT",
    "FilingFrequencyService",
    "FilingPlan",
    "month_bounds",
    "month_of",
    "position_in_quarter",
    "quarter_label",
    "quarter_months",
    "shift",
]
