"""Supplier free-goods schemes filled into purchase orders (PG-11, 86 #25, #27).

The supplier runs "10+2" on soap, and "a bucket free with every 10 shampoo".
An order of 25 soap takes 4 free by itself; an order of 20 shampoo is offered
a line of 2 buckets, which the buyer adds and the order keeps. A free-only
line (paid 0, free n) prices at nothing and flows to the receipt and the bill.
"""

# ruff: noqa: D103

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.utils.dates import utc_now
from app.core.utils.pricing import resolve_supplier_free_goods
from app.goods_receipt.models import GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseOrderUpdate
from app.purchase.services import PurchaseService
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services.purchase_invoice_service import (
    PurchaseInvoiceService,
)
from app.supplier_schemes.api.router import list_supplier_schemes, router
from app.supplier_schemes.models import SupplierScheme
from app.supplier_schemes.schemas import SupplierSchemeCreate, SupplierSchemeUpdate
from app.supplier_schemes.services import SupplierSchemeService
from app.vendors.models import Vendor
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
TODAY = utc_now().date()


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with a supplier, soap at 90 and a bucket at 50."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="SS01")
    bucket = Product(
        firm_id=built.firm.id,
        code="BUCKET",
        name="Bucket",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        purchase_price=D("50"),
    )
    built.session.add(bucket)
    built.session.commit()
    built.bucket = bucket  # type: ignore[attr-defined]
    return built


def _bucket(firm: _Firm) -> Product:
    bucket: Product = firm.bucket  # type: ignore[attr-defined]
    return bucket


def _scheme(
    firm: _Firm,
    *,
    vendor: bool = True,
    buy: str = "10",
    free: str = "2",
    free_product: UUID | None = None,
    valid_from: date = TODAY - timedelta(days=5),
    valid_to: date | None = TODAY + timedelta(days=30),
) -> SupplierScheme:
    payload: dict[str, object] = {
        "product_id": firm.product.id,
        "buy_quantity": buy,
        "free_quantity": free,
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat() if valid_to else None,
    }
    if vendor:
        payload["vendor_id"] = firm.vendor.id
    if free_product is not None:
        payload["free_product_id"] = free_product
    return SupplierSchemeService(firm.session).create(
        SupplierSchemeCreate.model_validate(payload),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _payload(
    firm: _Firm, *lines: dict[str, object], on: date = TODAY
) -> Any:  # noqa: ANN401
    return PurchaseOrderCreate.model_validate(
        {
            "branch_id": firm.branch.id,
            "warehouse_id": firm.warehouse.id,
            "vendor_id": firm.vendor.id,
            "purchase_date": on.isoformat(),
            "lines": list(lines),
        }
    )


def _soap(firm: _Firm, quantity: str = "25", **extra: object) -> dict[str, object]:
    return {"product_id": firm.product.id, "ordered_quantity": quantity, **extra}


def _lines(firm: _Firm, order: PurchaseOrder) -> list[PurchaseOrderLine]:
    return list(
        firm.session.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .order_by(PurchaseOrderLine.line_number)
        ).all()
    )


def _create(firm: _Firm, *lines: dict[str, object], on: date = TODAY) -> PurchaseOrder:
    return PurchaseService(firm.session).create_order(
        _payload(firm, *lines, on=on), firm_id=firm.firm.id, actor_id=firm.actor_id
    )


def test_the_free_quantity_is_resolved_in_the_pricing_module() -> None:
    def resolve(typed: Decimal | None, quantity: str) -> Decimal:
        return resolve_supplier_free_goods(
            typed=typed,
            quantity=D(quantity),
            buy_quantity=D("10"),
            scheme_free_quantity=D("2"),
        ).free_quantity

    assert resolve(None, "25") == D("4")
    assert resolve(None, "9") == D("0")
    assert resolve(D("0"), "25") == D("0")
    assert resolve(D("5"), "25") == D("5")
    other = resolve_supplier_free_goods(
        typed=None,
        quantity=D("20"),
        buy_quantity=D("10"),
        scheme_free_quantity=D("1"),
        same_product=False,
    )
    assert (other.free_quantity, other.other_product_quantity) == (D("0"), D("2"))


def test_a_same_product_scheme_fills_the_free_quantity(firm: _Firm) -> None:
    scheme = _scheme(firm)
    (line,) = _lines(firm, _create(firm, _soap(firm, "25")))
    assert line.free_quantity == D("4")
    assert (line.scheme_id, line.scheme_name) == (scheme.id, "10+2")
    # Free goods cost nothing: the line is worth what was paid for.
    assert line.gross_amount == D("2250")
    # The response carries it for the editor's "scheme applied".
    response = PurchaseService(firm.session).order_response(
        firm.session.get(PurchaseOrder, line.purchase_order_id)  # type: ignore[arg-type]
    )
    assert response.lines[0].scheme_name == "10+2"


def test_an_explicit_zero_refuses_the_scheme_and_a_typed_figure_stands(
    firm: _Firm,
) -> None:
    _scheme(firm)
    (refused,) = _lines(firm, _create(firm, _soap(firm, "25", free_quantity="0")))
    assert (refused.free_quantity, refused.scheme_id) == (D("0"), None)
    (typed,) = _lines(firm, _create(firm, _soap(firm, "25", free_quantity="3")))
    assert (typed.free_quantity, typed.scheme_id) == (D("3"), None)
    # The scheme's own figure echoed back on a re-save keeps the scheme.
    order = _create(firm, _soap(firm, "25"))
    PurchaseService(firm.session).update_order(
        order.id,
        PurchaseOrderUpdate.model_validate(
            _payload(firm, _soap(firm, "25", free_quantity="4")).model_dump(
                exclude={"po_number"}
            )
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    (echoed,) = _lines(firm, order)
    assert echoed.free_quantity == D("4")
    assert echoed.scheme_id is not None


def test_dates_are_respected(firm: _Firm) -> None:
    _scheme(
        firm,
        valid_from=TODAY + timedelta(days=10),
        valid_to=TODAY + timedelta(days=20),
    )
    (before,) = _lines(firm, _create(firm, _soap(firm, "25")))
    assert (before.free_quantity, before.scheme_id) == (D("0"), None)
    (inside,) = _lines(
        firm, _create(firm, _soap(firm, "25"), on=TODAY + timedelta(days=15))
    )
    assert inside.free_quantity == D("4")
    (after,) = _lines(
        firm, _create(firm, _soap(firm, "25"), on=TODAY + timedelta(days=21))
    )
    assert after.free_quantity == D("0")


def test_a_suppliers_own_scheme_beats_one_for_every_supplier(firm: _Firm) -> None:
    everyone = _scheme(firm, vendor=False, buy="5", free="1")
    (line,) = _lines(firm, _create(firm, _soap(firm, "25")))
    assert (line.free_quantity, line.scheme_id) == (D("5"), everyone.id)
    own = _scheme(firm, vendor=True)
    (line,) = _lines(firm, _create(firm, _soap(firm, "25")))
    assert (line.free_quantity, line.scheme_id) == (D("4"), own.id)
    # Another supplier still takes the all-suppliers scheme.
    other = Vendor(
        firm_id=firm.firm.id,
        code="VEN-OTHER",
        name="Other",
        display_name="Other",
        status="ACTIVE",
    )
    firm.session.add(other)
    firm.session.commit()
    payload = _payload(firm, _soap(firm, "25")).model_copy(
        update={"vendor_id": other.id}
    )
    order = PurchaseService(firm.session).create_order(
        payload, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert _lines(firm, order)[0].scheme_id == everyone.id


def test_an_overlapping_active_scheme_is_refused(firm: _Firm) -> None:
    first = _scheme(firm, valid_to=None)
    with pytest.raises(ValidationError, match="already runs"):
        _scheme(firm, valid_from=TODAY + timedelta(days=100), valid_to=None)
    # The all-suppliers scheme is counted separately, and does not clash.
    _scheme(firm, vendor=False)
    # Ending the first makes room after it.
    service = SupplierSchemeService(firm.session)
    service.update(
        first.id,
        SupplierSchemeUpdate(valid_to=TODAY + timedelta(days=50)),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    later = _scheme(firm, valid_from=TODAY + timedelta(days=51), valid_to=None)
    # Switching a scheme off is an edit; it no longer clashes nor applies.
    service.update(
        later.id,
        SupplierSchemeUpdate(is_active=False),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    _scheme(firm, valid_from=TODAY + timedelta(days=60), valid_to=None)
    actions = set(
        firm.session.scalars(
            select(AuditLog.action).where(AuditLog.entity_type == "supplier_scheme")
        ).all()
    )
    assert {"supplier_scheme.created", "supplier_scheme.updated"} <= actions
    with pytest.raises(ValidationError, match="cannot end before"):
        service.update(
            first.id,
            SupplierSchemeUpdate(valid_to=TODAY - timedelta(days=60)),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_an_update_leaves_out_what_it_does_not_name(firm: _Firm) -> None:
    scheme = _scheme(firm)
    SupplierSchemeService(firm.session).update(
        scheme.id,
        SupplierSchemeUpdate.model_validate({"notes": "Diwali"}),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert (scheme.buy_quantity, scheme.free_quantity, scheme.vendor_id) == (
        D("10"),
        D("2"),
        firm.vendor.id,
    )
    with pytest.raises(ValidationError, match="cannot be blank"):
        SupplierSchemeService(firm.session).update(
            scheme.id,
            SupplierSchemeUpdate.model_validate({"buy_quantity": None}),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_another_products_scheme_is_suggested_and_the_gift_line_is_kept(
    firm: _Firm,
) -> None:
    bucket = _bucket(firm)
    scheme = _scheme(firm, free="1", free_product=bucket.id)
    service = PurchaseService(firm.session)
    preview = service.preview_order(
        _payload(firm, _soap(firm, "20")),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    # Nothing free on the soap line itself; a bucket line is offered.
    assert preview.order.lines[0].free_quantity == D("0")
    (suggestion,) = preview.scheme_suggestions
    assert (
        suggestion.line_number,
        suggestion.scheme_id,
        suggestion.free_product_id,
        suggestion.free_quantity,
        suggestion.free_product_name,
        suggestion.existing_line_number,
    ) == (1, scheme.id, bucket.id, D("2"), "Bucket", None)
    assert suggestion.scheme_label == "10 + 1 Bucket"
    # Saving never invents the line ...
    assert len(_lines(firm, _create(firm, _soap(firm, "20")))) == 1
    # ... the client adds it, and the order keeps it, marked with the scheme.
    gift = {
        "product_id": bucket.id,
        "ordered_quantity": "0",
        "free_quantity": str(suggestion.free_quantity),
        "scheme_id": str(suggestion.scheme_id),
    }
    order = _create(firm, _soap(firm, "20"), gift)
    soap_line, bucket_line = _lines(firm, order)
    assert (bucket_line.ordered_quantity, bucket_line.free_quantity) == (
        D("0"),
        D("2"),
    )
    assert (bucket_line.scheme_id, bucket_line.scheme_name) == (
        scheme.id,
        "10 + 1 Bucket",
    )
    assert (bucket_line.net_amount, soap_line.free_quantity) == (D("0"), D("0"))
    # The preview of an order already carrying it says which line it is.
    again = service.preview_order(
        _payload(firm, _soap(firm, "30"), gift),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    (suggestion,) = again.scheme_suggestions
    assert (suggestion.existing_line_number, suggestion.free_quantity) == (2, D("3"))
    # A line naming a scheme that does not give its product is refused.
    with pytest.raises(ValidationError, match="does not give"):
        _create(firm, {**gift, "product_id": firm.product.id})


def test_a_free_only_line_prices_at_nothing(firm: _Firm) -> None:
    preview = PurchaseService(firm.session).preview_order(
        _payload(
            firm,
            _soap(firm, "10"),
            {
                "product_id": _bucket(firm).id,
                "ordered_quantity": "0",
                "free_quantity": "2",
            },
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    paid, free_only = preview.order.lines
    assert (free_only.gross_amount, free_only.tax_amount, free_only.net_amount) == (
        D("0"),
        D("0"),
        D("0"),
    )
    assert free_only.base_quantity == D("2")
    assert preview.order.grand_total == paid.net_amount
    assert preview.quantity_hints == []


def test_a_free_only_line_flows_to_the_receipt_and_the_bill(firm: _Firm) -> None:
    scheme = _scheme(firm, free="1", free_product=_bucket(firm).id)
    order = _create(
        firm,
        _soap(firm, "10"),
        {
            "product_id": _bucket(firm).id,
            "ordered_quantity": "0",
            "free_quantity": "1",
            "scheme_id": str(scheme.id),
        },
    )
    purchases = PurchaseService(firm.session)
    purchases.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    purchases.approve_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    soap_line, bucket_line = _lines(firm, order)
    receipts = GoodsReceiptService(firm.session)
    receipt = receipts.create_receipt(
        GoodsReceiptCreate.model_validate(
            {
                "purchase_order_id": order.id,
                "receipt_date": TODAY.isoformat(),
                "lines": [
                    {
                        "purchase_order_line_id": soap_line.id,
                        "line_number": 1,
                        "current_receipt_quantity": "10",
                    },
                    {
                        "purchase_order_line_id": bucket_line.id,
                        "line_number": 2,
                        "current_receipt_quantity": "0",
                        "free_quantity": str(bucket_line.free_quantity),
                    },
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    receipt_lines = list(
        firm.session.scalars(
            select(GoodsReceiptLine)
            .where(GoodsReceiptLine.goods_receipt_id == receipt.id)
            .order_by(GoodsReceiptLine.line_number)
        ).all()
    )
    # The receipt keeps the free-only line and inherits the scheme's label.
    assert (receipt_lines[1].free_quantity, receipt_lines[1].net_amount) == (
        D("1"),
        D("0"),
    )
    assert receipt_lines[1].scheme_name == "10 + 1 Bucket"
    # Its goods arriving receives the line: it used to read ORDERED for ever,
    # so the order was never complete (86 #27).
    response = purchases.order_response(order)
    assert [line.status for line in response.lines] == ["RECEIVED", "RECEIVED"]
    bills = PurchaseInvoiceService(firm.session)
    bill = bills.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "supplier_invoice_number": "SUP-77",
                "supplier_invoice_date": TODAY.isoformat(),
                "invoice_date": TODAY.isoformat(),
                "source_documents": [
                    {
                        "source_document_type": "GOODS_RECEIPT",
                        "source_document_id": receipt.id,
                    }
                ],
                "lines": [
                    {
                        "source_document_type": "GOODS_RECEIPT",
                        "source_document_id": receipt.id,
                        "source_document_line_id": receipt_line.id,
                        "line_number": number,
                        "current_invoice_quantity": quantity,
                    }
                    for number, (receipt_line, quantity) in enumerate(
                        zip(receipt_lines, ("10", "0"), strict=True), start=1
                    )
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    billed = bills.invoice_response(bill)
    assert billed.lines[1].net_amount == D("0")
    assert billed.grand_total == soap_line.net_amount
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    final = purchases.order_response(order)
    assert (final.billing_status, final.is_complete) == ("INVOICED", True)


def _codes(route: APIRoute) -> set[str]:
    """Return every permission code a route's dependencies enforce."""
    found: set[str] = set()
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        code = getattr(dependency.call, "permission_code", None)
        if code:
            found.add(code)
        pending.extend(dependency.dependencies)
    return found


def test_permissions() -> None:
    routes = {
        (method, route.path): _codes(route)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    base = "/api/v1/supplier-schemes"
    assert routes[("GET", base)] == {"SUPPLIER_SCHEME_VIEW"}
    assert routes[("GET", base + "/{scheme_id}")] == {"SUPPLIER_SCHEME_VIEW"}
    assert routes[("POST", base)] == {"SUPPLIER_SCHEME_MANAGE"}
    assert routes[("PUT", base + "/{scheme_id}")] == {"SUPPLIER_SCHEME_MANAGE"}
    assert routes[("DELETE", base + "/{scheme_id}")] == {"SUPPLIER_SCHEME_MANAGE"}
    for role in ("PURCHASE_EXECUTIVE", "PURCHASE_MANAGER", "FIRM_ADMIN"):
        assert {"SUPPLIER_SCHEME_VIEW", "SUPPLIER_SCHEME_MANAGE"} <= (
            ROLE_PERMISSION_CODES[role]
        ), role
    for role in ("ACCOUNTANT", "SALES_MANAGER"):
        assert "SUPPLIER_SCHEME_MANAGE" not in ROLE_PERMISSION_CODES[role], role


def _scope(firm_id: UUID) -> ResolvedFirmScope:
    user_id = uuid.uuid4()
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _page_statements(firm: _Firm, extra: int) -> int:
    for number in range(extra):
        product = Product(
            firm_id=firm.firm.id,
            code=f"P-{extra}-{number}",
            name=f"Item {number}",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        firm.session.add(product)
        firm.session.commit()
        SupplierSchemeService(firm.session).create(
            SupplierSchemeCreate(
                vendor_id=firm.vendor.id,
                product_id=product.id,
                buy_quantity=D("10"),
                free_quantity=D("1"),
                free_product_id=_bucket(firm).id,
                valid_from=TODAY,
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.expunge_all()
    with _counting(firm.session) as seen:
        page = list_supplier_schemes(
            scope=_scope(firm.firm.id),
            page=1,
            page_size=50,
            vendor_id=firm.vendor.id,
            product_id=None,
            all_suppliers=None,
            is_active=None,
            db=firm.session,
        )
    assert page.data
    return len(seen)


def test_the_list_costs_the_same_at_any_length(firm: _Firm) -> None:
    small = _page_statements(firm, 3)
    large = _page_statements(firm, 9)
    assert large <= small, f"{small} statements at 3 rows, {large} at 12"
