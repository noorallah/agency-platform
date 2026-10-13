"""The back-order report can be asked about named orders alone (D-UI-60).

The desktop read the whole firm's report after every approval to say what one
order had on back order. What an order is short of depends on the older open
orders that take the same stock first, so the filtered read still hands the
stock out across every open line of the products the named orders carry --
and must answer exactly what the whole report answers for those orders.
"""

import asyncio
import json
from collections.abc import Iterator
from decimal import Decimal
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.common.scope import ResolvedFirmScope
from app.core.database.dependencies import get_db
from app.customers.models import Customer
from app.firms.models import Firm
from app.products.models import Product
from app.sales_order.api.router import (
    MAX_BACK_ORDER_IDS,
    SalesOrderReportScope,
    back_order_report,
    router,
)
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesOrderBackOrderRecord
from app.sales_order.services import SalesOrderService
from tests.unit.test_audit_trail_api import _principal
from tests.unit.test_delivery_note_module import (
    _approved_order,
    _branch,
    _customer,
    _firm,
    _product,
    _session_factory,
    _stock,
    _warehouse,
)


class _Shop:
    """One firm with two customers and two products, ten of each on the shelf."""

    def __init__(self) -> None:
        """Build the firm, its masters and its stock."""
        self.session: Session = _session_factory()()
        self.firm: Firm = _firm(self.session)
        self.branch: Branch = _branch(self.session, firm_id=self.firm.id)
        self.warehouse: Warehouse = _warehouse(
            self.session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.first_customer: Customer = _customer(self.session, firm_id=self.firm.id)
        self.second_customer = Customer(
            firm_id=self.firm.id,
            code="CUS-002",
            customer_type="RETAIL",
            name="Customer CUS-002",
            display_name="Customer CUS-002",
            currency_code="INR",
            status="ACTIVE",
            credit_limit=Decimal("50000"),
            opening_balance=Decimal("0"),
        )
        self.soap: Product = _product(self.session, firm_id=self.firm.id)
        self.salt = Product(
            firm_id=self.firm.id,
            code="SKU-002",
            name="Product SKU-002",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.session.add_all([self.second_customer, self.salt])
        self.session.commit()
        self.actor: UUID = uuid4()
        for product in (self.soap, self.salt):
            _stock(
                self.session,
                firm=self.firm,
                branch=self.branch,
                warehouse=self.warehouse,
                product=product,
                quantity=Decimal("10"),
            )

    def order(self, customer: Customer, product: Product, quantity: str) -> SalesOrder:
        """Raise and approve an order of one line."""
        order, _ = _approved_order(
            self.session,
            firm=self.firm,
            branch=self.branch,
            warehouse=self.warehouse,
            customer=customer,
            product=product,
            quantity=Decimal(quantity),
            actor_id=self.actor,
        )
        return order

    def report(
        self, order_ids: list[UUID] | None = None
    ) -> list[SalesOrderBackOrderRecord]:
        """Read the report, whole or for the named orders."""
        return SalesOrderService(self.session).back_orders(
            firm_scope=self.firm.id, order_ids=order_ids
        )


def test_a_named_order_reads_as_it_does_in_the_whole_report() -> None:
    """An older order of another customer takes the stock first, filter or not."""
    shop = _Shop()
    # Ten soap on the shelf. The older order takes eight; the later one, of
    # another customer, is owed six and can have two: four short.
    older = shop.order(shop.first_customer, shop.soap, "8")
    later = shop.order(shop.second_customer, shop.soap, "6")
    # Salt is short on an order nobody names below.
    salty = shop.order(shop.first_customer, shop.salt, "25")

    whole = shop.report()
    assert [(row.order_id, row.back_order_quantity) for row in whole] == [
        (later.id, Decimal("4.0000")),
        (salty.id, Decimal("15.0000")),
    ]

    named = shop.report([later.id])
    assert named == [row for row in whole if row.order_id == later.id]
    assert named[0].available_stock == Decimal("10.0000")
    # The older order is covered, so naming it finds nothing -- and it does
    # not make the later one's row appear.
    assert shop.report([older.id]) == []


def test_several_orders_are_named_at_once() -> None:
    """Each named order's rows, in the report's own order, and no others."""
    shop = _Shop()
    shop.order(shop.first_customer, shop.soap, "8")
    later = shop.order(shop.second_customer, shop.soap, "6")
    salty = shop.order(shop.first_customer, shop.salt, "25")
    last = shop.order(shop.second_customer, shop.salt, "3")

    whole = shop.report()
    assert [row.order_id for row in whole] == [later.id, salty.id, last.id]

    assert shop.report([last.id, later.id]) == [
        row for row in whole if row.order_id in {later.id, last.id}
    ]
    assert shop.report([salty.id, later.id, last.id, later.id]) == whole


def test_an_order_of_another_firm_or_of_nobody_has_no_rows() -> None:
    """The firm is the scope: an id from elsewhere is not a way to read it."""
    shop = _Shop()
    short = shop.order(shop.first_customer, shop.soap, "40")
    other = Firm(
        name="Another Firm",
        code="OTH-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=shop.firm.financial_year_start,
    )
    shop.session.add(other)
    shop.session.commit()
    orders = SalesOrderService(shop.session)

    assert [row.order_id for row in shop.report([short.id])] == [short.id]
    assert orders.back_orders(firm_scope=other.id, order_ids=[short.id]) == []
    assert shop.report([uuid4()]) == []
    assert shop.report([]) == []
    assert [row.order_id for row in shop.report([uuid4(), short.id])] == [short.id]


def test_a_named_read_leaves_the_other_products_alone() -> None:
    """Only the products the named orders carry are read, lines and stock."""
    shop = _Shop()
    later = shop.order(shop.second_customer, shop.soap, "16")
    shop.order(shop.first_customer, shop.salt, "25")
    statements: list[tuple[str, object]] = []

    def _record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001 - SQLAlchemy's own signature
    ) -> None:
        """Keep every statement the engine is handed, with its values."""
        statements.append((statement, parameters))

    event.listen(shop.session.get_bind(), "before_cursor_execute", _record)
    [row] = shop.report([later.id])
    named = list(statements)
    statements.clear()
    shop.report()
    event.remove(shop.session.get_bind(), "before_cursor_execute", _record)

    assert row.back_order_quantity == Decimal("6.0000")
    assert named
    assert not _naming(named, shop.salt.id)
    # The whole report does name it, so the line above can fail.
    assert _naming(statements, shop.salt.id)


def _naming(statements: list[tuple[str, object]], product_id: UUID) -> list[str]:
    """Return the statements that carry ``product_id`` among their values."""
    spellings = (product_id.hex, str(product_id))
    return [
        text
        for text, values in statements
        if any(spelling in str(values) for spelling in spellings)
    ]


def test_the_route_takes_the_ids_and_refuses_too_many() -> None:
    """``order_id`` repeats; past the limit is a 422 rather than a long read."""
    shop = _Shop()
    short = shop.order(shop.first_customer, shop.soap, "40")
    shop.order(shop.second_customer, shop.salt, "40")
    scope = ResolvedFirmScope(
        principal=_principal(shop.actor, {"SALES_VIEW"}), firm_id=shop.firm.id
    )

    answer = back_order_report(scope=scope, order_id=[short.id], db=shop.session)
    assert [row.order_id for row in answer.data or []] == [short.id]
    assert len(back_order_report(scope=scope, db=shop.session).data or []) == 2

    def _db() -> Iterator[Session]:
        """Hand the route this test's session."""
        yield shop.session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[SalesOrderReportScope.__metadata__[0].dependency] = (
        lambda: scope
    )

    def get(order_ids: list[str]) -> tuple[int, list[dict[str, object]]]:
        """Send one GET through the application and return status and rows."""
        return _get(app, urlencode([("order_id", value) for value in order_ids]))

    status, rows = get([str(short.id), str(uuid4())])
    assert status == 200
    assert [row["order_id"] for row in rows] == [str(short.id)]
    assert len(get([])[1]) == 2

    at_limit = [str(uuid4()) for _ in range(MAX_BACK_ORDER_IDS)]
    assert get(at_limit)[0] == 200
    assert get([*at_limit, str(uuid4())])[0] == 422
    assert get(["not-an-id"])[0] == 422


def _get(app: FastAPI, query: str) -> tuple[int, list[dict[str, object]]]:
    """Call the back-order route over ASGI, as a request would arrive."""
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        """Hand over an empty request body."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        """Keep what the application answers."""
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/sales-orders/reports/back-orders",
        "raw_path": b"/api/v1/sales-orders/reports/back-orders",
        "root_path": "",
        "query_string": query.encode(),
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))  # type: ignore[arg-type]
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(
        bytes(m.get("body", b""))  # type: ignore[arg-type]
        for m in sent
        if m["type"] == "http.response.body"
    )
    assert isinstance(status, int)
    data = json.loads(body).get("data") if status == 200 else []
    return status, data or []
