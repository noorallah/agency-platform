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
from app.core.utils.dates import business_today
from app.core.utils.pricing import resolve_supplier_free_goods
from app.finance.services.control_accounts import ControlAccountPurpose
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
from app.purchase_return.models import PurchaseReturn
from app.purchase_return.schemas import PurchaseReturnCreate
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
)
from app.supplier_schemes.api.router import list_supplier_schemes, router
from app.supplier_schemes.models import SupplierScheme
from app.supplier_schemes.schemas import SupplierSchemeCreate, SupplierSchemeUpdate
from app.supplier_schemes.services import SupplierSchemeService
from app.vendors.models import Vendor
from tests.unit.test_purchase_chain_synthesis import (
    _Firm,
    _order_with_free,
    _part_bill,
)

D = Decimal
# The firm's own day, not the UTC one (D-CFG-25): every firm here is in India.
TODAY = business_today("IN")


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


def test_an_order_line_for_nothing_is_refused_where_it_is_saved(firm: _Firm) -> None:
    """D-BUY-53: an order of 0 with nothing free saved and was approved at 0.00."""
    purchases = PurchaseService(firm.session)
    with pytest.raises(ValidationError) as refusal:
        _create(firm, _soap(firm, "10"), _soap(firm, "0"))
    assert str(refusal.value.message) == (
        "Line 2 orders a quantity of 0 and nothing free. Type a quantity, or "
        "leave the line off the order."
    )
    firm.session.rollback()
    # A typed zero for the free goods is nothing free as well.
    with pytest.raises(ValidationError, match="Line 1 orders a quantity of 0"):
        _create(firm, _soap(firm, "0", free_quantity="0"))
    firm.session.rollback()
    # The preview is not asked: the line being typed has no quantity yet.
    preview = purchases.preview_order(
        _payload(firm, _soap(firm, "0")), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert preview.order.grand_total == D("0")
    # Free goods alone are goods, and an edit is asked what a create is.
    order = _create(firm, _soap(firm, "0", free_quantity="2"))
    with pytest.raises(ValidationError, match="Line 1 orders a quantity of 0"):
        purchases.update_order(
            order.id,
            PurchaseOrderUpdate.model_validate(
                _payload(firm, _soap(firm, "0")).model_dump(
                    mode="json", exclude_unset=True
                )
            ),
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_receipt_line_for_nothing_is_refused(firm: _Firm) -> None:
    """D-BUY-53: a receipt of 0 saved and completed, moving nothing."""
    order = _create(firm, _soap(firm, "10"))
    purchases = PurchaseService(firm.session)
    purchases.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    purchases.approve_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    (line,) = _lines(firm, order)

    def received(quantity: str, free: str) -> GoodsReceiptCreate:
        return GoodsReceiptCreate.model_validate(
            {
                "purchase_order_id": order.id,
                "receipt_date": TODAY.isoformat(),
                "lines": [
                    {
                        "purchase_order_line_id": line.id,
                        "line_number": 1,
                        "current_receipt_quantity": quantity,
                        "free_quantity": free,
                    }
                ],
            }
        )

    receipts = GoodsReceiptService(firm.session)
    with pytest.raises(ValidationError) as refusal:
        receipts.create_receipt(
            received("0", "0"), firm_id=firm.firm.id, actor_id=firm.actor_id
        )
    assert str(refusal.value.message) == (
        "Line 1 receives a quantity of 0 and nothing free. Type a quantity, or "
        "leave the line off the receipt."
    )
    firm.session.rollback()
    kept = receipts.create_receipt(
        received("4", "0"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert kept.status == "DRAFT"


def _received_with_free(firm: _Firm, bought: str, free: str) -> GoodsReceiptLine:
    """Order, approve and receive ``bought`` at 100 each with ``free`` free."""
    order = _create(firm, _soap(firm, bought, free_quantity=free, unit_price="100"))
    purchases = PurchaseService(firm.session)
    purchases.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    purchases.approve_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    (line,) = _lines(firm, order)
    receipts = GoodsReceiptService(firm.session)
    receipt = receipts.create_receipt(
        GoodsReceiptCreate.model_validate(
            {
                "purchase_order_id": order.id,
                "receipt_date": TODAY.isoformat(),
                "lines": [
                    {
                        "purchase_order_line_id": line.id,
                        "line_number": 1,
                        "current_receipt_quantity": bought,
                        "free_quantity": free,
                        "unit_price": "100",
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    return firm.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()


def _return(
    firm: _Firm, line: GoodsReceiptLine, quantity: str, **fields: object
) -> PurchaseReturn:
    """Save a return of ``quantity`` off the receipt line."""
    source = {
        "source_document_type": "GOODS_RECEIPT",
        "source_document_id": line.goods_receipt_id,
    }
    return PurchaseReturnService(firm.session).create_return(
        PurchaseReturnCreate.model_validate(
            {
                "return_date": TODAY.isoformat(),
                "warehouse_id": line.warehouse_id,
                "source_documents": [source],
                "lines": [
                    {
                        **source,
                        "source_document_line_id": line.id,
                        "line_number": 1,
                        "current_return_quantity": quantity,
                        "warehouse_id": line.warehouse_id,
                        **fields,
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _send_back(firm: _Firm, row: PurchaseReturn) -> None:
    returns = PurchaseReturnService(firm.session)
    returns.approve_return(row.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    returns.complete_return(row.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)


def test_what_was_received_can_go_back_free_goods_included(firm: _Firm) -> None:
    """D-BUY-56: 10 bought and 2 free came in; at most 10 could go back.

    The charged units are taken first and credited; the free ones go back
    beside them and are credited nothing.
    """
    line = _received_with_free(firm, "10", "2")
    assert firm.stock() == D("12")
    with pytest.raises(ValidationError) as refusal:
        _return(firm, line, "13")
    assert str(refusal.value.message) == (
        "Return quantity exceeds the available source quantity: line 1 can "
        "still send back 10 bought and 2 free."
    )
    firm.session.rollback()

    whole = _return(firm, line, "12")
    returns = PurchaseReturnService(firm.session)
    (sent,) = returns.return_response(whole).lines
    assert (sent.current_return_quantity, sent.free_quantity) == (D("12"), D("2"))
    # Ten at 100: the two free units are worth nothing to the supplier.
    assert sent.gross_amount == D("1000.0000")
    _send_back(firm, whole)
    assert firm.stock() == D("0")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == 0
    # Nothing was billed, so the receipt's accrual is what comes off, and the
    # stock left at the cost the receipt spread over all twelve: no variance.
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0

    # Nothing is left to send, bought or free; cancelling gives both back.
    with pytest.raises(ValidationError, match="0 bought and 0 free"):
        _return(firm, line, "1")
    firm.session.rollback()
    returns.cancel_return(
        whole.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="Kept"
    )
    assert firm.stock() == D("12")
    assert _return(firm, line, "12").status == "DRAFT"


def test_a_free_carton_goes_back_on_its_own_and_credits_nothing(firm: _Firm) -> None:
    """D-BUY-56: the line says how many of what goes back are free."""
    line = _received_with_free(firm, "10", "2")
    accrued = firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED)
    with pytest.raises(ValidationError, match="cannot exceed it"):
        _return(firm, line, "1", free_quantity="2")
    firm.session.rollback()

    carton = _return(firm, line, "1", free_quantity="1")
    returns = PurchaseReturnService(firm.session)
    (sent,) = returns.return_response(carton).lines
    assert (sent.current_return_quantity, sent.free_quantity) == (D("1"), D("1"))
    assert (sent.gross_amount, sent.net_amount) == (D("0"), D("0"))
    _send_back(firm, carton)
    assert firm.stock() == D("11")
    # No payable and no accrual moves: the supplier is owed nothing for it.
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == accrued
    # It leaves stock at the cost the receipt gave each of the twelve.
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("916.67")
    # All ten bought are still returnable, and one free; not two.
    with pytest.raises(ValidationError, match="10 bought and 1 free"):
        _return(firm, line, "2", free_quantity="2")
    firm.session.rollback()
    rest = returns.return_response(_return(firm, line, "11")).lines[0]
    assert (rest.current_return_quantity, rest.free_quantity) == (D("11"), D("1"))
    assert rest.gross_amount == D("1000.0000")


def test_a_line_of_free_goods_alone_can_be_returned(firm: _Firm) -> None:
    """D-BUY-56: a free-only receipt line could never be returned."""
    line = _received_with_free(firm, "0", "2")
    assert firm.stock() == D("2")
    one = _return(firm, line, "1")
    (sent,) = PurchaseReturnService(firm.session).return_response(one).lines
    assert (sent.current_return_quantity, sent.free_quantity) == (D("1"), D("1"))
    _send_back(firm, one)
    assert firm.stock() == D("1")
    with pytest.raises(ValidationError, match="0 bought and 1 free"):
        _return(firm, line, "2")


def test_free_units_typed_as_nothing_bought_go_back_as_free(firm: _Firm) -> None:
    """D-PRC-51: quantity 0 with 1 free, off a line that was all free.

    Refused as "a quantity of 0" while the same unit typed as a quantity of 1
    went back. It leaves stock at the cost it is carried at, which goes to
    purchase price variance -- the goods came in at nil cost -- and nothing
    is claimed from the supplier: no payable, no debit note value.
    """
    bought = _received_with_free(firm, "12", "0")
    line = _received_with_free(firm, "0", "1")
    # Thirteen on the shelf for 1,200.00: 92.31 a piece.
    assert firm.stock() == D("13")
    accrued = firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED)

    one = _return(firm, line, "0", free_quantity="1")

    returns = PurchaseReturnService(firm.session)
    (sent,) = returns.return_response(one).lines
    assert (sent.current_return_quantity, sent.free_quantity) == (D("1"), D("1"))
    assert (sent.gross_amount, sent.net_amount) == (D("0"), D("0"))
    assert one.grand_total == D("0")
    _send_back(firm, one)
    assert firm.stock() == D("12")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("1107.69")
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == D("92.31")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == accrued

    # No more free units than the line has left, and none off a line with none.
    with pytest.raises(ValidationError, match="0 bought and 0 free"):
        _return(firm, line, "0", free_quantity="1")
    firm.session.rollback()
    with pytest.raises(ValidationError, match="12 bought and 0 free"):
        _return(firm, bought, "0", free_quantity="1")
    firm.session.rollback()
    # Nothing bought and nothing free is still a line for nothing.
    with pytest.raises(ValidationError) as nothing:
        _return(firm, bought, "0", free_quantity="0")
    assert str(nothing.value.message) == (
        "Line 1 returns a quantity of 0 and nothing free. Type a quantity, or "
        "leave the line off the return."
    )
    firm.session.rollback()
    # A line of bought units is priced and credited as it always was.
    paid = returns.return_response(_return(firm, bought, "1")).lines[0]
    assert (paid.current_return_quantity, paid.free_quantity) == (D("1"), D("0"))
    assert paid.gross_amount == D("100.0000")


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


def test_scheme_free_goods_come_in_once_over_part_bills_with_receipts_off(
    firm: _Firm,
) -> None:
    # D-PRC-90: buy 12 get 1 on an order of 24, billed 12 and 12 with the
    # receipt stage off, put 4 free on the shelf: each part took both.
    _scheme(firm, buy="12", free="1", valid_from=date(2026, 8, 1), valid_to=None)
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(
        firm,
        {"product_id": firm.product.id, "ordered_quantity": "24", "unit_price": "60"},
    )
    assert line.free_quantity == D("2")

    first = _part_bill(firm, order, (line, "12", {}))
    assert (first.total_free_quantity, firm.stock()) == (D("1"), D("13"))
    second = _part_bill(firm, order, (line, "12", {}))
    assert (second.total_free_quantity, firm.stock()) == (D("1"), D("26"))
    free_lines = firm.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.free_quantity > 0)
    ).all()
    assert {row.scheme_name for row in free_lines} == {line.scheme_name}
