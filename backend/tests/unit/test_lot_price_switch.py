"""The bill's one switch between a lot's two prices (L3 step 3).

`docs/design/LOT_MARGINS_DESIGN.md`, section 3.5: a firm costing by lot has
two reserved price levels, Retail and Wholesale, that may be renamed but not
deleted or taken out of use; a customer with no level starts on the level of
his kind; the batch tier prices by the class of the level the bill is at; a
line naming no lot is priced at the lot that leaves first; and one line never
mixes two prices. A firm on Average prices exactly as before.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, ValidationError
from app.pricing.api.price_levels_router import list_price_levels, unit_prices
from app.pricing.models import PriceLevel
from app.pricing.schemas.price_level import PriceLevelWrite
from app.pricing.services.price_levels import PriceLevelService
from app.pricing.services.trade_levels import ensure_trade_levels
from app.pricing.services.unit_price import (
    StockPlace,
    UnitPriceResolver,
    customer_price_level,
)
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_order.services.discount_limit import DiscountLimitService
from tests.unit.report_windows import report_scope
from tests.unit.test_lot_selling import _ByLot


class _Priced(_ByLot):
    """The by-lot counter firm with each lot's PTR and PTS, and a retailer.

    EARLY (expiring first) sells at 80.00 to a retailer and 70.00 to a
    wholesaler, LATE at 90.00 and 75.00; the product's own price is 100.00.
    """

    def __init__(self, *, by_lot: bool = True) -> None:
        """Price the two lots and class the customer a retailer."""
        super().__init__(by_lot=by_lot)
        self.drug.selling_price = Decimal("100")
        for name, ptr, pts in (("EARLY", "80", "70"), ("LATE", "90", "75")):
            self.batches[name].ptr = Decimal(ptr)
            self.batches[name].pts = Decimal(pts)
        self.customer.trade_class = "RETAILER"
        self.session.commit()

    def levels(self) -> dict[str, PriceLevel]:
        """Return the firm's live levels by code."""
        return {
            row.code: row
            for row in self.session.scalars(
                select(PriceLevel).where(
                    PriceLevel.firm_id == self.firm.id,
                    PriceLevel.is_deleted.is_(False),
                )
            ).all()
        }

    def reserve(self) -> dict[str, PriceLevel]:
        """Make the two reserved levels and return every level by code."""
        ensure_trade_levels(self.session, self.firm.id, self.actor)
        self.session.commit()
        return self.levels()

    def unpriced(
        self,
        *picks: tuple[str, str],
        level: PriceLevel | None = None,
        price: str | None = None,
    ) -> SalesInvoiceCreate:
        """Describe a counter sale of four with no price typed."""
        return SalesInvoiceCreate(
            customer_id=self.customer.id,
            invoice_date=self.bill(None).invoice_date,
            price_level_id=None if level is None else level.id,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=self.drug.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=None if price is None else Decimal(price),
                    batches=[self.pick(name, quantity) for name, quantity in picks]
                    or None,
                )
            ],
        )

    def priced_at(self, data: SalesInvoiceCreate) -> Decimal:
        """Create the bill and return the price its one line was given."""
        draft = self.bills.create_invoice(
            data, firm_id=self.firm.id, actor_id=self.actor
        )
        return Decimal(
            self.session.scalars(
                select(SalesInvoiceLine.unit_price).where(
                    SalesInvoiceLine.sales_invoice_id == draft.id
                )
            ).one()
        )


def test_a_by_lot_firm_gets_retail_and_wholesale_once() -> None:
    """Two reserved levels, each naming its class; a second call adds none."""
    shop = _Priced()

    levels = shop.reserve()
    assert {code: row.trade_class for code, row in levels.items()} == {
        "RETAIL": "RETAILER",
        "WHOLESALE": "STOCKIST",
    }
    assert not ensure_trade_levels(shop.session, shop.firm.id, shop.actor)
    assert len(shop.levels()) == 2


def test_a_level_already_coded_retail_is_adopted_not_doubled() -> None:
    """The firm's own RETAIL level, even out of use, becomes the reserved one."""
    shop = _Priced()
    own = PriceLevelService(shop.session).create(
        PriceLevelWrite(code="RETAIL", name="Shop price", is_active=False),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    shop.session.commit()

    levels = shop.reserve()
    assert levels["RETAIL"].id == own.id
    assert (levels["RETAIL"].name, levels["RETAIL"].is_active) == ("Shop price", True)
    assert levels["RETAIL"].trade_class == "RETAILER"


def test_the_level_list_makes_them_for_a_by_lot_firm_only() -> None:
    """A firm that switched before step 3 gets them on its first read."""
    shop = _Priced()
    scope = report_scope(shop.firm.id)
    codes = [row.code for row in list_price_levels(scope, shop.session).data or []]
    assert codes == ["RETAIL", "WHOLESALE"]

    average = _Priced(by_lot=False)
    scope = report_scope(average.firm.id)
    assert list_price_levels(scope, average.session).data == []


def test_a_reserved_level_is_renamed_but_never_deleted_or_retired() -> None:
    """Rename and reorder stand; delete and making it inactive are refused."""
    shop = _Priced()
    retail = shop.reserve()["RETAIL"]
    service = PriceLevelService(shop.session)

    service.update(
        retail.id,
        PriceLevelWrite(code="RTL", name="Retail shops", sort_order=5),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    assert (retail.code, retail.name, retail.trade_class) == (
        "RTL",
        "Retail shops",
        "RETAILER",
    )
    with pytest.raises(ValidationError, match="not taken out of use"):
        service.update(
            retail.id,
            PriceLevelWrite(code="RTL", name="Retail shops", is_active=False),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )
    with pytest.raises(ConflictError, match="cannot be deleted"):
        service.delete(retail.id, firm_id=shop.firm.id, actor_id=shop.actor)


def test_a_customer_with_no_level_starts_on_the_level_of_his_kind() -> None:
    """A retailer on Retail, a stockist on Wholesale, anybody else on none."""
    shop = _Priced()
    levels = shop.reserve()

    assert customer_price_level(shop.session, shop.customer) == levels["RETAIL"].id
    shop.customer.trade_class = "STOCKIST"
    assert customer_price_level(shop.session, shop.customer) == levels["WHOLESALE"].id
    shop.customer.trade_class = "OTHER"
    assert customer_price_level(shop.session, shop.customer) is None


def test_a_line_naming_no_lot_takes_the_first_lots_price_for_the_bills_kind() -> None:
    """EARLY leaves first: 80.00 on a retailer's bill, 70.00 switched to Wholesale.

    No BATCH_PTR_PTS is needed: the firm costs by lot.
    """
    shop = _Priced()
    levels = shop.reserve()

    assert shop.priced_at(shop.unpriced()) == Decimal("80.0000")
    assert shop.priced_at(shop.unpriced(level=levels["WHOLESALE"])) == Decimal(
        "70.0000"
    )


def test_a_level_with_no_class_leaves_the_customers_kind_on_the_lot() -> None:
    """A Dealer bill for a retailer still takes the lot's PTR, as before."""
    shop = _Priced()
    shop.reserve()
    dealer = PriceLevelService(shop.session).create(
        PriceLevelWrite(code="DEALER", name="Dealer"),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    shop.session.commit()

    assert shop.priced_at(shop.unpriced(level=dealer)) == Decimal("80.0000")


def test_a_chosen_lot_is_priced_at_its_own_price() -> None:
    """LATE chosen on a Wholesale bill: its PTS, 75.00."""
    shop = _Priced()
    levels = shop.reserve()

    assert shop.priced_at(
        shop.unpriced(("LATE", "4"), level=levels["WHOLESALE"])
    ) == Decimal("75.0000")


def test_one_line_never_takes_lots_at_two_prices() -> None:
    """EARLY and LATE differ on a retailer's bill: refused, naming both prices."""
    shop = _Priced()
    shop.reserve()

    with pytest.raises(ValidationError, match=r"two prices .* 80\.00 and 90\.00"):
        shop.priced_at(shop.unpriced(("EARLY", "2"), ("LATE", "2")))


def test_lots_that_agree_on_the_bills_price_share_a_line() -> None:
    """LATE at a PTR of 80.00 too: one line at 80.00; a typed price is free."""
    shop = _Priced()
    shop.reserve()
    shop.batches["LATE"].ptr = Decimal("80")
    shop.session.commit()

    assert shop.priced_at(shop.unpriced(("EARLY", "2"), ("LATE", "2"))) == Decimal(
        "80.0000"
    )
    shop.batches["LATE"].ptr = Decimal("90")
    shop.session.commit()
    assert shop.priced_at(
        shop.unpriced(("EARLY", "2"), ("LATE", "2"), price="85")
    ) == Decimal("85.0000")


def test_the_editor_is_told_the_first_lots_price_at_the_warehouse() -> None:
    """The unit-price route prices at the lot first out of the place it names."""
    shop = _Priced()
    shop.reserve()
    scope = report_scope(shop.firm.id)
    on = shop.bill(None).invoice_date

    asked = unit_prices(
        scope,
        product_ids=[shop.drug.id],
        on=on,
        customer_id=shop.customer.id,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        db=shop.session,
    )
    assert asked.data is not None
    assert [(p.unit_price, p.source) for p in asked.data.prices] == [
        (Decimal("80"), "BATCH_PTR")
    ]
    unplaced = unit_prices(
        scope,
        product_ids=[shop.drug.id],
        on=on,
        customer_id=shop.customer.id,
        db=shop.session,
    )
    assert unplaced.data is not None
    assert unplaced.data.prices[0].unit_price == Decimal("100")


def test_the_discount_limit_judges_a_line_at_the_lot_it_was_priced_from() -> None:
    """The baseline is the lot named, else the lot first out of the warehouse."""
    shop = _Priced()
    shop.reserve()
    order_line = type(
        "OrderLine",
        (),
        {"product_id": shop.drug.id, "line_number": 1, "quantity": Decimal("4")},
    )()
    limits = DiscountLimitService(shop.session)
    common = {
        "firm_id": shop.firm.id,
        "customer_id": shop.customer.id,
        "territory_id": None,
        "on": shop.bill(None).invoice_date,
    }
    assert limits.customer_prices(
        [order_line],
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        **common,  # type: ignore[arg-type]
    ) == {1: Decimal("80.00")}
    assert limits.customer_prices(
        [order_line],
        batches={1: shop.batches["LATE"].id},
        **common,  # type: ignore[arg-type]
    ) == {1: Decimal("90.00")}


def test_a_firm_on_average_prices_as_before() -> None:
    """No reserved level, no lot price without BATCH_PTR_PTS: the product's 100."""
    shop = _Priced(by_lot=False)

    assert customer_price_level(shop.session, shop.customer) is None
    assert shop.priced_at(shop.unpriced()) == Decimal("100.0000")
    resolver = UnitPriceResolver(
        shop.session,
        firm_id=shop.firm.id,
        customer_id=shop.customer.id,
        territory_id=None,
        on=shop.bill(None).invoice_date,
    )
    place = StockPlace(branch_id=shop.branch.id, warehouse_id=shop.warehouse.id)
    assert resolver.price(shop.drug.id, place=place).price == Decimal("100")
