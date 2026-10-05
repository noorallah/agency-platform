"""Purchase requisitions (BUY-7, decision A109).

A storeman asks for ten widgets (the supplier is the product's preferred one)
and five gadgets from a second supplier. Submitted and approved, it converts
into two draft orders, one per supplier, and is then ORDERED. A line with no
supplier anywhere is refused by name; a draft cannot be converted; and the
reorder screen raises a requisition rather than an order.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.products.models import Product
from app.purchase.api.router import (
    create_purchase_requisition,
    get_purchase_requisition,
    list_purchase_requisitions,
    update_purchase_requisition,
)
from app.purchase.api.router import router as purchase_router
from app.purchase.schemas.requisition import PurchaseRequisitionWrite
from app.purchase.services.requisitions import PurchaseRequisitionService
from app.vendors.models import Vendor
from tests.unit.test_purchase_chain_synthesis import _Firm
from tests.unit.test_purchase_invoice_module import takes_if_match

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm whose widget names its supplier as preferred."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="REQSN")
    built.product.preferred_vendor_id = built.vendor.id
    built.session.commit()
    return built


def _gadget(firm: _Firm) -> Product:
    row = Product(
        firm_id=firm.firm.id,
        code="GADGET",
        name="Gadget",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        purchase_price=D("40"),
    )
    firm.session.add(row)
    firm.session.commit()
    return row


def _second_supplier(firm: _Firm) -> Vendor:
    row = Vendor(
        firm_id=firm.firm.id,
        code="SUP-TWO",
        name="Second supplier",
        display_name="Second supplier",
        status="ACTIVE",
    )
    firm.session.add(row)
    firm.session.commit()
    return row


def _raise(firm: _Firm, lines: list[dict[str, object]]) -> object:
    return PurchaseRequisitionService(firm.session).create(
        PurchaseRequisitionWrite.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "requisition_date": "2026-08-02",
                "needed_by": "2026-08-20",
                "lines": lines,
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_an_approved_requisition_becomes_one_order_per_supplier(firm: _Firm) -> None:
    gadget = _gadget(firm)
    other = _second_supplier(firm)
    requisition = _raise(
        firm,
        [
            {"product_id": firm.product.id, "quantity": "10"},
            {"product_id": gadget.id, "quantity": "5", "vendor_id": other.id},
        ],
    )
    service = PurchaseRequisitionService(firm.session)
    # Its own prefix, not the purchase return's PR (D-BUY-46).
    assert requisition.requisition_number.startswith("PRQ-")  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="Only an approved"):
        service.convert_to_orders(
            requisition.id,  # type: ignore[attr-defined]
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    service.submit(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]
    service.approve(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]
    orders = service.convert_to_orders(
        requisition.id,  # type: ignore[attr-defined]
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert sorted(o.vendor_id for o in orders) == sorted([firm.vendor.id, other.id])
    assert all(o.status == "DRAFT" for o in orders)
    assert all(o.expected_delivery_date == date(2026, 8, 20) for o in orders)
    (response,) = service.responses(
        [service.get(requisition.id, firm_id=firm.firm.id)]  # type: ignore[attr-defined]
    )
    assert response.status == "ORDERED"
    assert all(line.purchase_order_id for line in response.lines)


def test_a_line_with_no_supplier_is_refused_by_name(firm: _Firm) -> None:
    gadget = _gadget(firm)
    requisition = _raise(firm, [{"product_id": gadget.id, "quantity": "5"}])
    service = PurchaseRequisitionService(firm.session)
    service.submit(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]
    service.approve(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="Name a supplier for GADGET"):
        service.convert_to_orders(
            requisition.id,  # type: ignore[attr-defined]
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_the_reorder_screen_raises_a_requisition() -> None:
    from app.purchase.services.reorder import ReorderPick, ReorderService
    from tests.unit.test_reorder_suggestions import _Shop

    shop = _Shop()
    shop.stock(shop.product, available="2", reorder="5", maximum="20")
    (requisition,) = ReorderService(shop.session).raise_requisitions(
        shop.firm.id,
        [ReorderPick(warehouse_id=shop.warehouse.id, product_id=shop.product.id)],
        actor_id=shop.vendor.id,
    )
    (response,) = PurchaseRequisitionService(shop.session).responses([requisition])
    assert response.status == "DRAFT"
    assert response.lines[0].quantity == D("18.0000")


def _typed(firm: _Firm, quantity: str) -> PurchaseRequisitionWrite:
    return PurchaseRequisitionWrite.model_validate(
        {
            "branch_id": firm.branch.id,
            "warehouse_id": firm.warehouse.id,
            "requisition_date": "2026-08-02",
            "lines": [{"product_id": firm.product.id, "quantity": quantity}],
        }
    )


def test_a_requisition_publishes_its_version_and_refuses_a_stale_save(
    firm: _Firm,
) -> None:
    """D-BUY-54: the desktop already sent ``If-Match``; the server read none."""
    scope = SimpleNamespace(firm_id=firm.firm.id, actor_id=firm.actor_id)
    made = Response()
    created = create_purchase_requisition(
        data=_typed(firm, "2"), scope=scope, response=made, db=firm.session  # type: ignore[arg-type]
    ).data
    assert created is not None
    assert made.headers["ETag"] == f'"{created.version}"'
    read = Response()
    opened = get_purchase_requisition(
        requisition_id=created.id, scope=scope, response=read, db=firm.session  # type: ignore[arg-type]
    ).data
    assert opened is not None
    assert read.headers["ETag"] == f'"{opened.version}"'

    # Somebody else saves first.
    theirs = Response()
    saved = update_purchase_requisition(
        requisition_id=created.id,
        data=_typed(firm, "3").model_copy(update={"remarks": "Theirs"}),
        scope=scope,  # type: ignore[arg-type]
        response=theirs,
        db=firm.session,
        expected_version=opened.version,
    ).data
    assert saved is not None
    assert saved.version > opened.version
    assert theirs.headers["ETag"] == f'"{saved.version}"'
    with pytest.raises(ConflictError, match="changed since you loaded it"):
        update_purchase_requisition(
            requisition_id=created.id,
            data=_typed(firm, "4"),
            scope=scope,  # type: ignore[arg-type]
            response=Response(),
            db=firm.session,
            expected_version=opened.version,
        )
    # The precondition is opt-in: a client that sends none still saves.
    update_purchase_requisition(
        requisition_id=created.id,
        data=_typed(firm, "4"),
        scope=scope,  # type: ignore[arg-type]
        response=Response(),
        db=firm.session,
    )
    assert takes_if_match(purchase_router, "PUT", "/requisitions/{requisition_id}")


def test_the_requisition_list_is_paged(firm: _Firm) -> None:
    """D-BUY-54: the list took no page and returned every row."""
    scope = SimpleNamespace(firm_id=firm.firm.id, actor_id=firm.actor_id)
    for quantity in ("1", "2", "3"):
        _raise(firm, [{"product_id": firm.product.id, "quantity": quantity}])
    first = list_purchase_requisitions(
        scope=scope,  # type: ignore[arg-type]
        page=1,
        page_size=2,
        status_filter=None,
        db=firm.session,
    )
    assert len(first.data) == 2
    assert first.pagination.total_records == 3
    assert first.pagination.total_pages == 2
    second = list_purchase_requisitions(
        scope=scope,  # type: ignore[arg-type]
        page=2,
        page_size=2,
        status_filter=None,
        db=firm.session,
    )
    assert len(second.data) == 1
    numbers = [row.requisition_number for row in first.data + second.data]
    assert numbers == sorted(numbers, reverse=True)
    none = list_purchase_requisitions(
        scope=scope,  # type: ignore[arg-type]
        page=1,
        page_size=2,
        status_filter="APPROVED",
        db=firm.session,
    )
    assert none.data == [] and none.pagination.total_records == 0


def test_a_line_names_only_a_supplier_of_this_firm(firm: _Firm) -> None:
    """D-BUY-55: a stranger answered 409 off the foreign key, unexplained."""
    stranger = uuid4()
    with pytest.raises(ValidationError) as refusal:
        _raise(
            firm,
            [{"product_id": firm.product.id, "quantity": "1", "vendor_id": stranger}],
        )
    assert str(refusal.value.message) == f"Unknown supplier(s): {stranger}."
    firm.session.rollback()
    # Another firm's supplier in the same store is a stranger too.
    theirs = _second_supplier(firm)
    theirs.firm_id = uuid4()
    firm.session.commit()
    with pytest.raises(ValidationError, match="Unknown supplier"):
        _raise(
            firm,
            [{"product_id": firm.product.id, "quantity": "1", "vendor_id": theirs.id}],
        )
    firm.session.rollback()
    kept = _raise(
        firm,
        [{"product_id": firm.product.id, "quantity": "1", "vendor_id": firm.vendor.id}],
    )
    assert kept.status == "DRAFT"  # type: ignore[attr-defined]
