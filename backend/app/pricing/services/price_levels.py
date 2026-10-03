"""Keeping a firm's price levels and each product's price per level (SEL-9)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer, CustomerGroup
from app.pricing.models import PriceLevel, ProductPriceLevel
from app.pricing.schemas.price_level import (
    PriceLevelWrite,
    ProductLevelRateResponse,
    ProductLevelRatesWrite,
)
from app.products.models import Product


class PriceLevelService:
    """Create, change and retire price levels, and price products on them."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def list_levels(self, firm_id: UUID) -> list[PriceLevel]:
        """Return the firm's live levels in their order."""
        return list(
            self._session.scalars(
                select(PriceLevel)
                .where(PriceLevel.firm_id == firm_id, PriceLevel.is_deleted.is_(False))
                .order_by(PriceLevel.sort_order.asc(), PriceLevel.code.asc())
            ).all()
        )

    def get(self, level_id: UUID, *, firm_id: UUID) -> PriceLevel:
        """Return one of the firm's levels or refuse it as not found."""
        row = self._session.get(PriceLevel, level_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("Price level not found.")
        return row

    def create(
        self, data: PriceLevelWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PriceLevel:
        """Record one level; the caller commits."""
        self._assert_code_free(firm_id, data.code)
        row = PriceLevel(
            firm_id=firm_id,
            code=data.code,
            name=data.name.strip(),
            sort_order=data.sort_order,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit(row, "price_level.created", actor_id)
        return row

    def update(
        self, level_id: UUID, data: PriceLevelWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PriceLevel:
        """Replace one level's details; the caller commits."""
        row = self.get(level_id, firm_id=firm_id)
        self._assert_code_free(firm_id, data.code, excluding=row.id)
        row.code = data.code
        row.name = data.name.strip()
        row.sort_order = data.sort_order
        row.is_active = data.is_active
        row.updated_by = actor_id
        self._session.flush()
        self._audit(row, "price_level.updated", actor_id)
        return row

    def delete(self, level_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Retire a level nobody buys at; the caller commits.

        A soft delete never reaches the database's RESTRICT, so the refusal
        lives here: a level a customer or group still names would vanish from
        every picker while still pricing their documents.
        """
        row = self.get(level_id, firm_id=firm_id)
        held = (
            self._session.scalar(
                select(func.count(Customer.id)).where(
                    Customer.firm_id == firm_id,
                    Customer.is_deleted.is_(False),
                    Customer.price_level_id == row.id,
                )
            )
            or 0
        )
        held += (
            self._session.scalar(
                select(func.count(CustomerGroup.id)).where(
                    CustomerGroup.firm_id == firm_id,
                    CustomerGroup.is_deleted.is_(False),
                    CustomerGroup.price_level_id == row.id,
                )
            )
            or 0
        )
        if held:
            raise ConflictError(
                f"{row.name} is the price level of {held} customer(s) or group(s). "
                "Move them to another level first."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        self._audit(row, "price_level.deleted", actor_id)

    def product_rates(
        self, product_id: UUID, *, firm_id: UUID
    ) -> list[ProductLevelRateResponse]:
        """Return a product's price at each level that prices it."""
        self._product(product_id, firm_id=firm_id)
        return [
            ProductLevelRateResponse(
                price_level_id=level.id,
                price_level_code=level.code,
                price_level_name=level.name,
                rate=rate.rate,
            )
            for rate, level in self._session.execute(
                select(ProductPriceLevel, PriceLevel)
                .join(PriceLevel, PriceLevel.id == ProductPriceLevel.price_level_id)
                .where(
                    ProductPriceLevel.firm_id == firm_id,
                    ProductPriceLevel.product_id == product_id,
                    ProductPriceLevel.is_deleted.is_(False),
                    PriceLevel.is_deleted.is_(False),
                )
                .order_by(PriceLevel.sort_order.asc(), PriceLevel.code.asc())
            ).all()
        ]

    def replace_product_rates(
        self,
        product_id: UUID,
        data: ProductLevelRatesWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[ProductLevelRateResponse]:
        """Replace a product's prices per level; the caller commits.

        The whole list is replaced: a level left out no longer prices the
        product, and its customers fall back to the product's own price.
        """
        product = self._product(product_id, firm_id=firm_id)
        wanted = {item.price_level_id: item.rate for item in data.rates}
        if len(wanted) != len(data.rates):
            raise ValidationError("Each level may be priced once per product.")
        for level_id in wanted:
            self.get(level_id, firm_id=firm_id)
        before: dict[str, object] = {
            str(row.price_level_id): str(row.rate)
            for row in self._live_rates(firm_id, product_id)
        }
        for row in self._live_rates(firm_id, product_id):
            if row.price_level_id in wanted:
                row.rate = wanted.pop(row.price_level_id)
                row.updated_by = actor_id
            else:
                row.is_deleted = True
                row.deleted_at = utc_now()
                row.deleted_by = actor_id
        self._session.flush()
        for level_id, rate in wanted.items():
            self._session.add(
                ProductPriceLevel(
                    firm_id=firm_id,
                    product_id=product.id,
                    price_level_id=level_id,
                    rate=rate,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()
        record_audit(
            self._session,
            action="product.level_rates_replaced",
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                str(item.price_level_id): str(item.rate) for item in data.rates
            },
        )
        return self.product_rates(product_id, firm_id=firm_id)

    # ---- helpers -----------------------------------------------------------

    def _live_rates(self, firm_id: UUID, product_id: UUID) -> list[ProductPriceLevel]:
        """Return a product's live rows."""
        return list(
            self._session.scalars(
                select(ProductPriceLevel).where(
                    ProductPriceLevel.firm_id == firm_id,
                    ProductPriceLevel.product_id == product_id,
                    ProductPriceLevel.is_deleted.is_(False),
                )
            ).all()
        )

    def _product(self, product_id: UUID, *, firm_id: UUID) -> Product:
        """Return the firm's product or refuse it as not found."""
        product = self._session.get(Product, product_id)
        if product is None or product.firm_id != firm_id or product.is_deleted:
            raise ResourceNotFoundError("Product not found.")
        return product

    def _assert_code_free(
        self, firm_id: UUID, code: str, excluding: UUID | None = None
    ) -> None:
        """Refuse a code another live level already uses."""
        statement = select(PriceLevel.id).where(
            PriceLevel.firm_id == firm_id,
            PriceLevel.code == code,
            PriceLevel.is_deleted.is_(False),
        )
        if excluding is not None:
            statement = statement.where(PriceLevel.id != excluding)
        taken = self._session.scalar(statement)
        if taken is not None:
            raise ConflictError(f"A price level coded {code} already exists.")

    def _audit(self, row: PriceLevel, action: str, actor_id: UUID) -> None:
        """Record one change to a level."""
        record_audit(
            self._session,
            action=action,
            entity_type="price_level",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={"code": row.code, "name": row.name, "active": row.is_active},
        )


__all__ = ["PriceLevelService"]
