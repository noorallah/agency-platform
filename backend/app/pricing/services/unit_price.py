"""The price a sales line starts at when nobody typed one (SEL-9, A89).

Three arrangements can each name a price, and the most specific wins
(``resolve_unit_price``): a fixed rate on a price list that applies to this
customer on this date and quantity, then the customer's price level (its own,
or its group's), then the product's selling price. A typed price beats all
three, so a document asks only for a line that names none.

Built once per document, like ``PriceListResolver``: the customer, its level,
its territory and the date do not change between lines, so the lists and the
level's rates are read once and every line is matched against them.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.pricing import LinePrice, resolve_unit_price
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
        self._lists = PriceListResolver(
            session,
            firm_id=firm_id,
            customer_id=customer_id,
            territory_id=territory_id,
            on=on,
        )
        customer = session.get(Customer, customer_id) if customer_id else None
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

    def price(self, product_id: UUID, quantity: Decimal | None = None) -> LinePrice:
        """Return the price one product's line starts at."""
        return resolve_unit_price(
            product_price=self._product_price(product_id),
            level_rate=self._levels.get(product_id),
            list_rate=self._lists.price_for(product_id, quantity),
        )

    def _product_price(self, product_id: UUID) -> Decimal | None:
        """Return the product's own selling price, read once."""
        if product_id not in self._products:
            value = self._session.scalar(
                select(Product.selling_price).where(
                    Product.id == product_id, Product.firm_id == self._firm_id
                )
            )
            self._products[product_id] = None if value is None else Decimal(str(value))
        return self._products[product_id]


__all__ = ["UnitPriceResolver", "customer_price_level"]
