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

from sqlalchemy import and_, case, func, select
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
    never stored. An order line is priced from a contract in the contract's
    own unit, so its ordered quantity is in that unit -- except a line typed
    as boxes and pieces against a contract kept per box (L5), which is in
    pieces and draws its pieces over its pack size.
    Free goods are not drawn: the contract is a price agreement.
    """
    from app.purchase.models import PurchaseOrder, PurchaseOrderLine

    ids = list(set(contract_line_ids))
    if not ids:
        return {}
    in_pieces = and_(
        RateContractLine.uom_id.is_not(None),
        PurchaseOrderLine.purchase_uom_id != RateContractLine.uom_id,
        PurchaseOrderLine.pack_size.is_not(None),
    )
    drawn = case(
        (in_pieces, PurchaseOrderLine.ordered_quantity / PurchaseOrderLine.pack_size),
        else_=PurchaseOrderLine.ordered_quantity,
    )
    rows = session.execute(
        select(
            PurchaseOrderLine.rate_contract_line_id,
            func.coalesce(func.sum(drawn), 0),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .join(
            RateContractLine,
            RateContractLine.id == PurchaseOrderLine.rate_contract_line_id,
        )
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


def in_contract_units(
    quantity: Decimal,
    *,
    line_unit: UUID | None,
    pack_size: Decimal | None,
    contract_unit: UUID | None,
) -> Decimal:
    """Return what an order line of ``quantity`` draws on its contract line.

    The quantity itself, but for a line in pieces typed as boxes and pieces
    against a contract kept per box (L5): its pieces over its pack size.
    """
    if contract_unit is not None and line_unit != contract_unit and pack_size:
        return quantity / pack_size
    return quantity


def overdraw_warnings(
    session: Session,
    orders: Iterable[
        tuple[
            UUID,
            str,
            list[tuple[UUID | None, Decimal, UUID | None, Decimal | None]],
        ]
    ],
) -> dict[UUID, str]:
    """Say which orders take a rate contract past its contracted quantity.

    ``orders`` gives each order's id, status and its lines as (contract line,
    ordered quantity, the line's unit, its pack size), so a line in pieces
    drawing on a contract kept per box counts in boxes. An order that already
    draws is in the drawn total; one not yet approved is added to it, so a
    draft or a preview warns before the approval does. A cancelled order
    draws nothing and warns about nothing. Two reads for the whole page,
    however many orders it holds.
    """
    from app.products.models import Product

    wanted: dict[
        UUID, tuple[str, list[tuple[UUID, Decimal, UUID | None, Decimal | None]]]
    ] = {}
    for order_id, status, lines in orders:
        if status == "CANCELLED":
            continue
        drawing = [
            (line_id, qty, unit, pack)
            for line_id, qty, unit, pack in lines
            if line_id is not None
        ]
        if drawing:
            wanted[order_id] = (status, drawing)
    if not wanted:
        return {}
    line_ids = {line[0] for _, drawing in wanted.values() for line in drawing}
    terms: dict[UUID, tuple[Decimal, str, str, UUID | None]] = {
        line_id: (Decimal(str(contracted)), number, product_code, unit)
        for line_id, contracted, number, product_code, unit in session.execute(
            select(
                RateContractLine.id,
                RateContractLine.contracted_quantity,
                RateContract.contract_number,
                Product.code,
                RateContractLine.uom_id,
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
        for line_id, quantity, unit, pack in drawing:
            if line_id in terms:
                mine[line_id] += in_contract_units(
                    quantity,
                    line_unit=unit,
                    pack_size=pack,
                    contract_unit=terms[line_id][3],
                )
        notes: list[str] = []
        for line_id, quantity in mine.items():
            contracted, number, product_code, _ = terms[line_id]
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
