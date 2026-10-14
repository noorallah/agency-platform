"""Billing without stock on a firm costing by lot (L2 step 7a).

`docs/design/LOT_COST_DESIGN.md`, section 3.7. By default a by-lot firm
never sells what no lot holds. A firm may allow it -- its
``stock_lot_settings.allow_billing_without_stock`` and the item's own "allow
negative stock" must both be on -- and then the bill maker is asked and
confirms. The units leave at the item's newest lot cost, or its average
where it was never bought, and wait in ``lot_shortfalls`` for their lot.

The goods receipt that brings the item into the same warehouse covers them
at once, oldest sale first: the units leave the new lot, the sale's line
names it, and the difference between the cost used and the lot's cost is
posted on the receipt's date, never back into the day of the sale. A return
before then clears the units at the cost used. What is still waiting is
never stored; it is each row's quantity less what cleared it.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_today
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_money
from app.delivery_note.models import DeliveryNoteLineBatch
from app.inventory.models import (
    InventoryTransaction,
    LotShortfall,
    LotShortfallSettlement,
    ProductValuation,
    StockLedgerEntry,
    StockLotSettings,
)
from app.inventory.schemas import LotShortfallResponse
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.lots import costs_by_lot, newest_lot_cost
from app.products.models import Product

ZERO = Decimal("0")

#: A lot that came in covered the units.
SETTLED = "SETTLED"
#: The customer sent the units back before their lot came.
RETURNED = "RETURNED"


@dataclass(frozen=True, slots=True)
class OpenShortfall:
    """One shortfall and what of it is still waiting for a lot."""

    row: LotShortfall
    quantity: Decimal
    cost: Decimal

    def share_of_cost(self, quantity: Decimal) -> Decimal:
        """Return the cost used for ``quantity`` of the units still waiting.

        The last share takes all that is left, so a row clears at exactly
        the cost its sale carried.
        """
        if quantity >= self.quantity:
            return self.cost
        return quantize_money(self.cost * quantity / self.quantity)


class LotShortfallService:
    """Record, settle and report units billed before any lot held them."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the caller's session; it never commits."""
        self._session = session

    def may_bill_short(self, firm_id: UUID, product_id: UUID) -> bool:
        """Say whether the firm may bill this item past what its lots hold."""
        if not costs_by_lot(self._session, firm_id):
            return False
        allowed = self._session.scalar(
            select(StockLotSettings.allow_billing_without_stock).where(
                StockLotSettings.firm_id == firm_id,
                StockLotSettings.is_deleted.is_(False),
            )
        )
        if not allowed:
            return False
        product = self._session.get(Product, product_id)
        return product is not None and bool(product.allow_negative_stock)

    def cost_for(self, firm_id: UUID, product_id: UUID) -> Decimal:
        """Return what a unit billed before its lot leaves at.

        The item's newest lot cost -- its last purchase -- or its average
        where no lot of it was ever valued, or nothing at all for an item
        never bought.
        """
        newest = newest_lot_cost(self._session, firm_id, product_id)
        if newest is not None:
            return newest
        average = self._session.scalar(
            select(ProductValuation.average_cost).where(
                ProductValuation.firm_id == firm_id,
                ProductValuation.product_id == product_id,
                ProductValuation.is_deleted.is_(False),
            )
        )
        return ZERO if average is None else Decimal(str(average))

    def record(
        self,
        *,
        firm_id: UUID,
        product_id: UUID,
        place: tuple[UUID, UUID, UUID | None],
        note_id: UUID,
        note_line_id: UUID,
        document_number: str,
        movement: InventoryTransaction,
        sale_date: date,
        unit_cost: Decimal,
        actor_id: UUID,
    ) -> LotShortfall:
        """Write down units a confirmed dispatch took past what lots held.

        ``place`` is the (branch, warehouse, bin) the units left from;
        ``actor_id`` is who confirmed the bill.
        """
        cost = self._session.scalar(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                StockLedgerEntry.transaction_id == movement.id
            )
        )
        branch_id, warehouse_id, node_id = place
        row = LotShortfall(
            firm_id=firm_id,
            product_id=product_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=node_id,
            delivery_note_id=note_id,
            delivery_note_line_id=note_line_id,
            document_number=document_number,
            inventory_transaction_id=movement.id,
            sale_date=sale_date,
            quantity=Decimal(str(movement.quantity)),
            unit_cost=unit_cost,
            cost_amount=Decimal(str(cost or ZERO)),
            confirmed_by=actor_id,
            confirmed_at=utc_now(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def open_shortfalls(
        self,
        firm_id: UUID,
        *,
        product_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        note_line_id: UUID | None = None,
    ) -> list[OpenShortfall]:
        """Return the shortfalls still waiting, oldest sale first."""
        query = select(LotShortfall).where(
            LotShortfall.firm_id == firm_id,
            LotShortfall.is_deleted.is_(False),
        )
        if product_id is not None:
            query = query.where(LotShortfall.product_id == product_id)
        if warehouse_id is not None:
            query = query.where(LotShortfall.warehouse_id == warehouse_id)
        if note_line_id is not None:
            query = query.where(LotShortfall.delivery_note_line_id == note_line_id)
        rows = list(
            self._session.scalars(
                query.order_by(
                    LotShortfall.sale_date.asc(),
                    LotShortfall.created_at.asc(),
                    LotShortfall.id.asc(),
                )
            ).all()
        )
        if not rows:
            return []
        cleared = {
            shortfall_id: (Decimal(str(quantity)), Decimal(str(cost)))
            for shortfall_id, quantity, cost in self._session.execute(
                select(
                    LotShortfallSettlement.lot_shortfall_id,
                    func.sum(LotShortfallSettlement.quantity),
                    func.sum(LotShortfallSettlement.cost_used_amount),
                )
                .where(
                    LotShortfallSettlement.lot_shortfall_id.in_(
                        [row.id for row in rows]
                    ),
                    LotShortfallSettlement.is_deleted.is_(False),
                )
                .group_by(LotShortfallSettlement.lot_shortfall_id)
            ).all()
        }
        waiting: list[OpenShortfall] = []
        for row in rows:
            quantity, cost = cleared.get(row.id, (ZERO, ZERO))
            left = Decimal(str(row.quantity)) - quantity
            if left > ZERO:
                waiting.append(
                    OpenShortfall(
                        row=row,
                        quantity=left,
                        cost=Decimal(str(row.cost_amount)) - cost,
                    )
                )
        return waiting

    def settle_from_lot(
        self,
        *,
        firm_id: UUID,
        product_id: UUID,
        lot_id: UUID,
        lot_place: tuple[UUID, UUID, UUID | None],
        available: Decimal,
        on: date,
        document_id: UUID,
        document_line_id: UUID,
        document_number: str,
        actor_id: UUID,
    ) -> Decimal:
        """Cover units waiting in this warehouse from a lot a receipt brought.

        Oldest sale first, up to ``available`` -- what the lot holds free.
        Each covered share leaves the lot at the lot's cost and fills the row
        the sale took below zero at exactly the cost it left with, and the
        sale's delivery line now names the lot.

        Returns:
            The lot's cost less the cost used, over every share covered: what
            the cost of those sales was out by, for the caller to post on the
            receipt's date.

        """
        inventory = InventoryService(self._session)
        out_by = ZERO
        for waiting in self.open_shortfalls(
            firm_id, product_id=product_id, warehouse_id=lot_place[1]
        ):
            if available <= ZERO:
                break
            take = min(waiting.quantity, available)
            owed_value = waiting.share_of_cost(take)
            row = waiting.row
            out, back, given = inventory.settle_shortfall(
                firm_scope=firm_id,
                actor_id=actor_id,
                product_id=product_id,
                lot_id=lot_id,
                lot_place=lot_place,
                owed_place=(row.branch_id, row.warehouse_id, row.storage_node_id),
                quantity=take,
                owed_value=owed_value,
                reference_number=f"{document_number}-LS",
                transaction_date=on,
            )
            self._session.add(
                LotShortfallSettlement(
                    lot_shortfall_id=row.id,
                    firm_id=firm_id,
                    kind=SETTLED,
                    quantity=take,
                    batch_id=lot_id,
                    cost_used_amount=owed_value,
                    lot_cost_amount=given,
                    settled_on=on,
                    document_type="GOODS_RECEIPT",
                    document_id=document_id,
                    document_line_id=document_line_id,
                    document_number=document_number,
                    out_transaction_id=out.id,
                    in_transaction_id=back.id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            # The sale's line now names the lot its units came out of, at
            # what the lot gave, so a bill raised from it later and a return
            # of it read the lot like any other.
            self._session.add(
                DeliveryNoteLineBatch(
                    delivery_note_line_id=row.delivery_note_line_id,
                    firm_id=firm_id,
                    batch_id=lot_id,
                    quantity=take,
                    inventory_transaction_id=out.id,
                    cost_amount=given,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            out_by += given - owed_value
            available -= take
        self._session.flush()
        return out_by

    def record_return(
        self,
        waiting: OpenShortfall,
        *,
        quantity: Decimal,
        value: Decimal,
        movement_id: UUID,
        on: date,
        document_id: UUID,
        document_line_id: UUID,
        document_number: str,
        actor_id: UUID,
    ) -> None:
        """Clear units the customer sent back before their lot came."""
        self._session.add(
            LotShortfallSettlement(
                lot_shortfall_id=waiting.row.id,
                firm_id=waiting.row.firm_id,
                kind=RETURNED,
                quantity=quantity,
                batch_id=None,
                cost_used_amount=value,
                lot_cost_amount=None,
                settled_on=on,
                document_type="SALES_RETURN",
                document_id=document_id,
                document_line_id=document_line_id,
                document_number=document_number,
                out_transaction_id=None,
                in_transaction_id=movement_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    def returns_of_line(self, return_line_id: UUID) -> list[LotShortfallSettlement]:
        """Return the live rows a sales return line's units cleared."""
        return list(
            self._session.scalars(
                select(LotShortfallSettlement).where(
                    LotShortfallSettlement.document_line_id == return_line_id,
                    LotShortfallSettlement.kind == RETURNED,
                    LotShortfallSettlement.is_deleted.is_(False),
                )
            ).all()
        )

    def assert_none_open(
        self, firm_id: UUID, *, starts_on: date, ends_on: date, label: str
    ) -> None:
        """Refuse a year-close while units sold in it still wait for a lot.

        ``label`` names what is being closed, as the refusal says it.

        Raises:
            ValidationError: Naming the bills still waiting.

        """
        waiting = [
            item
            for item in self.open_shortfalls(firm_id)
            if starts_on <= item.row.sale_date <= ends_on
        ]
        if waiting:
            numbers = sorted({item.row.document_number for item in waiting})
            more = " and more" if len(numbers) > 12 else ""
            raise ValidationError(
                f"{label} cannot be closed while {len(numbers)} "
                f"bill{'s' if len(numbers) != 1 else ''} dated in it "
                f"{'wait' if len(numbers) != 1 else 'waits'} for their cost: "
                f"{', '.join(numbers[:12])}{more}. Enter the purchases that "
                "bring their goods first."
            )

    def report(self, firm_id: UUID, *, show_cost: bool) -> list[LotShortfallResponse]:
        """List every bill waiting for its cost, oldest first, with its age."""
        waiting = self.open_shortfalls(firm_id)
        if not waiting:
            return []
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_({item.row.product_id for item in waiting})
                )
            ).all()
        }
        today = firm_today(self._session, firm_id)
        rows: list[LotShortfallResponse] = []
        for item in waiting:
            row = item.row
            product = products.get(row.product_id)
            rows.append(
                LotShortfallResponse(
                    id=row.id,
                    product_id=row.product_id,
                    product_code=product.code if product else "",
                    product_name=product.name if product else "",
                    warehouse_id=row.warehouse_id,
                    delivery_note_id=row.delivery_note_id,
                    document_number=row.document_number,
                    sale_date=row.sale_date,
                    age_days=max((today - row.sale_date).days, 0),
                    quantity=Decimal(str(row.quantity)),
                    quantity_waiting=item.quantity,
                    unit_cost=Decimal(str(row.unit_cost)) if show_cost else None,
                    cost_waiting=item.cost if show_cost else None,
                    confirmed_by=row.confirmed_by,
                    confirmed_at=row.confirmed_at,
                )
            )
        return rows
