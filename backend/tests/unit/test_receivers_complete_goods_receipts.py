"""Whoever receives goods can raise, edit and complete the goods receipt.

D-ROLE-3, found live on 2026-10-04: `POST /goods-receipts/{id}/complete` was
gated on `PURCHASE_APPROVE`, the code that approves orders and bills, so
Purchasing (`PURCHASE_EXECUTIVE`) raised a receipt and was refused at Complete,
and Warehouse (`INVENTORY_MANAGER`) could not raise one at all. Receiving now
has its own code, `PURCHASE_RECEIVE`.

This pins both halves against the built application: the receipt routes
enforce the code, and the roles that receive goods hold it. Ordering stays
off Warehouse (`PURCHASE_CREATE`), and completing a purchase **return** stays
with `PURCHASE_APPROVE` -- it reduces what is owed, a maker-checker decision
(decided 2026-10-04).
"""

from collections.abc import Iterable, Iterator
from functools import lru_cache

import pytest
from fastapi.routing import APIRoute

from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

_RECEIVERS = ("PURCHASE_EXECUTIVE", "PURCHASE_MANAGER", "INVENTORY_MANAGER")


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


def test_the_code_is_seeded() -> None:
    """An unseeded code can be attached to no role."""
    assert "PURCHASE_RECEIVE" in SYSTEM_PERMISSION_CODES


@pytest.mark.parametrize("role", _RECEIVERS)
def test_each_receiving_role_holds_the_code(role: str) -> None:
    """Purchasing, the purchase manager and Warehouse all receive goods."""
    assert "PURCHASE_RECEIVE" in ROLE_PERMISSION_CODES[role]


def test_warehouse_receives_but_does_not_order() -> None:
    """Raising a purchase order stays off the storeman."""
    granted = ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]
    assert "PURCHASE_CREATE" not in granted
    assert "PURCHASE_APPROVE" not in granted


@pytest.mark.parametrize(
    "route",
    [
        "POST /api/v1/goods-receipts",
        "PUT /api/v1/goods-receipts/{receipt_id}",
        "POST /api/v1/goods-receipts/{receipt_id}/complete",
    ],
)
def test_the_receipt_writes_enforce_the_code(route: str) -> None:
    """Raising, editing and completing a receipt take `PURCHASE_RECEIVE`."""
    gates = _gates()[route]
    assert frozenset({"PURCHASE_RECEIVE"}) in gates, f"{route} enforces {gates}"
    assert not any("PURCHASE_APPROVE" in gate for gate in gates)


@pytest.mark.parametrize("role", _RECEIVERS)
@pytest.mark.parametrize(
    "route",
    [
        # What the receipt screen and its editor read.
        "GET /api/v1/goods-receipts",
        "GET /api/v1/goods-receipts/{receipt_id}",
        "GET /api/v1/purchases",
        "GET /api/v1/purchases/{order_id}",
        # What they write.
        "POST /api/v1/goods-receipts",
        "PUT /api/v1/goods-receipts/{receipt_id}",
        "POST /api/v1/goods-receipts/{receipt_id}/complete",
    ],
)
def test_each_receiving_role_can_do_the_job(role: str, route: str) -> None:
    """Every route on the receiver's path opens to every receiving role."""
    assert _opened_by(
        route, ROLE_PERMISSION_CODES[role]
    ), f"{role} is refused {route}: {_gates()[route]}"


def test_warehouse_reads_no_bills() -> None:
    """Reading orders to receive against does not open the supplier's bills."""
    granted = ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]
    assert not _opened_by("GET /api/v1/purchase-invoices", granted)


@pytest.mark.parametrize(
    "route",
    [
        "POST /api/v1/purchase-returns/{return_id}/approve",
        "POST /api/v1/purchase-returns/{return_id}/complete",
    ],
)
def test_completing_a_purchase_return_stays_with_the_approver(route: str) -> None:
    """A return reduces what is owed: Purchasing raises it, the manager completes."""
    assert not _opened_by(route, ROLE_PERMISSION_CODES["PURCHASE_EXECUTIVE"])
    assert not _opened_by(route, ROLE_PERMISSION_CODES["INVENTORY_MANAGER"])
    assert _opened_by(route, ROLE_PERMISSION_CODES["PURCHASE_MANAGER"])
