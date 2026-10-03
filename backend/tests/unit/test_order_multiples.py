"""A supplier's minimum order and order multiple (BUY-5, decision A103).

The supplier takes widgets from 100 in twenties. 115 suggests 120 and 40
suggests 100. By default the order is saved and the preview carries the
suggestion; a firm that refuses has the order refused, naming the line. An
order a supplier bill raises is never refused, and the reorder planner rounds
its own suggestion up to the supplier's terms.
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
from app.purchase.schemas import PurchaseOrderCreate, PurchaseWorkflowSettingsWrite
from app.purchase.services import PurchaseService
from app.purchase.services.reorder import ReorderService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.vendors.schemas.supplier_product import SupplierProductWrite
from app.vendors.services.order_quantities import rounded_quantity
from app.vendors.services.supplier_catalogue import SupplierCatalogueService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store, its supplier selling in 20s."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="MULTI")
    SupplierCatalogueService(built.session).add(
        built.vendor.id,
        SupplierProductWrite(
            product_id=built.product.id,
            minimum_order_quantity=D("100"),
            order_multiple=D("20"),
            effective_from=date(2026, 4, 1),
        ),
        firm_id=built.firm.id,
        actor_id=built.actor_id,
    )
    return built


def _payload(firm: _Firm, quantity: str) -> PurchaseOrderCreate:
    return PurchaseOrderCreate.model_validate(
        {
            "branch_id": firm.branch.id,
            "warehouse_id": firm.warehouse.id,
            "vendor_id": firm.vendor.id,
            "purchase_date": "2026-08-02",
            "lines": [
                {
                    "product_id": firm.product.id,
                    "ordered_quantity": quantity,
                    "unit_price": "10",
                }
            ],
        }
    )


def _refuse(firm: _Firm) -> None:
    PurchaseWorkflowService(firm.session).update_settings(
        PurchaseWorkflowSettingsWrite(
            purchase_order_stage=True,
            goods_receipt_stage=False,
            order_quantity_policy="REFUSE",
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_rounding() -> None:
    assert rounded_quantity(D("115"), minimum=D("100"), multiple=D("20")) == D("120")
    assert rounded_quantity(D("40"), minimum=D("100"), multiple=D("20")) == D("100")
    assert rounded_quantity(D("120"), minimum=D("100"), multiple=D("20")) == D("120")
    assert rounded_quantity(D("7"), minimum=None, multiple=None) == D("7")


def test_a_warning_firm_saves_and_the_preview_suggests(firm: _Firm) -> None:
    service = PurchaseService(firm.session)
    preview = service.preview_order(
        _payload(firm, "115"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    (hint,) = preview.quantity_hints
    assert hint.suggested_quantity == D("120")
    assert "120 would do" in hint.message
    order = service.create_order(
        _payload(firm, "115"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert order.status == "DRAFT"


def test_a_refusing_firm_refuses_but_not_a_raised_order(firm: _Firm) -> None:
    _refuse(firm)
    service = PurchaseService(firm.session)
    with pytest.raises(ValidationError, match="line 1: 115"):
        service.create_order(
            _payload(firm, "115"), firm_id=firm.firm.id, actor_id=firm.actor_id
        )
    firm.session.rollback()
    assert service.create_order(
        _payload(firm, "120"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    # A bill of 7 from a firm that types no orders raises its own order of 7.
    firm.stages(order=False, receipt=False)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill("7"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    approved = bills.approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    assert approved.status == "APPROVED"


def test_the_reorder_suggestion_rounds_to_the_terms() -> None:
    from tests.unit.test_reorder_suggestions import _Shop

    shop = _Shop()
    SupplierCatalogueService(shop.session).add(
        shop.vendor.id,
        SupplierProductWrite(
            product_id=shop.product.id,
            minimum_order_quantity=D("10"),
            order_multiple=D("6"),
            effective_from=date(2026, 4, 1),
        ),
        firm_id=shop.firm.id,
        actor_id=shop.vendor.id,
    )
    shop.stock(shop.product, available="3", reorder="5", maximum="20")
    [row] = ReorderService(shop.session).below_reorder(shop.firm.id)
    # 17 short; at least 10 in sixes is 18.
    assert row.suggested_quantity == D("18.0000")
