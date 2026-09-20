"""What a sale is worth once what came back is taken off.

Commission and sales targets both measure a period on one of two bases --
what was invoiced, or what was collected -- and until D-TER-3 neither took
anything off: a bill credited in full by a credit note, or returned in full,
went on earning its commission and meeting its target. Both modules now read
these two walks and nothing else, so the two cannot disagree about the same
money.

**A credit belongs to the sale it credits, not to the day it was raised.**
`credited_against` is the one derivation of what returns and credit notes have
taken off a bill, and it is applied here to the bill's own row: an April
invoice credited in September is April's sale, now worth less. That is what
lets the payout module see the reduction as a shortfall on April's payout and
carry it forward (`CommissionPayoutService._shortfalls`) rather than as a
negative sale in September that a slab could not read.

**A refund is the cash side of a credit, not a second reduction.** A refund
cannot be allocated to an invoice (`SettlementService.create` refuses it), so
it only ever hands back money that was never counted as collected against a
bill -- an advance, or the excess a credit note left on the customer's
account. The credit note or return that put it there is what takes the sale
off; counting the refund as well would take it off twice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

from app.core.utils.money import ZERO
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementStatus,
)
from app.settlements.services.settlement_service import credited_against

#: The states in which an invoice is a sale. A draft is not one and a
#: cancelled one is not either -- the same test `app/sales_targets` and
#: `app/commission` have always applied.
SOLD_STATUSES: tuple[str, ...] = ("APPROVED", "CLOSED")


@dataclass(frozen=True)
class NetSale:
    """One measured row: who sold it, where, which bill, when, and how much.

    On the invoiced basis a row is a bill and `amount` is its total less what
    has been credited against it. On the collected basis a row is one
    allocation of a receipt and `amount` is its share of the money that the
    bill is still worth.
    """

    salesman_id: UUID | None
    territory_id: UUID | None
    invoice_id: UUID
    when: date
    amount: Decimal


def invoiced_net(
    session: Session,
    *,
    firm_id: UUID,
    from_date: date,
    to_date: date,
    salesman_id: UUID | None = None,
) -> list[NetSale]:
    """Return each approved bill dated in the window, net of its credits.

    Row-grained rather than summed in SQL because the callers resolve a rate
    or a target per row on its own date and scope. A bill credited beyond its
    own total -- which the caps on both documents should make impossible --
    reads as zero rather than as a negative sale.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        from_date: First invoice date to include, inclusive.
        to_date: Last invoice date to include, inclusive.
        salesman_id: Restrict to bills tagged to one person.

    Returns:
        One row per bill, in no particular order.

    """
    statement = select(
        SalesInvoice.salesman_id,
        SalesInvoice.territory_id,
        SalesInvoice.id,
        SalesInvoice.invoice_date,
        SalesInvoice.grand_total,
    ).where(
        SalesInvoice.firm_id == firm_id,
        SalesInvoice.is_deleted.is_(False),
        SalesInvoice.status.in_(SOLD_STATUSES),
        SalesInvoice.invoice_date >= from_date,
        SalesInvoice.invoice_date <= to_date,
    )
    if salesman_id is not None:
        statement = statement.where(SalesInvoice.salesman_id == salesman_id)
    rows = session.execute(statement).all()
    credited = credited_against(
        session, firm_id=firm_id, invoice_ids=[row[2] for row in rows]
    )
    return [
        NetSale(
            salesman_id=owner,
            territory_id=territory_id,
            invoice_id=invoice_id,
            when=when,
            amount=max(ZERO, Decimal(str(total)) - credited.get(invoice_id, ZERO)),
        )
        for owner, territory_id, invoice_id, when, total in rows
    ]


def collected_net(
    session: Session,
    *,
    firm_id: UUID,
    from_date: date,
    to_date: date,
    salesman_id: UUID | None = None,
) -> list[NetSale]:
    """Return each receipt allocation dated in the window, net of credits.

    Collections are read from the allocations that cleared sales invoices,
    joined to the settlement that made them, so a **reversed** settlement
    contributes nothing: its allocations stay on the record to show what it
    had cleared, and `Settlement.status` is the only thing that says the
    money went back.

    A credit against a bill reduces what that bill can be said to have
    collected. What was received beyond the bill's remaining worth is money
    the customer is now owed back, and it comes off the **latest** receipts
    first: the earlier ones were good money for a good sale on the day, and a
    payout already made on them is corrected by the shortfall it leaves, not
    by rewriting which receipt it was.

    **A collection is dated by when the money met the bill**, which is the
    allocation's own date and not the receipt's. They are the same day for a
    receipt allocated as it arrived, and differ for an advance applied to a
    bill raised since: that is the bill's day, or the period it was counted
    in would be one whose payout may already have been paid (D-TER-6).

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        from_date: First allocation date to include, inclusive.
        to_date: Last allocation date to include, inclusive.
        salesman_id: Restrict to bills tagged to one person.

    Returns:
        One row per allocation, in no particular order.

    """
    statement = _allocations(firm_id).where(
        _allocated_on() >= from_date,
        _allocated_on() <= to_date,
    )
    if salesman_id is not None:
        statement = statement.where(SalesInvoice.salesman_id == salesman_id)
    in_window = session.execute(statement).all()
    invoice_ids = {row[2] for row in in_window}
    credited = credited_against(session, firm_id=firm_id, invoice_ids=list(invoice_ids))
    net = _net_allocations(session, firm_id=firm_id, credited=credited)
    return [
        NetSale(
            salesman_id=owner,
            territory_id=territory_id,
            invoice_id=invoice_id,
            when=when,
            amount=net.get(allocation_id, Decimal(str(amount))),
        )
        for owner, territory_id, invoice_id, when, allocation_id, amount, _, _ in (
            in_window
        )
    ]


#: One allocation as the walk below reads it: salesman, territory, invoice,
#: the day the money met the bill, allocation id, amount, when it was
#: recorded, bill total.
_AllocationRow = tuple[
    UUID | None, UUID | None, UUID, date, UUID, Decimal, datetime, Decimal
]


def _allocated_on() -> ColumnElement[date]:
    """Return the day an allocation met its bill, as the walk dates it.

    The allocation's own date where it has one; the settlement's where it
    does not, which is every row written before the column existed and is
    what the backfill wrote for them, so the fallback changes no answer.
    """
    return func.coalesce(SettlementAllocation.allocated_on, Settlement.settlement_date)


def _allocations(firm_id: UUID) -> Select[_AllocationRow]:
    """Build the walk over every live allocation of a posted receipt."""
    return (
        select(
            SalesInvoice.salesman_id,
            SalesInvoice.territory_id,
            SalesInvoice.id,
            _allocated_on(),
            SettlementAllocation.id,
            SettlementAllocation.amount,
            SettlementAllocation.created_at,
            SalesInvoice.grand_total,
        )
        .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
        .join(SalesInvoice, SalesInvoice.id == SettlementAllocation.sales_invoice_id)
        .where(
            SettlementAllocation.firm_id == firm_id,
            SettlementAllocation.is_deleted.is_(False),
            SettlementAllocation.sales_invoice_id.is_not(None),
            Settlement.is_deleted.is_(False),
            Settlement.status == SettlementStatus.POSTED.value,
            Settlement.direction == SettlementDirection.RECEIPT.value,
            SalesInvoice.is_deleted.is_(False),
        )
    )


def _net_allocations(
    session: Session, *, firm_id: UUID, credited: dict[UUID, Decimal]
) -> dict[UUID, Decimal]:
    """Return, per allocation, what it is worth once the bill's credits bite.

    Only allocations of credited bills are answered; every other allocation
    is worth what it says. For a credited bill, everything received beyond
    `total - credited` is taken off its allocations latest-first, whatever
    window the caller asked about -- which is what keeps the answer for one
    receipt the same whichever period is being reported.
    """
    if not credited:
        return {}
    rows = session.execute(
        _allocations(firm_id).where(SalesInvoice.id.in_(list(credited)))
    ).all()
    by_invoice: dict[UUID, list[tuple[date, datetime, UUID, Decimal]]] = {}
    totals: dict[UUID, Decimal] = {}
    for _, _, invoice_id, when, allocation_id, amount, created_at, total in rows:
        by_invoice.setdefault(invoice_id, []).append(
            (when, created_at, allocation_id, Decimal(str(amount)))
        )
        totals[invoice_id] = Decimal(str(total))
    answer: dict[UUID, Decimal] = {}
    for invoice_id, allocations in by_invoice.items():
        received = sum((amount for _, _, _, amount in allocations), ZERO)
        excess = max(
            ZERO, received + credited.get(invoice_id, ZERO) - totals[invoice_id]
        )
        # Latest first: the date the money arrived, then the order it was
        # recorded in, then the id so two rows written together resolve the
        # same way on every database.
        ordered = sorted(
            allocations,
            key=lambda row: (row[0], str(row[1]), str(row[2])),
            reverse=True,
        )
        for _, _, allocation_id, amount in ordered:
            taken = min(excess, amount)
            answer[allocation_id] = amount - taken
            excess -= taken
    return answer


def sum_of(rows: Sequence[NetSale]) -> Decimal:
    """Add a walk up, which is what a target wants and a report does per rule."""
    return sum((row.amount for row in rows), ZERO)


__all__ = ["SOLD_STATUSES", "NetSale", "collected_net", "invoiced_net", "sum_of"]
