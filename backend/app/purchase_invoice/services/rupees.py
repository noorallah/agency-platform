"""The rupees a document against a supplier's bill is worth (D-BUY-41).

A bill in another currency (PG-12) carries the rate it was booked at, and its
journal posted rupees at that rate. A debit note or a purchase return against
it is typed in the bill's currency and is worth that many units at the
**bill's** rate -- not the day's, which is what a payment states and where an
exchange difference belongs. These read that rate for the lines or the bills
a document names; one for a bill in rupees.
"""

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.chunks import over_chunks
from app.finance.currency import rupee_rate
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine


@over_chunks("bill_line_ids")
def bill_line_rupee_rates(
    session: Session, bill_line_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Return the rupees one unit of each bill line's currency is worth."""
    if not bill_line_ids:
        return {}
    return {
        line_id: rupee_rate(currency, rate)
        for line_id, currency, rate in session.execute(
            select(
                PurchaseInvoiceLine.id,
                PurchaseInvoice.currency_code,
                PurchaseInvoice.exchange_rate,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(PurchaseInvoiceLine.id.in_(list(bill_line_ids)))
        ).all()
    }


__all__ = ["bill_line_rupee_rates"]
