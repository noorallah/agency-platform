"""Warn on, or refuse, a sale below cost or below a product's minimum price.

BACKLOG 64 row 2. Nothing warned before: anybody who could edit an order could
type any rate, and the only thing that ever noticed a sale below cost was the
commission rule that refused to pay on it.

**What is compared.** A line's net value -- its gross less its own discount and
its share of the bill discount -- against a floor for the stock it moves. The
floor per stock unit is the product's ``minimum_selling_price`` and, unless the
firm turned it off, its cost: the moving average the stock is held at, or the
purchase price where nothing has moved yet. Per **stock unit**, because that is
the unit cost is kept in; a line sold by the box is judged on the box's share.
Free goods are not judged -- nothing is charged for them, which is the point --
so a gift line (no quantity charged) never appears here.

**When.** At approval, where a price becomes a promise: a sales order, and a
bill, which may be raised from no order or re-priced from one. The order a
counter bill raises for itself is not judged again; its bill is. A policy of
WARN records the finding on the APPROVED event; BLOCK refuses unless the caller
holds ``SALES_PRICE_OVERRIDE`` and gives a reason, which the event keeps -- the
shape of the licence check (``app/trade_licences/services/licence_check.py``).

A message names the minimum price but never the cost: who sells is not always
allowed to see what the goods cost (``PRODUCT_VIEW_COST_PRICE`` on the product form).

**Near expiry (decision A2).** A line drawn wholly from batches inside the
firm's near-expiry window may be sold below its floor, unless the firm turned
that off (``batch_sale_settings``). The finding is still made and kept on the
approval with the batches named -- the trail says why the floor did not bite --
but it neither warns nor blocks. The batches are the ones the line will take:
those its delivery note recorded, or the earliest-expiry split of the line's
warehouse where nothing is recorded yet.

**By lot (L2 step 10).** A firm costing by lot judges a line against the cost
of the lots it takes, where those are known: the batch an order line pins, or
the lots its delivery note line recorded, weighted by quantity, each at its
unit cost in ``batch_valuations``. A line with no lot chosen yet is judged on
the item's average, as on a firm on Average, which is unchanged.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.services.batch_sale_policy import BatchSalePolicyService
from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import quantize_money
from app.inventory.models import BatchValuation, ProductValuation
from app.inventory.services.lots import costs_by_lot
from app.products.models import Product
from app.sales_order.models import PriceFloorSettings
from app.sales_order.schemas import (
    PriceFloorCheckResponse,
    PriceFloorFinding,
    PriceFloorSettingsResponse,
    PriceFloorSettingsWrite,
)

_ZERO = Decimal("0")

#: The policy every firm without a row shares. Never mutated.
DEFAULT_ENFORCEMENT = "WARN"
DEFAULT_INCLUDE_COST = True


@dataclass(frozen=True, slots=True)
class PricedLine:
    """What one document line sold, in the terms the floor is judged in."""

    line_number: int
    product_id: UUID
    #: Charged quantity in stock units; free goods excluded.
    stock_quantity: Decimal
    #: Gross less the line's discount and its share of the bill discount.
    net_amount: Decimal
    #: Where the stock leaves from, to know which batches a line takes (A2).
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    #: The delivery-note line a bill line ships, whose batches are recorded.
    delivery_note_line_id: UUID | None = None
    #: The lot the line names, where it names one: an order line's pinned
    #: batch. Judged on that lot's cost on a firm costing by lot.
    lot_id: UUID | None = None


def _net(gross: Decimal, discount: Decimal, bill_share: Decimal) -> Decimal:
    """Return what a line is worth after every discount."""
    return (
        Decimal(gross or _ZERO)
        - Decimal(discount or _ZERO)
        - Decimal(bill_share or _ZERO)
    )


def order_lines(
    lines: Iterable[object], *, warehouse_id: UUID | None = None
) -> list[PricedLine]:
    """Read sales order lines: ``base_quantity`` is already in stock units.

    ``warehouse_id`` is the order's own, for a line that names none.
    """
    return [
        PricedLine(
            line_number=int(getattr(line, "line_number", 0)),
            product_id=getattr(line, "product_id"),  # noqa: B009
            stock_quantity=Decimal(getattr(line, "base_quantity", None) or _ZERO),
            net_amount=_net(
                getattr(line, "gross_amount", _ZERO),
                getattr(line, "discount_amount", _ZERO),
                getattr(line, "bill_discount_amount", _ZERO),
            ),
            warehouse_id=getattr(line, "warehouse_id", None) or warehouse_id,
            storage_node_id=getattr(line, "storage_node_id", None),
            lot_id=getattr(line, "pinned_batch_id", None),
        )
        for line in lines
    ]


def _source_type(line: object) -> str:
    """Return a bill line's source type as text, stored or enum alike."""
    kind = getattr(line, "source_document_type", None)
    return str(getattr(kind, "value", kind) or "")


def invoice_lines(lines: Iterable[object]) -> list[PricedLine]:
    """Read bill lines: the billed quantity through the line's own factor."""
    return [
        PricedLine(
            line_number=int(getattr(line, "line_number", 0)),
            product_id=getattr(line, "product_id"),  # noqa: B009
            stock_quantity=Decimal(
                getattr(line, "current_invoice_quantity", None) or _ZERO
            )
            * Decimal(getattr(line, "conversion_factor", None) or Decimal("1")),
            net_amount=_net(
                getattr(line, "gross_amount", _ZERO),
                getattr(line, "discount_amount", _ZERO),
                getattr(line, "bill_discount_amount", _ZERO),
            ),
            warehouse_id=getattr(line, "warehouse_id", None),
            storage_node_id=getattr(line, "storage_node_id", None),
            delivery_note_line_id=(
                getattr(line, "source_document_line_id", None)
                if _source_type(line) == "DELIVERY_NOTE"
                else None
            ),
        )
        for line in lines
    ]


class PriceFloorService:
    """The firm's price-floor policy, and judging a document against it."""

    def __init__(self, session: Session) -> None:
        """Hold the session the document is being written on."""
        self._session = session

    # -- Policy ---------------------------------------------------------------

    def _stored(self, firm_id: UUID) -> PriceFloorSettings | None:
        """Return the firm's own row, or None if it never chose."""
        return self._session.scalar(
            select(PriceFloorSettings).where(
                PriceFloorSettings.firm_id == firm_id,
                PriceFloorSettings.is_deleted.is_(False),
            )
        )

    def settings_response(self, firm_id: UUID) -> PriceFloorSettingsResponse:
        """Report the firm's policy and whether the firm actually chose it."""
        stored = self._stored(firm_id)
        return PriceFloorSettingsResponse(
            enforcement=(
                stored.enforcement if stored is not None else DEFAULT_ENFORCEMENT
            ),
            include_cost=(
                stored.include_cost if stored is not None else DEFAULT_INCLUDE_COST
            ),
            is_configured=stored is not None,
        )

    def update_settings(
        self, data: PriceFloorSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PriceFloorSettingsResponse:
        """Replace the firm's policy, creating its row on the first write."""
        row = self._stored(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = PriceFloorSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = {"enforcement": row.enforcement, "include_cost": row.include_cost}
        row.enforcement = data.enforcement
        row.include_cost = data.include_cost
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "price_floor_settings.updated"
                if before is not None
                else "price_floor_settings.created"
            ),
            entity_type="price_floor_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "enforcement": row.enforcement,
                "include_cost": row.include_cost,
            },
        )
        self._session.commit()
        return self.settings_response(firm_id)

    # -- Judging --------------------------------------------------------------

    def _costs(self, firm_id: UUID, product_ids: Sequence[UUID]) -> dict[UUID, Decimal]:
        """Return each product's moving average cost, where it has one."""
        rows = self._session.execute(
            select(ProductValuation.product_id, ProductValuation.average_cost).where(
                ProductValuation.firm_id == firm_id,
                ProductValuation.product_id.in_(product_ids),
                ProductValuation.is_deleted.is_(False),
            )
        ).all()
        return {
            product_id: Decimal(cost)
            for product_id, cost in rows
            if cost is not None and Decimal(cost) > _ZERO
        }

    def _lot_costs(
        self, firm_id: UUID, lines: Sequence[PricedLine]
    ) -> dict[PricedLine, Decimal]:
        """Return the unit cost of the lots each line takes, where all are known.

        Only for a firm costing by lot. A line's lots are the batch it names,
        or else those its delivery note line recorded, weighted by quantity.
        A line with a lot that holds no cost is left to the average, as is
        a line with no lot at all. One query for every line's lots.
        """
        named = {line: line.lot_id for line in lines if line.lot_id is not None}
        shipped = {
            line: line.delivery_note_line_id
            for line in lines
            if line.lot_id is None and line.delivery_note_line_id is not None
        }
        if not (named or shipped) or not costs_by_lot(self._session, firm_id):
            return {}
        # Imported here: the delivery note imports this module.
        from app.delivery_note.models import DeliveryNoteLineBatch

        picks: dict[UUID, list[tuple[UUID, Decimal]]] = {}
        if shipped:
            for note_line_id, batch_id, quantity in self._session.execute(
                select(
                    DeliveryNoteLineBatch.delivery_note_line_id,
                    DeliveryNoteLineBatch.batch_id,
                    DeliveryNoteLineBatch.quantity,
                ).where(
                    DeliveryNoteLineBatch.delivery_note_line_id.in_(
                        set(shipped.values())
                    ),
                    DeliveryNoteLineBatch.is_deleted.is_(False),
                )
            ).all():
                picks.setdefault(note_line_id, []).append((batch_id, Decimal(quantity)))
        wanted = set(named.values()) | {
            batch_id for rows in picks.values() for batch_id, _ in rows
        }
        if not wanted:
            return {}
        unit = {
            batch_id: Decimal(str(cost))
            for batch_id, cost in self._session.execute(
                select(BatchValuation.batch_id, BatchValuation.unit_cost).where(
                    BatchValuation.firm_id == firm_id,
                    BatchValuation.batch_id.in_(wanted),
                    BatchValuation.is_deleted.is_(False),
                )
            ).all()
            if cost is not None and Decimal(str(cost)) > _ZERO
        }
        found: dict[PricedLine, Decimal] = {}
        for line, batch_id in named.items():
            if batch_id in unit:
                found[line] = unit[batch_id]
        for line, note_line_id in shipped.items():
            rows = [row for row in picks.get(note_line_id, []) if row[1] > _ZERO]
            if not rows or any(batch_id not in unit for batch_id, _ in rows):
                continue
            quantity = sum((qty for _, qty in rows), _ZERO)
            found[line] = (
                sum((unit[batch_id] * qty for batch_id, qty in rows), _ZERO) / quantity
            )
        return found

    def unit_costs(
        self, firm_id: UUID, lines: Sequence[PricedLine]
    ) -> dict[PricedLine, Decimal]:
        """Return each line's cost per stock unit, as the floor would judge it.

        The lots the line takes where all are known (a firm costing by lot),
        else the item's moving average, else its purchase price; a line with
        none of the three is left out. A few reads for every line given, so a
        page of documents is costed at once (L3 step 4).
        """
        product_ids = sorted({line.product_id for line in lines}, key=str)
        if not product_ids:
            return {}
        averages = self._costs(firm_id, product_ids)
        lots = self._lot_costs(firm_id, lines)
        purchase = {
            product_id: Decimal(price)
            for product_id, price in self._session.execute(
                select(Product.id, Product.purchase_price).where(
                    Product.id.in_(product_ids)
                )
            ).all()
            if price
        }
        found: dict[PricedLine, Decimal] = {}
        for line in lines:
            cost = (
                lots.get(line)
                or averages.get(line.product_id)
                or purchase.get(line.product_id)
            )
            if cost is not None:
                found[line] = cost
        return found

    def _split(
        self, firm_id: UUID, line: PricedLine, *, as_of: date
    ) -> list[tuple[UUID | None, Decimal]]:
        """Return the batches a line takes: recorded, or what FEFO would draw."""
        # Imported here: the delivery note imports this module.
        from app.batch_serial.services.batch_serial_service import (
            BatchSerialService,
        )
        from app.delivery_note.models import DeliveryNoteLine, DeliveryNoteLineBatch

        warehouse_id = line.warehouse_id
        storage_node_id = line.storage_node_id
        order_line_id: UUID | None = None
        if line.delivery_note_line_id is not None:
            recorded = self._session.execute(
                select(
                    DeliveryNoteLineBatch.batch_id, DeliveryNoteLineBatch.quantity
                ).where(
                    DeliveryNoteLineBatch.delivery_note_line_id
                    == line.delivery_note_line_id,
                    DeliveryNoteLineBatch.is_deleted.is_(False),
                )
            ).all()
            if recorded:
                return [(batch_id, Decimal(qty)) for batch_id, qty in recorded]
            note_line = self._session.get(DeliveryNoteLine, line.delivery_note_line_id)
            if note_line is not None:
                warehouse_id = note_line.warehouse_id or warehouse_id
                storage_node_id = note_line.storage_node_id or storage_node_id
                order_line_id = note_line.sales_order_line_id
        if warehouse_id is None:
            return []
        return [
            (item.batch_id, item.fefo)
            for item in BatchSerialService(self._session).batch_availability(
                firm_scope=firm_id,
                product_id=line.product_id,
                warehouse_id=warehouse_id,
                storage_node_id=storage_node_id,
                as_of=as_of,
                quantity=line.stock_quantity,
                sales_order_line_id=order_line_id,
            )
            if item.fefo > _ZERO
        ]

    def check(
        self,
        firm_id: UUID,
        lines: Sequence[PricedLine],
        *,
        as_of: date | None = None,
    ) -> PriceFloorCheckResponse:
        """Judge every charged line against its floor under the firm's policy.

        ``as_of`` is the document's date: with it, a line drawn wholly from
        near-expiry batches is found but exempt (decision A2).
        """
        policy = self.settings_response(firm_id)
        if policy.enforcement == "OFF":
            return PriceFloorCheckResponse(
                enforcement="OFF", findings=[], would_block=False, message=None
            )
        charged = [line for line in lines if line.stock_quantity > _ZERO]
        product_ids = sorted({line.product_id for line in charged}, key=str)
        if not product_ids:
            return PriceFloorCheckResponse(
                enforcement=policy.enforcement,
                findings=[],
                would_block=False,
                message=None,
            )
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            )
        }
        costs = self._costs(firm_id, product_ids) if policy.include_cost else {}
        lot_costs = self._lot_costs(firm_id, charged) if policy.include_cost else {}
        findings: list[PriceFloorFinding] = []
        for line in sorted(charged, key=lambda item: item.line_number):
            product = products.get(line.product_id)
            if product is None:
                continue
            minimum = product.minimum_selling_price
            cost: Decimal | None = None
            if policy.include_cost:
                cost = lot_costs.get(line) or costs.get(line.product_id)
                if cost is None and product.purchase_price:
                    cost = Decimal(product.purchase_price)
            floors = [
                (Decimal(minimum), "minimum") if minimum else None,
                (cost, "cost") if cost else None,
            ]
            candidates = [item for item in floors if item is not None]
            if not candidates:
                continue
            floor_rate, kind = max(candidates, key=lambda item: item[0])
            floor_amount = quantize_money(floor_rate * line.stock_quantity)
            if quantize_money(line.net_amount) >= floor_amount:
                continue
            net_rate = quantize_money(line.net_amount / line.stock_quantity)
            label = f"{product.code} {product.name}".strip()
            exemption = (
                BatchSalePolicyService(self._session).floor_exemption(
                    firm_id, self._split(firm_id, line, as_of=as_of), as_of=as_of
                )
                if as_of is not None
                else None
            )
            if kind == "minimum":
                message = (
                    f"Line {line.line_number} ({label}) is sold at {net_rate} a "
                    f"unit, below its minimum price of {quantize_money(floor_rate)}."
                )
            else:
                message = (
                    f"Line {line.line_number} ({label}) is sold at {net_rate} a "
                    "unit, below what it cost."
                )
            findings.append(
                PriceFloorFinding(
                    line_number=line.line_number,
                    product_id=line.product_id,
                    product_code=product.code,
                    product_name=product.name,
                    net_rate=net_rate,
                    floor=kind,
                    minimum_price=(
                        quantize_money(floor_rate) if kind == "minimum" else None
                    ),
                    message=(
                        f"{message} Allowed, {exemption}." if exemption else message
                    ),
                    exemption=exemption,
                )
            )
        judged = [item for item in findings if item.exemption is None]
        would_block = bool(judged) and policy.enforcement == "BLOCK"
        summary: str | None = None
        if judged:
            summary = (
                f"{len(judged)} line(s) are sold below their floor price. "
                + " ".join(item.message for item in judged)
            )
        return PriceFloorCheckResponse(
            enforcement=policy.enforcement,
            findings=findings,
            would_block=would_block,
            message=summary,
        )

    def enforce(
        self,
        firm_id: UUID,
        lines: Sequence[PricedLine],
        *,
        override_reason: str | None,
        as_of: date | None = None,
    ) -> tuple[str | None, dict[str, object] | None]:
        """Refuse a blocked document, or say what to record on its timeline.

        Returns the remark and the event details: a warning under WARN, an
        override when BLOCK refused and a reason was given, nothing when every
        line clears its floor. A line exempt for near expiry (A2) is kept as
        ``price_near_expiry`` and never warns or blocks. Whether the caller
        may override is the router's question -- it holds the principal.
        """
        result = self.check(firm_id, lines, as_of=as_of)
        if not result.findings:
            return None, None
        exempt = [
            item.model_dump(mode="json")
            for item in result.findings
            if item.exemption is not None
        ]
        findings = [
            item.model_dump(mode="json")
            for item in result.findings
            if item.exemption is None
        ]
        if not findings:
            return (
                "Sold below the floor price on near-expiry stock: "
                + " ".join(str(item["message"]) for item in exempt),
                {"price_near_expiry": {"findings": exempt}},
            )
        extra: dict[str, object] = (
            {"price_near_expiry": {"findings": exempt}} if exempt else {}
        )
        if result.would_block:
            reason = (override_reason or "").strip()
            if not reason:
                raise ValidationError(
                    f"{result.message} The firm's policy refuses a sale below "
                    "its floor price; correct the rate, or approve with an "
                    "override reason if you hold the price override permission."
                )
            return (
                f"Price floor overridden: {reason}",
                {"price_override": {"reason": reason, "findings": findings}, **extra},
            )
        return result.message, {"price_warning": {"findings": findings}, **extra}
