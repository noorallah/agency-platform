"""Stock held for an order that never ships lapses (STK-12, decision A115).

The shop's order, dated 2026-09-16, holds eight. With no rule nothing lapses.
With seven days, a pass on the 24th releases the hold and flags the order --
still approved -- and reserving again holds the stock once more.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.inventory.models import InventoryRecord
from app.sales_order.schemas import SalesWorkflowSettingsWrite
from app.sales_order.services import SalesOrderService
from app.sales_order.services.reservation_lapse import lapse_firm
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from tests.unit.test_batch_picker import _Shop

D = Decimal


def _reserved(shop: _Shop) -> Decimal:
    total = shop.session.scalar(
        select(func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0)).where(
            InventoryRecord.product_id == shop.product.id
        )
    )
    return D(str(total))


def test_a_hold_lapses_after_the_firms_days_and_can_be_taken_again() -> None:
    shop = _Shop()
    assert _reserved(shop) == D("8")
    assert lapse_firm(shop.session, shop.firm_id, on=date(2026, 12, 1)) == 0

    SalesWorkflowService(shop.session).update_settings(
        SalesWorkflowSettingsWrite(
            quotation_stage=True,
            sales_order_stage=True,
            delivery_note_stage=True,
            reservation_lapse_days=7,
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    assert lapse_firm(shop.session, shop.firm_id, on=date(2026, 9, 20)) == 0
    assert lapse_firm(shop.session, shop.firm_id, on=date(2026, 9, 24)) == 1
    shop.session.refresh(shop.order)
    assert shop.order.reservation_lapsed_at is not None
    assert shop.order.status == "APPROVED"
    assert _reserved(shop) == D("0")
    # Already lapsed: a second pass leaves it alone.
    assert lapse_firm(shop.session, shop.firm_id, on=date(2026, 9, 30)) == 0

    service = SalesOrderService(shop.session)
    again = service.reserve_again(
        shop.order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )
    assert again.reservation_lapsed_at is None
    assert _reserved(shop) == D("8")
    with pytest.raises(ValidationError, match="has not lapsed"):
        service.reserve_again(
            shop.order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
        )
