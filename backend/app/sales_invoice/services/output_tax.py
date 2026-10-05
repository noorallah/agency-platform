"""The output tax a sales document owes, per component (backlog 63.3).

Output tax was credited to one account, so the ledger could not say how much
CGST the firm owed without a report. The posting now splits it per GST head,
and these say what to split: the components the document's lines recorded,
exactly as GSTR-1 and 3B read them -- never re-derived from an address or
today's tax profile.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utils.money import ZERO, quantize_money
from app.sales_invoice.models import (
    SalesInvoiceCharge,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.tax.services.gst_buckets import (
    CESS,
    CGST,
    IGST,
    SGST,
    TaxComponent,
    intra_state_halves,
    split_components,
)


def invoice_tax_by_component(session: Session, invoice_id: UUID) -> dict[str, Decimal]:
    """Sum an invoice's charged tax per component code.

    Tax already inside a price is left out: the invoice's tax total does not
    add it, so neither does its posting. Empty for an invoice whose lines
    carry no components, and the posting then credits `OUTPUT_TAX` whole.

    The bill's separately taxed charges (SG-4) keep their tax by GST head
    rather than by component, so each head is added under its plain code --
    the code the posting maps to that head's account.
    """
    totals: dict[str, Decimal] = {}
    for code, amount in session.execute(
        select(
            SalesInvoiceLineTax.component_code,
            func.coalesce(func.sum(SalesInvoiceLineTax.amount), 0),
        )
        .join(
            SalesInvoiceLine,
            SalesInvoiceLine.id == SalesInvoiceLineTax.sales_invoice_line_id,
        )
        .where(
            SalesInvoiceLine.sales_invoice_id == invoice_id,
            SalesInvoiceLine.is_deleted.is_(False),
            SalesInvoiceLineTax.is_deleted.is_(False),
            SalesInvoiceLineTax.included_in_price.is_(False),
        )
        .group_by(SalesInvoiceLineTax.component_code)
    ).all():
        totals[code] = quantize_money(Decimal(str(amount)))
    heads = session.execute(
        select(
            func.coalesce(func.sum(SalesInvoiceCharge.igst_amount), 0),
            func.coalesce(func.sum(SalesInvoiceCharge.cgst_amount), 0),
            func.coalesce(func.sum(SalesInvoiceCharge.sgst_amount), 0),
            func.coalesce(func.sum(SalesInvoiceCharge.cess_amount), 0),
        ).where(
            SalesInvoiceCharge.sales_invoice_id == invoice_id,
            SalesInvoiceCharge.is_deleted.is_(False),
        )
    ).one()
    for code, amount in zip((IGST, CGST, SGST, CESS), heads, strict=True):
        charged = quantize_money(Decimal(str(amount)))
        if charged != ZERO:
            totals[code] = totals.get(code, ZERO) + charged
    return totals


def credited_tax_by_component(
    session: Session, invoice_id: UUID, tax: Decimal
) -> dict[str, Decimal]:
    """Split a credit note's single tax figure the way its invoice was taxed.

    A credit note stores one tax figure per line, not its components. IGST is
    chargeable only between states and CGST with SGST only within one, so the
    invoice it credits settles the split -- the rule GSTR-1's credit-note
    rows already use (``GstReturnService._issued_credit_notes``). An invoice
    that recorded no GST components gives nothing, and the note's tax
    reverses `OUTPUT_TAX` whole.
    """
    if tax == ZERO:
        return {}
    charged = invoice_tax_by_component(session, invoice_id)
    buckets = split_components(
        [
            TaxComponent(code=code, percentage=ZERO, amount=amount)
            for code, amount in charged.items()
        ]
    )
    if buckets.igst > ZERO:
        return {"IGST": quantize_money(tax)}
    if buckets.cgst > ZERO or buckets.sgst > ZERO:
        central, state = intra_state_halves(tax)
        return {CGST: central, SGST: state}
    return {}
