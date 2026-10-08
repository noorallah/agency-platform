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
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.utils.money import quantize_ledger
from app.finance.models import GLPosting, JournalEntry
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.products.models import Product, ProductCategory
from app.products.models.goods_type import GENERAL_GOODS, GoodsType
from app.uom.models import Uom

ZERO = Decimal("0")


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
    ) -> list[StockValuationRow]:
        """Return each item's quantity, rate and value, then the totals.

        Args:
            firm_id: The firm.
            on: The day the stock is valued as on, inclusive.
            warehouse_id: One warehouse, or None for every warehouse. The
                books cannot be split by warehouse, so the comparison with the
                Inventory account is made only for the whole firm.
            include_zero: List items with nothing on hand as well.

        """
        # What the firm owns, which is not always what it can sell: goods in
        # quarantine have left `current` and are still the firm's and still
        # on the books, and a damaged unit a customer returned was owned
        # without being shelved. The movement records what it did to the
        # owned quantity in `owned_quantity_delta` where that differs from
        # `current`; a quarantine hold records neither, and moves the goods
        # between `current` and `quarantine`, which together are unchanged.
        owned = func.coalesce(
            InventoryTransaction.owned_quantity_delta,
            InventoryTransaction.current_quantity_delta
            + InventoryTransaction.quarantine_quantity_delta,
        )
        quantity_filters = [
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.is_deleted.is_(False),
            InventoryTransaction.transaction_date <= on,
        ]
        if warehouse_id is not None:
            quantity_filters.append(InventoryTransaction.warehouse_id == warehouse_id)
        quantities: dict[UUID, Decimal] = {
            product_id: amount
            for product_id, amount in self._session.execute(
                select(InventoryTransaction.product_id, func.sum(owned))
                .where(*quantity_filters)
                .group_by(InventoryTransaction.product_id)
            ).all()
        }
        rates = self._rates(firm_id, on)
        # The six columns the report shows, for the firm's products: whole
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
        for product_id, raw_quantity in quantities.items():
            product = products.get(product_id)
            if product is None:
                continue
            quantity = Decimal(str(raw_quantity or 0))
            if quantity == ZERO and not include_zero:
                continue
            rate = rates.get(product_id, ZERO)
            value = quantize_ledger(quantity * rate)
            total += value
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
                )
            )
        rows.sort(key=lambda row: (row.category, row.product_code))
        rows.append(_closing("TOTAL", "Grand total", total))
        if warehouse_id is None:
            books = self._books(firm_id, on)
            if books is not None:
                rows.append(_closing("BOOKS", "Inventory account in the books", books))
                rows.append(_closing("DIFFERENCE", "Difference", total - books))
        return rows

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


def _closing(kind: str, label: str, value: Decimal) -> StockValuationRow:
    return StockValuationRow(
        row_type=kind,
        product_code="",
        product_name=label,
        category="",
        unit="",
        quantity=None,
        rate=None,
        value=quantize_ledger(value),
    )


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
            )
            if row.row_type == "ITEM"
        }
        closing = {
            row.product_code: row
            for row in valuation.valuation(
                firm_id, on=to_date, warehouse_id=warehouse_id, include_zero=True
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
        # Freight added to stock on hand (BUY-16) is value in with no
        # quantity; a cancelled voucher's movement takes it out.
        landed = InventoryTransaction.transaction_type == "LANDED_COST"
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
