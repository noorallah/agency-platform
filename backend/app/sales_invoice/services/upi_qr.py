"""The UPI QR a printed bill carries, so the customer can pay by scanning it.

The QR holds a ``upi://pay`` link in the form NPCI's UPI linking
specification sets out, which every UPI app reads: the payee's address and
name, the amount, the currency and a note. The note is the bill's number, so
the firm can match the money that arrives to the bill it paid (MSG-2, A55).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

#: A UPI app shows the note in one line and some truncate it; the bill number
#: fits well inside this.
_NOTE_LIMIT = 50


@dataclass(frozen=True, slots=True)
class UpiPayment:
    """What the bill asks for by UPI, already resolved."""

    upi_id: str
    amount: Decimal
    uri: str


def upi_payment(
    *, upi_id: str | None, payee: str, amount: Decimal, note: str
) -> UpiPayment | None:
    """Return the payment a bill's QR asks for, or None where it asks none.

    Args:
        upi_id: The firm's UPI ID; None or blank prints no QR.
        payee: The firm's name, which the paying app shows for confirmation.
        amount: What the bill still owes. Nothing owed asks for nothing.
        note: The bill's number, carried as the transaction note.

    Returns:
        The UPI ID, the amount and the link the QR encodes.

    """
    address = (upi_id or "").strip()
    if not address or amount <= 0:
        return None
    figure = amount.quantize(Decimal("0.01"))
    params = (
        ("pa", address),
        ("pn", payee.strip()[:99]),
        ("am", f"{figure:.2f}"),
        ("cu", "INR"),
        ("tn", note.strip()[:_NOTE_LIMIT]),
    )
    query = "&".join(f"{key}={quote(value, safe='@.-_')}" for key, value in params)
    return UpiPayment(upi_id=address, amount=figure, uri=f"upi://pay?{query}")
