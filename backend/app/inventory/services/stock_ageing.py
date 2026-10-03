"""Stock ageing, slow-moving and dead stock (backlog 55 S7).

Three questions about the stock on hand, read from the movements and storing
nothing. Quantities are what the firm **owns** -- the measure the stock
valuation uses -- across every warehouse; moves between the firm's own
warehouses are left out, since nothing came in or went out. Values are at
the moving-average cost the valuation uses on the same day, so a report's
value column agrees with *Stock valuation*.

**Stock ageing -- how old is what is on hand.** The movements do not record
which unit left, so the age is worked out the way FIFO would leave it: what
went out was the oldest, so what is on hand is the most recently received.
Receipts -- goods receipts, opening stock and goods customers returned, each
net of its own reversals -- are summed in SQL into age buckets by their date
(0-30, 31-60, 61-90, 91-180 and over 180 days before the day asked about),
and the quantity on hand is laid over them newest first. What is left once
every receipt is used -- stock found at a count, or older than any movement
-- goes in the oldest bucket, because nothing says it is young.

**Slow-moving** -- stock on hand whose issues over the last ``days`` days
would take more than ``days`` days to sell it at that pace, or that had no
issue at all. **Dead stock** -- stock on hand with no issue in the last
``days`` days. An issue is a dispatch to a customer, net of dispatches
reversed: a write-off, a count loss or goods sent back to a supplier is not
demand, and counting them would make stock nobody buys look alive.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ValidationError
from app.core.utils.chunks import over_chunks
from app.core.utils.money import quantize_ledger
from app.inventory.models import InventoryTransaction
from app.inventory.services.stock_valuation import StockValuationService
from app.products.models import Product, ProductCategory
from app.uom.models import Uom

ZERO = Decimal("0")

#: The upper bound of each bucket, in days before the day asked about; the
#: last bucket is open-ended.
AGE_BOUNDS: tuple[int, ...] = (30, 60, 90, 180)

#: What a receipt is, for the ageing: goods arriving from outside.
RECEIPT_TYPES = ("GOODS_RECEIPT", "OPENING_STOCK", "SALES_RETURN")

#: Moves between the firm's own warehouses.
INTERNAL_TYPES = ("TRANSFER_IN", "TRANSFER_OUT")

#: An issue, for slow and dead stock: goods sent to a customer.
ISSUE_TYPES = ("DISPATCH", "DISPATCH_REVERSAL")


def _owned() -> ColumnElement[Decimal]:
    """Return what a movement did to the quantity the firm owns."""
    return func.coalesce(
        InventoryTransaction.owned_quantity_delta,
        InventoryTransaction.current_quantity_delta
        + InventoryTransaction.quarantine_quantity_delta,
    )


@dataclass(frozen=True)
class _Item:
    code: str
    name: str
    category: str
    unit: str


@dataclass(frozen=True)
class StockAgeingRow:
    """One item's stock on hand, valued, and split by how old it is."""

    product_code: str
    product_name: str
    category: str
    unit: str
    quantity: Decimal
    rate: Decimal
    value: Decimal
    days_0_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_91_180: Decimal
    days_over_180: Decimal
    last_receipt_date: date | None
    #: Issued to customers over the year to the day asked about (STK-14).
    issued_last_year: Decimal = ZERO
    #: Times a year the stock on hand turns over at that pace: issued in
    #: the year over what is on hand. None with nothing issued.
    turnover: Decimal | None = None


@dataclass(frozen=True)
class SlowStockRow:
    """One item on hand that is selling slowly, or not at all."""

    product_code: str
    product_name: str
    category: str
    unit: str
    quantity: Decimal
    value: Decimal
    issued_quantity: Decimal
    days_of_cover: Decimal | None
    last_issue_date: date | None
    days_since_issue: int | None
    last_receipt_date: date | None


class StockAgeingService:
    """Read the ageing and the slow and dead stock for a firm."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def ageing(self, firm_id: UUID, *, on: date) -> list[StockAgeingRow]:
        """Return each item on hand as on ``on``, split into age buckets."""
        on_hand = self._on_hand(firm_id, on)
        if not on_hand:
            return []
        thresholds = [on - timedelta(days=bound) for bound in AGE_BOUNDS]
        when = InventoryTransaction.transaction_date
        bucket = case(
            *((when >= threshold, index) for index, threshold in enumerate(thresholds)),
            else_=len(thresholds),
        )
        received: dict[UUID, list[Decimal]] = {}
        for product_id, index, quantity in self._session.execute(
            select(InventoryTransaction.product_id, bucket, func.sum(_owned()))
            .where(
                *self._moved(firm_id, on),
                InventoryTransaction.transaction_type.in_(
                    RECEIPT_TYPES + tuple(f"{kind}_REVERSAL" for kind in RECEIPT_TYPES)
                ),
            )
            .group_by(InventoryTransaction.product_id, bucket)
        ).all():
            row = received.setdefault(product_id, [ZERO] * (len(AGE_BOUNDS) + 1))
            row[int(index)] += Decimal(str(quantity or 0))
        last_receipts = self._last(firm_id, on, RECEIPT_TYPES)
        rates = StockValuationService(self._session).rates(firm_id, on)
        items = _items(self._session, product_ids=list(on_hand))
        issued = self._issued(firm_id, on, since=on - timedelta(days=365))

        rows: list[StockAgeingRow] = []
        for product_id, quantity in on_hand.items():
            item = items.get(product_id)
            if item is None:
                continue
            split = _newest_first(
                quantity, received.get(product_id, [ZERO] * (len(AGE_BOUNDS) + 1))
            )
            rate = rates.get(product_id, ZERO)
            rows.append(
                StockAgeingRow(
                    product_code=item.code,
                    product_name=item.name,
                    category=item.category,
                    unit=item.unit,
                    quantity=quantity,
                    rate=rate,
                    value=quantize_ledger(quantity * rate),
                    days_0_30=split[0],
                    days_31_60=split[1],
                    days_61_90=split[2],
                    days_91_180=split[3],
                    days_over_180=split[4],
                    last_receipt_date=last_receipts.get(product_id),
                    issued_last_year=max(issued.get(product_id, ZERO), ZERO),
                    turnover=(
                        (max(issued.get(product_id, ZERO), ZERO) / quantity).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        if issued.get(product_id, ZERO) > ZERO
                        else None
                    ),
                )
            )
        rows.sort(key=lambda row: (row.category, row.product_code))
        return rows

    def _issued(self, firm_id: UUID, on: date, *, since: date) -> dict[UUID, Decimal]:
        """Return each product's quantity issued to customers after ``since``."""
        return {
            product_id: -Decimal(str(quantity or 0))
            for product_id, quantity in self._session.execute(
                select(InventoryTransaction.product_id, func.sum(_owned()))
                .where(
                    *self._moved(firm_id, on),
                    InventoryTransaction.transaction_date > since,
                    InventoryTransaction.transaction_type.in_(ISSUE_TYPES),
                )
                .group_by(InventoryTransaction.product_id)
            ).all()
        }

    def slow_moving(
        self, firm_id: UUID, *, on: date, days: int, dead_only: bool = False
    ) -> list[SlowStockRow]:
        """Return the stock on hand selling slower than ``days`` days' cover.

        With ``dead_only``, only what had no issue at all in the ``days``
        days to ``on``. Slowest first: no issue, then the most days of cover,
        then the longest since an issue.

        Raises:
            ValidationError: If ``days`` is not positive.

        """
        if days < 1:
            raise ValidationError("Days must be one or more.")
        on_hand = self._on_hand(firm_id, on)
        if not on_hand:
            return []
        since = on - timedelta(days=days)
        issued: dict[UUID, Decimal] = {
            product_id: -Decimal(str(quantity or 0))
            for product_id, quantity in self._session.execute(
                select(InventoryTransaction.product_id, func.sum(_owned()))
                .where(
                    *self._moved(firm_id, on),
                    InventoryTransaction.transaction_date > since,
                    InventoryTransaction.transaction_type.in_(ISSUE_TYPES),
                )
                .group_by(InventoryTransaction.product_id)
            ).all()
        }
        last_issues = self._last(firm_id, on, ("DISPATCH",))
        last_receipts = self._last(firm_id, on, RECEIPT_TYPES)
        rates = StockValuationService(self._session).rates(firm_id, on)
        items = _items(self._session, product_ids=list(on_hand))

        rows: list[SlowStockRow] = []
        for product_id, quantity in on_hand.items():
            item = items.get(product_id)
            if item is None:
                continue
            out = max(issued.get(product_id, ZERO), ZERO)
            cover = (
                None
                if out == ZERO
                else (quantity * days / out).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                )
            )
            if dead_only and out > ZERO:
                continue
            if not dead_only and cover is not None and cover <= days:
                continue
            last_issue = last_issues.get(product_id)
            rows.append(
                SlowStockRow(
                    product_code=item.code,
                    product_name=item.name,
                    category=item.category,
                    unit=item.unit,
                    quantity=quantity,
                    value=quantize_ledger(quantity * rates.get(product_id, ZERO)),
                    issued_quantity=out,
                    days_of_cover=cover,
                    last_issue_date=last_issue,
                    days_since_issue=(
                        None if last_issue is None else (on - last_issue).days
                    ),
                    last_receipt_date=last_receipts.get(product_id),
                )
            )
        rows.sort(
            key=lambda row: (
                row.days_of_cover is not None,
                -(row.days_of_cover or ZERO),
                row.last_issue_date is not None,
                row.last_issue_date or on,
                row.product_code,
            )
        )
        return rows

    # ------------------------------------------------------------------

    def _moved(self, firm_id: UUID, on: date) -> tuple[ColumnElement[bool], ...]:
        """Return the clauses for the firm's movements to ``on``, not internal."""
        return (
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.is_deleted.is_(False),
            InventoryTransaction.transaction_date <= on,
            InventoryTransaction.transaction_type.not_in(INTERNAL_TYPES),
        )

    def _on_hand(self, firm_id: UUID, on: date) -> dict[UUID, Decimal]:
        """Return each product's owned quantity as on ``on``, where above zero."""
        quantity = func.sum(_owned())
        return {
            product_id: Decimal(str(amount))
            for product_id, amount in self._session.execute(
                select(InventoryTransaction.product_id, quantity)
                .where(*self._moved(firm_id, on))
                .group_by(InventoryTransaction.product_id)
                .having(quantity > 0)
            ).all()
        }

    def _last(
        self, firm_id: UUID, on: date, kinds: tuple[str, ...]
    ) -> dict[UUID, date]:
        """Return each product's latest movement date of ``kinds`` to ``on``."""
        return {
            product_id: last
            for product_id, last in self._session.execute(
                select(
                    InventoryTransaction.product_id,
                    func.max(InventoryTransaction.transaction_date),
                )
                .where(
                    *self._moved(firm_id, on),
                    InventoryTransaction.transaction_type.in_(kinds),
                )
                .group_by(InventoryTransaction.product_id)
            ).all()
            if last is not None
        }


def _newest_first(quantity: Decimal, received: list[Decimal]) -> list[Decimal]:
    """Lay ``quantity`` over the receipts newest bucket first; the rest is oldest."""
    left = quantity
    split: list[Decimal] = []
    for amount in received[:-1]:
        taken = min(left, max(amount, ZERO))
        split.append(taken)
        left -= taken
    split.append(left)
    return split


@over_chunks("product_ids")
def _items(session: Session, *, product_ids: list[UUID]) -> dict[UUID, _Item]:
    """Read each product's code, name, category and unit, once."""
    if not product_ids:
        return {}
    return {
        product_id: _Item(code, name, category or "", unit or "")
        for product_id, code, name, category, unit in session.execute(
            select(
                Product.id,
                Product.code,
                Product.name,
                ProductCategory.name,
                Uom.code,
            )
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(Uom, Uom.id == Product.base_uom_id)
            .where(Product.id.in_(product_ids))
        ).all()
    }
