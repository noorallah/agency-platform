"""Whoever records the money against a bill can open the bill.

D-UI-46, found on screen on 2026-10-07 (SC-PB-031): Accounts (`ACCOUNTANT`)
records receipts and pays suppliers, and was offered neither Sales Invoices
nor Purchase Invoices -- both lists answered 403, because every read on them
asked for `SALES_VIEW` or `PURCHASE_VIEW` and the role holds neither.

Handing it those codes would have opened the orders, quotations, rate
contracts and supplier schemes with them, so the bills' own read routes take
the module's code **or** the settlement's: `RECEIPT_VIEW` for a customer's
bill, `PAYMENT_VIEW` for a supplier's. This pins both halves against the built
application, and that nothing else opened with them.
"""

from collections.abc import Iterable, Iterator
from functools import lru_cache

import pytest
from fastapi.routing import APIRoute

from app.identity.system_seed import ROLE_PERMISSION_CODES

_SALES = "/api/v1/sales-invoices"
_PURCHASE = "/api/v1/purchase-invoices"

#: What the two bill lists read to show a bill.
_BILL_READS = (
    f"GET {_SALES}",
    f"GET {_SALES}/{{invoice_id}}",
    f"GET {_PURCHASE}",
    f"GET {_PURCHASE}/summary",
    f"GET {_PURCHASE}/{{invoice_id}}",
    f"GET {_PURCHASE}/{{invoice_id}}/history",
)

#: What stays closed: raising, changing and approving a bill, and the
#: documents upstream of it.
_STILL_CLOSED = (
    f"POST {_SALES}",
    f"PUT {_SALES}/{{invoice_id}}",
    f"POST {_SALES}/{{invoice_id}}/approve",
    f"POST {_PURCHASE}",
    f"PUT {_PURCHASE}/{{invoice_id}}",
    f"POST {_PURCHASE}/{{invoice_id}}/approve",
    f"POST {_PURCHASE}/{{invoice_id}}/cancel",
    "GET /api/v1/sales-orders",
    "GET /api/v1/quotations",
    "GET /api/v1/purchases",
    "GET /api/v1/goods-receipts",
)


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


@pytest.mark.parametrize("route", _BILL_READS)
def test_accounts_can_open_the_bills(route: str) -> None:
    """Every read behind the two bill lists opens to Accounts."""
    granted = ROLE_PERMISSION_CODES["ACCOUNTANT"]
    assert _opened_by(route, granted), f"refused {route}: {_gates()[route]}"


@pytest.mark.parametrize("route", _STILL_CLOSED)
def test_reading_a_bill_opens_nothing_else(route: str) -> None:
    """The settlement codes raise no bill and reach no order or receipt of goods."""
    settles = frozenset({"RECEIPT_VIEW", "PAYMENT_VIEW"})
    assert not _opened_by(route, settles), route


@pytest.mark.parametrize(
    ("route", "code"),
    [(f"GET {_SALES}", "SALES_VIEW"), (f"GET {_PURCHASE}", "PURCHASE_VIEW")],
)
def test_the_module_code_alone_still_opens_the_list(route: str, code: str) -> None:
    """A role built on the module's own code keeps working unchanged."""
    assert _opened_by(route, frozenset({code}))
