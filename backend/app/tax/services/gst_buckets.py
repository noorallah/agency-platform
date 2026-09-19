"""What a firm's tax components mean when a return is filed.

A GST return and an e-invoice both need one line's tax split into the buckets
the authority files under -- CGST, SGST, IGST and cess. That splitting is one
definition, not two: if a return and the document it reports disagreed about
which bucket a component belongs in, the firm would file one number and hold
another.

Matched on the **component code the document actually carried**, never on the
profile it was resolved from. A firm may rename a component next month, and
the supply was still taxed as whatever it said at the time.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.utils.money import ZERO, quantize_ledger, quantize_money

CGST = "CGST"
SGST = "SGST"
IGST = "IGST"
CESS = "CESS"


@dataclass(frozen=True, slots=True)
class TaxComponent:
    """One component as a document recorded it."""

    code: str
    percentage: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class GstBuckets:
    """One line's tax, in the buckets a return is filed under."""

    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    igst: Decimal = ZERO
    cess: Decimal = ZERO
    #: The GST rate the line was taxed at: nine plus nine is eighteen, which
    #: is what both the portal and the return want on the item. Cess is
    #: excluded, because it is reported separately and is often a flat sum
    #: rather than a rate.
    rate: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        """Return every bucket added together."""
        return quantize_money(self.cgst + self.sgst + self.igst + self.cess)

    def plus(self, other: "GstBuckets") -> "GstBuckets":
        """Return the sum of two sets of buckets.

        The rate is **not** added: two lines at 18% are still 18%, and adding
        them would report 36% on a summary row. Where rates differ the caller
        is grouping by rate already, which is what every GST summary does.
        """
        return GstBuckets(
            cgst=self.cgst + other.cgst,
            sgst=self.sgst + other.sgst,
            igst=self.igst + other.igst,
            cess=self.cess + other.cess,
            rate=self.rate or other.rate,
        )

    def negated(self) -> "GstBuckets":
        """Return the same buckets with every amount reversed.

        For a credit note netted off a summary row. The **rate is kept as it
        is** -- a credit at 18% is still a credit at 18%, and negating it
        would give the row a rate no supply was ever taxed at.

        Returns:
            The buckets with each amount's sign flipped.

        """
        return GstBuckets(
            cgst=-self.cgst,
            sgst=-self.sgst,
            igst=-self.igst,
            cess=-self.cess,
            rate=self.rate,
        )


def split_components(components: list[TaxComponent]) -> GstBuckets:
    """Split one line's components into the buckets a return is filed under.

    A component whose code names none of the four is ignored rather than
    guessed at: a firm may carry a local levy the return has no column for,
    and putting it in the wrong bucket is worse than leaving it out of a
    figure that is reconciled against the ledger anyway.

    Args:
        components: What the document recorded, code and all.

    Returns:
        The four buckets and the GST rate.

    """
    cgst = sgst = igst = cess = ZERO
    rate = ZERO
    for component in components:
        code = (component.code or "").strip().upper()
        amount = quantize_money(Decimal(str(component.amount)))
        if CGST in code:
            cgst += amount
        elif SGST in code:
            sgst += amount
        elif IGST in code:
            igst += amount
        elif CESS in code:
            cess += amount
        else:
            continue
        if CESS not in code:
            rate += Decimal(str(component.percentage))
    return GstBuckets(cgst=cgst, sgst=sgst, igst=igst, cess=cess, rate=rate)


def settle_to_ledger(lines: list[GstBuckets]) -> list[GstBuckets]:
    """Round one document's tax to paise so it adds to what the ledger credited.

    A document is priced at four decimals and the journal credits output tax
    **once, as the rounded sum** -- ``quantize_ledger`` of the document's tax.
    Rounding each bucket on its own instead declares 36.86 + 36.86 = 73.72 on
    a bill whose halves are 36.855 and whose journal credited 73.71 (D-CMP-4):
    rounding the sum is not rounding the parts.

    So every bucket of every line is rounded half up to paise, and whatever
    that leaves between their sum and the rounded document total -- never more
    than a paisa or two -- is put on the **last** bucket that carries tax: the
    last line's SGST on an intra-state bill, its IGST on an inter-state one,
    cess only where nothing else was charged.

    Args:
        lines: The document's lines, split into buckets at four decimals.

    Returns:
        The same lines at two decimals, adding up to the ledger's figure.

    """
    target = quantize_ledger(
        sum((line.cgst + line.sgst + line.igst + line.cess for line in lines), ZERO)
    )
    rounded = [
        GstBuckets(
            cgst=quantize_ledger(line.cgst),
            sgst=quantize_ledger(line.sgst),
            igst=quantize_ledger(line.igst),
            cess=quantize_ledger(line.cess),
            rate=line.rate,
        )
        for line in lines
    ]
    residual = target - sum(
        (line.cgst + line.sgst + line.igst + line.cess for line in rounded), ZERO
    )
    if residual == ZERO:
        return rounded
    for index in range(len(rounded) - 1, -1, -1):
        line = rounded[index]
        for bucket in ("igst", "sgst", "cgst", "cess"):
            # Judged on what was charged, not on what rounding left: a
            # quarter paisa rounds to nothing and still carried the tax.
            if getattr(lines[index], bucket) != ZERO:
                values = {
                    "cgst": line.cgst,
                    "sgst": line.sgst,
                    "igst": line.igst,
                    "cess": line.cess,
                }
                values[bucket] += residual
                rounded[index] = GstBuckets(rate=line.rate, **values)
                return rounded
    return rounded


def intra_state_halves(tax: Decimal) -> tuple[Decimal, Decimal]:
    """Split a tax charged within one state into CGST and SGST at paise.

    For a document that stores one tax figure rather than its components, such
    as a credit note. The halves add to the rounded whole -- what the journal
    credited -- with the odd paisa on SGST.

    Args:
        tax: The tax the document charged, at any scale.

    Returns:
        CGST and SGST, at two decimals, adding to ``quantize_ledger(tax)``.

    """
    whole = quantize_ledger(tax)
    central = quantize_ledger(Decimal(str(tax)) / 2)
    return central, whole - central
