"""What a return or a debit note takes off a bill's reverse charge.

Backlog 68 row 8 put the tax a reverse-charge bill owes on the bill's lines
(``purchase_invoice_line_taxes`` rows with ``reverse_charge`` set): the firm
owes it itself, and claims it back as input credit. The supplier charged none
of it, so a purchase return or a debit note against such a line carries no tax
of its own -- and until this module nothing took the liability or the credit
off again when the goods went back or the price came down.

A returned or claimed line takes the **same share** of its bill line's reverse
charge as of the bill line's taxable value. The share is of the value, not of
the tax, because the tax the note carries is zero.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.money import quantize_money
from app.finance.currency import rupee_rate
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)

ZERO = Decimal("0")


@dataclass(slots=True)
class ReverseChargeShare:
    """The part of a bill's reverse charge one document takes off."""

    #: The taxable value of the reverse-charge lines taken off (3.1(d)).
    taxable: Decimal = ZERO
    #: The tax no longer owed, per component code.
    owed: dict[str, Decimal] = field(default_factory=dict)
    #: The part of it that had been claimed as credit, per component code.
    credit: dict[str, Decimal] = field(default_factory=dict)


def reverse_charge_share(
    session: Session, parts: Iterable[tuple[UUID, Decimal]]
) -> ReverseChargeShare:
    """Return what a document's lines take off their bill lines' reverse charge.

    Args:
        session: The firm's store.
        parts: Each line as (the bill line it is against, its taxable value).

    Returns:
        The taxable value and the tax per head taken off; empty for lines
        whose bill lines carry no reverse charge.

    """
    taken = [(line_id, Decimal(str(value))) for line_id, value in parts]
    share = ReverseChargeShare()
    if not taken:
        return share
    bill_lines = {line_id for line_id, _ in taken}
    rows: dict[UUID, list[tuple[str, Decimal, bool]]] = {}
    for line_id, code, amount, recoverable in session.execute(
        select(
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            PurchaseInvoiceLineTax.component_code,
            PurchaseInvoiceLineTax.amount,
            PurchaseInvoiceLineTax.recoverable,
        ).where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(bill_lines),
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
            PurchaseInvoiceLineTax.reverse_charge.is_(True),
        )
    ).all():
        rows.setdefault(line_id, []).append(
            (code, Decimal(str(amount)), bool(recoverable))
        )
    if not rows:
        return share
    # The supplier charged no tax on such a line, so its net is its value --
    # the same reading GSTR-3B's 3.1(d) takes of the bill.
    bill_value: dict[UUID, Decimal] = {}
    # A bill in another currency charged in it; what comes off is in rupees
    # at the bill's own rate, as its journal posted it (D-BUY-41).
    rupees: dict[UUID, Decimal] = {}
    for line_id, net, tax, currency, rate in session.execute(
        select(
            PurchaseInvoiceLine.id,
            PurchaseInvoiceLine.net_amount,
            PurchaseInvoiceLine.tax_amount,
            PurchaseInvoice.currency_code,
            PurchaseInvoice.exchange_rate,
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(PurchaseInvoiceLine.id.in_(list(rows)))
    ).all():
        bill_value[line_id] = Decimal(str(net)) - Decimal(str(tax))
        rupees[line_id] = rupee_rate(currency, rate)
    for line_id, value in taken:
        components = rows.get(line_id)
        whole = bill_value.get(line_id, ZERO)
        if not components or whole <= ZERO or value <= ZERO:
            continue
        ratio = min(value / whole, Decimal("1"))
        in_rupees = rupees.get(line_id, Decimal("1"))
        share.taxable += quantize_money(value * in_rupees)
        for code, amount, recoverable in components:
            part = quantize_money(amount * ratio * in_rupees)
            share.owed[code] = share.owed.get(code, ZERO) + part
            if recoverable:
                share.credit[code] = share.credit.get(code, ZERO) + part
    return share


__all__ = ["ReverseChargeShare", "reverse_charge_share"]
