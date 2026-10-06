"""Maintaining a firm's price lists.

Nothing subtle happens here — it is create, read, replace and soft-delete over
two tables. The one decision worth naming is that a list's **items are
replaced** on update rather than merged, and the update is otherwise partial:
absent means leave alone for the scalars, and `items` is only touched when the
caller actually sends it.

That combination is deliberate. A price list is edited as a whole in the one
screen that shows it, so replacing the rows is what a user means by saving;
but reconciling a collection the caller never mentioned is the shape that
destroyed a vendor's addresses, so silence has to leave the rows alone.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import PaginationParams
from app.customers.models import Customer
from app.pricing.models import PriceList, PriceListItem
from app.pricing.schemas import (
    PriceListFilters,
    PriceListItemResponse,
    PriceListResponse,
    PriceListWrite,
)
from app.products.models import Product
from app.sales.models.territory import SalesTerritoryNode

#: The fields of a list that name who it is for.
_PARTIES = ("customer_id", "territory_id", "vendor_id")


class PriceListService:
    """Create, read and revise the arrangements a firm has agreed."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the lists live on."""
        self._session = session

    # ---- reading -------------------------------------------------------
    def list_price_lists(
        self,
        *,
        firm_scope: UUID,
        pagination: PaginationParams,
        search: str = "",
        filters: PriceListFilters | None = None,
    ) -> tuple[list[PriceListResponse], int]:
        """Return one page of price lists, newest window first."""
        criteria = filters or PriceListFilters()
        statement = self._scoped(firm_scope, criteria)
        if search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(
                PriceList.code.ilike(term) | PriceList.name.ilike(term)
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = list(
            self._session.scalars(
                statement.order_by(
                    PriceList.effective_from.desc(), PriceList.code.asc()
                )
                .offset(pagination.offset)
                .limit(pagination.page_size)
            ).all()
        )
        return [self.response(row) for row in rows], int(total or 0)

    def get(self, price_list_id: UUID, *, firm_scope: UUID) -> PriceList:
        """Return one price list inside the firm's scope."""
        row = self._session.scalar(
            select(PriceList).where(
                PriceList.id == price_list_id,
                PriceList.firm_id == firm_scope,
                PriceList.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Price list not found.")
        return row

    def _scoped(
        self, firm_scope: UUID, filters: PriceListFilters
    ) -> Select[tuple[PriceList]]:
        statement = select(PriceList).where(PriceList.firm_id == firm_scope)
        if not filters.include_deleted:
            statement = statement.where(PriceList.is_deleted.is_(False))
        if filters.customer_id is not None:
            statement = statement.where(PriceList.customer_id == filters.customer_id)
        if filters.territory_id is not None:
            statement = statement.where(PriceList.territory_id == filters.territory_id)
        if filters.vendor_id is not None:
            statement = statement.where(PriceList.vendor_id == filters.vendor_id)
        if filters.status:
            statement = statement.where(PriceList.status == filters.status)
        return statement

    # ---- writing -------------------------------------------------------
    def create(
        self, data: PriceListWrite, *, firm_scope: UUID, actor_id: UUID
    ) -> PriceList:
        """Create one price list and its rates."""
        self._assert_code_free(firm_scope, data.code)
        self._check_parties(
            data.model_dump(include=set(_PARTIES)), firm_scope=firm_scope
        )
        self._check_items(data, firm_scope=firm_scope)
        row = PriceList(
            firm_id=firm_scope,
            code=data.code,
            name=data.name,
            description=data.description,
            customer_id=data.customer_id,
            territory_id=data.territory_id,
            vendor_id=data.vendor_id,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            status=data.status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_items(row, data, actor_id=actor_id, firm_scope=firm_scope)
        record_audit(
            self._session,
            action="price_list.created",
            entity_type="price_list",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"code": row.code, "name": row.name},
        )
        self._session.commit()
        return row

    def update(
        self,
        price_list_id: UUID,
        data: PriceListWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PriceList:
        """Revise one price list.

        Partial on the scalars -- absent means leave alone, per the standing
        rule in CLAUDE.md -- and the rates are replaced only when the caller
        actually sends them.
        """
        row = self.get(price_list_id, firm_scope=firm_scope)
        before: dict[str, object] = {
            "code": row.code,
            "name": row.name,
            "status": row.status,
        }
        values = data.model_dump(exclude={"items"}, exclude_unset=True)
        if "code" in values and values["code"] != row.code:
            self._assert_code_free(firm_scope, str(values["code"]))
        # Only a party that is changing: a list already naming a customer
        # retired since can still be saved around it.
        self._check_parties(
            {
                field: value
                for field, value in values.items()
                if field in _PARTIES and value != getattr(row, field)
            },
            firm_scope=firm_scope,
        )
        if "items" in data.model_fields_set:
            self._check_items(data, firm_scope=firm_scope)
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_by = actor_id
        if "items" in data.model_fields_set:
            self._replace_items(row, data, actor_id=actor_id, firm_scope=firm_scope)
        record_audit(
            self._session,
            action="price_list.updated",
            entity_type="price_list",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"code": row.code, "name": row.name, "status": row.status},
        )
        self._session.commit()
        return row

    def delete(self, price_list_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> None:
        """Soft-delete one price list.

        Documents already priced under it keep what they were charged: the
        rate is stored on the line, so withdrawing the arrangement changes
        nothing that has already been agreed.
        """
        row = self.get(price_list_id, firm_scope=firm_scope)
        row.is_deleted = True
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="price_list.deleted",
            entity_type="price_list",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": row.code},
        )
        self._session.commit()

    def _check_parties(self, values: dict[str, object], *, firm_scope: UUID) -> None:
        """Refuse a customer, territory or supplier that is not the firm's.

        Asked before the write and by name. In a firm's own store another
        firm's id fails the foreign key, which answered only that the request
        conflicted with existing data; in the shared store it was accepted,
        and the list then named a customer its firm cannot see (D-PRC-12).
        """
        from app.vendors.models import Vendor

        masters: dict[str, tuple[type[Customer | SalesTerritoryNode | Vendor], str]]
        masters = {
            "customer_id": (Customer, "customer"),
            "territory_id": (SalesTerritoryNode, "territory"),
            "vendor_id": (Vendor, "supplier"),
        }
        for field, (model, label) in masters.items():
            row_id = values.get(field)
            if row_id is None:
                continue
            found = self._session.scalar(
                select(model.id).where(
                    model.id == row_id,
                    model.firm_id == firm_scope,
                    model.is_deleted.is_(False),
                )
            )
            if found is None:
                raise ValidationError(
                    f"The {label} this price list names was not found in this firm."
                )

    def _check_items(self, data: PriceListWrite, *, firm_scope: UUID) -> None:
        """Refuse a row naming a product not the firm's, or a break twice.

        Both used to reach the database and come back as its error: a product
        from elsewhere failed the foreign key, and two rows for one product
        at one quantity failed `UQ_price_list_items_list_product_quantity`
        (D-PRC-12). The rows are counted from one, as the screen lists them.
        """
        if not data.items:
            return
        codes: dict[UUID, str] = {
            product_id: code
            for product_id, code in self._session.execute(
                select(Product.id, Product.code).where(
                    Product.id.in_({item.product_id for item in data.items}),
                    Product.firm_id == firm_scope,
                    Product.is_deleted.is_(False),
                )
            )
        }
        seen: dict[tuple[UUID, Decimal], int] = {}
        for number, item in enumerate(data.items, start=1):
            if item.product_id not in codes:
                raise ValidationError(
                    f"Row {number}: the product was not found in this firm."
                )
            key = (item.product_id, item.min_quantity)
            if key in seen:
                raise ValidationError(
                    f"Row {number}: {codes[item.product_id]} already has a rate "
                    f"from a quantity of {item.min_quantity.normalize():f} on row "
                    f"{seen[key]}. A product takes one rate at each quantity."
                )
            seen[key] = number

    def _replace_items(
        self,
        row: PriceList,
        data: PriceListWrite,
        *,
        actor_id: UUID,
        firm_scope: UUID,
    ) -> None:
        """Replace the list's rates with what was sent."""
        self._session.query(PriceListItem).filter(
            PriceListItem.price_list_id == row.id
        ).delete(synchronize_session=False)
        for item in data.items:
            self._session.add(
                PriceListItem(
                    price_list_id=row.id,
                    firm_id=firm_scope,
                    product_id=item.product_id,
                    min_quantity=item.min_quantity,
                    discount_percent=item.discount_percent,
                    rate=item.rate,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def _assert_code_free(self, firm_scope: UUID, code: str) -> None:
        """Refuse a code another live list in this firm already uses."""
        clash = self._session.scalar(
            select(PriceList.id).where(
                PriceList.firm_id == firm_scope,
                PriceList.code == code,
                PriceList.is_deleted.is_(False),
            )
        )
        if clash is not None:
            raise ConflictError(f"A price list with the code {code} already exists.")

    # ---- responses -----------------------------------------------------
    def response(self, row: PriceList) -> PriceListResponse:
        """Build the response, naming the parties rather than listing UUIDs."""
        items = list(
            self._session.scalars(
                select(PriceListItem)
                .where(
                    PriceListItem.price_list_id == row.id,
                    PriceListItem.is_deleted.is_(False),
                )
                .order_by(PriceListItem.created_at.asc())
            ).all()
        )
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_({item.product_id for item in items})
                )
            ).all()
        }
        customer = (
            self._session.get(Customer, row.customer_id)
            if row.customer_id is not None
            else None
        )
        territory = (
            self._session.get(SalesTerritoryNode, row.territory_id)
            if row.territory_id is not None
            else None
        )
        from app.vendors.models import Vendor

        vendor = (
            self._session.get(Vendor, row.vendor_id)
            if row.vendor_id is not None
            else None
        )
        return PriceListResponse(
            id=row.id,
            version=row.version,
            firm_id=row.firm_id,
            code=row.code,
            name=row.name,
            description=row.description,
            customer_id=row.customer_id,
            customer_name=(
                None if customer is None else (customer.display_name or customer.name)
            ),
            territory_id=row.territory_id,
            territory_name=None if territory is None else territory.name,
            vendor_id=row.vendor_id,
            vendor_name=None if vendor is None else vendor.name,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            status=row.status,
            items=[
                PriceListItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    min_quantity=item.min_quantity,
                    product_code=(
                        products[item.product_id].code
                        if item.product_id in products
                        else None
                    ),
                    product_name=(
                        products[item.product_id].name
                        if item.product_id in products
                        else None
                    ),
                    discount_percent=item.discount_percent,
                    rate=item.rate,
                )
                for item in items
            ],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
