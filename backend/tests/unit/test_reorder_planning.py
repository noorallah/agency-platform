"""Reorder on what sold, not only on typed levels (backlog 69 row 12, A39).

A firm planning on SALES gets a level for every product nobody typed one for:
net sales over the window as a daily rate, reordered when available stock
falls to the rate times lead time plus safety days, and ordered up to that
plus the cover days. A typed level always wins.
"""

# ruff: noqa: D103

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.inventory.services import InventoryService
from app.products.models import Product
from app.purchase.api.router import ReorderPlanningWrite
from app.purchase.services.reorder import PlanningSettings, ReorderService
from tests.unit.test_reorder_suggestions import _Shop

pytestmark = pytest.mark.typed_document_numbers

TODAY = utc_now().date()


def _sold(
    shop: _Shop, product: Product, *, received: str, sold: str, days_ago: int = 10
) -> None:
    """Receive stock long ago, then dispatch some of it ``days_ago``."""
    inventory = InventoryService(shop.session)
    actor = uuid4()
    inventory.record_goods_receipt(
        firm_scope=shop.firm.id,
        actor_id=actor,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number=f"GRN-{product.code}",
        transaction_date=TODAY - timedelta(days=200),
        total_quantity=Decimal(received),
        unit_cost=Decimal("10"),
    )
    inventory.record_delivery_note_dispatch(
        firm_scope=shop.firm.id,
        actor_id=actor,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number=f"DN-{product.code}-{days_ago}",
        transaction_date=TODAY - timedelta(days=days_ago),
        dispatch_quantity=Decimal(sold),
    )
    shop.session.commit()


def _on_sales(shop: _Shop) -> None:
    """Plan the firm on sales with the defaults: 90, 7, 7 and 30 days."""
    ReorderService(shop.session).save_planning(
        shop.firm.id, PlanningSettings(basis="SALES"), actor_id=uuid4()
    )


def test_a_firm_with_no_settings_plans_on_typed_levels() -> None:
    shop = _Shop()
    product = shop.other_product()
    _sold(shop, product, received="100", sold="90")

    service = ReorderService(shop.session)
    assert service.planning(shop.firm.id) == PlanningSettings()
    assert service.below_reorder(shop.firm.id) == [], "sales alone list nothing"


def test_on_sales_a_product_is_ordered_up_to_a_months_cover() -> None:
    """90 sold in 90 days is one a day: reorder at 14, order up to 44."""
    shop = _Shop()
    product = shop.other_product()
    _sold(shop, product, received="100", sold="90")
    _on_sales(shop)

    rows = ReorderService(shop.session).below_reorder(shop.firm.id)

    [row] = [row for row in rows if row.product_id == product.id]
    assert row.basis == "SALES"
    assert row.average_daily_sales == Decimal("1.0000")
    assert row.available_quantity == Decimal("10.0000")
    assert row.reorder_level == Decimal("14.0000")
    assert row.maximum_level == Decimal("44.0000")
    assert row.suggested_quantity == Decimal("34.0000")


def test_returns_count_against_demand_and_old_sales_do_not_count() -> None:
    """Nine come back and an old sale is outside the window: not due yet."""
    shop = _Shop()
    product = shop.other_product()
    _sold(shop, product, received="100", sold="90")
    InventoryService(shop.session).record_sales_return(
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number="SR-1",
        transaction_date=TODAY - timedelta(days=5),
        return_quantity=Decimal("9"),
        restock_quantity=Decimal("9"),
    )
    shop.session.commit()
    _on_sales(shop)

    rows = ReorderService(shop.session).below_reorder(shop.firm.id)

    # 81 kept is 0.9 a day: the point is 12.6 and 19 are on the shelf.
    assert [row for row in rows if row.product_id == product.id] == []


def test_a_derived_suggestion_rounds_up_to_whole_units() -> None:
    """100 sold in 90 days orders 37, not 36.4444."""
    shop = _Shop()
    product = shop.other_product()
    _sold(shop, product, received="112", sold="100")
    _on_sales(shop)

    [row] = [
        row
        for row in ReorderService(shop.session).below_reorder(shop.firm.id)
        if row.product_id == product.id
    ]

    # 1.1111 a day: up to 48.8889, less the 12 on the shelf.
    assert row.suggested_quantity == Decimal("37.0000")


def test_a_typed_level_wins_over_the_derived_one() -> None:
    shop = _Shop()
    product = shop.other_product()
    _sold(shop, product, received="100", sold="90")
    shop.stock(product, available="0", reorder="50", maximum="60", locator="B-1")
    _on_sales(shop)

    [row] = [
        row
        for row in ReorderService(shop.session).below_reorder(shop.firm.id)
        if row.product_id == product.id
    ]

    assert row.basis == "LEVEL"
    assert row.reorder_level == Decimal("50")
    assert row.suggested_quantity == Decimal("50.0000")


def test_saving_the_planning_is_audited_and_checked() -> None:
    shop = _Shop()
    service = ReorderService(shop.session)

    saved = service.save_planning(
        shop.firm.id,
        PlanningSettings(basis="SALES", lead_time_days=3, cover_days=15),
        actor_id=uuid4(),
    )

    assert saved.is_configured
    assert (saved.basis, saved.lead_time_days, saved.cover_days) == ("SALES", 3, 15)
    trail = shop.session.scalars(
        select(AuditLog).where(AuditLog.action == "purchase.reorder_planning_updated")
    ).all()
    assert len(trail) == 1
    with pytest.raises(ValidationError, match="1 to 365 days"):
        service.save_planning(
            shop.firm.id, PlanningSettings(cover_days=0), actor_id=uuid4()
        )
    with pytest.raises(SchemaError):
        ReorderPlanningWrite(
            basis="SALES",
            sales_window_days=3,
            lead_time_days=7,
            safety_days=7,
            cover_days=30,
        )
