"""A supplier's lead time, used and measured (BUY-6, decision A105).

The supplier quotes five days for widgets. A new order with no expected date
is expected five days after it; a typed date stands. A receipt three days
after an order expected in two counts as late, and the summary sets the
quote beside what was delivered. The sales-based reorder point uses the
supplier's five days, not the firm's seven.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.goods_receipt.models import GoodsReceipt
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.vendors.schemas.supplier_product import SupplierProductWrite
from app.vendors.services.lead_times import lead_time_summary
from app.vendors.services.supplier_catalogue import SupplierCatalogueService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm whose supplier quotes five days for widgets."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="LEADT")
    SupplierCatalogueService(built.session).add(
        built.vendor.id,
        SupplierProductWrite(
            product_id=built.product.id,
            lead_time_days=5,
            effective_from=date(2026, 4, 1),
        ),
        firm_id=built.firm.id,
        actor_id=built.actor_id,
    )
    return built


def _order(firm: _Firm, expected: str | None = None) -> object:
    payload: dict[str, object] = {
        "branch_id": firm.branch.id,
        "warehouse_id": firm.warehouse.id,
        "vendor_id": firm.vendor.id,
        "purchase_date": "2026-08-02",
        "lines": [
            {"product_id": firm.product.id, "ordered_quantity": "10", "unit_price": "1"}
        ],
    }
    if expected:
        payload["expected_delivery_date"] = expected
    return PurchaseService(firm.session).create_order(
        PurchaseOrderCreate.model_validate(payload),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_the_expected_date_fills_from_the_lead_time(firm: _Firm) -> None:
    assert _order(firm).expected_delivery_date == date(2026, 8, 7)  # type: ignore[attr-defined]
    typed = _order(firm, expected="2026-08-20")
    assert typed.expected_delivery_date == date(2026, 8, 20)  # type: ignore[attr-defined]


def test_the_summary_sets_the_quote_beside_the_deliveries(firm: _Firm) -> None:
    firm.stages(order=False, receipt=False)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill("10"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    receipt = firm.session.scalar(select(GoodsReceipt))
    assert receipt is not None
    # Ordered three days before it arrived, and expected after two.
    order = receipt.purchase_order_id
    from app.purchase.models import PurchaseOrder

    row = firm.session.get(PurchaseOrder, order)
    assert row is not None
    row.purchase_date = receipt.receipt_date - timedelta(days=3)
    row.expected_delivery_date = receipt.receipt_date - timedelta(days=1)
    firm.session.commit()

    summary = lead_time_summary(
        firm.session, firm_id=firm.firm.id, vendor_id=firm.vendor.id
    )
    assert summary.quoted_days == 5
    assert summary.receipts == 1
    assert summary.average_days == D("3.0")
    assert summary.late_receipts == 1
    assert summary.on_time_percent == D("0.0")


def test_the_reorder_point_uses_the_suppliers_lead_time() -> None:
    from app.purchase.services.reorder import ReorderService
    from tests.unit.test_reorder_suggestions import _Shop

    shop = _Shop()
    service = ReorderService(shop.session)
    terms = service._supplier_lead_times(shop.firm.id, {shop.product.id})
    assert terms == {}
    SupplierCatalogueService(shop.session).add(
        shop.vendor.id,
        SupplierProductWrite(
            product_id=shop.product.id,
            lead_time_days=5,
            effective_from=date(2026, 4, 1),
        ),
        firm_id=shop.firm.id,
        actor_id=shop.vendor.id,
    )
    assert service._supplier_lead_times(shop.firm.id, {shop.product.id}) == {
        shop.product.id: 5
    }
