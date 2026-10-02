"""No B2B invoice leaves the firm without its IRN (backlog 77 row 6, A43).

CGST rule 48(4): once a firm must e-invoice, an invoice to a registered buyer
that was not reported to the IRP is not an invoice at all. Rule 48(5) says so
outright, and rule 46 makes the IRN and signed QR part of the document. So an
invoice -- and a credit or debit note against one, which the IRP registers the
same way -- may be neither printed nor sent until it has a live registration.

What is judged is the same as what decides whether the firm registers it at
all (``must_einvoice``): the firm's dated *e-invoicing applies* setting and a
buyer with a GSTIN. A consumer's bill, a document dated before the setting, a
draft and a cancelled document are never held -- the last two already print
under a banner saying they are no tax invoice.

The refusal offers a way out rather than a dead end: a *reference copy*, which
prints with a banner saying it is not a valid tax invoice, for checking the
figures or showing a customer before the portal answers. That is what India
Compliance (ERPNext) and Zoho Books do: the invoice prints, marked, until the
IRN arrives; neither lets the unmarked original out first.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError
from app.customers.models import Customer

#: ``details.reason`` on the refusal, so a client can offer the reference copy
#: without reading the sentence.
IRN_REQUIRED = "irn_required"

#: What a reference copy says across its top.
REFERENCE_COPY_BANNER = "NO IRN YET - NOT A VALID TAX INVOICE"

#: Statuses that already print as no tax invoice, so are never held.
_NOT_ISSUED = {"DRAFT", "CANCELLED"}


def must_einvoice(
    session: Session, *, firm_scope: UUID, on: date, customer_id: UUID
) -> date | None:
    """Return the date the firm e-invoices from, if a document must be registered.

    None when the firm does not e-invoice, the document is dated before it
    had to, or the buyer has no GSTIN.
    """
    from app.tax.services.gst_compliance import GstComplianceService

    since = (
        GstComplianceService(session).settings_response(firm_scope)
    ).einvoice_applicable_from
    if since is None or on < since:
        return None
    customer = session.get(Customer, customer_id)
    if not (getattr(customer, "gst_number", None) or "").strip():
        return None
    return since


def has_live_irn(
    session: Session,
    *,
    firm_scope: UUID,
    sales_invoice_id: UUID | None = None,
    credit_note_id: UUID | None = None,
    customer_debit_note_id: UUID | None = None,
) -> bool:
    """Whether one document carries a REGISTERED registration with an IRN."""
    from app.einvoice.models import EInvoiceRegistration

    column, value = next(
        (column, value)
        for column, value in (
            (EInvoiceRegistration.sales_invoice_id, sales_invoice_id),
            (EInvoiceRegistration.credit_note_id, credit_note_id),
            (EInvoiceRegistration.customer_debit_note_id, customer_debit_note_id),
        )
        if value is not None
    )
    irn = session.scalar(
        select(EInvoiceRegistration.irn).where(
            EInvoiceRegistration.firm_id == firm_scope,
            column == value,
            EInvoiceRegistration.status == "REGISTERED",
            EInvoiceRegistration.is_deleted.is_(False),
        )
    )
    return bool(irn)


def missing_irn(
    session: Session,
    *,
    firm_scope: UUID,
    number: str,
    on: date,
    customer_id: UUID,
    status: str,
    sales_invoice_id: UUID | None = None,
    credit_note_id: UUID | None = None,
    customer_debit_note_id: UUID | None = None,
) -> str | None:
    """Say why a document may not go out yet, or None when it may.

    Args:
        session: The firm's store.
        firm_scope: The owning firm.
        number: The document's number, for the sentence.
        on: The document's own date.
        customer_id: The buyer.
        status: The document's status.
        sales_invoice_id: The invoice, when the document is one.
        credit_note_id: The credit note, when the document is one.
        customer_debit_note_id: The debit note, when the document is one.

    """
    if status in _NOT_ISSUED:
        return None
    since = must_einvoice(
        session, firm_scope=firm_scope, on=on, customer_id=customer_id
    )
    if since is None:
        return None
    if has_live_irn(
        session,
        firm_scope=firm_scope,
        sales_invoice_id=sales_invoice_id,
        credit_note_id=credit_note_id,
        customer_debit_note_id=customer_debit_note_id,
    ):
        return None
    return (
        f"{number} has no IRN yet. The firm e-invoices from {since:%d %b %Y} and "
        "the buyer is registered for GST, so it is not a valid tax invoice "
        "until it is registered on the portal (CGST rule 48(4)). Register it "
        "under E-invoice first, or print a reference copy marked not valid."
    )


def refuse_without_irn(reason: str | None) -> None:
    """Raise the refusal a client can recognise, when there is a reason.

    Raises:
        BusinessRuleError: When ``reason`` is not None.

    """
    if reason is not None:
        raise BusinessRuleError(reason, details={"reason": IRN_REQUIRED})
