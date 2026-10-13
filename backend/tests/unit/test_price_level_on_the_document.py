"""A document that names its own price level (backlog 131, row M13).

Detergent sells at 100, dealers pay 90 and wholesale is 70. A customer carries
a usual level, his own or his group's, and a document is priced at it unless
the document names another: the one switch that changes the whole bill. The
level takes the customer's place in the ranking and no other, so a price list
agreed with the customer still comes first and a typed price beats them all.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.pricing.api.price_levels_router import list_price_levels, unit_prices
from app.pricing.models import PriceLevel, PriceListItem
from app.pricing.schemas.price_level import (
    PriceLevelWrite,
    ProductLevelRate,
    ProductLevelRatesWrite,
)
from app.pricing.services.price_levels import PriceLevelService
from app.pricing.services.unit_price import UnitPriceResolver, document_price_level
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesOrderUpdate,
)
from app.sales_order.services import SalesOrderService
from tests.unit.report_windows import report_scope
from tests.unit.test_price_levels import ON, _priced_firm
from tests.unit.test_sales_chain_synthesis import (
    _Firm,
    _request_session,
    _sent_back,
)

D = Decimal


class _Shop:
    """The firm of ``test_price_levels`` with a second level, Wholesale at 70."""

    def __init__(self) -> None:
        """Build the firm and add the level."""
        (
            self.session,
            firm,
            branch,
            warehouse,
            self.anand,
            self.walk_in,
        ) = _priced_firm()
        self.firm_id: UUID = firm.id  # type: ignore[attr-defined]
        self.branch_id: UUID = branch.id  # type: ignore[attr-defined]
        self.warehouse_id: UUID = warehouse.id  # type: ignore[attr-defined]
        item = self.session.scalar(select(PriceListItem))
        assert item is not None
        self.product_id = item.product_id
        self.dealer = _level_of(self.session, "DEALER")
        self.wholesale = _add_level(
            self.session,
            firm_id=self.firm_id,
            product_id=self.product_id,
            code="wholesale",
            name="Wholesale",
            rates={self.dealer.id: D("90"), None: D("70")},
        )

    def price(
        self, customer: Customer | None, level: PriceLevel | None
    ) -> tuple[Decimal, str]:
        """Return the price and its source for a customer and a named level."""
        found = UnitPriceResolver(
            self.session,
            firm_id=self.firm_id,
            customer_id=None if customer is None else customer.id,
            territory_id=None,
            on=ON,
            price_level_id=None if level is None else level.id,
        ).price(self.product_id)
        return found.price, found.source

    def order(
        self, customer: Customer, level: PriceLevel | None, **line: object
    ) -> SalesOrderCreate:
        """Describe an order of two with whatever the line states."""
        return SalesOrderCreate(
            customer_id=customer.id,
            branch_id=self.branch_id,
            warehouse_id=self.warehouse_id,
            order_date=ON,
            price_level_id=None if level is None else level.id,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=self.product_id,
                    quantity=D("2"),
                    **line,  # type: ignore[arg-type]
                )
            ],
        )

    def first_price(self, order: SalesOrder) -> Decimal:
        """Return the price on the order's one line."""
        [line] = SalesOrderService(self.session).order_response(order).lines
        return line.unit_price


def _level_of(session: Session, code: str) -> PriceLevel:
    """Return the live level with this code."""
    level = session.scalar(select(PriceLevel).where(PriceLevel.code == code))
    assert level is not None
    return level


def _add_level(
    session: Session,
    *,
    firm_id: UUID,
    product_id: UUID,
    code: str,
    name: str,
    rates: dict[UUID | None, Decimal],
) -> PriceLevel:
    """Create a level and restate the product's rates; None keys the new one."""
    levels = PriceLevelService(session)
    level = levels.create(
        PriceLevelWrite(code=code, name=name), firm_id=firm_id, actor_id=uuid4()
    )
    levels.replace_product_rates(
        product_id,
        ProductLevelRatesWrite(
            rates=[
                ProductLevelRate(price_level_id=key or level.id, rate=rate)
                for key, rate in rates.items()
            ]
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    session.commit()
    return level


def test_a_named_level_takes_the_customers_place_and_no_other() -> None:
    shop = _Shop()
    assert shop.price(shop.walk_in, None) == (D("100"), "PRODUCT")
    assert shop.price(shop.walk_in, shop.wholesale) == (D("70"), "PRICE_LEVEL")
    assert shop.price(shop.walk_in, shop.dealer) == (D("90"), "PRICE_LEVEL")
    # Anand's own list agrees 80: an agreement beats any level, named or not.
    assert shop.price(shop.anand, shop.wholesale) == (D("80"), "PRICE_LIST")
    shop.session.query(PriceListItem).update({"rate": None})
    shop.session.commit()
    assert shop.price(shop.anand, None) == (D("90"), "PRICE_LEVEL"), "his group's"
    assert shop.price(shop.anand, shop.wholesale) == (D("70"), "PRICE_LEVEL")


def test_a_product_with_no_rate_at_the_named_level_falls_to_its_own_price() -> None:
    shop = _Shop()
    bare = _add_level(
        shop.session,
        firm_id=shop.firm_id,
        product_id=shop.product_id,
        code="export",
        name="Export",
        rates={shop.dealer.id: D("90"), shop.wholesale.id: D("70")},
    )
    # Not the dealer's 90 the customer's group would have given.
    shop.session.query(PriceListItem).update({"rate": None})
    shop.session.commit()
    assert shop.price(shop.anand, bare) == (D("100"), "PRODUCT")


def test_a_level_not_in_use_or_not_the_firms_is_refused_by_name() -> None:
    shop = _Shop()
    shop.wholesale.is_active = False
    shop.session.commit()
    with pytest.raises(ValidationError, match="Wholesale is not in use"):
        document_price_level(
            shop.session, firm_id=shop.firm_id, price_level_id=shop.wholesale.id
        )
    with pytest.raises(ValidationError, match="one of the firm's price levels"):
        document_price_level(
            shop.session, firm_id=uuid4(), price_level_id=shop.dealer.id
        )
    with pytest.raises(ValidationError, match="one of the firm's price levels"):
        document_price_level(shop.session, firm_id=shop.firm_id, price_level_id=uuid4())
    assert (
        document_price_level(shop.session, firm_id=shop.firm_id, price_level_id=None)
        is None
    )
    # An order written while the level was in use is priced as the customer's
    # once it is withdrawn, rather than at rates nobody keeps.
    assert shop.price(shop.walk_in, shop.wholesale) == (D("100"), "PRODUCT")


def test_an_order_is_priced_at_the_level_it_names_and_a_typed_price_stands() -> None:
    shop = _Shop()
    service = SalesOrderService(shop.session)
    actor = uuid4()
    usual = service.create_order(
        shop.order(shop.walk_in, None), firm_id=shop.firm_id, actor_id=actor
    )
    switched = service.create_order(
        shop.order(shop.walk_in, shop.wholesale), firm_id=shop.firm_id, actor_id=actor
    )
    typed = service.create_order(
        shop.order(shop.walk_in, shop.wholesale, unit_price=D("95")),
        firm_id=shop.firm_id,
        actor_id=actor,
    )
    assert shop.first_price(usual) == D("100.0000")
    assert shop.first_price(switched) == D("70.0000")
    assert shop.first_price(typed) == D("95.0000")
    answer = service.order_response(switched)
    assert answer.price_level_id == shop.wholesale.id
    assert service.order_response(usual).price_level_id is None


def test_an_edit_keeps_the_level_on_silence_and_clears_it_on_null() -> None:
    shop = _Shop()
    service = SalesOrderService(shop.session)
    actor = uuid4()
    order = service.create_order(
        shop.order(shop.walk_in, shop.wholesale), firm_id=shop.firm_id, actor_id=actor
    )
    said = shop.order(shop.walk_in, None).model_dump(exclude={"price_level_id"})

    service.update_order(
        order.id, SalesOrderUpdate(**said), firm_scope=shop.firm_id, actor_id=actor
    )
    shop.session.refresh(order)
    assert order.price_level_id == shop.wholesale.id, "silence keeps it"
    assert shop.first_price(order) == D("70.0000")

    service.update_order(
        order.id,
        SalesOrderUpdate(**said, price_level_id=shop.dealer.id),
        firm_scope=shop.firm_id,
        actor_id=actor,
    )
    shop.session.refresh(order)
    assert shop.first_price(order) == D("90.0000"), "the line nobody priced follows"

    service.update_order(
        order.id,
        SalesOrderUpdate(**said, price_level_id=None),
        firm_scope=shop.firm_id,
        actor_id=actor,
    )
    shop.session.refresh(order)
    assert order.price_level_id is None
    assert shop.first_price(order) == D("100.0000"), "the customer's usual again"


def test_the_editor_is_told_the_price_at_a_level_and_what_usual_is() -> None:
    shop = _Shop()
    shop.session.query(PriceListItem).update({"rate": None})
    shop.session.commit()
    scope = report_scope(shop.firm_id)

    def asked(level: PriceLevel | None) -> tuple[UUID | None, UUID | None, Decimal]:
        """Return the level used, the customer's usual and the price."""
        data = unit_prices(
            scope,
            product_ids=[shop.product_id],
            on=ON,
            customer_id=shop.anand.id,
            territory_id=None,
            price_level_id=None if level is None else level.id,
            db=shop.session,
        ).data
        assert data is not None
        [price] = data.prices
        return data.price_level_id, data.customer_price_level_id, price.unit_price

    assert asked(None) == (shop.dealer.id, shop.dealer.id, D("90"))
    assert asked(shop.wholesale) == (shop.wholesale.id, shop.dealer.id, D("70"))
    with pytest.raises(ValidationError, match="one of the firm's price levels"):
        unit_prices(
            scope,
            product_ids=[shop.product_id],
            on=ON,
            customer_id=shop.anand.id,
            territory_id=None,
            price_level_id=uuid4(),
            db=shop.session,
        )
    names = [row.name for row in list_price_levels(scope, db=shop.session).data or []]
    assert sorted(names) == ["Dealer", "Wholesale"]


def _counter_firm() -> tuple[Session, _Firm, PriceLevel]:
    """Build a firm that types only the bill, with Wholesale at 70."""
    session = _request_session()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.product.selling_price = D("100")
    session.commit()
    wholesale = _add_level(
        session,
        firm_id=setup.firm.id,
        product_id=setup.product.id,
        code="wholesale",
        name="Wholesale",
        rates={None: D("70")},
    )
    return session, setup, wholesale


def _unpriced_bill(setup: _Firm, level: PriceLevel | None) -> SalesInvoiceCreate:
    """Describe a bill of four with no price typed."""
    return SalesInvoiceCreate(
        customer_id=setup.customer.id,
        invoice_date=date(2026, 8, 4),
        price_level_id=None if level is None else level.id,
        lines=[
            SalesInvoiceLineWrite(
                product_id=setup.product.id,
                line_number=1,
                current_invoice_quantity=D("4"),
                unit_price=None,
            )
        ],
    )


def _billed_at(session: Session, invoice: SalesInvoice) -> Decimal:
    """Return the price on the bill's one line."""
    [price] = session.scalars(
        select(SalesInvoiceLine.unit_price).where(
            SalesInvoiceLine.sales_invoice_id == invoice.id,
            SalesInvoiceLine.is_deleted.is_(False),
        )
    ).all()
    return price


def test_a_bill_typed_directly_is_priced_at_the_level_it_names() -> None:
    session, setup, wholesale = _counter_firm()
    service = SalesInvoiceService(session)
    usual = service.create_invoice(
        _unpriced_bill(setup, None), firm_id=setup.firm.id, actor_id=uuid4()
    )
    switched = service.create_invoice(
        _unpriced_bill(setup, wholesale), firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert _billed_at(session, usual) == D("100.0000")
    assert _billed_at(session, switched) == D("70.0000")
    levels = session.scalars(select(SalesOrder.price_level_id)).all()
    assert sorted(str(level or "") for level in levels) == sorted(
        ["", str(wholesale.id)]
    ), "the order the bill raised keeps the level"


def test_a_bill_starts_from_the_customers_usual_level() -> None:
    session, setup, wholesale = _counter_firm()
    setup.customer.price_level_id = wholesale.id
    session.commit()
    invoice = SalesInvoiceService(session).create_invoice(
        _unpriced_bill(setup, None), firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert _billed_at(session, invoice) == D("70.0000")


def test_a_bill_of_documents_cannot_name_a_level() -> None:
    session, setup, wholesale = _counter_firm()
    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        setup.bare_bill(D("3")), firm_id=setup.firm.id, actor_id=uuid4()
    )
    again = _sent_back(service, invoice, "3").model_copy(
        update={"price_level_id": wholesale.id}
    )
    # A new bill of a note somebody else's bill raised is refused for its own
    # reasons first, so ask the chain the question directly.
    from app.sales_invoice.services.sales_chain_service import SalesChainService

    with pytest.raises(ValidationError, match="cannot name a price level"):
        SalesChainService(session).ensure_invoice_source(
            again, firm_id=setup.firm.id, actor_id=uuid4()
        )


def test_a_saved_bill_keeps_its_level_when_an_edit_raises_its_order_again() -> None:
    session, setup, wholesale = _counter_firm()
    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        _unpriced_bill(setup, wholesale), firm_id=setup.firm.id, actor_id=uuid4()
    )
    # Grown from 4 to 6 by its source fields, saying nothing of the level.
    edit = _sent_back(service, invoice, "6")
    edit.lines[0] = edit.lines[0].model_copy(update={"unit_price": None})
    service.update_invoice(invoice.id, edit, firm_id=setup.firm.id, actor_id=uuid4())
    session.refresh(invoice)
    assert _billed_at(session, invoice) == D("70.0000")
    live = session.scalars(
        select(SalesOrder.price_level_id).where(
            SalesOrder.raised_by_sales_invoice_id == invoice.id,
            SalesOrder.status != "CANCELLED",
        )
    ).all()
    assert live == [wholesale.id]


def test_a_cheaper_level_named_on_the_order_is_judged_by_the_sellers_limit() -> None:
    """The switch is not a way round a discount limit (D-PRC-2).

    The limit measures what a line charges against the customer's own price,
    so wholesale at 42.00 for a customer whose price is 84.00 is half off
    whoever named the level, and it needs somebody allowed that much.
    """
    from tests.unit.test_discount_limit_judges_the_price import _Desk

    desk = _Desk()
    wholesale = _add_level(
        desk.session,
        firm_id=desk.firm_id,
        product_id=desk.setup.product.id,
        code="wholesale",
        name="Wholesale",
        rates={None: D("42")},
    )
    switched = desk.order(price=None, price_level_id=wholesale.id)

    with pytest.raises(ValidationError, match=r"42.00 where .* 84.00: 50.00% off"):
        desk.approve(switched, desk.manager)
    assert desk.approve(switched, desk.head) == "APPROVED"
    # A customer whose usual level it is pays it without anybody's leave.
    desk.setup.customer.price_level_id = wholesale.id
    desk.session.commit()
    assert desk.approve(desk.order(price=None), desk.manager) == "APPROVED"
