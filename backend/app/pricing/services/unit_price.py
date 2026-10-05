"""The price a sales line starts at when nobody typed one (SEL-9, A89).

Four arrangements can each name a price, and the most specific wins
(``resolve_unit_price``): a fixed rate on a price list that applies to this
customer on this date and quantity, then the batch's price to retailer or to
stockist by the customer's trade class where the line names a batch and the
firm's profile has BATCH_PTR_PTS (PG-14), then the customer's price level (its
own, or its group's), then the product's selling price. A typed price beats
all of them, so a document asks only for a line that names none.

Built once per document, like ``PriceListResolver``: the customer, its level,
its territory and the date do not change between lines, so the lists and the
level's rates are read once and every line is matched against them.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.business.gating import feature_enabled
from app.core.utils.pricing import LinePrice, batch_trade_rate, resolve_unit_price
from app.customers.models import Customer, CustomerGroup
from app.pricing.models import PriceLevel, ProductPriceLevel
from app.pricing.services.price_list_service import PriceListResolver
from app.products.models import Product


def customer_price_level(session: Session, customer: Customer | None) -> UUID | None:
    """Return the level a customer buys at: its own, else its group's."""
    if customer is None:
        return None
    if customer.price_level_id is not None:
        return customer.price_level_id
    if customer.customer_group_id is None:
        return None
    group = session.get(CustomerGroup, customer.customer_group_id)
    if group is None or group.is_deleted:
        return None
    return group.price_level_id


class UnitPriceResolver:
    """Answer what price a line starts at, for one customer on one date."""

    def __init__(
        self,
        session: Session,
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        territory_id: UUID | None,
        on: date,
    ) -> None:
        """Load the customer's lists and level for one document."""
        self._session = session
        self._firm_id = firm_id
        self._on = on
        self._lists = PriceListResolver(
            session,
            firm_id=firm_id,
            customer_id=customer_id,
            territory_id=territory_id,
            on=on,
        )
        customer = session.get(Customer, customer_id) if customer_id else None
        self._trade_class = customer.trade_class if customer is not None else None
        #: Read on the first line naming a batch, never for a document without.
        self._batch_rates_on: bool | None = None
        self.level_id = customer_price_level(session, customer)
        level = session.get(PriceLevel, self.level_id) if self.level_id else None
        if level is None or level.is_deleted or not level.is_active:
            self.level_id = None
        self._levels: dict[UUID, Decimal] = {}
        if self.level_id is not None:
            self._levels = {
                product_id: Decimal(str(rate))
                for product_id, rate in session.execute(
                    select(ProductPriceLevel.product_id, ProductPriceLevel.rate).where(
                        ProductPriceLevel.firm_id == firm_id,
                        ProductPriceLevel.price_level_id == self.level_id,
                        ProductPriceLevel.is_deleted.is_(False),
                    )
                ).all()
            }
        self._products: dict[UUID, Decimal | None] = {}

    def price(
        self,
        product_id: UUID,
        quantity: Decimal | None = None,
        *,
        batch_id: UUID | None = None,
    ) -> LinePrice:
        """Return the price one product's line starts at.

        ``batch_id`` is the batch the line sells from, where it names one: its
        trade rate for this customer's class is offered to the ranking.
        """
        return resolve_unit_price(
            product_price=self._product_price(product_id),
            level_rate=self._levels.get(product_id),
            list_rate=self._lists.price_for(product_id, quantity),
            batch_rate=self._batch_rate(product_id, batch_id),
        )

    def _batch_rate(self, product_id: UUID, batch_id: UUID | None) -> LinePrice | None:
        """Return the batch's PTR or PTS for this customer, if it applies."""
        if batch_id is None or self._trade_class not in ("RETAILER", "STOCKIST"):
            return None
        if self._batch_rates_on is None:
            self._batch_rates_on = feature_enabled(
                self._session, self._firm_id, "BATCH_PTR_PTS"
            )
        if not self._batch_rates_on:
            return None
        batch = self._session.get(BatchRecord, batch_id)
        if (
            batch is None
            or batch.is_deleted
            or batch.firm_id != self._firm_id
            or batch.product_id != product_id
        ):
            return None
        return batch_trade_rate(
            trade_class=self._trade_class,
            ptr=None if batch.ptr is None else Decimal(str(batch.ptr)),
            pts=None if batch.pts is None else Decimal(str(batch.pts)),
        )

    def _product_price(self, product_id: UUID) -> Decimal | None:
        """Return the product's selling price in force on the date, read once.

        A dated revision (MST-2) in force on the document's date wins over
        the product's own price.
        """
        if product_id not in self._products:
            from app.products.services.price_revisions import price_in_force

            revised = price_in_force(
                self._session, product_id, "selling_price", on=self._on
            )
            if revised is not None:
                self._products[product_id] = revised
                return revised
            value = self._session.scalar(
                select(Product.selling_price).where(
                    Product.id == product_id, Product.firm_id == self._firm_id
                )
            )
            self._products[product_id] = None if value is None else Decimal(str(value))
        return self._products[product_id]


__all__ = ["UnitPriceResolver", "customer_price_level"]
