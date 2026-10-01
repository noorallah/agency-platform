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
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utils.money import quantize_ledger
from app.finance.models import GLPosting, JournalEntry
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.products.models import Product, ProductCategory
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
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.firm_id == firm_id,
                    Product.id.in_(list(quantities) or [None]),
                )
            )
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

    def _rates(self, firm_id: UUID, on: date) -> dict[UUID, Decimal]:
        """Each product's moving-average cost after its last costed movement."""
        ranked = (
            select(
                StockLedgerEntry.product_id.label("product_id"),
                StockLedgerEntry.average_cost_after.label("rate"),
                func.row_number()
                .over(
                    partition_by=StockLedgerEntry.product_id,
                    order_by=(
                        StockLedgerEntry.transaction_date.desc(),
                        StockLedgerEntry.created_at.desc(),
                        StockLedgerEntry.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .where(
                StockLedgerEntry.firm_id == firm_id,
                StockLedgerEntry.is_deleted.is_(False),
                StockLedgerEntry.transaction_date <= on,
                StockLedgerEntry.average_cost_after.is_not(None),
            )
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
