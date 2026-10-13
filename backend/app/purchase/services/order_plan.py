"""Plan an order for a company from what sold (backlog 130, row M12).

Below reorder level lists what is already short. A month-end order is planned
the other way round: the buyer names a company, and every product of its
brands is listed with what to order, short or not.

**One sum per product, which a person can do by hand.** Over the last
``sales_days`` days up to today the warehouse sold *S* (dispatches less
returns, each net of its reversals, in stock units). The plan covers
``cover_days`` days. A plan that names no ``sales_days`` reads the last six
months (``PLAN_SALES_DAYS``, backlog 142): a month-end order is judged on a
longer run of sales than the reorder alert is.

    needed    = S / sales_days * cover_days
    to order  = needed - stock in hand - already on open orders

rounded **up** to a whole unit and never below zero. Where the supplier's
catalogue quotes a minimum order or a pack multiple, a quantity above zero is
rounded up to it (BUY-5). *Stock in hand* is what is available in that
warehouse, so reserved stock is not counted twice; *on open orders* counts
drafts, so planning twice does not order twice (decision A6).

**Which products.** A company (principal) means the products of its brands;
brands may be named instead, or as well. A supplier named on its own means the
brands that supplier may sell (backlog 129); a supplier nothing limits, and no
filter at all, mean every product. Only active products held as stock.

**From whom.** The supplier named on the plan, for every row. Otherwise the
product's preferred supplier, else the one last billed for it, else the
supplier its company is bought from. A row with none is listed and cannot be
ordered until one is chosen.

Raising orders goes through ``ReorderService._stage_orders``: one DRAFT per
supplier, numbered, taxed and audited as a typed order, committed once, and a
row that cannot be ordered refuses the whole batch by name.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.branches.models import Warehouse
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.inventory.models import InventoryRecord
from app.inventory.services.pipeline import incoming
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.products.services.stockless import STOCKLESS_TYPES
from app.purchase.models import PurchaseOrder
from app.purchase.services.reorder import (
    OPEN_ORDER_STATUSES,
    QUANTUM,
    ZERO,
    ReorderService,
)
from app.vendors.models import Vendor
from app.vendors.models.supplier_product import SupplierProduct
from app.vendors.services.order_quantities import rounded_quantity
from app.vendors.services.vendor_brands import VendorBrandService

#: The days of sales a plan reads when none are named: six months.
PLAN_SALES_DAYS = 180

#: Products asked about at a time: a statement holds 65,535 parameters, and a
#: plan with no filter names every product the firm has.
_CHUNK = 5000


@dataclass(frozen=True)
class OrderPlanQuery:
    """What the buyer chose: where, whose products, and over how many days."""

    warehouse_id: UUID
    company_id: UUID | None = None
    brand_ids: tuple[UUID, ...] = ()
    vendor_id: UUID | None = None
    #: ``None`` reads the last six months (``PLAN_SALES_DAYS``).
    sales_days: int | None = None
    #: ``None`` takes the firm's reorder planning figure (30 unset).
    cover_days: int | None = None


@dataclass(frozen=True)
class OrderPlanRow:
    """One product of the plan, with the sum that gives its quantity."""

    branch_id: UUID
    warehouse_id: UUID
    warehouse_code: str
    product_id: UUID
    product_code: str
    product_name: str
    brand_id: UUID | None
    brand_name: str | None
    sales_days: int
    cover_days: int
    sold_quantity: Decimal
    average_daily_sales: Decimal
    required_quantity: Decimal
    available_quantity: Decimal
    on_order_quantity: Decimal
    suggested_quantity: Decimal
    supplier_id: UUID | None
    supplier_name: str | None
    unit_price: Decimal
    #: The supplier's terms the suggestion was rounded up to, so a screen
    #: that raises the suggestion can round the same way (backlog 142).
    minimum_order_quantity: Decimal | None = None
    order_multiple: Decimal | None = None


@dataclass(frozen=True)
class OrderPlanPick:
    """One row the buyer ticked, optionally with their own quantity."""

    product_id: UUID
    quantity: Decimal | None = None
    supplier_id: UUID | None = None


class OrderPlanService(ReorderService):
    """Say what to order for a company's products, and raise the drafts."""

    def plan(self, firm_id: UUID, query: OrderPlanQuery) -> list[OrderPlanRow]:
        """Return every chosen product with what to order, by product code.

        Raises:
            ResourceNotFoundError: When the warehouse, company or supplier is
                not this firm's.
            ValidationError: When a number of days is out of range.

        """
        planning = self.planning(firm_id)
        sales_days = query.sales_days or PLAN_SALES_DAYS
        cover_days = query.cover_days or planning.cover_days
        if not 7 <= sales_days <= 365:
            raise ValidationError("Read sales over 7 to 365 days.")
        if not 1 <= cover_days <= 365:
            raise ValidationError("Order enough for 1 to 365 days.")
        warehouse = self._warehouse(firm_id, query.warehouse_id)
        named = self._named_supplier(firm_id, query.vendor_id)
        products = self._products(firm_id, query)
        if not products:
            return []
        sold = self._sales_by_location(
            firm_id, replace(planning, sales_window_days=sales_days), warehouse.id
        )
        held = self._held(firm_id, warehouse.id)
        coming = incoming(
            self._session,
            firm_id=firm_id,
            product_ids=None,
            open_statuses=OPEN_ORDER_STATUSES,
        )
        brands = self._brands(firm_id, {row.brand_id for row in products.values()})
        suppliers, terms = self._sources(firm_id, products, brands, named)
        names = self._supplier_names({v for v, _ in suppliers.values()})
        rows: list[OrderPlanRow] = []
        for product_id, product in products.items():
            quantity = sold.get((warehouse.id, product_id), ZERO)
            daily = quantity / sales_days
            # Multiplied first and held to four places: 100 / 60 * 30 is
            # 50.000...01 in decimal arithmetic, and rounding that up orders
            # one more than the hand sum does.
            needed = (quantity * cover_days / sales_days).quantize(QUANTUM)
            in_hand = held.get(product_id, ZERO)
            on_order = coming.get((warehouse.id, product_id), ZERO)
            gap = max(needed - in_hand - on_order, ZERO)
            suggested = gap.to_integral_value(rounding=ROUND_CEILING)
            listed = terms.get(product_id)
            if listed is not None and suggested > ZERO:
                suggested = rounded_quantity(
                    suggested,
                    minimum=listed.minimum_order_quantity,
                    multiple=listed.order_multiple,
                )
            supplier, rate = suppliers.get(product_id, (None, None))
            brand = brands.get(product.brand_id) if product.brand_id else None
            rows.append(
                OrderPlanRow(
                    branch_id=warehouse.branch_id,
                    warehouse_id=warehouse.id,
                    warehouse_code=warehouse.code,
                    product_id=product_id,
                    product_code=product.code,
                    product_name=product.name,
                    brand_id=product.brand_id,
                    brand_name=None if brand is None else brand.name,
                    sales_days=sales_days,
                    cover_days=cover_days,
                    sold_quantity=quantity.quantize(QUANTUM),
                    average_daily_sales=daily.quantize(QUANTUM),
                    required_quantity=needed,
                    available_quantity=in_hand.quantize(QUANTUM),
                    on_order_quantity=on_order.quantize(QUANTUM),
                    suggested_quantity=suggested.quantize(QUANTUM),
                    supplier_id=supplier,
                    supplier_name=None if supplier is None else names.get(supplier),
                    unit_price=(
                        rate
                        if rate is not None
                        else Decimal(str(product.purchase_price or 0))
                    ),
                    minimum_order_quantity=(
                        None if listed is None else listed.minimum_order_quantity
                    ),
                    order_multiple=None if listed is None else listed.order_multiple,
                )
            )
        rows.sort(key=lambda row: row.product_code)
        return rows

    def raise_plan_drafts(
        self,
        firm_id: UUID,
        query: OrderPlanQuery,
        picks: list[OrderPlanPick],
        *,
        actor_id: UUID,
    ) -> list[PurchaseOrder]:
        """Raise one DRAFT order per supplier for the ticked rows of the plan.

        The plan is worked out again from ``query``, so a quantity left blank
        is today's suggestion and a product outside the plan is refused. Any
        refusal refuses the whole batch by name.
        """
        if not picks:
            raise ValidationError("Choose at least one row to order.")
        rows = {row.product_id: row for row in self.plan(firm_id, query)}
        grouped: dict[tuple[UUID, UUID, UUID], list[tuple[UUID, Decimal, Decimal]]]
        grouped = defaultdict(list)
        problems: list[str] = []
        seen: set[UUID] = set()
        for pick in picks:
            row = rows.get(pick.product_id)
            if row is None:
                problems.append(f"{pick.product_id} is not a product of this plan.")
                continue
            if pick.product_id in seen:
                problems.append(f"{row.product_code} is ticked twice.")
                continue
            seen.add(pick.product_id)
            supplier = pick.supplier_id or row.supplier_id
            quantity = (
                pick.quantity if pick.quantity is not None else row.suggested_quantity
            )
            if supplier is None:
                problems.append(
                    f"{row.product_code}: no supplier is known for it, so choose "
                    "one for the plan."
                )
                continue
            if quantity <= ZERO:
                problems.append(
                    f"{row.product_code}: nothing to order -- stock and open "
                    "orders already cover it."
                )
                continue
            grouped[(supplier, row.branch_id, row.warehouse_id)].append(
                (row.product_id, quantity, row.unit_price)
            )
        if problems:
            raise ValidationError("No order was raised. " + " ".join(problems))
        used = next(iter(rows.values()))
        return self._stage_orders(
            firm_id,
            grouped,
            actor_id=actor_id,
            remarks=(
                f"Raised from the order plan: sales of {used.sales_days} days, "
                f"stock for {used.cover_days} days."
            ),
        )

    def _warehouse(self, firm_id: UUID, warehouse_id: UUID) -> Warehouse:
        """Return the firm's live warehouse, or refuse."""
        row = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Warehouse not found.")
        return row

    def _named_supplier(self, firm_id: UUID, vendor_id: UUID | None) -> Vendor | None:
        """Return the supplier the plan orders from, if one was named."""
        if vendor_id is None:
            return None
        row = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Supplier not found.")
        if row.status != "ACTIVE":
            raise ValidationError(f"{row.name} is not active, so nothing is ordered.")
        return row

    def _products(self, firm_id: UUID, query: OrderPlanQuery) -> dict[UUID, Product]:
        """Return the active stocked products the plan is about, by id."""
        statement = select(Product).where(
            Product.firm_id == firm_id,
            Product.is_deleted.is_(False),
            Product.status == "ACTIVE",
            Product.product_type.not_in(STOCKLESS_TYPES),
        )
        if query.company_id is not None:
            company = self._session.scalar(
                select(Principal.id).where(
                    Principal.id == query.company_id,
                    Principal.firm_id == firm_id,
                    Principal.is_deleted.is_(False),
                )
            )
            if company is None:
                raise ResourceNotFoundError("Company not found.")
            statement = statement.where(
                Product.brand_id.in_(
                    select(Brand.id).where(
                        Brand.firm_id == firm_id,
                        Brand.principal_id == company,
                        Brand.is_deleted.is_(False),
                    )
                )
            )
        if query.brand_ids:
            statement = statement.where(Product.brand_id.in_(query.brand_ids))
        elif query.company_id is None and query.vendor_id is not None:
            # A supplier on its own: the brands it may sell, if it is limited.
            allowed = VendorBrandService(self._session).brands_of(
                query.vendor_id, firm_id=firm_id
            )
            if allowed.source != "NONE":
                statement = statement.where(
                    Product.brand_id.in_([row.brand_id for row in allowed.brands])
                )
        return {row.id: row for row in self._session.scalars(statement)}

    def _held(self, firm_id: UUID, warehouse_id: UUID) -> dict[UUID, Decimal]:
        """Return what is available in the warehouse, per product."""
        statement = (
            select(
                InventoryRecord.product_id,
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
            )
            .where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.warehouse_id == warehouse_id,
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(InventoryRecord.product_id)
        )
        return {
            product_id: Decimal(str(quantity))
            for product_id, quantity in self._session.execute(statement).all()
        }

    def _brands(self, firm_id: UUID, brand_ids: set[UUID | None]) -> dict[UUID, Brand]:
        """Return the brands the plan's products carry, by id."""
        wanted = {brand_id for brand_id in brand_ids if brand_id is not None}
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Brand).where(Brand.firm_id == firm_id, Brand.id.in_(wanted))
            )
        }

    def _sources(
        self,
        firm_id: UUID,
        products: dict[UUID, Product],
        brands: dict[UUID, Brand],
        named: Vendor | None,
    ) -> tuple[dict[UUID, tuple[UUID, Decimal | None]], dict[UUID, SupplierProduct]]:
        """Return, per product, the supplier with a rate, and its catalogue row.

        The supplier named on the plan takes every row, with the last bill's
        rate only where that bill was its own. Otherwise the choice Below
        reorder level makes, and then the supplier the product's company is
        bought from.
        """
        company_supplier = self._company_suppliers(firm_id, brands)
        suppliers: dict[UUID, tuple[UUID, Decimal | None]] = {}
        terms: dict[UUID, SupplierProduct] = {}
        ids = list(products)
        for start in range(0, len(ids), _CHUNK):
            part = {key: products[key] for key in ids[start : start + _CHUNK]}
            if named is not None:
                last = self._last_supplier(firm_id, part)
                chosen: dict[UUID, tuple[UUID, Decimal | None]] = {}
                for product_id in part:
                    billed = last.get(product_id)
                    rate = billed[1] if billed and billed[0] == named.id else None
                    chosen[product_id] = (named.id, rate)
            else:
                chosen = self._suppliers(firm_id, part)
                for product_id, product in part.items():
                    brand = brands.get(product.brand_id) if product.brand_id else None
                    fallback = None if brand is None else company_supplier.get(brand.id)
                    if product_id not in chosen and fallback is not None:
                        chosen[product_id] = (fallback, None)
            suppliers.update(chosen)
            terms.update(self._supplier_terms(firm_id, chosen))
        return suppliers, terms

    def _company_suppliers(
        self, firm_id: UUID, brands: dict[UUID, Brand]
    ) -> dict[UUID, UUID]:
        """Return, per brand, the active supplier its company is bought from."""
        companies = {row.principal_id for row in brands.values() if row.principal_id}
        if not companies:
            return {}
        bought_from: dict[UUID, UUID] = {
            company: vendor
            for company, vendor in self._session.execute(
                select(Principal.id, Principal.vendor_id)
                .join(Vendor, Vendor.id == Principal.vendor_id)
                .where(
                    Principal.firm_id == firm_id,
                    Principal.id.in_(companies),
                    Principal.is_deleted.is_(False),
                    Vendor.is_deleted.is_(False),
                    Vendor.status == "ACTIVE",
                )
            ).all()
        }
        return {
            brand_id: bought_from[row.principal_id]
            for brand_id, row in brands.items()
            if row.principal_id in bought_from
        }

    def _supplier_names(self, supplier_ids: set[UUID]) -> dict[UUID, str]:
        """Return the name of each supplier the plan orders from."""
        if not supplier_ids:
            return {}
        return {
            row_id: name
            for row_id, name in self._session.execute(
                select(Vendor.id, Vendor.name).where(Vendor.id.in_(supplier_ids))
            ).all()
        }
