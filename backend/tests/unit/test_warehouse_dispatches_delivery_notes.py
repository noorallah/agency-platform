"""Whoever dispatches goods can see, raise and dispatch a delivery note.

D-UI-30, found on screen on 2026-10-07 (SC-DN-025, SC-SO-034): Warehouse
(`INVENTORY_MANAGER`) "receives, stores, picks and dispatches stock" and held
no code that reached a delivery note. Every note route asked for a sales code,
so the server answered 403 and the desktop offered the role no screen.

Delivery notes now have their own codes -- `DELIVERY_NOTE_VIEW`,
`DELIVERY_NOTE_CREATE` and `DELIVERY_NOTE_DISPATCH` -- and every note route
takes the sales code it always took **or** one of them. This pins both halves
against the built application: the routes accept the codes, and Warehouse
holds them. It also pins what the split is for: the orders, quotations, bills
and returns stay closed to Warehouse, and "Dispatch and invoice", which raises
and approves a bill, stays with `SALES_APPROVE`.
"""

from collections.abc import Iterable, Iterator
from functools import lru_cache

import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute

from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

_CODES = ("DELIVERY_NOTE_VIEW", "DELIVERY_NOTE_CREATE", "DELIVERY_NOTE_DISPATCH")

#: Each new code and the sales code it stands beside.
_BESIDE = {
    "DELIVERY_NOTE_VIEW": "SALES_VIEW",
    "DELIVERY_NOTE_CREATE": "SALES_CREATE",
    "DELIVERY_NOTE_DISPATCH": "SALES_APPROVE",
}

_NOTES = "/api/v1/delivery-notes"

#: What the Delivery Notes screen and its editor read and write.
_WAREHOUSE_ROUTES = (
    f"GET {_NOTES}",
    f"GET {_NOTES}/summary",
    f"GET {_NOTES}/transporters",
    f"GET {_NOTES}/{{note_id}}",
    f"GET {_NOTES}/{{note_id}}/history",
    f"GET {_NOTES}/{{note_id}}/print",
    f"GET {_NOTES}/{{note_id}}/batch-check",
    f"GET {_NOTES}/{{note_id}}/dispatch-check",
    f"GET {_NOTES}/{{note_id}}/files",
    f"POST {_NOTES}/pick-list",
    f"POST {_NOTES}/loading-sheet",
    # The approved orders a note is raised from, and the firm's stages.
    "GET /api/v1/sales-orders",
    "GET /api/v1/sales-orders/{order_id}",
    "GET /api/v1/sales-orders/workflow-settings",
    # Home's "Orders to deliver" counts it.
    "GET /api/v1/sales-orders/reports/pending",
    # What it writes.
    f"POST {_NOTES}",
    f"PUT {_NOTES}/{{note_id}}",
    f"POST {_NOTES}/{{note_id}}/proof-of-delivery",
    f"POST {_NOTES}/{{note_id}}/files",
    f"POST {_NOTES}/{{note_id}}/approve",
    f"POST {_NOTES}/{{note_id}}/dispatch",
    f"POST {_NOTES}/{{note_id}}/complete",
    f"POST {_NOTES}/{{note_id}}/close",
    f"POST {_NOTES}/{{note_id}}/cancel",
    f"POST {_NOTES}/bulk-approve",
    f"POST {_NOTES}/bulk-cancel",
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


@pytest.mark.parametrize("code", _CODES)
def test_each_code_is_seeded(code: str) -> None:
    """An unseeded code can be attached to no role."""
    assert code in SYSTEM_PERMISSION_CODES


@pytest.mark.parametrize("code", _CODES)
def test_warehouse_holds_each_code(code: str) -> None:
    """Warehouse picks, packs and dispatches."""
    assert code in ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]


@pytest.mark.parametrize("code", _CODES)
def test_every_holder_of_the_sales_code_holds_the_note_code(code: str) -> None:
    """The catalogue reads the same for the roles that could act before."""
    sales = _BESIDE[code]
    missing = sorted(
        role
        for role, codes in ROLE_PERMISSION_CODES.items()
        if sales in codes and code not in codes
    )
    assert not missing, f"{missing} hold {sales} without {code}"


@pytest.mark.parametrize("route", _WAREHOUSE_ROUTES)
def test_warehouse_can_do_the_job(route: str) -> None:
    """Every route on the dispatcher's path opens to Warehouse."""
    granted = ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]
    assert _opened_by(route, granted), f"refused {route}: {_gates()[route]}"


@pytest.mark.parametrize("route", _WAREHOUSE_ROUTES)
def test_nobody_who_could_act_before_lost_anything(route: str) -> None:
    """The sales manager passes every gate it passed on the sales codes."""
    assert _opened_by(route, ROLE_PERMISSION_CODES["SALES_MANAGER"]), route


@pytest.mark.parametrize(
    ("route", "sales"),
    [
        (f"GET {_NOTES}", "SALES_VIEW"),
        (f"POST {_NOTES}", "SALES_CREATE"),
        (f"PUT {_NOTES}/{{note_id}}", "SALES_UPDATE"),
        (f"POST {_NOTES}/{{note_id}}/approve", "SALES_APPROVE"),
        (f"POST {_NOTES}/{{note_id}}/dispatch", "SALES_APPROVE"),
        (f"POST {_NOTES}/{{note_id}}/cancel", "SALES_CANCEL"),
    ],
)
def test_the_sales_code_alone_still_opens_the_route(route: str, sales: str) -> None:
    """A firm's own role built on the sales codes keeps working unchanged."""
    assert _opened_by(route, frozenset({sales}))


def test_viewing_notes_does_not_write_them() -> None:
    """`DELIVERY_NOTE_VIEW` alone raises, changes and dispatches nothing."""
    viewer = frozenset({"DELIVERY_NOTE_VIEW"})
    for route in (
        f"POST {_NOTES}",
        f"PUT {_NOTES}/{{note_id}}",
        f"POST {_NOTES}/{{note_id}}/approve",
        f"POST {_NOTES}/{{note_id}}/dispatch",
        f"POST {_NOTES}/{{note_id}}/cancel",
    ):
        assert not _opened_by(route, viewer), route


def test_dispatch_and_invoice_stays_with_the_bill_approver() -> None:
    """It raises and approves a bill, which dispatching goods does not confer."""
    route = f"POST {_NOTES}/{{note_id}}/dispatch-and-invoice"
    assert not _opened_by(route, ROLE_PERMISSION_CODES["INVENTORY_MANAGER"])
    assert not _opened_by(
        route, frozenset({"DELIVERY_NOTE_DISPATCH", "SALES_INVOICE_CREATE"})
    )
    assert _opened_by(route, ROLE_PERMISSION_CODES["SALES_MANAGER"])
    granted = ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]
    assert "SALES_INVOICE_CREATE" not in granted
    assert "SALES_APPROVE" not in granted


@pytest.mark.parametrize(
    "route",
    [
        # Orders are read, never written.
        "POST /api/v1/sales-orders",
        "PUT /api/v1/sales-orders/{order_id}",
        "POST /api/v1/sales-orders/{order_id}/approve",
        "POST /api/v1/sales-orders/{order_id}/cancel",
        "GET /api/v1/sales-orders/summary",
        "GET /api/v1/sales-orders/export",
        "GET /api/v1/sales-orders/reports/register",
        "GET /api/v1/sales-orders/reports/by-customer",
        # Quotations, bills and returns are not read at all.
        "GET /api/v1/quotations",
        "GET /api/v1/sales-invoices",
        "GET /api/v1/sales-returns",
        "POST /api/v1/sales-returns",
        # Bulk movement of notes in and out stays with the sales desk.
        f"GET {_NOTES}/export",
        f"POST {_NOTES}/import",
    ],
)
def test_the_rest_of_selling_stays_closed_to_warehouse(route: str) -> None:
    """The note codes open delivery notes and the orders behind them only."""
    assert not _opened_by(route, ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]), route


def test_search_finds_notes_for_a_dispatcher_and_not_the_orders() -> None:
    """Global search lists the screen a dispatcher is offered, and no other."""
    from uuid import uuid4

    from app.search.services.search_service import _DEFINITIONS, SearchService
    from tests.unit.test_global_search import _principal, _session_factory

    service = SearchService(_session_factory()())
    by_type = {definition.entity_type: definition for definition in _DEFINITIONS}
    dispatcher = _principal(
        uuid4(), permissions={"DELIVERY_NOTE_VIEW"}, firm_id=uuid4()
    )
    reader = _principal(uuid4(), permissions={"SALES_VIEW"}, firm_id=uuid4())

    assert service._is_accessible(by_type["delivery_notes"], dispatcher)
    assert service._is_accessible(by_type["delivery_notes"], reader)
    # The desktop offers a dispatcher no Sales Orders screen to land on.
    for entity in ("sales_orders", "sales_invoices"):
        assert not service._is_accessible(by_type[entity], dispatcher), entity
        assert service._is_accessible(by_type[entity], reader), entity


def _migration() -> object:
    """Load the migration module by path; its name starts with a digit."""
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261007_0349_delivery_note_codes.py"
    )
    spec = spec_from_file_location("delivery_note_codes_migration", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_grants_existing_databases_what_the_seed_grants() -> None:
    """Replayed over a database seeded before the codes, it matches the seed.

    Twice, because firm stores and a re-run must find nothing left to do.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.core.database.base import Base
    from app.identity.models import Permission, Role, RolePermission
    from app.identity.system_seed import seed_system_rbac

    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_system_rbac(session)
        session.flush()
        # Take the database back to before the change: no code, no grant.
        new_ids = [
            row.id
            for row in session.scalars(
                sa.select(Permission).where(Permission.code.in_(_CODES))
            )
        ]
        session.execute(
            sa.delete(RolePermission).where(RolePermission.permission_id.in_(new_ids))
        )
        session.execute(sa.delete(Permission).where(Permission.id.in_(new_ids)))
        session.commit()

    module = _migration()
    for _ in range(2):
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                module.upgrade()  # type: ignore[attr-defined]

    with Session(engine) as session:
        rows = session.execute(
            sa.select(Role.code, Permission.code)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Permission.code.in_(_CODES), RolePermission.is_deleted.is_(False))
        ).all()
    granted = sorted((role, code) for role, code in rows)
    assert len(granted) == len(set(granted)), "a grant was written twice"
    expected = sorted(
        (role, code)
        for role, codes in ROLE_PERMISSION_CODES.items()
        for code in _CODES
        if code in codes
    )
    assert granted == expected
