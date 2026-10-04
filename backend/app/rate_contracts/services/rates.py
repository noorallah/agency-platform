"""What a rate contract says a purchase line costs, and what it has drawn.

Kept apart from the service so the purchase order can ask without importing
the whole module: the order prices its lines from here (PG-9) and its
responses read the drawn quantities from here.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.rate_contracts.models import RateContract, RateContractLine

ZERO = Decimal("0")

#: Purchase order statuses whose lines count as drawn on a contract: approved
#: and everything after it, except a cancelled order -- whose quantity goes
#: back to the contract by not being counted, with nothing to reverse.
DRAWING_STATUSES = (
    "APPROVED",
    "PARTIALLY_ORDERED",
    "ORDERED",
    "PARTIALLY_RECEIVED",
    "RECEIVED",
    "CLOSED",
)


def contract_lines_in_force(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    product_ids: Iterable[UUID],
    on: date,
) -> dict[UUID, list[RateContractLine]]:
    """Return the active contract lines with the supplier valid on ``on``.

    Keyed by product, most recent contract first. Activation refuses two
    active contracts covering the same product on overlapping dates, so a
    product normally has one; the order is explicit, on columns that are
    never null, so that if it ever has two the same one is always taken.
    """
    wanted = set(product_ids)
    if not wanted:
        return {}
    rows = session.execute(
        select(RateContractLine)
        .join(RateContract, RateContract.id == RateContractLine.contract_id)
        .where(
            RateContract.firm_id == firm_id,
            RateContract.vendor_id == vendor_id,
            RateContract.status == "ACTIVE",
            RateContract.is_deleted.is_(False),
            RateContract.valid_from <= on,
            RateContract.valid_to >= on,
            RateContractLine.is_deleted.is_(False),
            RateContractLine.product_id.in_(wanted),
        )
        .order_by(
            RateContract.valid_from.desc(),
            RateContract.contract_number.desc(),
            RateContractLine.line_number.asc(),
        )
    ).scalars()
    grouped: dict[UUID, list[RateContractLine]] = defaultdict(list)
    for row in rows:
        grouped[row.product_id].append(row)
    return grouped


def drawn_quantities(
    session: Session, contract_line_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Return what approved, uncancelled orders have drawn on each line.

    Summed on every read from the order lines that name the contract line,
    never stored. An order line is priced from a contract only in the
    contract's own unit, so its ordered quantity is already in that unit.
    Free goods are not drawn: the contract is a price agreement.
    """
    from app.purchase.models import PurchaseOrder, PurchaseOrderLine

    ids = list(set(contract_line_ids))
    if not ids:
        return {}
    rows = session.execute(
        select(
            PurchaseOrderLine.rate_contract_line_id,
            func.coalesce(func.sum(PurchaseOrderLine.ordered_quantity), 0),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(
            PurchaseOrderLine.rate_contract_line_id.in_(ids),
            PurchaseOrderLine.is_deleted.is_(False),
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status.in_(DRAWING_STATUSES),
        )
        .group_by(PurchaseOrderLine.rate_contract_line_id)
    ).all()
    return {
        line_id: Decimal(str(total)) for line_id, total in rows if line_id is not None
    }


def _plain(value: Decimal) -> str:
    """Render a quantity without trailing zeros or an exponent."""
    return f"{value.normalize():f}"


def overdraw_warnings(
    session: Session,
    orders: Iterable[tuple[UUID, str, list[tuple[UUID | None, Decimal]]]],
) -> dict[UUID, str]:
    """Say which orders take a rate contract past its contracted quantity.

    ``orders`` gives each order's id, status and its lines as (contract line,
    ordered quantity). An order that already draws is in the drawn total; one
    not yet approved is added to it, so a draft or a preview warns before the
    approval does. A cancelled order draws nothing and warns about nothing.
    Two reads for the whole page, however many orders it holds.
    """
    from app.products.models import Product

    wanted: dict[UUID, tuple[str, list[tuple[UUID, Decimal]]]] = {}
    for order_id, status, lines in orders:
        if status == "CANCELLED":
            continue
        drawing = [(line_id, qty) for line_id, qty in lines if line_id is not None]
        if drawing:
            wanted[order_id] = (status, drawing)
    if not wanted:
        return {}
    line_ids = {line_id for _, drawing in wanted.values() for line_id, _ in drawing}
    terms: dict[UUID, tuple[Decimal, str, str]] = {
        line_id: (Decimal(str(contracted)), number, product_code)
        for line_id, contracted, number, product_code in session.execute(
            select(
                RateContractLine.id,
                RateContractLine.contracted_quantity,
                RateContract.contract_number,
                Product.code,
            )
            .join(RateContract, RateContract.id == RateContractLine.contract_id)
            .join(Product, Product.id == RateContractLine.product_id)
            .where(
                RateContractLine.id.in_(line_ids),
                RateContractLine.contracted_quantity.is_not(None),
            )
        ).all()
    }
    if not terms:
        return {}
    drawn = drawn_quantities(session, terms)
    answer: dict[UUID, str] = {}
    for order_id, (status, drawing) in wanted.items():
        mine: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        for line_id, quantity in drawing:
            mine[line_id] += quantity
        notes: list[str] = []
        for line_id, quantity in mine.items():
            if line_id not in terms:
                continue
            contracted, number, product_code = terms[line_id]
            total = drawn.get(line_id, ZERO)
            if status not in DRAWING_STATUSES:
                total += quantity
            if total > contracted:
                notes.append(
                    f"{number} {product_code}: {_plain(total)} drawn of "
                    f"{_plain(contracted)} contracted"
                )
        if notes:
            answer[order_id] = "Over rate contract: " + "; ".join(notes) + "."
    return answer
