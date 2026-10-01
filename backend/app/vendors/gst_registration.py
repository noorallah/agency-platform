"""A supplier's GST standing, and what it changes about a purchase (78 row 2).

Suppliers carried a GSTIN and a registered yes/no and nothing else, so a
purchase from a composition dealer or an unregistered shop was taxed by the
firm's rules like any other -- and its credit claimed -- though such a supplier
charges no GST at all: a composition dealer issues a bill of supply (CGST Act
s.10(4)), an unregistered one cannot charge tax, and goods from abroad carry
IGST on the bill of entry, not on the supplier's invoice.

``vendors.gst_registration_type`` is the marker, as customers carry one
(``app/customers/gst_registration.py``). NULL keeps every existing supplier as
it was: a GSTIN reads as REGULAR, none as UNREGISTERED. What each type changes:

* **REGULAR** -- taxed by the firm's rules, credit claimable.
* **COMPOSITION, UNREGISTERED, OVERSEAS**, when **declared** -- the supplier
  charges no GST, so a purchase document's lines carry none and no credit is
  claimed. A tax rule's *Reverse charge* still applies: then the firm owes the
  tax itself. A NULL type never drops tax, even with no GSTIN on file: a
  GSTIN nobody typed in does not make a supplier unregistered (A37).
* **SEZ** -- an SEZ unit supplying the firm is taxed as an inter-state supply
  under the firm's rules.

The type also reaches the tax engine as ``vendor_type``, so a rule can be
written against it.
"""

from typing import Literal

from app.core.exceptions import ValidationError

SupplierGstType = Literal["REGULAR", "COMPOSITION", "UNREGISTERED", "OVERSEAS", "SEZ"]

#: Suppliers who charge no GST on their own bill.
CHARGES_NO_TAX = frozenset({"COMPOSITION", "UNREGISTERED", "OVERSEAS"})
#: Types only a registered supplier can be, so they need a GSTIN.
NEEDS_GSTIN = frozenset({"REGULAR", "COMPOSITION", "SEZ"})
#: Types that cannot carry a GSTIN.
NO_GSTIN = frozenset({"UNREGISTERED", "OVERSEAS"})


def effective_type(declared: str | None, gstin: str | None) -> str:
    """Return the type a supplier is treated as; NULL is read off the GSTIN."""
    if declared:
        return declared
    return "REGULAR" if (gstin or "").strip() else "UNREGISTERED"


def assert_consistent(declared: str | None, gstin: str | None) -> None:
    """Refuse a type the GSTIN contradicts, naming both.

    Raises:
        ValidationError: When a registered type has no GSTIN, or an
            unregistered or overseas supplier has one.

    """
    if declared is None:
        return
    has_gstin = bool((gstin or "").strip())
    if declared in NEEDS_GSTIN and not has_gstin:
        raise ValidationError(f"A {declared.lower()} supplier must have a GST number.")
    if declared in NO_GSTIN and has_gstin:
        raise ValidationError(
            f"An {declared.lower()} supplier cannot have a GST number; clear it "
            "or choose the registered type."
        )
