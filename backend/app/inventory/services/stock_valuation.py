"""What the firm's stock is worth, as on any day (D-GOLIVE-3).

Tally's *Stock Summary*: every item with its quantity, rate and value, and a
grand total. An accountant needs it to check the opening stock brought over
from the old tool, for the closing stock in the accounts, and for the monthly
stock statement a distributor's bank asks for against its cash-credit limit.

**Read from the movements, so any past day can be asked.** The quantity is
what every movement dated on or before the day did to what the firm *owns* --
quarantined and returned-damaged goods included, as the books include them;
the rate is the moving
weighted-average cost the ledger recorded after the last costed movement on
or before it (`average_cost_after`), which is the firm-wide average
`ProductValuation` keeps -- one average per product, not per warehouse, so a
warehouse's stock is valued at the firm's rate.

**The books are stated beside the stock.** The last rows are the grand total,
the balance of the Inventory control account on the same day, and the
difference. They agree when every movement posted at the cost it moved at; a
difference is the first thing to look into before the year end.

**The same stock at its MRP, beside its cost (backlog 109).** A distributor
reads the two together: what the shelf cost and what it would fetch at the
printed price. Each unit is priced at the MRP of its own batch, and at the
product's where the batch has none or the stock is not kept by batch --
the manufacturer prints a different MRP on each batch, so one figure per
product would misstate a shelf holding two. The MRP is the one held today:
no history of it is kept, so a past day is valued at today's printed price.
A unit with no MRP anywhere adds nothing, and an item with none is left blank
rather than shown as worth zero.

**A firm costing by lot (L2 step 10).** An item is worth the sum of its lots
(`docs/design/LOT_COST_DESIGN.md`, section 5): as on today what
``batch_valuations`` holds, and as on a past day that less the signed value
of every movement of the lot dated after it, added up by the database --
read backwards because a lot carried forward at the switch-over has a
history from before it that does not name it. Units billed before their lot
came (L2 step 7a) are a line of their own, *Units owed to lots*, at the cost
they left with, so the grand total still compares with the Inventory
account. A day before the firm switched is valued on Average, as the firm
was then. ``StockValuationService.lots`` lists the lots behind each item.
"""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.batch_serial.models import BatchRecord
from app.core.utils.chunks import over_chunks
from app.core.utils.money import quantize_ledger
from app.finance.models import GLPosting, JournalEntry
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.inventory.models import (
    BatchValuation,
    InventoryRecord,
    InventoryTransaction,
    LotShortfall,
    LotShortfallSettlement,
    StockLedgerEntry,
)
from app.inventory.services.lots import costs_by_lot, switch_over_day
from app.products.models import Product, ProductCategory
from app.products.models.goods_type import GENERAL_GOODS, GoodsType
from app.uom.models import Uom

ZERO = Decimal("0")
#: The scale a cost rate is stated to, as ``batch_valuations.unit_cost``.
RATE_SCALE = Decimal("0.000001")
#: The closing line for units billed before their lot (L2 step 10).
OWED_LABEL = "Units owed to lots"


@dataclass(frozen=True)
class StockValuationRow:
    """One line of the valuation: an item, or one of the closing totals."""

    row_type: str
    product_code: str
    product_name: str
    category: str
    unit: str
    quantity: Decimal | None
    rate: Decimal | None
    value: Decimal
    #: The product's goods type, General where it has none (backlog 89);
    #: empty on the closing rows.
    goods_type: str = ""
    #: The MRP of a unit, where every unit on hand carries the same one;
    #: None where the batches on hand differ, or none is recorded.
    mrp: Decimal | None = None
    #: The quantity at its MRP, each unit at its own batch's (backlog 109).
    #: None where no unit on hand has an MRP, and on the two books rows.
    mrp_value: Decimal | None = None


class StockValuationService:
    """Value a firm's stock as on a day."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def valuation(
        self,
        firm_id: UUID,
        *,
        on: date,
        warehouse_id: UUID | None = None,
        include_zero: bool = False,
        owed_apart: bool = True,
    ) -> list[StockValuationRow]:
        """Return each item's quantity, rate and value, then the totals.

        Args:
            firm_id: The firm.
            on: The day the stock is valued as on, inclusive.
            warehouse_id: One warehouse, or None for every warehouse. The
                books cannot be split by warehouse, so the comparison with the
                Inventory account is made only for the whole firm.
            include_zero: List items with nothing on hand as well.
            owed_apart: For a firm costing by lot, state the units owed to
                lots as a line of their own; False takes them off each
                item's own line instead, which the stock statement wants, so
                its quantities still add up movement by movement.

        """
        by_lot = lot_stock(self._session, firm_id, on=on, warehouse_id=warehouse_id)
        owed_quantity = ZERO
        owed_value = ZERO
        values: dict[UUID, Decimal]
        if by_lot is None:
            quantities, at_mrp = self._owned_by_product(firm_id, on, warehouse_id)
            rates = self._rates(firm_id, on)
            values = {
                product_id: quantize_ledger(quantity * rates.get(product_id, ZERO))
                for product_id, quantity in quantities.items()
            }
        else:
            quantities, at_mrp, values = {}, {}, {}
            for lot in by_lot.lots:
                pid = lot.product_id
                quantities[pid] = quantities.get(pid, ZERO) + lot.quantity
                values[pid] = values.get(pid, ZERO) + lot.value
                at_mrp.setdefault(pid, []).append((lot.mrp, lot.quantity))
            for pid, (quantity, value) in by_lot.owed.items():
                if owed_apart:
                    owed_quantity += quantity
                    owed_value += value
                    continue
                quantities[pid] = quantities.get(pid, ZERO) - quantity
                values[pid] = values.get(pid, ZERO) - quantize_ledger(value)
                at_mrp.setdefault(pid, []).append((None, -quantity))
            rates = {
                pid: _rate(values[pid], quantity)
                for pid, quantity in quantities.items()
            }
        # The seven columns the report reads, for the firm's products: whole
        # rows of five thousand products were most of what this report took.
        products = {
            product.id: product
            for product in self._session.execute(
                select(
                    Product.id,
                    Product.code,
                    Product.name,
                    Product.category_id,
                    Product.goods_type_id,
                    Product.base_uom_id,
                    Product.mrp,
                ).where(Product.firm_id == firm_id)
            )
            if product.id in quantities
        }
        categories: dict[UUID | None, str] = {
            category_id: name
            for category_id, name in self._session.execute(
                select(ProductCategory.id, ProductCategory.name).where(
                    ProductCategory.id.in_(
                        [p.category_id for p in products.values()] or [None]
                    )
                )
            ).all()
        }
        goods_types = goods_type_names(
            self._session,
            {p.goods_type_id for p in products.values() if p.goods_type_id},
        )
        units: dict[UUID | None, str] = {
            unit_id: code
            for unit_id, code in self._session.execute(
                select(Uom.id, Uom.code).where(
                    Uom.id.in_([p.base_uom_id for p in products.values()] or [None])
                )
            ).all()
        }

        rows: list[StockValuationRow] = []
        total = ZERO
        mrp_total = ZERO
        for product_id, quantity in quantities.items():
            product = products.get(product_id)
            if product is None:
                continue
            value = values.get(product_id, ZERO)
            # A by-lot item holding no units but some value (a correction
            # on a lot since emptied) is still stated, or the total would
            # part from the books without saying where.
            if (
                quantity == ZERO
                and not include_zero
                and (by_lot is None or value == ZERO)
            ):
                continue
            rate = rates.get(product_id, ZERO)
            total += value
            mrp, mrp_value = _at_mrp(at_mrp[product_id], product.mrp)
            mrp_total += mrp_value or ZERO
            rows.append(
                StockValuationRow(
                    row_type="ITEM",
                    product_code=product.code,
                    product_name=product.name,
                    category=categories.get(product.category_id, "") or "",
                    unit=units.get(product.base_uom_id, "") or "",
                    quantity=quantity,
                    rate=rate,
                    value=value,
                    goods_type=goods_types.get(product.goods_type_id, GENERAL_GOODS),
                    mrp=mrp,
                    mrp_value=mrp_value,
                )
            )
        rows.sort(key=lambda row: (row.category, row.product_code))
        if owed_quantity != ZERO or owed_value != ZERO:
            # Units sold before their lot came left the books at the cost
            # used, so the books hold the lots less these.
            owed = quantize_ledger(-owed_value)
            total += owed
            rows.append(
                StockValuationRow(
                    row_type="OWED",
                    product_code="",
                    product_name=OWED_LABEL,
                    category="",
                    unit="",
                    quantity=-owed_quantity,
                    rate=None,
                    value=owed,
                )
            )
        rows.append(_closing("TOTAL", "Grand total", total, mrp_value=mrp_total))
        if warehouse_id is None:
            books = self._books(firm_id, on)
            if books is not None:
                rows.append(_closing("BOOKS", "Inventory account in the books", books))
                rows.append(_closing("DIFFERENCE", "Difference", total - books))
        return rows

    def lots(
        self,
        firm_id: UUID,
        *,
        on: date,
        warehouse_id: UUID | None = None,
        product_id: UUID | None = None,
    ) -> list["StockLotRow"]:
        """Return each lot holding stock as on ``on``, for a firm costing by lot.

        The drill-down behind the valuation: an item's line is the sum of
        its lots here, so the rows add up to the grand total less the units
        owed to lots. Stock that names no lot -- goods a customer sent back
        from a sale that left with none -- is one row of its own with no
        reference. A firm on Average, or a day before the firm switched, has
        no lots and answers nothing.
        """
        by_lot = lot_stock(
            self._session,
            firm_id,
            on=on,
            warehouse_id=warehouse_id,
            product_id=product_id,
        )
        if by_lot is None:
            return []
        query = select(Product.id, Product.code, Product.name, Product.mrp).where(
            Product.firm_id == firm_id
        )
        if product_id is not None:
            query = query.where(Product.id == product_id)
        products = {row.id: row for row in self._session.execute(query)}
        rows: list[StockLotRow] = []
        for lot in by_lot.lots:
            product = products.get(lot.product_id)
            if product is None:
                continue
            printed = lot.mrp if lot.mrp is not None else product.mrp
            mrp = None if printed is None else Decimal(str(printed))
            rows.append(
                StockLotRow(
                    product_code=product.code,
                    product_name=product.name,
                    lot_reference=lot.lot_reference,
                    batch_number=lot.batch_number,
                    received_on=lot.received_on,
                    expiry_date=lot.expiry_date,
                    mrp=mrp,
                    quantity=lot.quantity,
                    rate=_rate(lot.value, lot.quantity),
                    value=lot.value,
                    mrp_value=(
                        None if mrp is None else quantize_ledger(lot.quantity * mrp)
                    ),
                )
            )
        rows.sort(
            key=lambda row: (
                row.product_code,
                row.received_on is None,
                row.received_on or on,
                row.lot_reference,
            )
        )
        return rows

    def _owned_by_product(
        self, firm_id: UUID, on: date, warehouse_id: UUID | None
    ) -> tuple[dict[UUID, Decimal], dict[UUID, list[tuple[Decimal | None, Decimal]]]]:
        """Return each product's owned quantity, and that quantity by batch MRP."""
        # What the firm owns, which is not always what it can sell: goods in
        # quarantine have left `current` and are still the firm's and still
        # on the books, and a damaged unit a customer returned was owned
        # without being shelved. The movement records what it did to the
        # owned quantity in `owned_quantity_delta` where that differs from
        # `current`; a quarantine hold records neither, and moves the goods
        # between `current` and `quarantine`, which together are unchanged.
        quantity_filters = [
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.is_deleted.is_(False),
            InventoryTransaction.transaction_date <= on,
        ]
        if warehouse_id is not None:
            quantity_filters.append(InventoryTransaction.warehouse_id == warehouse_id)
        # One row per product and per MRP its batches carry, so the stock is
        # added up by the database and the batches never come here by id.
        quantities: dict[UUID, Decimal] = {}
        at_mrp: dict[UUID, list[tuple[Decimal | None, Decimal]]] = {}
        for product_id, batch_mrp, amount in self._session.execute(
            select(InventoryTransaction.product_id, BatchRecord.mrp, func.sum(_owned()))
            .outerjoin(BatchRecord, BatchRecord.id == InventoryTransaction.batch_id)
            .where(*quantity_filters)
            .group_by(InventoryTransaction.product_id, BatchRecord.mrp)
        ).all():
            held = Decimal(str(amount or 0))
            quantities[product_id] = quantities.get(product_id, ZERO) + held
            at_mrp.setdefault(product_id, []).append((batch_mrp, held))
        return quantities, at_mrp

    def rates(self, firm_id: UUID, on: date) -> dict[UUID, Decimal]:
        """Return each product's moving-average cost as on ``on``.

        The rate the valuation values stock at, for the reports that value
        stock beside it (backlog 55 S7).
        """
        return self._rates(firm_id, on)

    def _rates(self, firm_id: UUID, on: date) -> dict[UUID, Decimal]:
        """Each product's moving-average cost after its last costed movement.

        Asked in two steps, because ranking every costed movement the firm
        ever made is a sort of the whole ledger (six seconds on PERF01): the
        last costed day of each product is one grouped pass, and only that
        day's rows are ranked to pick the last of them.
        """
        costed = (
            StockLedgerEntry.firm_id == firm_id,
            StockLedgerEntry.is_deleted.is_(False),
            StockLedgerEntry.transaction_date <= on,
            StockLedgerEntry.average_cost_after.is_not(None),
        )
        last_day = (
            select(
                StockLedgerEntry.product_id.label("product_id"),
                func.max(StockLedgerEntry.transaction_date).label("day"),
            )
            .where(*costed)
            .group_by(StockLedgerEntry.product_id)
            .subquery()
        )
        ranked = (
            select(
                StockLedgerEntry.product_id.label("product_id"),
                StockLedgerEntry.average_cost_after.label("rate"),
                func.row_number()
                .over(
                    partition_by=StockLedgerEntry.product_id,
                    order_by=(
                        StockLedgerEntry.created_at.desc(),
                        StockLedgerEntry.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .join(
                last_day,
                and_(
                    last_day.c.product_id == StockLedgerEntry.product_id,
                    last_day.c.day == StockLedgerEntry.transaction_date,
                ),
            )
            .where(*costed)
            .subquery()
        )
        return {
            product_id: Decimal(str(rate))
            for product_id, rate in self._session.execute(
                select(ranked.c.product_id, ranked.c.rate).where(ranked.c.rank == 1)
            ).all()
        }

    def _books(self, firm_id: UUID, on: date) -> Decimal | None:
        """Return the Inventory control account's balance on the day, or None.

        None where the firm's books are not open, so there is no account to
        compare with -- a row reading 0 would claim the books say nothing.
        """
        account_id = (
            ControlAccountService(self._session)
            .mapping(firm_id)
            .get(ControlAccountPurpose.INVENTORY.value)
        )
        if account_id is None:
            return None
        value = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            )
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(
                GLPosting.firm_id == firm_id,
                GLPosting.ledger_account_id == account_id,
                GLPosting.is_deleted.is_(False),
                JournalEntry.journal_date <= on,
            )
        )
        return quantize_ledger(Decimal(str(value or 0)))


def goods_type_names(session: Session, ids: set[UUID]) -> dict[UUID | None, str]:
    """Return the name of each goods type named, read once for a report."""
    if not ids:
        return {}
    return {
        goods_type_id: name
        for goods_type_id, name in session.execute(
            select(GoodsType.id, GoodsType.name).where(GoodsType.id.in_(ids))
        ).all()
    }


def _at_mrp(
    held: list[tuple[Decimal | None, Decimal]], product_mrp: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    """Return an item's MRP and its stock's value at MRP.

    ``held`` is the quantity owned under each batch MRP, None being the units
    whose batch has none or which have no batch: those take the product's.
    The MRP is stated only where every unit on hand carries the same one.
    """
    value: Decimal | None = None
    seen: set[Decimal | None] = set()
    for batch_mrp, quantity in held:
        if quantity == ZERO:
            continue
        mrp = batch_mrp if batch_mrp is not None else product_mrp
        seen.add(None if mrp is None else Decimal(str(mrp)))
        if mrp is not None:
            value = (value or ZERO) + quantity * Decimal(str(mrp))
    if not seen:
        seen.add(None if product_mrp is None else Decimal(str(product_mrp)))
    single = next(iter(seen)) if len(seen) == 1 else None
    return single, None if value is None else quantize_ledger(value)


def _closing(
    kind: str, label: str, value: Decimal, *, mrp_value: Decimal | None = None
) -> StockValuationRow:
    return StockValuationRow(
        row_type=kind,
        product_code="",
        product_name=label,
        category="",
        unit="",
        quantity=None,
        rate=None,
        value=quantize_ledger(value),
        mrp_value=None if mrp_value is None else quantize_ledger(mrp_value),
    )


def _owned() -> ColumnElement[Decimal]:
    """Return what a movement did to the quantity the firm owns."""
    return func.coalesce(
        InventoryTransaction.owned_quantity_delta,
        InventoryTransaction.current_quantity_delta
        + InventoryTransaction.quarantine_quantity_delta,
    )


def _rate(value: Decimal, quantity: Decimal) -> Decimal:
    """Return the cost of one unit, value over quantity; nothing for none."""
    if quantity == ZERO:
        return ZERO
    return (value / quantity).quantize(RATE_SCALE, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class StockLotRow:
    """One lot holding stock, as the valuation's drill-down lists it."""

    product_code: str
    product_name: str
    #: Our own reference; empty on the row for stock that names no lot.
    lot_reference: str
    #: The batch printed on the packs; empty where the goods carry none.
    batch_number: str
    received_on: date | None
    expiry_date: date | None
    #: The lot's own MRP, else the product's.
    mrp: Decimal | None
    quantity: Decimal
    rate: Decimal
    value: Decimal
    mrp_value: Decimal | None


@dataclass(frozen=True)
class LotHolding:
    """What one lot of an item holds and is worth on a day.

    ``batch_id`` None is the item's stock that names no lot, less the units
    owed to lots, which are stated apart.
    """

    product_id: UUID
    batch_id: UUID | None
    quantity: Decimal
    #: To the books' scale; an item's lots add up to its value to the paisa.
    value: Decimal
    lot_reference: str = ""
    batch_number: str = ""
    received_on: date | None = None
    expiry_date: date | None = None
    #: The lot's own MRP; None where it has none.
    mrp: Decimal | None = None


@dataclass(frozen=True)
class LotStock:
    """A by-lot firm's stock on a day: its lots, and the units owed to them."""

    lots: list[LotHolding]
    #: Per product, the units billed before their lot and still waiting on
    #: the day, with the cost they left at.
    owed: dict[UUID, tuple[Decimal, Decimal]] = field(default_factory=dict)


def lot_stock(
    session: Session,
    firm_id: UUID,
    *,
    on: date,
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
) -> LotStock | None:
    """Return what each lot holds and is worth as on ``on``, by lot.

    None where the firm costs on Average, or ``on`` is before the day it
    switched: it was valued on Average then, and the report says so.

    A lot's quantity is what its movements did to what the firm owns, up to
    the day; the movements a lot carried forward at the switch-over made
    before it name no batch, so they are matched through the stock row,
    which the switch-over pointed at the lot. A lot's value is what
    ``batch_valuations`` holds now less the signed value of its movements
    dated after the day -- every one of those was valued by lot. One cost per
    lot, so a warehouse's share is the lot's value pro rata to its units.
    """
    if not costs_by_lot(session, firm_id):
        return None
    switched_on = switch_over_day(session, firm_id)
    if switched_on is not None and on < switched_on:
        return None
    lot = func.coalesce(InventoryTransaction.batch_id, InventoryRecord.batch_id)
    moved = [
        InventoryTransaction.firm_id == firm_id,
        InventoryTransaction.is_deleted.is_(False),
        InventoryTransaction.transaction_date <= on,
    ]
    if product_id is not None:
        moved.append(InventoryTransaction.product_id == product_id)
    held: dict[UUID, Decimal] = {}
    held_here: dict[UUID, Decimal] = {}
    for lot_id, warehouse, amount in session.execute(
        select(lot, InventoryTransaction.warehouse_id, func.sum(_owned()))
        .join(InventoryRecord, InventoryRecord.id == InventoryTransaction.inventory_id)
        .where(*moved, lot.is_not(None))
        .group_by(lot, InventoryTransaction.warehouse_id)
    ).all():
        quantity = Decimal(str(amount or 0))
        held[lot_id] = held.get(lot_id, ZERO) + quantity
        if warehouse_id is None or warehouse == warehouse_id:
            held_here[lot_id] = held_here.get(lot_id, ZERO) + quantity
    worth = _lot_values(session, firm_id, on=on, product_id=product_id)
    details = _lot_details(session, batch_ids=list(set(held) | set(worth)))

    lots: list[LotHolding] = []
    for lot_id in sorted(set(held) | set(worth), key=str):
        whole = held.get(lot_id, ZERO)
        here = held_here.get(lot_id, ZERO)
        value = worth.get(lot_id, ZERO)
        if warehouse_id is not None:
            value = ZERO if whole == ZERO else value * here / whole
        info = details.get(lot_id)
        if info is None:
            continue
        lots.append(
            LotHolding(
                product_id=info.product_id,
                batch_id=lot_id,
                quantity=here,
                value=value,
                lot_reference=info.lot_reference,
                batch_number=info.batch_number if info.has_printed_batch else "",
                received_on=info.received_on,
                expiry_date=info.expiry_date,
                mrp=None if info.mrp is None else Decimal(str(info.mrp)),
            )
        )

    owed = _owed_to_lots(
        session, firm_id, on=on, warehouse_id=warehouse_id, product_id=product_id
    )
    unlotted = _unlotted(
        session,
        firm_id,
        on=on,
        since=switched_on,
        warehouse_id=warehouse_id,
        product_id=product_id,
    )
    for pid in sorted(set(unlotted) | set(owed), key=str):
        quantity, value = unlotted.get(pid, (ZERO, ZERO))
        owed_quantity, owed_value = owed.get(pid, (ZERO, ZERO))
        # The row with no lot went below zero by the units owed; what is
        # left once they are put back is stock in its own right.
        lots.append(LotHolding(pid, None, quantity + owed_quantity, value + owed_value))
    return LotStock(lots=_to_the_paisa(lots), owed=owed)


def _to_the_paisa(lots: list[LotHolding]) -> list[LotHolding]:
    """Round each lot's value to the books' scale so an item's lots add up.

    An item is worth its lots' value rounded once, as the books would round
    it; each lot is rounded on its own and the residual goes on the lot worth
    most, so the drill-down adds up to the item to the paisa. A lot holding
    nothing and worth nothing is left out.
    """
    by_product: dict[UUID, list[int]] = {}
    for index, lot in enumerate(lots):
        by_product.setdefault(lot.product_id, []).append(index)
    rounded = [quantize_ledger(lot.value) for lot in lots]
    for indexes in by_product.values():
        whole = quantize_ledger(sum((lots[i].value for i in indexes), ZERO))
        residual = whole - sum((rounded[i] for i in indexes), ZERO)
        if residual != ZERO:
            largest = max(indexes, key=lambda i: (abs(lots[i].value), str(i)))
            rounded[largest] += residual
    return [
        replace(lot, value=value)
        for lot, value in zip(lots, rounded, strict=True)
        if lot.quantity != ZERO or value != ZERO
    ]


def _signed_value() -> ColumnElement[Decimal]:
    """Return a stock ledger row's value, plus in and minus out.

    A movement's ``total_cost`` is what it moved, unsigned; its direction is
    what it did to the quantity the valuation keeps (the owned delta, else
    the shelf). A value-only movement -- a landed cost, a correction -- moves
    no quantity and carries its own sign.
    """
    direction = func.coalesce(
        InventoryTransaction.owned_quantity_delta,
        InventoryTransaction.current_quantity_delta,
    )
    cost = func.coalesce(StockLedgerEntry.total_cost, 0)
    return case((direction > 0, cost), (direction < 0, -cost), else_=cost)


def _lot_values(
    session: Session, firm_id: UUID, *, on: date, product_id: UUID | None
) -> dict[UUID, Decimal]:
    """Return each lot's value as on ``on``: now, less what moved since."""
    now = select(BatchValuation.batch_id, BatchValuation.total_value).where(
        BatchValuation.firm_id == firm_id,
        BatchValuation.is_deleted.is_(False),
    )
    since = (
        select(StockLedgerEntry.batch_id, func.sum(_signed_value()))
        .join(
            InventoryTransaction,
            InventoryTransaction.id == StockLedgerEntry.transaction_id,
        )
        .where(
            StockLedgerEntry.firm_id == firm_id,
            StockLedgerEntry.is_deleted.is_(False),
            StockLedgerEntry.transaction_date > on,
            StockLedgerEntry.batch_id.is_not(None),
        )
        .group_by(StockLedgerEntry.batch_id)
    )
    if product_id is not None:
        now = now.where(BatchValuation.product_id == product_id)
        since = since.where(StockLedgerEntry.product_id == product_id)
    values = {
        batch_id: Decimal(str(value or 0))
        for batch_id, value in session.execute(now).all()
    }
    for batch_id, moved in session.execute(since).all():
        if batch_id in values:
            values[batch_id] -= Decimal(str(moved or 0))
    return values


def _owed_to_lots(
    session: Session,
    firm_id: UUID,
    *,
    on: date,
    warehouse_id: UUID | None,
    product_id: UUID | None,
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return each item's units billed before their lot, waiting on ``on``.

    Sold on or before the day, less what a lot or a return cleared on or
    before it, with the cost they left at -- what
    ``LotShortfallService.open_shortfalls`` derives, as on a day and added
    up by the database.
    """
    sold = [
        LotShortfall.firm_id == firm_id,
        LotShortfall.is_deleted.is_(False),
        LotShortfall.sale_date <= on,
    ]
    if warehouse_id is not None:
        sold.append(LotShortfall.warehouse_id == warehouse_id)
    if product_id is not None:
        sold.append(LotShortfall.product_id == product_id)
    owed: dict[UUID, tuple[Decimal, Decimal]] = {
        pid: (Decimal(str(quantity or 0)), Decimal(str(cost or 0)))
        for pid, quantity, cost in session.execute(
            select(
                LotShortfall.product_id,
                func.sum(LotShortfall.quantity),
                func.sum(LotShortfall.cost_amount),
            )
            .where(*sold)
            .group_by(LotShortfall.product_id)
        ).all()
    }
    if not owed:
        return {}
    for pid, quantity, cost in session.execute(
        select(
            LotShortfall.product_id,
            func.sum(LotShortfallSettlement.quantity),
            func.sum(LotShortfallSettlement.cost_used_amount),
        )
        .join(LotShortfall, LotShortfall.id == LotShortfallSettlement.lot_shortfall_id)
        .where(
            *sold,
            LotShortfallSettlement.is_deleted.is_(False),
            LotShortfallSettlement.settled_on <= on,
        )
        .group_by(LotShortfall.product_id)
    ).all():
        waiting, left = owed[pid]
        owed[pid] = (
            waiting - Decimal(str(quantity or 0)),
            left - Decimal(str(cost or 0)),
        )
    return {pid: pair for pid, pair in owed.items() if pair != (ZERO, ZERO)}


def _unlotted(
    session: Session,
    firm_id: UUID,
    *,
    on: date,
    since: date | None,
    warehouse_id: UUID | None,
    product_id: UUID | None,
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return each item's stock that names no lot, quantity and signed value.

    Only movements from the switch-over day on: before it every unbatched
    row was carried into a lot, and a row that names no lot now held
    nothing then.
    """
    unlotted = [
        InventoryTransaction.firm_id == firm_id,
        InventoryTransaction.is_deleted.is_(False),
        InventoryTransaction.transaction_date <= on,
        InventoryTransaction.batch_id.is_(None),
        InventoryRecord.batch_id.is_(None),
    ]
    if since is not None:
        unlotted.append(InventoryTransaction.transaction_date >= since)
    if warehouse_id is not None:
        unlotted.append(InventoryTransaction.warehouse_id == warehouse_id)
    if product_id is not None:
        unlotted.append(InventoryTransaction.product_id == product_id)
    return {
        pid: (Decimal(str(quantity or 0)), Decimal(str(value or 0)))
        for pid, quantity, value in session.execute(
            select(
                InventoryTransaction.product_id,
                func.sum(_owned()),
                func.sum(_signed_value()),
            )
            .join(
                InventoryRecord, InventoryRecord.id == InventoryTransaction.inventory_id
            )
            .outerjoin(
                StockLedgerEntry,
                and_(
                    StockLedgerEntry.transaction_id == InventoryTransaction.id,
                    StockLedgerEntry.is_deleted.is_(False),
                ),
            )
            .where(*unlotted)
            .group_by(InventoryTransaction.product_id)
        ).all()
    }


@dataclass(frozen=True)
class _LotDetail:
    product_id: UUID
    lot_reference: str
    batch_number: str
    has_printed_batch: bool
    received_on: date | None
    expiry_date: date | None
    mrp: Decimal | None


@over_chunks("batch_ids")
def _lot_details(session: Session, *, batch_ids: list[UUID]) -> dict[UUID, _LotDetail]:
    """Read each lot's reference, printed batch, dates and MRP, once."""
    if not batch_ids:
        return {}
    return {
        row.id: _LotDetail(
            row.product_id,
            row.lot_reference,
            row.batch_number,
            bool(row.has_printed_batch),
            row.received_on,
            row.expiry_date,
            row.mrp,
        )
        for row in session.execute(
            select(
                BatchRecord.id,
                BatchRecord.product_id,
                BatchRecord.lot_reference,
                BatchRecord.batch_number,
                BatchRecord.has_printed_batch,
                BatchRecord.received_on,
                BatchRecord.expiry_date,
                BatchRecord.mrp,
            ).where(BatchRecord.id.in_(batch_ids))
        ).all()
    }


@dataclass(frozen=True)
class StockStatementRow:
    """One item's stock over a period, or the total (``row_type`` TOTAL)."""

    row_type: str
    product_code: str
    product_name: str
    category: str
    unit: str
    opening_quantity: Decimal
    opening_value: Decimal
    inward_quantity: Decimal
    inward_value: Decimal
    outward_quantity: Decimal
    outward_value: Decimal
    closing_quantity: Decimal
    closing_value: Decimal


#: Movements between the firm's own warehouses: in and out of one store, so a
#: firm-wide statement leaves them out -- nothing came in or went out.
_INTERNAL = ("TRANSFER_IN", "TRANSFER_OUT")


class StockStatementService:
    """The monthly stock statement a bank asks for (backlog 70 row 6).

    A distributor with a cash-credit limit files one every month: opening
    stock, what came in, what went out, closing stock, each quantity with its
    value -- the drawing-power statement. Opening and closing are the stock
    valuation as on the day before the period and on its last day, so this
    agrees with *Stock valuation* by construction; what came in is valued at
    what it cost (`total_cost` of the inward movements); what went out is the
    balancing figure, opening + in - closing, which is how the moving average
    values issues and keeps the four columns adding up exactly.
    """

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session

    def statement(
        self,
        firm_id: UUID,
        *,
        from_date: date,
        to_date: date,
        warehouse_id: UUID | None = None,
    ) -> list[StockStatementRow]:
        """Return each item's opening, in, out and closing, then the total."""
        valuation = StockValuationService(self._session)
        opening = {
            row.product_code: row
            for row in valuation.valuation(
                firm_id,
                on=from_date - timedelta(days=1),
                warehouse_id=warehouse_id,
                include_zero=True,
                owed_apart=False,
            )
            if row.row_type == "ITEM"
        }
        closing = {
            row.product_code: row
            for row in valuation.valuation(
                firm_id,
                on=to_date,
                warehouse_id=warehouse_id,
                include_zero=True,
                owed_apart=False,
            )
            if row.row_type == "ITEM"
        }
        moved = self._inward(firm_id, from_date, to_date, warehouse_id)
        codes = sorted(
            set(opening) | set(closing) | set(moved),
            key=lambda code: (
                (
                    (closing.get(code) or opening.get(code)).category  # type: ignore[union-attr]
                    if (closing.get(code) or opening.get(code))
                    else ""
                ),
                code,
            ),
        )
        rows: list[StockStatementRow] = []
        totals = [ZERO] * 8
        for code in codes:
            first = opening.get(code)
            last = closing.get(code)
            inward_quantity, inward_value, outward_quantity, names = moved.get(
                code, (ZERO, ZERO, ZERO, None)
            )
            source = last or first
            if source is None and names is None:
                continue
            opening_quantity = first.quantity or ZERO if first else ZERO
            opening_value = first.value if first else ZERO
            closing_quantity = last.quantity or ZERO if last else ZERO
            closing_value = last.value if last else ZERO
            outward_value = quantize_ledger(
                opening_value + inward_value - closing_value
            )
            if not any(
                (opening_quantity, inward_quantity, outward_quantity, closing_quantity)
            ):
                continue
            values = [
                opening_quantity,
                opening_value,
                inward_quantity,
                inward_value,
                outward_quantity,
                outward_value,
                closing_quantity,
                closing_value,
            ]
            totals = [
                total + value for total, value in zip(totals, values, strict=True)
            ]
            rows.append(
                StockStatementRow(
                    "ITEM",
                    code,
                    source.product_name if source else (names or ("", "", ""))[0],
                    source.category if source else (names or ("", "", ""))[1],
                    source.unit if source else (names or ("", "", ""))[2],
                    *values,
                )
            )
        rows.append(StockStatementRow("TOTAL", "", "Total", "", "", *totals))
        return rows

    def _inward(
        self,
        firm_id: UUID,
        from_date: date,
        to_date: date,
        warehouse_id: UUID | None,
    ) -> dict[str, tuple[Decimal, Decimal, Decimal, tuple[str, str, str] | None]]:
        """Return each item's quantity in (with its cost) and out in the period."""
        owned = func.coalesce(
            InventoryTransaction.owned_quantity_delta,
            InventoryTransaction.current_quantity_delta
            + InventoryTransaction.quarantine_quantity_delta,
        )
        filters = [
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.is_deleted.is_(False),
            InventoryTransaction.transaction_date >= from_date,
            InventoryTransaction.transaction_date <= to_date,
        ]
        if warehouse_id is not None:
            filters.append(InventoryTransaction.warehouse_id == warehouse_id)
        else:
            filters.append(InventoryTransaction.transaction_type.not_in(_INTERNAL))
        # Asked of the period's movements only, and added up by the database:
        # a year of a busy firm is a row per movement, and reading each one
        # here to add it up took the report past half a minute on PERF01.
        cost = (
            select(
                StockLedgerEntry.transaction_id,
                func.sum(func.coalesce(StockLedgerEntry.total_cost, 0)).label("cost"),
            )
            .where(
                StockLedgerEntry.firm_id == firm_id,
                StockLedgerEntry.transaction_id.in_(
                    select(InventoryTransaction.id).where(*filters)
                ),
            )
            .group_by(StockLedgerEntry.transaction_id)
            .subquery()
        )
        moved = func.coalesce(owned, 0)
        value = func.coalesce(cost.c.cost, 0)
        # Freight added to stock on hand (BUY-16), and a bill's rate put
        # onto its lot (L2 step 8), are value in with no quantity; a
        # cancelled voucher's or bill's movement takes it out.
        landed = InventoryTransaction.transaction_type.in_(
            ("LANDED_COST", "COST_CORRECTION")
        )
        result: dict[
            str, tuple[Decimal, Decimal, Decimal, tuple[str, str, str] | None]
        ] = {}
        for code, name, inward, inward_value, outward in self._session.execute(
            select(
                Product.code,
                func.max(Product.name),
                func.sum(case((moved > 0, moved), else_=0)),
                func.sum(case((moved > 0, func.abs(value)), (landed, value), else_=0)),
                func.sum(
                    case((moved > 0, 0), (landed, 0), (moved < 0, -moved), else_=0)
                ),
            )
            .join(Product, Product.id == InventoryTransaction.product_id)
            .outerjoin(cost, cost.c.transaction_id == InventoryTransaction.id)
            .where(*filters)
            .group_by(Product.code)
        ).all():
            result[code] = (
                Decimal(str(inward or 0)),
                quantize_ledger(Decimal(str(inward_value or 0))),
                Decimal(str(outward or 0)),
                (name, "", ""),
            )
        return result
