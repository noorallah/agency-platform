"""A role that may raise a document may read the masters it is typed from.

D-ROLE-1, found live on 2026-10-04. The Purchasing job (`PURCHASE_EXECUTIVE`)
holds `PURCHASE_CREATE` and opened a purchase order to be told "An order needs
a vendor to buy from and a product to buy": the server refused it
`GET /vendors`, `/products`, `/branches` and `/warehouses`, because the master
view codes are enforced and were never granted to the job roles whose editors
read them. The same gap ran through the sales, stock and billing roles.

`test_every_role_can_open_something.py` could not see it: it asks whether a
role can open *a* screen, not whether it can finish its own document. This asks
the second question per document. `_DOCUMENTS` names, for each document, the
route that creates it, the codes that create it, and the master lists its
desktop editor loads to fill its pickers (the management page's lookups --
`purchase_management_page.dart` `_loadLookups` for the purchase order, and so
on). Every seeded role holding one of the create codes must hold the view code
of every list named.

Both halves of the table are checked against the application, not trusted: the
create route must enforce one of the codes listed for it, and each list route
must enforce the code listed for it. A route that changes its gate fails here
rather than quietly making the table wrong.

`CASHIER` is deliberately absent: Receipts and Payments read their own party
list (`GET /receipts/parties`, `/payments/parties`), so
recording money needs no customer or vendor master (plan step 22.4).
"""

from collections.abc import Iterable, Iterator
from functools import lru_cache

import pytest
from fastapi.routing import APIRoute

from app.identity.system_seed import ROLE_PERMISSION_CODES

#: The master lists a document editor loads, and the code each one enforces.
_LISTS: dict[str, tuple[str, str]] = {
    "vendors": ("GET /api/v1/vendors", "VENDOR_VIEW"),
    "customers": ("GET /api/v1/customers", "CUSTOMER_VIEW"),
    "products": ("GET /api/v1/products", "PRODUCT_VIEW"),
    "branches": ("GET /api/v1/branches", "BRANCH_VIEW"),
    "warehouses": ("GET /api/v1/warehouses", "WAREHOUSE_VIEW"),
    "storage nodes": (
        "GET /api/v1/warehouses/{warehouse_id}/storage-nodes",
        "WAREHOUSE_VIEW",
    ),
    "tax profiles": ("GET /api/v1/tax-framework/profiles", "TAX_VIEW"),
    "units": ("GET /api/v1/uom-framework/uoms", "UOM_VIEW"),
}

_PURCHASE_LINES = ("products", "tax profiles", "units")

#: (document, create route, codes that create it, lists its editor loads).
#:
#: The sales order and invoice name the narrow `SALES_ORDER_CREATE` and
#: `SALES_INVOICE_CREATE` beside `SALES_CREATE`, which is what their routes
#: enforce: `SALES_EXECUTIVE` and `BILLING_EXECUTIVE` hold the narrow codes
#: because raising those documents is their job, and they must be able to
#: read what the editor offers when the route lets them.
_DOCUMENTS: tuple[tuple[str, str, frozenset[str], tuple[str, ...]], ...] = (
    (
        "purchase order",
        "POST /api/v1/purchases",
        frozenset({"PURCHASE_CREATE"}),
        ("vendors", "branches", "warehouses", "storage nodes", *_PURCHASE_LINES),
    ),
    (
        "goods receipt",
        "POST /api/v1/goods-receipts",
        # D-ROLE-3: receiving has its own code, which Warehouse holds too.
        frozenset({"PURCHASE_RECEIVE"}),
        ("warehouses", *_PURCHASE_LINES),
    ),
    (
        "purchase invoice",
        "POST /api/v1/purchase-invoices",
        frozenset({"PURCHASE_CREATE"}),
        ("vendors", *_PURCHASE_LINES),
    ),
    (
        "purchase return",
        "POST /api/v1/purchase-returns",
        frozenset({"PURCHASE_CREATE"}),
        _PURCHASE_LINES,
    ),
    (
        "purchase requisition",
        "POST /api/v1/purchases/requisitions",
        frozenset({"PURCHASE_REQUISITION_CREATE"}),
        ("branches", "warehouses", "vendors", "products"),
    ),
    (
        "quotation",
        "POST /api/v1/quotations",
        frozenset({"SALES_QUOTATION_CREATE"}),
        ("customers", "products", "branches", "warehouses"),
    ),
    (
        "sales order",
        "POST /api/v1/sales-orders",
        frozenset({"SALES_CREATE", "SALES_ORDER_CREATE"}),
        ("customers", "products", "branches", "warehouses"),
    ),
    (
        "delivery note",
        "POST /api/v1/delivery-notes",
        frozenset({"SALES_CREATE"}),
        ("warehouses", "products", "tax profiles", "units"),
    ),
    (
        "sales invoice",
        "POST /api/v1/sales-invoices",
        frozenset({"SALES_CREATE", "SALES_INVOICE_CREATE"}),
        ("customers", "products"),
    ),
    (
        "sales return",
        "POST /api/v1/sales-returns",
        frozenset({"SALES_RETURN"}),
        ("warehouses",),
    ),
    (
        "stock adjustment",
        "POST /api/v1/inventory/adjustments",
        frozenset({"INVENTORY_ADJUST"}),
        ("branches", "warehouses", "storage nodes", "products"),
    ),
    (
        # A write-off as a free gift must name the customer it went to.
        "stock write-off",
        "POST /api/v1/inventory/write-offs",
        frozenset({"INVENTORY_ADJUST"}),
        ("customers",),
    ),
    (
        "stock transfer",
        "POST /api/v1/inventory/stock-transfers",
        frozenset({"INVENTORY_ADJUST"}),
        ("products", "warehouses"),
    ),
)


def _walk(route: APIRoute) -> Iterator[str]:
    """Yield every permission code the route's dependency tree records."""
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        code = getattr(dependency.call, "permission_code", None)
        if code:
            yield code
        pending.extend(dependency.dependencies)


def _endpoints(routes: Iterable[object]) -> Iterator[object]:
    """Yield the leaf endpoints of a built application.

    An included router sits in `app.routes` as a wrapper carrying only
    `original_router`, so the walk descends through it (see
    `test_document_framework.py::_endpoints`).
    """
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
def _enforced() -> dict[str, frozenset[str]]:
    """Map `METHOD path` to the codes the built application enforces on it."""
    from app.main import create_app

    enforced: dict[str, set[str]] = {}
    for route in _endpoints(create_app().routes):
        if not isinstance(route, APIRoute):
            continue
        codes = set(_walk(route))
        for method in route.methods:
            enforced.setdefault(f"{method} {route.path}", set()).update(codes)
    return {key: frozenset(codes) for key, codes in enforced.items()}


@pytest.mark.parametrize("name", sorted(_LISTS))
def test_each_master_list_enforces_the_code_named_for_it(name: str) -> None:
    """The table's view codes are what the list routes really demand."""
    route, code = _LISTS[name]
    assert route in _enforced(), f"{route} is not a route"
    assert code in _enforced()[route], (
        f"{route} enforces {sorted(_enforced()[route])}, not {code}: " "update `_LISTS`"
    )


@pytest.mark.parametrize(
    ("document", "route", "codes"),
    [(doc, route, codes) for doc, route, codes, _ in _DOCUMENTS],
)
def test_each_document_is_created_under_a_code_named_for_it(
    document: str, route: str, codes: frozenset[str]
) -> None:
    """The table's create codes include what the create route demands."""
    assert route in _enforced(), f"{route} ({document}) is not a route"
    assert (
        codes & _enforced()[route]
    ), f"{route} enforces {sorted(_enforced()[route])}, none of {sorted(codes)}"


@pytest.mark.parametrize(
    ("document", "codes", "lists"),
    [(doc, codes, lists) for doc, _, codes, lists in _DOCUMENTS],
)
def test_whoever_raises_a_document_reads_its_masters(
    document: str, codes: frozenset[str], lists: tuple[str, ...]
) -> None:
    """Every seeded role holding a create code holds each list's view code."""
    missing = {
        role: sorted(
            f"{_LISTS[name][1]} ({_LISTS[name][0]})"
            for name in lists
            if _LISTS[name][1] not in granted
        )
        for role, granted in ROLE_PERMISSION_CODES.items()
        if codes & granted
    }
    missing = {role: gaps for role, gaps in missing.items() if gaps}
    assert not missing, (
        f"these roles may raise a {document} and cannot read what its editor "
        f"picks from: {missing}"
    )


def test_the_purchase_manager_owns_the_vendor_masters_but_not_where_money_goes() -> (
    None
):
    """The template's promise, kept short of a payment instruction."""
    granted = ROLE_PERMISSION_CODES["PURCHASE_MANAGER"]
    assert {"VENDOR_CREATE", "VENDOR_UPDATE", "VENDOR_MANAGE_CATEGORIES"} <= granted
    assert "VENDOR_MANAGE_BANK_DETAILS" not in granted
    assert "VENDOR_VIEW_FINANCIAL_DETAILS" not in granted
    assert (
        "VENDOR_MANAGE_BANK_DETAILS" not in ROLE_PERMISSION_CODES["PURCHASE_EXECUTIVE"]
    )


#: The masters every document view names (`DocumentLineLabels.load` in
#: `desktop/lib/ui/document_framework/document_line_labels.dart`): each line's
#: product, unit and tax profile, and the header's branch and warehouse.
_VIEW_LABELS = ("products", "units", "tax profiles", "branches", "warehouses")

#: The codes that open a purchase or sales document view.
_DOCUMENT_VIEW_CODES = frozenset({"PURCHASE_VIEW", "PURCHASE_RECEIVE", "SALES_VIEW"})


def test_whoever_opens_a_document_can_read_the_names_it_shows() -> None:
    """D-ROLE-4: a view a role may open never falls back to ids.

    Counter Sales opened a sales invoice and saw the branch and the tax
    profile as ids, because D-ROLE-1 derived the grants from the editors and
    the views read more.
    """
    missing = {
        role: sorted(
            _LISTS[name][1] for name in _VIEW_LABELS if _LISTS[name][1] not in granted
        )
        for role, granted in ROLE_PERMISSION_CODES.items()
        if _DOCUMENT_VIEW_CODES & granted
    }
    missing = {role: gaps for role, gaps in missing.items() if gaps}
    assert (
        not missing
    ), f"these roles open documents whose names they cannot read: {missing}"
