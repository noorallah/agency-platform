"""A sales order and a sales invoice are raised under their own create codes.

D-ROLE-2, found live on 2026-10-04: `SALES_EXECUTIVE` held `SALES_ORDER_CREATE`
and `SALES_INVOICE_CREATE`, and `BILLING_EXECUTIVE` `SALES_INVOICE_CREATE`, from
the first identity seed -- and `POST /sales-orders` and `POST /sales-invoices`
asked for `SALES_CREATE`. Field Sales could quote and never take the order;
Counter Sales could not raise a bill.

This pins it against the built application: the create routes enforce the
per-document code, the job roles reach the routes on their path, every role
that holds `SALES_CREATE` holds both codes so nobody lost an action, and a
draft is editable by whoever raised it under the create code and by nobody
else short of `SALES_UPDATE`. Approval stays with `SALES_APPROVE`: the role
that raises a document is not the one that agrees to it.
"""

from collections.abc import Iterable, Iterator
from datetime import date
from decimal import Decimal
from functools import lru_cache
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from fastapi.routing import APIRoute

from app.common.scope import ResolvedFirmScope
from app.core.exceptions import AuthorizationError
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES
from app.sales_order.api.router import update_sales_order
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_sales_order_module import (
    _branch,
    _customer,
    _firm,
    _principal,
    _product,
    _session_factory,
    _warehouse,
)

_ORDER = "SALES_ORDER_CREATE"
_INVOICE = "SALES_INVOICE_CREATE"


def _walk(route: APIRoute) -> Iterator[frozenset[str]]:
    """Yield, per permission dependency, the codes any one of which opens it."""
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        codes = getattr(dependency.call, "permission_codes", None)
        code = getattr(dependency.call, "permission_code", None)
        if codes:
            yield frozenset(codes)
        elif code:
            yield frozenset({code})
        pending.extend(dependency.dependencies)


def _endpoints(routes: Iterable[object]) -> Iterator[object]:
    """Yield the leaf endpoints of a built application, through included routers."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _endpoints(inner.routes)
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from _endpoints(nested)
            continue
        yield route


@lru_cache(maxsize=1)
def _gates() -> dict[str, tuple[frozenset[str], ...]]:
    """Map `METHOD path` to the permission gates the application enforces."""
    from app.main import create_app

    gates: dict[str, list[frozenset[str]]] = {}
    for route in _endpoints(create_app().routes):
        if not isinstance(route, APIRoute):
            continue
        found = list(_walk(route))
        for method in route.methods:
            gates.setdefault(f"{method} {route.path}", []).extend(found)
    return {key: tuple(value) for key, value in gates.items()}


def _opened_by(route: str, codes: frozenset[str]) -> bool:
    """Whether a holder of `codes` passes every permission gate on `route`."""
    assert route in _gates(), f"{route} is not a route"
    gates = _gates()[route]
    assert gates, f"{route} enforces no permission code"
    return all(gate & codes for gate in gates)


def test_both_codes_are_seeded() -> None:
    """An unseeded code can be attached to no role."""
    assert {_ORDER, _INVOICE} <= set(SYSTEM_PERMISSION_CODES)


@pytest.mark.parametrize(
    ("route", "code"),
    [
        ("POST /api/v1/sales-orders", _ORDER),
        ("POST /api/v1/sales-orders/preview", _ORDER),
        ("POST /api/v1/sales-invoices", _INVOICE),
        ("POST /api/v1/sales-invoices/preview", _INVOICE),
    ],
)
def test_the_create_routes_enforce_the_document_code(route: str, code: str) -> None:
    """Raising a document takes its own code, not the module's `SALES_CREATE`."""
    gates = _gates()[route]
    assert frozenset({code}) in gates, f"{route} enforces {gates}"
    assert not any("SALES_CREATE" in gate for gate in gates)


@pytest.mark.parametrize(
    "route",
    [
        "GET /api/v1/sales-orders",
        "GET /api/v1/sales-orders/{order_id}",
        "POST /api/v1/sales-orders",
        "POST /api/v1/sales-orders/preview",
        "PUT /api/v1/sales-orders/{order_id}",
        "POST /api/v1/sales-invoices",
        "PUT /api/v1/sales-invoices/{invoice_id}",
    ],
)
def test_field_sales_can_take_and_correct_an_order(route: str) -> None:
    """Field Sales raises an order and corrects the draft it raised."""
    granted = ROLE_PERMISSION_CODES["SALES_EXECUTIVE"]
    assert _opened_by(route, granted), f"refused {route}: {_gates()[route]}"


@pytest.mark.parametrize(
    "route",
    [
        "GET /api/v1/sales-invoices",
        "GET /api/v1/sales-invoices/{invoice_id}",
        "POST /api/v1/sales-invoices",
        "POST /api/v1/sales-invoices/preview",
        "PUT /api/v1/sales-invoices/{invoice_id}",
    ],
)
def test_counter_sales_can_raise_and_correct_a_bill(route: str) -> None:
    """Counter Sales raises a bill and corrects the draft it raised."""
    granted = ROLE_PERMISSION_CODES["BILLING_EXECUTIVE"]
    assert _opened_by(route, granted), f"refused {route}: {_gates()[route]}"


@pytest.mark.parametrize("role", ["SALES_EXECUTIVE", "BILLING_EXECUTIVE"])
@pytest.mark.parametrize(
    "route",
    [
        "POST /api/v1/sales-orders/{order_id}/approve",
        "POST /api/v1/sales-invoices/{invoice_id}/approve",
    ],
)
def test_approval_stays_with_the_approver(role: str, route: str) -> None:
    """Whoever raises a document is not the one who agrees to it."""
    assert not _opened_by(route, ROLE_PERMISSION_CODES[role])


def test_counter_sales_takes_no_order() -> None:
    """A bill does not make the counter clerk an order taker."""
    granted = ROLE_PERMISSION_CODES["BILLING_EXECUTIVE"]
    assert not _opened_by("POST /api/v1/sales-orders", granted)


@pytest.mark.parametrize(
    "role",
    sorted(
        role for role, codes in ROLE_PERMISSION_CODES.items() if "SALES_CREATE" in codes
    ),
)
def test_every_holder_of_sales_create_holds_both_codes(role: str) -> None:
    """Nobody who could raise an order or a bill before can no longer."""
    assert {_ORDER, _INVOICE} <= ROLE_PERMISSION_CODES[role]


def test_a_draft_order_is_corrected_by_its_author_only() -> None:
    """The create code edits the caller's own draft and nobody else's."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)

    def _payload(quantity: str) -> SalesOrderCreate:
        """Build an order for `quantity` of the one product."""
        return SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal("100"),
                )
            ],
        )

    author, colleague, manager = uuid4(), uuid4(), uuid4()
    executive = set(ROLE_PERMISSION_CODES["SALES_EXECUTIVE"])
    order = SalesOrderService(session).create_order(
        _payload("4"), firm_id=firm.id, actor_id=author
    )

    def _edit(user: UUID, codes: set[str], quantity: str) -> None:
        """Edit the order as `user` holding `codes`."""
        update_sales_order(
            order_id=order.id,
            data=_payload(quantity),
            scope=ResolvedFirmScope(principal=_principal(user, codes), firm_id=firm.id),
            response=Response(),
            db=session,
        )

    _edit(author, executive, "5")
    with pytest.raises(AuthorizationError):
        _edit(colleague, executive, "6")
    _edit(manager, set(ROLE_PERMISSION_CODES["SALES_MANAGER"]), "7")
    response = SalesOrderService(session).order_response(
        SalesOrderService(session).get_order(order.id, firm_scope=firm.id)
    )
    assert response.created_by == author
    assert response.lines[0].quantity == Decimal("7")
