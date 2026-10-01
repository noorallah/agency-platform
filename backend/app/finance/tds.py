"""Tax deducted at source: the sections a deduction is filed under.

Backlog 53.1 items 3 and 4. A deduction is filed in the quarterly return
(26Q for everything but salary) under the section of the Income-tax Act that
required it, so every deduction records one. The sections are the Act's and
change only with it; the **rates** and thresholds change every Finance Act,
so none of them is written here -- the person recording the payment states
the amount deducted, as the challan and the return will.
"""

from decimal import Decimal

ZERO = Decimal("0")

#: The sections a trading firm commonly deducts under, by code, with what each
#: covers in the words a firm's accountant uses. Codes are as the return names
#: them.
TDS_SECTIONS: dict[str, str] = {
    "194Q": "Purchase of goods",
    "194C": "Contractors and transporters",
    "194J": "Professional or technical fees",
    "194I": "Rent",
    "194H": "Commission or brokerage",
    "194A": "Interest other than on securities",
    "194R": "Benefits or perquisites of business",
    "194T": "Payments by a firm to its partners",
    "192": "Salary",
    "194O": "E-commerce operator",
}


def check_tds(amount: Decimal, tds_amount: Decimal | None, section: str | None) -> str:
    """Refuse a deduction that cannot be filed; return it as text for messages.

    Raises:
        ValueError: If a deduction has no section, the section is not one of
            ``TDS_SECTIONS``, a section is named with nothing deducted, or the
            deduction is not less than the amount it is deducted from.

    """
    deducted = tds_amount or ZERO
    if deducted < ZERO:
        raise ValueError("TDS deducted cannot be negative.")
    if deducted == ZERO:
        if section:
            raise ValueError("A TDS section was named but nothing was deducted.")
        return ""
    if not section:
        raise ValueError(
            "Name the TDS section the deduction is filed under, e.g. 194Q."
        )
    if section not in TDS_SECTIONS:
        raise ValueError(
            f"{section} is not a TDS section this firm files under. Use one of "
            + ", ".join(TDS_SECTIONS)
            + "."
        )
    if deducted >= amount:
        raise ValueError(
            "TDS deducted must be less than the amount it is deducted from."
        )
    return f"{deducted} under {section}"
