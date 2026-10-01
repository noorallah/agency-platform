"""A buyer's GST standing, and what it changes about a sale (backlog 75 row 2).

Customers carried a GSTIN and INDIVIDUAL / BUSINESS and nothing else, so a
supply to a Special Economic Zone, a deemed export or a buyer abroad was billed
and returned exactly like any other: charged CGST and SGST when the SEZ unit
sat in the firm's own state, filed in B2B as a regular invoice, registered on
the e-invoice portal as B2B. ``customers.gst_registration_type`` is the marker
the e-invoice builder said no customer carried.

NULL keeps every existing customer as it was: a GSTIN reads as REGULAR, none as
UNREGISTERED. What each type changes:

* **SEZ_WITH_PAYMENT / SEZ_WITHOUT_PAYMENT** -- a supply to an SEZ is
  inter-state wherever the unit is (IGST Act section 7(5)(b)), so it is
  charged IGST; GSTR-1 files it in B2B as SEWP / SEWOP; the e-invoice is
  SEZWP / SEZWOP. Without payment means under a bond or LUT, where no tax is
  charged -- a bill that charges some is warned about, not refused, because
  whether the LUT covers this supply is the firm's to know.
* **DEEMED_EXPORT** -- taxed normally, filed in B2B as DE, e-invoice DEXP.
* **OVERSEAS** -- an export: GSTR-1's EXP table (WPAY / WOPAY by whether IGST
  was charged), e-invoice EXPWP / EXPWOP. A foreign address already made the
  place of supply 96; this says so when the address does not.
* **COMPOSITION** -- billed and filed as a regular registered buyer; recorded
  because the buyer cannot take credit, which a firm's salesmen should know.
"""

from decimal import Decimal
from typing import Literal

from app.core.exceptions import ValidationError

GstRegistrationType = Literal[
    "REGULAR",
    "COMPOSITION",
    "UNREGISTERED",
    "SEZ_WITH_PAYMENT",
    "SEZ_WITHOUT_PAYMENT",
    "DEEMED_EXPORT",
    "OVERSEAS",
]

SEZ_TYPES = frozenset({"SEZ_WITH_PAYMENT", "SEZ_WITHOUT_PAYMENT"})
#: Types that only a registered buyer can be, so they need a GSTIN.
NEEDS_GSTIN = frozenset({"REGULAR", "COMPOSITION", "DEEMED_EXPORT"} | SEZ_TYPES)
#: Types that cannot carry a GSTIN.
NO_GSTIN = frozenset({"UNREGISTERED", "OVERSEAS"})

#: Zero-rated under IGST Act section 16: GSTR-3B Table 3.1(b).
ZERO_RATED_TYPES = SEZ_TYPES | {"OVERSEAS"}

#: GSTR-1's B2B invoice type by registration type; anything else is "R".
GSTR1_INVOICE_TYPES: dict[str, str] = {
    "SEZ_WITH_PAYMENT": "SEWP",
    "SEZ_WITHOUT_PAYMENT": "SEWOP",
    "DEEMED_EXPORT": "DE",
}


def effective_type(declared: str | None, gst_number: str | None) -> str:
    """Return the type a customer is treated as; NULL is read off the GSTIN."""
    if declared:
        return declared
    return "REGULAR" if (gst_number or "").strip() else "UNREGISTERED"


def assert_consistent(declared: str | None, gst_number: str | None) -> None:
    """Refuse a type the GSTIN contradicts, naming both."""
    if declared is None:
        return
    has_gstin = bool((gst_number or "").strip())
    if declared in NEEDS_GSTIN and not has_gstin:
        raise ValidationError(
            f"A {declared.replace('_', ' ').lower()} customer must have a GST "
            "number."
        )
    if declared in NO_GSTIN and has_gstin:
        raise ValidationError(
            f"An {declared.lower()} customer cannot have a GST number; clear it "
            "or choose the registered type."
        )


def sez_tax_warning(
    customer: object | None, tax_total: object
) -> tuple[str | None, dict[str, object] | None]:
    """Say so when a bill to an SEZ unit under an LUT charges tax.

    Warned, not refused: whether the LUT covers this supply is the firm's to
    know. Returns the remark and the event details, or nothing.
    """
    if customer is None:
        return None, None
    if getattr(customer, "gst_registration_type", None) != "SEZ_WITHOUT_PAYMENT":
        return None, None
    tax = Decimal(str(tax_total or 0))
    if tax <= 0:
        return None, None
    name = getattr(customer, "display_name", None) or "The customer"
    return (
        f"{name} is an SEZ unit supplied without payment of tax (under an "
        f"LUT), yet this bill charges {tax} tax.",
        {"sez_tax_warning": {"tax_total": str(tax)}},
    )
