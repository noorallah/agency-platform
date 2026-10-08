"""Home's stock alerts and the batch card count the same near-expiry batches.

The alerts counted a batch by what was on the shelf over the firm's own
window; the card counted shelf, quarantine, damaged and blocked over a fixed
30 days. A batch held only in quarantine, or a firm whose window is not 30,
read differently on the two (D-STK-47).
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from app.batch_serial.schemas.batch_serial import BatchCreate, BatchSaleSettingsWrite
from app.batch_serial.services import BatchSerialService
from app.batch_serial.services.batch_sale_policy import BatchSalePolicyService
from app.core.utils.dates import business_today
from app.inventory.models import InventoryRecord
from app.inventory.services.stock_alerts import stock_alerts
from tests.unit.test_batch_serial_expiry import (
    _branch,
    _firm,
    _product,
    _session_factory,
    _warehouse,
)


def test_a_quarantined_batch_inside_the_firms_window_is_on_both() -> None:
    """Forty-five days out, a 60-day window, nothing on the shelf."""
    session = _session_factory()()
    firm = _firm(session, "NEAR1")
    product = _product(session, firm.id)
    actor_id = uuid4()
    warehouse = _warehouse(session, firm.id, _branch(session, firm.id).id)
    today = business_today("IN")
    BatchSalePolicyService(session).update_settings(
        BatchSaleSettingsWrite(
            near_expiry_days=60,
            near_expiry_policy="WARN",
            fefo_skip_policy="RECORD",
            near_expiry_below_floor=True,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service = BatchSerialService(session)
    batch = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="HELD",
            expiry_date=today + timedelta(days=45),
        ),
    )
    session.add(
        InventoryRecord(
            firm_id=firm.id,
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            storage_locator="MAIN",
            product_id=product.id,
            batch_id=batch.id,
            current_quantity=Decimal("0"),
            available_quantity=Decimal("0"),
            quarantine_quantity=Decimal("4"),
        )
    )
    session.commit()

    alerts = stock_alerts(session, firm.id, on=today)
    summary = service.batch_summary(firm_scope=firm.id)

    assert alerts.near_expiry == 1
    assert summary.near_expiry == 1
    near = next(row for row in alerts.rows if row.kind == "NEAR_EXPIRY")
    assert near.quantity == Decimal("4.0000")
    # The dashboard's card is named for its 30 days and keeps them.
    assert service.expiry_dashboard(firm_scope=firm.id).expire_in_30_days == 0
