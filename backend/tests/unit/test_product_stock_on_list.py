"""The product list carries stock, and counts and filters low stock and no price.

The phase 2 Products screen (docs/UI_PHASE_2_DESIGN.md, wireframe view 6)
shows a Stock column with low stock in red and two counters that filter:
**Low stock** and **No price**. Low stock is the inventory summary's own test
-- at or below the reorder level, else the minimum level, else zero -- so the
Products and Stock screens cannot disagree about which products are short.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Warehouse
from app.core.database.base import Base
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
from app.products.api.router import _responses
from app.products.models import Product
from app.products.schemas import ProductListFilters
from app.products.services import ProductService


class _Shop:
    """A firm with a warehouse and products held at chosen quantities."""

    def __init__(self) -> None:
        """Build the firm and its one warehouse."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session: Session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.firm = Firm(
            name="Stock Firm",
            code="STOCK",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.flush()
        self.warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=uuid4(),
            code="MAIN",
            name="Main",
            display_name="Main",
        )
        self.session.add(self.warehouse)
        self.session.commit()
        self.service = ProductService(self.session)

    def product(
        self,
        code: str,
        *,
        price: str | None = "10",
        on_hand: str | None = None,
        reorder: str | None = None,
    ) -> Product:
        """Add a product, and a stock row when ``on_hand`` is given."""
        row = Product(
            firm_id=self.firm.id,
            code=code,
            name=code,
            product_type="STOCK_ITEM",
            status="ACTIVE",
            selling_price=None if price is None else Decimal(price),
        )
        self.session.add(row)
        self.session.flush()
        if on_hand is not None:
            self.session.add(
                InventoryRecord(
                    firm_id=self.firm.id,
                    branch_id=self.warehouse.branch_id,
                    warehouse_id=self.warehouse.id,
                    storage_locator="MAIN",
                    product_id=row.id,
                    current_quantity=Decimal(on_hand),
                    available_quantity=Decimal(on_hand),
                    reorder_level=None if reorder is None else Decimal(reorder),
                )
            )
        self.session.commit()
        return row

    def codes(self, **filters: bool) -> set[str]:
        """List the codes the product list returns under ``filters``."""
        rows, _ = self.service.list_products(
            firm_scope=self.firm.id,
            filters=ProductListFilters(**filters),
            page=1,
            page_size=50,
            search=None,
            sort_by="code",
            descending=False,
        )
        return {row.code for row in rows}


def _shop() -> _Shop:
    """Four products: plenty, short, never stocked and unpriced."""
    shop = _Shop()
    shop.product("PLENTY", on_hand="240", reorder="10")
    shop.product("SHORT", on_hand="6", reorder="10")
    shop.product("NEVER")
    shop.product("UNPRICED", price=None, on_hand="90")
    return shop


def test_a_page_of_products_carries_its_stock() -> None:
    """On hand and the low flag ride on each row; never stocked is not zero."""
    shop = _shop()
    rows, _ = shop.service.list_products(
        firm_scope=shop.firm.id,
        filters=ProductListFilters(),
        page=1,
        page_size=50,
        search=None,
        sort_by="code",
        descending=False,
    )
    listed = {
        row.code: row for row in _responses(rows, can_view_cost=True, db=shop.session)
    }

    assert listed["PLENTY"].stock_on_hand == Decimal("240")
    assert listed["PLENTY"].low_stock is False
    assert listed["SHORT"].stock_on_hand == Decimal("6")
    assert listed["SHORT"].low_stock is True
    assert listed["NEVER"].stock_on_hand is None
    assert listed["NEVER"].low_stock is False


def test_low_stock_and_no_price_are_counted_and_filter_the_list() -> None:
    """The counters and the filters they open agree."""
    shop = _shop()
    summary = shop.service.summary(
        firm_scope=shop.firm.id, filters=ProductListFilters()
    )

    assert summary.low_stock == 1
    assert summary.no_price == 1
    assert shop.codes(low_stock=True) == {"SHORT"}
    assert shop.codes(no_price=True) == {"UNPRICED"}
    assert shop.codes() == {"PLENTY", "SHORT", "NEVER", "UNPRICED"}


def test_a_zero_price_is_no_price() -> None:
    """A selling price of zero cannot be sold at either."""
    shop = _Shop()
    shop.product("FREE", price="0")

    assert shop.codes(no_price=True) == {"FREE"}
