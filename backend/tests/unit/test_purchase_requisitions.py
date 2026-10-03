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

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.products.models import Product
from app.purchase.schemas.requisition import PurchaseRequisitionWrite
from app.purchase.services.requisitions import PurchaseRequisitionService
from app.vendors.models import Vendor
from tests.unit.test_purchase_chain_synthesis import _Firm

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
    assert requisition.requisition_number.startswith("PR")  # type: ignore[attr-defined]
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
