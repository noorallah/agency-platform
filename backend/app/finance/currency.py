"""Foreign currency on a supplier's bill and its payment (PG-12 part A).

The books are kept in rupees. A bill from a foreign supplier is typed in the
supplier's currency and stored as entered; it carries the rate it was booked
at (rupees per unit), and every rupee figure the ledger needs is worked out
from it here, one leg at a time -- rounding the sum is not rounding the parts.

Blank and ``INR`` are both the firm's own currency: everything that existed
before this module reads as rupees and behaves exactly as it did.
"""

from decimal import Decimal

from app.core.exceptions import ValidationError
from app.core.utils.money import quantize_ledger

#: The currency the books are kept in. Every firm on the platform keeps GST
#: books, so this is rupees; a bill in it carries no rate.
BASE_CURRENCY = "INR"


def normalize_currency(code: str | None) -> str | None:
    """Return an ISO code in upper case, or None for blank."""
    if code is None:
        return None
    token = code.strip().upper()
    return token or None


def is_foreign(code: str | None) -> bool:
    """Say whether a currency is anything but the books' own."""
    normalized = normalize_currency(code)
    return normalized is not None and normalized != BASE_CURRENCY


def check_currency(code: str | None, rate: Decimal | None) -> None:
    """Refuse a foreign currency without a rate, or a code that is not ISO.

    Raises:
        ValidationError: If the code is not three letters, or a currency other
            than rupees has no rate above nothing.

    """
    normalized = normalize_currency(code)
    if normalized is None:
        return
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValidationError(
            f"{normalized} is not a currency code. Use the three-letter ISO "
            "code, such as USD or EUR.",
            details={"field": "currency_code"},
        )
    if normalized != BASE_CURRENCY and (rate is None or rate <= 0):
        raise ValidationError(
            f"A bill in {normalized} needs its exchange rate: the rupees one "
            f"{normalized} was worth on the bill's date.",
            details={"field": "exchange_rate"},
        )


def to_base(amount: Decimal, rate: Decimal) -> Decimal:
    """Return one leg in rupees at a rate, rounded to the ledger's scale."""
    return quantize_ledger(Decimal(amount) * Decimal(rate))
