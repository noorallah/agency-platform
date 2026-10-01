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
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import quantize_money
from app.inventory.models import ProductValuation
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


def _net(gross: Decimal, discount: Decimal, bill_share: Decimal) -> Decimal:
    """Return what a line is worth after every discount."""
    return (
        Decimal(gross or _ZERO)
        - Decimal(discount or _ZERO)
        - Decimal(bill_share or _ZERO)
    )


def order_lines(lines: Iterable[object]) -> list[PricedLine]:
    """Read sales order lines: ``base_quantity`` is already in stock units."""
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
        )
        for line in lines
    ]


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

    def check(
        self, firm_id: UUID, lines: Sequence[PricedLine]
    ) -> PriceFloorCheckResponse:
        """Judge every charged line against its floor under the firm's policy."""
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
        findings: list[PriceFloorFinding] = []
        for line in sorted(charged, key=lambda item: item.line_number):
            product = products.get(line.product_id)
            if product is None:
                continue
            minimum = product.minimum_selling_price
            cost: Decimal | None = None
            if policy.include_cost:
                cost = costs.get(line.product_id)
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
                    message=message,
                )
            )
        would_block = bool(findings) and policy.enforcement == "BLOCK"
        summary: str | None = None
        if findings:
            summary = (
                f"{len(findings)} line(s) are sold below their floor price. "
                + " ".join(item.message for item in findings)
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
    ) -> tuple[str | None, dict[str, object] | None]:
        """Refuse a blocked document, or say what to record on its timeline.

        Returns the remark and the event details: a warning under WARN, an
        override when BLOCK refused and a reason was given, nothing when every
        line clears its floor. Whether the caller may override is the router's
        question -- it holds the principal.
        """
        result = self.check(firm_id, lines)
        if not result.findings:
            return None, None
        findings = [item.model_dump(mode="json") for item in result.findings]
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
                {"price_override": {"reason": reason, "findings": findings}},
            )
        return result.message, {"price_warning": {"findings": findings}}
