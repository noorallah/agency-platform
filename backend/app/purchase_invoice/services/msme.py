"""When a supplier's bill falls due, and when an MSME one must be paid.

Backlog 68 rows 1-2. A supplier now carries its days of credit, and a bill's
due date defaults from them when nobody typed one -- the way a customer's terms
already default a sales bill.

A **micro or small** enterprise (Udyam) must be paid within the period agreed
in writing, at most 45 days, or within 15 days where nothing was agreed (MSMED
Act section 15). Income Tax section 43B(h) disallows, in the year, an expense
owed to one and not paid within that time -- so an unpaid bill past its date
costs the firm tax. A **medium** enterprise is outside both.

The period runs from the day the goods were accepted; the bill's own dates are
what the books hold, so the earlier of the supplier's invoice date and the
firm's bill date is used -- never later than the law's start.
"""

from datetime import date, timedelta

#: The categories the 45-day rule applies to.
MSME_RULE_CATEGORIES = frozenset({"MICRO", "SMALL"})
AGREED_LIMIT_DAYS = 45
UNAGREED_LIMIT_DAYS = 15


def _start(invoice_date: date, supplier_invoice_date: date | None) -> date:
    """Return the day the payment period runs from."""
    if supplier_invoice_date is not None and supplier_invoice_date < invoice_date:
        return supplier_invoice_date
    return invoice_date


def msme_pay_by(
    vendor: object | None,
    *,
    invoice_date: date,
    supplier_invoice_date: date | None,
) -> date | None:
    """Return the last day a bill to a micro or small supplier may be paid."""
    if vendor is None:
        return None
    if getattr(vendor, "msme_category", None) not in MSME_RULE_CATEGORIES:
        return None
    days = (
        AGREED_LIMIT_DAYS
        if getattr(vendor, "msme_written_agreement", False)
        else UNAGREED_LIMIT_DAYS
    )
    return _start(invoice_date, supplier_invoice_date) + timedelta(days=days)


def default_due_date(
    vendor: object | None, *, typed: date | None, invoice_date: date
) -> date | None:
    """Return the typed due date, else the bill date plus the supplier's terms."""
    if typed is not None:
        return typed
    terms = int(getattr(vendor, "payment_terms_days", 0) or 0)
    if terms <= 0:
        return None
    return invoice_date + timedelta(days=terms)


def msme_warning(
    *, pay_by: date | None, due_date: date | None, vendor_name: str
) -> str | None:
    """Say so when a bill to an MSME supplier is due after the law allows."""
    if pay_by is None:
        return None
    if due_date is not None and due_date <= pay_by:
        return None
    return (
        f"{vendor_name} is a micro or small enterprise: this bill must be paid "
        f"by {pay_by.isoformat()} (MSMED Act s.15), or the expense is disallowed "
        "this year under Income Tax s.43B(h)."
        + (
            f" Its due date is {due_date.isoformat()}."
            if due_date is not None
            else " It has no due date."
        )
    )
