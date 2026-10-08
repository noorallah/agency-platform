"""Stock alerts for Home's to-do list (STK-14, decision A116).

One read of what needs attention in a firm's stock, each kind counted and
the worst rows listed: at or below the reorder level, out of stock, over the
maximum level, batches near expiry, goods in transit between warehouses, and
count sheets still open. Derived on every read; nothing stored.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.inventory.models import InventoryRecord
from app.products.models import Product

ZERO = Decimal("0")
#: How many rows each kind lists; the count is always the full number.
ROWS_PER_KIND = 10


@dataclass(frozen=True)
class StockAlertRow:
    """One thing to look at."""

    kind: str
    product_code: str
    product_name: str
    quantity: Decimal
    level: Decimal | None = None
    detail: str = ""


@dataclass
class StockAlerts:
    """What needs attention, counted, with the first rows of each kind."""

    low: int = 0
    out: int = 0
    over_maximum: int = 0
    near_expiry: int = 0
    in_transit: int = 0
    open_counts: int = 0
    rows: list[StockAlertRow] = field(default_factory=list)


def stock_alerts(session: Session, firm_id: UUID, *, on: date) -> StockAlerts:
    """Return the firm's stock alerts as on ``on``."""
    from app.batch_serial.services.batch_sale_policy import BatchSalePolicyService
    from app.inventory.models import PhysicalCount

    level = func.max(
        func.coalesce(InventoryRecord.reorder_level, InventoryRecord.minimum_level)
    )
    available = func.sum(InventoryRecord.available_quantity)
    held = func.sum(InventoryRecord.current_quantity)
    maximum = func.max(InventoryRecord.maximum_level)
    in_transit = func.sum(InventoryRecord.in_transit_quantity)
    grouped = session.execute(
        select(
            InventoryRecord.product_id,
            available,
            held,
            level,
            maximum,
            in_transit,
        )
        .join(Product, Product.id == InventoryRecord.product_id)
        .where(
            InventoryRecord.firm_id == firm_id,
            InventoryRecord.is_deleted.is_(False),
            Product.status == "ACTIVE",
            Product.is_deleted.is_(False),
        )
        .group_by(InventoryRecord.product_id)
    ).all()
    products = (
        {
            p.id: p
            for p in session.scalars(
                select(Product).where(Product.id.in_([row[0] for row in grouped]))
            ).all()
        }
        if grouped
        else {}
    )
    alerts = StockAlerts()
    listed: dict[str, list[StockAlertRow]] = {
        "OUT": [],
        "LOW": [],
        "OVER_MAXIMUM": [],
        "IN_TRANSIT": [],
        "NEAR_EXPIRY": [],
    }

    def add(kind: str, row: StockAlertRow) -> None:
        """Keep the first rows of each kind."""
        if len(listed[kind]) < ROWS_PER_KIND:
            listed[kind].append(row)

    for product_id, free, on_hand, reorder, top, moving in grouped:
        product = products.get(product_id)
        if product is None:
            continue
        free = Decimal(str(free or 0))
        on_hand = Decimal(str(on_hand or 0))
        if free <= ZERO and reorder is not None:
            alerts.out += 1
            add("OUT", StockAlertRow("OUT", product.code, product.name, free, reorder))
        elif reorder is not None and free <= Decimal(str(reorder)):
            alerts.low += 1
            add(
                "LOW",
                StockAlertRow(
                    "LOW", product.code, product.name, free, Decimal(str(reorder))
                ),
            )
        if top is not None and on_hand > Decimal(str(top)):
            alerts.over_maximum += 1
            add(
                "OVER_MAXIMUM",
                StockAlertRow(
                    "OVER_MAXIMUM",
                    product.code,
                    product.name,
                    on_hand,
                    Decimal(str(top)),
                ),
            )
        if moving and Decimal(str(moving)) > ZERO:
            alerts.in_transit += 1
            add(
                "IN_TRANSIT",
                StockAlertRow(
                    "IN_TRANSIT", product.code, product.name, Decimal(str(moving))
                ),
            )

    window = BatchSalePolicyService(session).near_expiry_days(firm_id)
    # The batch card's test of a batch that still holds stock
    # (``batch_holds_stock``) and its window, so Home and the card count
    # the same batches: a batch held only in quarantine was on the card
    # and not here (D-STK-47).
    near = session.execute(
        select(
            BatchRecord,
            func.sum(
                InventoryRecord.current_quantity
                + InventoryRecord.quarantine_quantity
                + InventoryRecord.damaged_quantity
                + InventoryRecord.blocked_quantity
            ),
        )
        .join(InventoryRecord, InventoryRecord.batch_id == BatchRecord.id)
        .where(
            BatchRecord.firm_id == firm_id,
            BatchRecord.is_deleted.is_(False),
            BatchRecord.expiry_date.is_not(None),
            BatchRecord.expiry_date > on,
            BatchRecord.expiry_date <= on + timedelta(days=window),
            InventoryRecord.is_deleted.is_(False),
        )
        .group_by(BatchRecord.id)
        .order_by(BatchRecord.expiry_date.asc())
    ).all()
    near_products = (
        {
            p.id: p
            for p in session.scalars(
                select(Product).where(
                    Product.id.in_({batch.product_id for batch, _ in near})
                )
            ).all()
        }
        if near
        else {}
    )
    for batch, quantity in near:
        if not quantity or Decimal(str(quantity)) <= ZERO:
            continue
        alerts.near_expiry += 1
        product = near_products.get(batch.product_id)
        add(
            "NEAR_EXPIRY",
            StockAlertRow(
                "NEAR_EXPIRY",
                product.code if product else "",
                product.name if product else "",
                Decimal(str(quantity)),
                detail=f"{batch.batch_number} expires {batch.expiry_date.isoformat()}",
            ),
        )

    alerts.open_counts = int(
        session.scalar(
            select(func.count(PhysicalCount.id)).where(
                PhysicalCount.firm_id == firm_id,
                PhysicalCount.status == "DRAFT",
                PhysicalCount.is_deleted.is_(False),
            )
        )
        or 0
    )
    for kind in ("OUT", "LOW", "NEAR_EXPIRY", "OVER_MAXIMUM", "IN_TRANSIT"):
        alerts.rows.extend(listed[kind])
    return alerts
