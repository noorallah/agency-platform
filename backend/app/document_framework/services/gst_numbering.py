"""Which documents carry a GST serial number, and how long it may be (GST-2).

CGST rule 46(b) gives a tax invoice "a consecutive serial number not
exceeding sixteen characters, in one or multiple series, containing alphabets
or numerals or special characters hyphen or dash and slash", unique for a
financial year. Rules 53 (credit and debit notes) and 55 (delivery challans)
apply the same limit, and the IRP refuses a document number longer than 16.

The six types below are the ones this platform issues under those rules: the
tax invoice, the credit note, a sales return (the firm's credit note for
goods), the debit note to a customer, the delivery challan and the
reverse-charge self-invoice. Quotations, orders, proformas and the firm's own
vouchers are not GST documents and keep whatever length a firm likes.
"""

from __future__ import annotations

import re

#: The longest serial number rule 46(b) allows.
GST_NUMBER_LIMIT = 16

#: Document type codes numbered under rules 46, 53 and 55.
GST_NUMBERED_TYPES = frozenset(
    {
        "SALES_INVOICE",
        "CREDIT_NOTE",
        "SALES_RETURN",
        "CUSTOMER_DEBIT_NOTE",
        "DELIVERY_NOTE",
        "RCM_SELF_INVOICE",
    }
)

_ALLOWED = re.compile(r"^[A-Za-z0-9/-]+$")


def gst_number_problem(number: str) -> str | None:
    """Say what is wrong with ``number`` as a GST serial number, if anything.

    Args:
        number: A document number as it would print.

    Returns:
        A sentence naming the fault, or ``None`` when the number complies.

    """
    if len(number) > GST_NUMBER_LIMIT:
        return (
            f"{number!r} is {len(number)} characters long; a GST document "
            f"number may have at most {GST_NUMBER_LIMIT} (CGST rule 46(b))"
        )
    if not _ALLOWED.match(number):
        return (
            f"{number!r} uses a character a GST document number may not "
            "carry; only letters, digits, '-' and '/' are allowed (CGST rule "
            "46(b))"
        )
    return None


def short_year(label: str) -> str:
    """Return ``26-27`` for the label ``2026-2027``; anything else unchanged."""
    found = re.fullmatch(r"(\d{4})-(\d{4})", label)
    if found is None:
        return label
    return f"{found.group(1)[2:]}-{found.group(2)[2:]}"
