"""Expiry rules per product (STK-5, decision A113).

Three day counts, each on the product, else its category, else the firm:

* **stop selling** -- a batch this close to expiry is not dispatched; the
  firm's rule is none (only an expired batch is refused);
* **alert** -- the near-expiry window, else the firm's
  ``batch_sale_settings.near_expiry_days``;
* **return to supplier** -- a batch this close to expiry is due back; the
  firm has no default, so a product with no rule is never listed.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.products.models import Product, ProductCategory


@dataclass(frozen=True)
class ExpiryRule:
    """What one product's batches are held to."""

    stop_sale_days: int
    alert_days: int
    return_days: int | None

    def sell_until(self, as_of: date) -> date | None:
        """Return the date a batch must outlast to be sold, or None."""
        return (
            as_of + timedelta(days=self.stop_sale_days) if self.stop_sale_days else None
        )


def _pick(product: Product, category: ProductCategory | None, field: str) -> int | None:
    """Return the product's value for a rule, else its category's."""
    own = getattr(product, field)
    if own is not None:
        return int(own)
    inherited = getattr(category, field) if category is not None else None
    return None if inherited is None else int(inherited)


def expiry_rules(
    session: Session, firm_id: UUID, product_ids: set[UUID]
) -> dict[UUID, ExpiryRule]:
    """Return each product's rule, product over category over firm."""
    from app.batch_serial.services.batch_sale_policy import BatchSalePolicyService

    firm_alert = BatchSalePolicyService(session).near_expiry_days(firm_id)
    if not product_ids:
        return {}
    products = list(
        session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    )
    category_ids = {p.category_id for p in products if p.category_id}
    categories = (
        {
            c.id: c
            for c in session.scalars(
                select(ProductCategory).where(ProductCategory.id.in_(category_ids))
            ).all()
        }
        if category_ids
        else {}
    )
    rules: dict[UUID, ExpiryRule] = {}
    for product in products:
        category = categories.get(product.category_id) if product.category_id else None

        stop = _pick(product, category, "expiry_stop_sale_days")
        alert = _pick(product, category, "expiry_alert_days")
        rules[product.id] = ExpiryRule(
            stop_sale_days=stop or 0,
            alert_days=firm_alert if alert is None else alert,
            return_days=_pick(product, category, "expiry_return_days"),
        )
    return rules


@dataclass(frozen=True)
class ReturnDueRecord:
    """One batch due back to its supplier."""

    batch_id: UUID
    batch_number: str
    product_id: UUID
    product_code: str
    product_name: str
    vendor_id: UUID | None
    expiry_date: date
    days_to_expiry: int
    quantity: Decimal


def returns_due(session: Session, firm_id: UUID, *, on: date) -> list[ReturnDueRecord]:
    """Return the batches in stock within their product's return window."""
    from app.inventory.models import InventoryRecord

    held = session.execute(
        select(
            BatchRecord,
            func.sum(
                InventoryRecord.current_quantity + InventoryRecord.quarantine_quantity
            ),
        )
        .join(InventoryRecord, InventoryRecord.batch_id == BatchRecord.id)
        .where(
            BatchRecord.firm_id == firm_id,
            BatchRecord.is_deleted.is_(False),
            BatchRecord.expiry_date.is_not(None),
            BatchRecord.status != "DESTROYED",
            InventoryRecord.is_deleted.is_(False),
        )
        .group_by(BatchRecord.id)
    ).all()
    stocked = [(batch, qty) for batch, qty in held if qty and Decimal(str(qty)) > 0]
    rules = expiry_rules(session, firm_id, {batch.product_id for batch, _ in stocked})
    products = (
        {
            p.id: p
            for p in session.scalars(
                select(Product).where(Product.id.in_(list(rules)))
            ).all()
        }
        if rules
        else {}
    )
    due: list[ReturnDueRecord] = []
    for batch, quantity in stocked:
        rule = rules.get(batch.product_id)
        if rule is None or rule.return_days is None or batch.expiry_date is None:
            continue
        if batch.expiry_date > on + timedelta(days=rule.return_days):
            continue
        product = products.get(batch.product_id)
        due.append(
            ReturnDueRecord(
                batch_id=batch.id,
                batch_number=batch.batch_number,
                product_id=batch.product_id,
                product_code=product.code if product else "",
                product_name=product.name if product else "",
                vendor_id=batch.vendor_id,
                expiry_date=batch.expiry_date,
                days_to_expiry=(batch.expiry_date - on).days,
                quantity=Decimal(str(quantity)),
            )
        )
    due.sort(key=lambda record: (record.expiry_date, record.batch_number))
    return due
