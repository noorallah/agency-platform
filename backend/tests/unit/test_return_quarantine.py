"""Customer returns held until checked (STK-13, §70 row 17, decision A62).

A firm that turns on *hold customer returns until checked* gets the sellable
part of every completed sales return in quarantine rather than on the shelf:
still owned and still valued, but not sold until somebody releases it. Off by
default, when returns go straight back on the shelf as before.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.batch_serial.schemas import BatchSaleSettingsWrite
from app.batch_serial.services import BatchSalePolicyService
from app.inventory.models import InventoryRecord
from app.inventory.schemas import StockQuarantineCreate
from app.inventory.services import InventoryService
from tests.unit.test_sales_return_module import _Dispatch, _session_factory


def _record(setup: _Dispatch) -> InventoryRecord:
    setup.session.expire_all()
    record = setup.session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == setup.firm.id,
            InventoryRecord.product_id == setup.product.id,
        )
    )
    assert record is not None
    return record


def _hold(setup: _Dispatch, on: bool) -> None:
    current = BatchSalePolicyService(setup.session).settings_response(setup.firm.id)
    values = current.model_dump(exclude={"is_configured"})
    values["hold_returns_for_check"] = on
    BatchSalePolicyService(setup.session).update_settings(
        BatchSaleSettingsWrite(**values),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )


def test_off_by_default_a_return_goes_back_on_the_shelf() -> None:
    setup = _Dispatch(_session_factory()())
    before = _record(setup).current_quantity

    setup.completed(quantity=Decimal("2"))

    record = _record(setup)
    assert record.current_quantity == before + Decimal("2")
    assert record.quarantine_quantity == Decimal("0")
    assert (
        BatchSalePolicyService(setup.session)
        .settings_response(setup.firm.id)
        .hold_returns_for_check
        is False
    )


def test_held_a_return_waits_in_quarantine_still_valued() -> None:
    setup = _Dispatch(_session_factory()())
    _hold(setup, True)
    before = _record(setup)
    shelf, owned = before.current_quantity, before.current_quantity

    setup.completed(quantity=Decimal("2"))

    record = _record(setup)
    assert record.current_quantity == shelf
    assert record.quarantine_quantity == Decimal("2")
    # Owned either way: the value came back with the goods.
    assert record.current_quantity + record.quarantine_quantity == owned + Decimal("2")


def test_damaged_goods_still_go_to_damaged_when_held() -> None:
    setup = _Dispatch(_session_factory()())
    _hold(setup, True)

    setup.completed(quantity=Decimal("2"), damaged=Decimal("1"))

    record = _record(setup)
    assert record.quarantine_quantity == Decimal("1")
    assert record.damaged_quantity == Decimal("1")


def test_checked_goods_are_released_onto_the_shelf() -> None:
    setup = _Dispatch(_session_factory()())
    _hold(setup, True)
    shelf = _record(setup).current_quantity
    setup.completed(quantity=Decimal("2"))

    InventoryService(setup.session).quarantine_stock(
        StockQuarantineCreate(
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            product_id=setup.product.id,
            action="RELEASE",  # type: ignore[arg-type]
            quantity=Decimal("2"),
            transaction_date=date(2026, 8, 6),
        ),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )
    setup.session.commit()

    record = _record(setup)
    assert record.current_quantity == shelf + Decimal("2")
    assert record.quarantine_quantity == Decimal("0")


def test_cancelling_a_held_return_takes_it_out_of_quarantine() -> None:
    setup = _Dispatch(_session_factory()())
    _hold(setup, True)
    shelf = _record(setup).current_quantity
    service, row = setup.completed(quantity=Decimal("2"))

    service.cancel_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="wrong"
    )

    record = _record(setup)
    assert record.current_quantity == shelf
    assert record.quarantine_quantity == Decimal("0")
