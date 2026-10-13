"""Plan an order for a company from what sold (backlog 130, row M12).

Every product of the company's brands is listed, short or not, with one sum a
person can do by hand: sold over the window, divided by its days, times the
days to cover, less the stock in hand and what open orders still bring,
rounded up to a whole unit and never below zero.
"""

# ruff: noqa: D103

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.inventory.services import InventoryService
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.services.order_plan import (
    OrderPlanPick,
    OrderPlanQuery,
    OrderPlanRow,
    OrderPlanService,
)
from app.vendors.models import Vendor
from app.vendors.models.supplier_product import SupplierProduct
from tests.unit.test_reorder_suggestions import _Shop

pytestmark = pytest.mark.typed_document_numbers


class _Agency(_Shop):
    """A shop holding one company's agency: two brands and their products."""

    def __init__(self) -> None:
        """Add the company, bought from the shop's supplier, and two brands."""
        super().__init__()
        self.today = firm_today(self.session, self.firm.id)
        self.company = Principal(
            firm_id=self.firm.id, code="HUL", name="Hindustan", vendor_id=self.vendor.id
        )
        self.session.add(self.company)
        self.session.flush()
        self.soap = Brand(
            firm_id=self.firm.id, name="Lux", principal_id=self.company.id
        )
        self.wash = Brand(
            firm_id=self.firm.id, name="Surf", principal_id=self.company.id
        )
        self.other_brand = Brand(firm_id=self.firm.id, name="Tide")
        self.session.add_all([self.soap, self.wash, self.other_brand])
        self.session.commit()
        self._serial = 10

    def item(self, code: str, brand: Brand | None, **values: object) -> Product:
        """Add an active stocked product under ``brand``."""
        fields: dict[str, object] = {
            "product_type": "STOCK_ITEM",
            "status": "ACTIVE",
            "purchase_price": Decimal("40"),
            **values,
        }
        row = Product(
            firm_id=self.firm.id,
            code=code,
            name=f"Product {code}",
            brand_id=None if brand is None else brand.id,
            **fields,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def stockist(self) -> Vendor:
        """Add a second active supplier."""
        row = Vendor(
            firm_id=self.firm.id,
            code="STK",
            name="Stockist",
            display_name="Stockist",
            status="ACTIVE",
        )
        self.session.add(row)
        self.session.commit()
        return row

    def trade(
        self, product: Product, *, received: str, sold: str, days_ago: int = 10
    ) -> None:
        """Receive ``received`` long ago and dispatch ``sold`` ``days_ago``."""
        inventory = InventoryService(self.session)
        actor = uuid4()
        self._serial += 1
        inventory.record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=actor,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=product.id,
            reference_number=f"GRN-{self._serial}",
            transaction_date=self.today - timedelta(days=200),
            total_quantity=Decimal(received),
            unit_cost=Decimal("10"),
        )
        if Decimal(sold) > 0:
            inventory.record_delivery_note_dispatch(
                firm_scope=self.firm.id,
                actor_id=actor,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                storage_node_id=None,
                product_id=product.id,
                reference_number=f"DN-{self._serial}",
                transaction_date=self.today - timedelta(days=days_ago),
                dispatch_quantity=Decimal(sold),
            )
        self.session.commit()

    def plan(self, **values: object) -> dict[str, OrderPlanRow]:
        """Return the company's plan for the warehouse, by product code."""
        query = OrderPlanQuery(
            warehouse_id=self.warehouse.id,
            **{"company_id": self.company.id, **values},  # type: ignore[arg-type]
        )
        rows = OrderPlanService(self.session).plan(self.firm.id, query)
        return {row.product_code: row for row in rows}


def test_three_items_match_a_hand_calculation() -> None:
    """The row's own trial: 30 days of sales, stock for 30 days."""
    shop = _Agency()
    # Sold 100, 2 left, nothing coming: the owner's own case, 98.
    first = shop.item("A-1", shop.soap)
    shop.trade(first, received="102", sold="100")
    # Sold 45, 20 left: 45 - 20 = 25.
    second = shop.item("A-2", shop.wash)
    shop.trade(second, received="65", sold="45")
    # Sold 10, 50 left: more than enough, so nothing.
    third = shop.item("A-3", shop.wash)
    shop.trade(third, received="60", sold="10")

    rows = shop.plan(sales_days=30, cover_days=30)

    assert set(rows) == {"A-1", "A-2", "A-3"}
    assert rows["A-1"].sold_quantity == Decimal("100.0000")
    assert rows["A-1"].available_quantity == Decimal("2.0000")
    assert rows["A-1"].required_quantity == Decimal("100.0000")
    assert rows["A-1"].suggested_quantity == Decimal("98.0000")
    assert rows["A-2"].suggested_quantity == Decimal("25.0000")
    assert rows["A-3"].suggested_quantity == Decimal("0.0000")
    assert rows["A-1"].brand_name == "Lux"


def test_a_longer_window_is_averaged_and_rounded_up() -> None:
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="100", sold="100")

    row = shop.plan(sales_days=90, cover_days=30)["A-1"]

    # 100 / 90 * 30 = 33.33, nothing in hand: 34 whole units.
    assert row.average_daily_sales == Decimal("1.1111")
    assert row.required_quantity == Decimal("33.3333")
    assert row.suggested_quantity == Decimal("34.0000")


def test_a_sum_that_comes_out_whole_is_not_rounded_up_past_it() -> None:
    """100 / 60 * 30 is 50, not the 50.000...01 that dividing first gives."""
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="102", sold="100")

    row = shop.plan(sales_days=60, cover_days=30)["A-1"]

    assert row.required_quantity == Decimal("50.0000")
    assert row.suggested_quantity == Decimal("48.0000")


def test_a_plan_reads_six_months_unless_told_otherwise() -> None:
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="90", sold="90")

    row = shop.plan()["A-1"]

    # Six months of sales (backlog 142), stock for the firm's own 30 days:
    # 90 / 180 * 30 = 15.
    assert (row.sales_days, row.cover_days) == (180, 30)
    assert row.suggested_quantity == Decimal("15.0000")


def test_a_sale_before_the_window_does_not_count() -> None:
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="50", sold="50", days_ago=40)

    row = shop.plan(sales_days=30, cover_days=30)["A-1"]

    assert row.sold_quantity == Decimal("0.0000")
    assert row.suggested_quantity == Decimal("0.0000")


def test_what_is_on_an_open_order_is_taken_off() -> None:
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="102", sold="100")
    service = OrderPlanService(shop.session)
    query = OrderPlanQuery(
        warehouse_id=shop.warehouse.id,
        company_id=shop.company.id,
        sales_days=30,
        cover_days=30,
    )

    [order] = service.raise_plan_drafts(
        shop.firm.id,
        query,
        [OrderPlanPick(product_id=product.id, quantity=Decimal("60"))],
        actor_id=uuid4(),
    )

    assert order.status == "DRAFT"
    assert order.vendor_id == shop.vendor.id
    [row] = service.plan(shop.firm.id, query)
    assert row.on_order_quantity == Decimal("60.0000")
    # 100 needed, 2 in hand, 60 coming.
    assert row.suggested_quantity == Decimal("38.0000")


def test_only_the_companys_products_are_planned() -> None:
    shop = _Agency()
    shop.item("A-1", shop.soap)
    shop.item("B-1", shop.other_brand)
    shop.item("C-1", None)
    shop.item("A-9", shop.soap, status="INACTIVE")
    shop.item("A-8", shop.soap).product_type = "SERVICE"
    shop.session.commit()

    assert set(shop.plan()) == {"A-1"}
    assert set(shop.plan(brand_ids=(shop.wash.id,))) == set()
    everything = shop.plan(company_id=None)
    assert {"A-1", "B-1", "C-1", "SKU-001"} <= set(everything)
    assert "A-9" not in everything and "A-8" not in everything


def test_a_supplier_alone_plans_the_brands_it_may_sell() -> None:
    shop = _Agency()
    shop.item("A-1", shop.soap)
    shop.item("B-1", shop.other_brand)

    # The company is bought from the shop's supplier, so its brands count.
    rows = shop.plan(company_id=None, vendor_id=shop.vendor.id)

    assert set(rows) == {"A-1"}
    assert rows["A-1"].supplier_id == shop.vendor.id


def test_the_supplier_is_the_preferred_one_then_the_companys() -> None:
    shop = _Agency()
    stockist = shop.stockist()
    shop.item("A-1", shop.soap, preferred_vendor_id=stockist.id)
    shop.item("A-2", shop.soap)
    shop.item("B-1", shop.other_brand)

    rows = shop.plan(company_id=None)

    assert rows["A-1"].supplier_id == stockist.id
    assert rows["A-2"].supplier_id == shop.vendor.id, "its company's supplier"
    assert rows["B-1"].supplier_id is None, "nobody is known to sell it"
    assert rows["A-2"].unit_price == Decimal("40")

    named = shop.plan(company_id=None, vendor_id=stockist.id)
    assert {row.supplier_id for row in named.values()} == {stockist.id}


def test_the_suppliers_pack_rounds_the_quantity_up() -> None:
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="102", sold="100")
    shop.session.add(
        SupplierProduct(
            firm_id=shop.firm.id,
            vendor_id=shop.vendor.id,
            product_id=product.id,
            order_multiple=Decimal("12"),
            effective_from=shop.today - timedelta(days=30),
        )
    )
    shop.session.commit()

    row = shop.plan(sales_days=30, cover_days=30)["A-1"]

    # 98 needed, sold by the dozen: 108.
    assert row.suggested_quantity == Decimal("108.0000")
    # The terms travel with the row, so a raised figure can keep to them.
    assert row.order_multiple == Decimal("12")
    assert row.minimum_order_quantity is None


def test_a_row_with_no_catalogue_entry_carries_no_terms() -> None:
    shop = _Agency()
    product = shop.item("A-1", shop.soap)
    shop.trade(product, received="102", sold="100")

    row = shop.plan(sales_days=30, cover_days=30)["A-1"]

    assert row.order_multiple is None
    assert row.minimum_order_quantity is None


def test_drafts_are_one_per_supplier_and_take_the_typed_quantity() -> None:
    shop = _Agency()
    stockist = shop.stockist()
    first = shop.item("A-1", shop.soap)
    second = shop.item("A-2", shop.wash)
    third = shop.item("A-3", shop.wash, preferred_vendor_id=stockist.id)
    for product in (first, second, third):
        shop.trade(product, received="100", sold="90")
    query = OrderPlanQuery(
        warehouse_id=shop.warehouse.id,
        company_id=shop.company.id,
        sales_days=30,
        cover_days=30,
    )

    orders = OrderPlanService(shop.session).raise_plan_drafts(
        shop.firm.id,
        query,
        [
            OrderPlanPick(product_id=first.id),
            OrderPlanPick(product_id=second.id, quantity=Decimal("7")),
            OrderPlanPick(product_id=third.id),
        ],
        actor_id=uuid4(),
    )

    by_vendor = {order.vendor_id: order for order in orders}
    assert set(by_vendor) == {shop.vendor.id, stockist.id}
    lines = {
        line.product_id: line.ordered_quantity
        for line in shop.session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == by_vendor[shop.vendor.id].id
            )
        )
    }
    # 90 needed, 10 in hand: 80; the second as typed.
    assert lines == {first.id: Decimal("80"), second.id: Decimal("7")}
    assert "order plan" in (by_vendor[stockist.id].remarks or "")


def test_a_refusal_raises_no_order_at_all() -> None:
    shop = _Agency()
    wanted = shop.item("A-1", shop.soap)
    shop.trade(wanted, received="100", sold="90")
    covered = shop.item("A-2", shop.soap)
    shop.trade(covered, received="100", sold="5")
    stranger = shop.item("B-1", shop.other_brand)
    query = OrderPlanQuery(
        warehouse_id=shop.warehouse.id, company_id=shop.company.id, sales_days=30
    )
    before = len(shop.session.scalars(select(PurchaseOrder)).all())
    service = OrderPlanService(shop.session)

    with pytest.raises(ValidationError) as refusal:
        service.raise_plan_drafts(
            shop.firm.id,
            query,
            [
                OrderPlanPick(product_id=wanted.id),
                OrderPlanPick(product_id=covered.id),
                OrderPlanPick(product_id=stranger.id),
            ],
            actor_id=uuid4(),
        )

    message = str(refusal.value)
    assert "A-2: nothing to order" in message
    assert "not a product of this plan" in message
    shop.session.rollback()
    assert len(shop.session.scalars(select(PurchaseOrder)).all()) == before


def test_a_row_with_no_supplier_is_refused_until_one_is_chosen() -> None:
    shop = _Agency()
    product = shop.item("B-1", shop.other_brand)
    shop.trade(product, received="100", sold="90")
    query = OrderPlanQuery(warehouse_id=shop.warehouse.id, sales_days=30)
    service = OrderPlanService(shop.session)

    with pytest.raises(ValidationError, match="no supplier is known"):
        service.raise_plan_drafts(
            shop.firm.id,
            query,
            [OrderPlanPick(product_id=product.id)],
            actor_id=uuid4(),
        )
    shop.session.rollback()

    [order] = service.raise_plan_drafts(
        shop.firm.id,
        query,
        [OrderPlanPick(product_id=product.id, supplier_id=shop.vendor.id)],
        actor_id=uuid4(),
    )
    assert order.vendor_id == shop.vendor.id


def test_another_firms_warehouse_company_or_supplier_is_not_found() -> None:
    shop = _Agency()
    service = OrderPlanService(shop.session)

    with pytest.raises(ResourceNotFoundError):
        service.plan(shop.firm.id, OrderPlanQuery(warehouse_id=uuid4()))
    with pytest.raises(ResourceNotFoundError):
        shop.plan(company_id=uuid4())
    with pytest.raises(ResourceNotFoundError):
        shop.plan(vendor_id=uuid4())
    with pytest.raises(ValidationError):
        shop.plan(sales_days=3)
