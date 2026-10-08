"""Stock transfer as a document (STK-1, decision A126).

Ten units are held at 100 each in the main warehouse. A transfer of four is
drafted, dispatched -- off the main shelf, in transit at the depot, still the
firm's at 400 -- and received with one damaged and one short: two on the
depot's shelf to sell, one blocked, and 100 written off as a shortage.
Cancelling a dispatched transfer brings the goods home.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models.batch_serial import BatchRecord
from app.branches.models.branch_warehouse import Warehouse
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.models import InventoryRecord
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.stock_transfers import (
    StockTransferDispatch,
    StockTransferReceive,
    StockTransferService,
    StockTransferWrite,
)
from app.inventory.services.stock_valuation import StockValuationService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
ON = date(2026, 8, 12)


@pytest.fixture
def firm() -> _Firm:
    """Build a firm holding ten units at 100, with a second warehouse."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="XFER")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    depot = Warehouse(
        firm_id=built.firm.id,
        branch_id=built.branch.id,
        code="WH-DEPOT",
        name="Depot",
        display_name="Depot",
        status="ACTIVE",
        is_default=False,
    )
    built.session.add(depot)
    built.session.commit()
    built.depot = depot  # type: ignore[attr-defined]
    return built


def _record(firm: _Firm, warehouse_id: object) -> InventoryRecord:
    row = firm.session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.product_id == firm.product.id,
            InventoryRecord.warehouse_id == warehouse_id,
        )
    )
    assert row is not None
    return row


def _draft(firm: _Firm, quantity: str = "4", batch_id: object = None) -> object:
    line: dict[str, object] = {"product_id": firm.product.id, "quantity": quantity}
    if batch_id is not None:
        line["batch_id"] = batch_id
    return StockTransferService(firm.session).create(
        StockTransferWrite(
            transfer_date=ON,
            from_warehouse_id=firm.warehouse.id,
            to_warehouse_id=firm.depot.id,  # type: ignore[attr-defined]
            vehicle_number="KA01AB1234",
            lines=[line],  # type: ignore[list-item]
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _valued(firm: _Firm, warehouse_id: object | None = None) -> Decimal:
    rows = StockValuationService(firm.session).valuation(
        firm.firm.id, on=date(2026, 12, 31), warehouse_id=warehouse_id
    )
    return sum(
        (
            row.quantity or D("0")
            for row in rows
            if row.product_code == firm.product.code
        ),
        D("0"),
    )


def test_a_transfer_travels_in_two_steps_and_writes_off_the_shortage(
    firm: _Firm,
) -> None:
    service = StockTransferService(firm.session)
    transfer = _draft(firm)
    assert transfer.status == "DRAFT"  # type: ignore[attr-defined]
    assert transfer.transfer_number.startswith("TO")  # type: ignore[attr-defined]
    assert _record(firm, firm.warehouse.id).current_quantity == D("10")

    service.dispatch(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert transfer.status == "DISPATCHED"  # type: ignore[attr-defined]
    assert transfer.dispatched_value == D("400")  # type: ignore[attr-defined]
    assert _record(firm, firm.warehouse.id).current_quantity == D("6")
    depot = _record(firm, firm.depot.id)  # type: ignore[attr-defined]
    assert (depot.current_quantity, depot.in_transit_quantity) == (D("0"), D("4"))
    # Still owned, still on the books, and shown against where it is going.
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("1000")
    assert _valued(firm) == D("10")
    assert _valued(firm, firm.depot.id) == D("4")  # type: ignore[attr-defined]

    service.receive(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferReceive.model_validate(
            {
                "lines": [
                    {
                        "line_number": 1,
                        "received_quantity": "3",
                        "damaged_quantity": "1",
                    }
                ]
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert transfer.status == "RECEIVED"  # type: ignore[attr-defined]
    assert transfer.shortage_value == D("100")  # type: ignore[attr-defined]
    depot = _record(firm, firm.depot.id)  # type: ignore[attr-defined]
    assert (
        depot.current_quantity,
        depot.in_transit_quantity,
        depot.damaged_quantity,
        depot.available_quantity,
    ) == (D("3"), D("0"), D("1"), D("2"))
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("900")
    assert firm.balance(ControlAccountPurpose.INVENTORY_ADJUSTMENT) == D("100")
    assert _valued(firm) == D("9")
    assert _valued(firm, firm.depot.id) == D("3")  # type: ignore[attr-defined]
    (view,) = service.responses([transfer])  # type: ignore[list-item]
    assert (view.lines[0].received_quantity, view.lines[0].short_quantity) == (
        D("3"),
        D("1"),
    )

    with pytest.raises(ValidationError, match="final"):
        service.cancel(
            transfer.id,  # type: ignore[attr-defined]
            "Too late",
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_receiving_without_lines_takes_everything_in(firm: _Firm) -> None:
    service = StockTransferService(firm.session)
    transfer = _draft(firm)
    service.dispatch(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.receive(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferReceive(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    depot = _record(firm, firm.depot.id)  # type: ignore[attr-defined]
    assert (depot.current_quantity, depot.available_quantity) == (D("4"), D("4"))
    assert transfer.shortage_value == D("0")  # type: ignore[attr-defined]
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("1000")


def test_cancelling_a_dispatched_transfer_brings_the_goods_home(
    firm: _Firm,
) -> None:
    service = StockTransferService(firm.session)
    transfer = _draft(firm)
    service.dispatch(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.cancel(
        transfer.id,  # type: ignore[attr-defined]
        "Truck broke down",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert transfer.status == "CANCELLED"  # type: ignore[attr-defined]
    assert _record(firm, firm.warehouse.id).current_quantity == D("10")
    depot = _record(firm, firm.depot.id)  # type: ignore[attr-defined]
    assert depot.in_transit_quantity == D("0")
    assert _valued(firm) == D("10")
    assert _valued(firm, firm.depot.id) == D("0")  # type: ignore[attr-defined]
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("1000")


def test_a_transfer_cannot_send_more_than_is_free(firm: _Firm) -> None:
    transfer = _draft(firm, quantity="11")
    with pytest.raises(ValidationError, match="cannot be sent"):
        StockTransferService(firm.session).dispatch(
            transfer.id,  # type: ignore[attr-defined]
            StockTransferDispatch(),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_more_cannot_arrive_than_was_sent(firm: _Firm) -> None:
    service = StockTransferService(firm.session)
    transfer = _draft(firm)
    service.dispatch(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    with pytest.raises(ValidationError, match="cannot have arrived"):
        service.receive(
            transfer.id,  # type: ignore[attr-defined]
            StockTransferReceive.model_validate(
                {"lines": [{"line_number": 1, "received_quantity": "5"}]}
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_batch_travels_as_itself(firm: _Firm) -> None:
    batch = BatchRecord(
        firm_id=firm.firm.id,
        product_id=firm.product.id,
        batch_number="B-2405",
        status="AVAILABLE",
    )
    firm.session.add(batch)
    firm.session.flush()
    InventoryService(firm.session).record_goods_receipt(
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        branch_id=firm.branch.id,
        warehouse_id=firm.warehouse.id,
        storage_node_id=None,
        product_id=firm.product.id,
        reference_number="GRN-B",
        transaction_date=ON,
        total_quantity=D("5"),
        unit_cost=D("100"),
        batch_id=batch.id,
    )
    firm.session.commit()
    service = StockTransferService(firm.session)
    transfer = _draft(firm, quantity="2", batch_id=batch.id)
    service.dispatch(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.receive(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferReceive(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    arrived = firm.session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.warehouse_id == firm.depot.id,  # type: ignore[attr-defined]
            InventoryRecord.batch_id == batch.id,
        )
    )
    assert arrived is not None and arrived.current_quantity == D("2")
    (view,) = service.responses([transfer])  # type: ignore[list-item]
    assert view.lines[0].batch_number == "B-2405"


def test_only_a_draft_changes_and_the_challan_waits_for_dispatch(
    firm: _Firm,
) -> None:
    service = StockTransferService(firm.session)
    transfer = _draft(firm)
    with pytest.raises(ValidationError, match="once the goods are dispatched"):
        service.render_challan(
            transfer.id, firm_id=firm.firm.id  # type: ignore[attr-defined]
        )
    service.dispatch(
        transfer.id,  # type: ignore[attr-defined]
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    pdf, name = service.render_challan(
        transfer.id, firm_id=firm.firm.id  # type: ignore[attr-defined]
    )
    assert pdf.startswith(b"%PDF") and name.endswith(".pdf")
    with pytest.raises(ValidationError, match="Only a draft"):
        service.update(
            transfer.id,  # type: ignore[attr-defined]
            StockTransferWrite(
                transfer_date=ON,
                from_warehouse_id=firm.warehouse.id,
                to_warehouse_id=firm.depot.id,  # type: ignore[attr-defined]
                lines=[{"product_id": firm.product.id, "quantity": "1"}],  # type: ignore[list-item]
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_an_edit_of_the_lines_alone_moves_the_version(firm: _Firm) -> None:
    """D-STK-42: a stale copy of a draft whose lines changed is refused."""
    service = StockTransferService(firm.session)
    transfer = _draft(firm)
    seen = transfer.version  # type: ignore[attr-defined]

    def save(quantity: str) -> object:
        return service.update(
            transfer.id,  # type: ignore[attr-defined]
            StockTransferWrite(
                transfer_date=ON,
                from_warehouse_id=firm.warehouse.id,
                to_warehouse_id=firm.depot.id,  # type: ignore[attr-defined]
                vehicle_number="KA01AB1234",
                lines=[{"product_id": firm.product.id, "quantity": quantity}],  # type: ignore[list-item]
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
            expected_version=seen,
        )

    assert save("2").version > seen  # type: ignore[attr-defined]
    with pytest.raises(ConflictError):
        save("3")
    assert [line.quantity for line in service.lines(transfer.id)] == [  # type: ignore[attr-defined]
        Decimal("2")
    ]


def test_a_transfer_goes_somewhere_else() -> None:
    same = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(SchemaError, match="different warehouse"):
        StockTransferWrite.model_validate(
            {
                "transfer_date": "2026-08-12",
                "from_warehouse_id": same,
                "to_warehouse_id": same,
                "lines": [
                    {
                        "product_id": "00000000-0000-0000-0000-000000000003",
                        "quantity": "1",
                    }
                ],
            }
        )
