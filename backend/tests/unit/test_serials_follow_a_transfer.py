"""A serial number goes where its goods go (D-STK-40, backlog 90 gap 1).

A serial records the warehouse its unit is in, and a dispatch refuses a unit
that is not in the warehouse the line ships from. Neither transfer moved it,
so serial-numbered goods sent to the depot could not be shipped from the
depot. Ten phones sit in the main warehouse, each with its number:

* the one-step transfer names the units it moves and lands them at the depot;
* the transfer document picks them as a draft, holds them IN_TRANSIT, and at
  the receipt lands the good ones AVAILABLE and the damaged one DAMAGED at
  the depot, and marks the one that never came LOST;
* an opening stock line types its units, and posting creates them.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models.batch_serial import DocumentLineSerial, SerialNumber
from app.batch_serial.services.serial_history import serial_trail
from app.branches.models.branch_warehouse import Warehouse
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.inventory.schemas import (
    OpeningStockBatchCreate,
    OpeningStockUpdate,
    StockTransferCreate,
)
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.stock_transfers import (
    StockTransferDispatch,
    StockTransferReceive,
    StockTransferService,
    StockTransferWrite,
)
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
ON = date(2026, 8, 12)


@pytest.fixture
def firm() -> _Firm:
    """Build a firm holding ten numbered phones, with a second warehouse."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="SNXF")
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
    built.product.track_serial = True
    for number in range(1, 11):
        built.session.add(
            SerialNumber(
                firm_id=built.firm.id,
                product_id=built.product.id,
                warehouse_id=built.warehouse.id,
                branch_id=built.branch.id,
                serial_number=f"PH{number:03d}",
                status="AVAILABLE",
            )
        )
    built.session.commit()
    built.depot = depot  # type: ignore[attr-defined]
    return built


def _units(firm: _Firm, *numbers: str) -> list[UUID]:
    rows = {
        row.serial_number: row.id
        for row in firm.session.scalars(
            select(SerialNumber).where(SerialNumber.firm_id == firm.firm.id)
        ).all()
    }
    return [rows[number] for number in numbers]


def _unit(firm: _Firm, number: str) -> SerialNumber:
    row = firm.session.scalar(
        select(SerialNumber).where(
            SerialNumber.serial_number == number, SerialNumber.is_deleted.is_(False)
        )
    )
    assert row is not None
    return row


def _move(firm: _Firm, quantity: str, serial_ids: list[UUID]) -> None:
    InventoryService(firm.session).transfer_stock(
        StockTransferCreate(
            branch_id=firm.branch.id,
            from_warehouse_id=firm.warehouse.id,
            to_warehouse_id=firm.depot.id,  # type: ignore[attr-defined]
            product_id=firm.product.id,
            quantity=D(quantity),
            transaction_date=ON,
            serial_ids=serial_ids,
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _draft(firm: _Firm, quantity: str, serial_ids: list[UUID]) -> UUID:
    row = StockTransferService(firm.session).create(
        StockTransferWrite.model_validate(
            {
                "transfer_date": ON,
                "from_warehouse_id": firm.warehouse.id,
                "to_warehouse_id": firm.depot.id,  # type: ignore[attr-defined]
                "lines": [
                    {
                        "product_id": firm.product.id,
                        "quantity": quantity,
                        "serial_ids": serial_ids,
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    return row.id


def _dispatch(firm: _Firm, transfer_id: UUID) -> None:
    StockTransferService(firm.session).dispatch(
        transfer_id,
        StockTransferDispatch(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


# ---- the one-step transfer ------------------------------------------------


def test_a_one_step_transfer_takes_its_units_to_the_destination(firm: _Firm) -> None:
    _move(firm, "2", _units(firm, "PH001", "PH002"))

    depot = firm.depot.id  # type: ignore[attr-defined]
    moved = _unit(firm, "PH001")
    assert (moved.status, moved.warehouse_id) == ("AVAILABLE", depot)
    assert moved.inventory_id is not None
    assert _unit(firm, "PH003").warehouse_id == firm.warehouse.id
    trail = serial_trail(firm.session, firm_id=firm.firm.id, serial_id=moved.id)
    assert [event.document_type for event in trail.events] == ["STOCK_MOVE"]
    assert trail.events[0].document_number


def test_a_one_step_transfer_refuses_until_one_unit_is_named_per_unit(
    firm: _Firm,
) -> None:
    with pytest.raises(ValidationError, match="pick 2 more"):
        _move(firm, "2", [])
    firm.session.rollback()
    with pytest.raises(ValidationError, match="pick 1 more"):
        _move(firm, "2", _units(firm, "PH001"))
    firm.session.rollback()
    assert _unit(firm, "PH001").warehouse_id == firm.warehouse.id


def test_a_one_step_transfer_refuses_a_unit_that_is_not_on_the_source_shelf(
    firm: _Firm,
) -> None:
    _move(firm, "1", _units(firm, "PH001"))
    # PH001 is at the depot now; it cannot leave the main warehouse again.
    with pytest.raises(ValidationError, match="not in the warehouse"):
        _move(firm, "1", _units(firm, "PH001"))
    firm.session.rollback()
    sold = _unit(firm, "PH002")
    sold.status = "SOLD"
    firm.session.commit()
    with pytest.raises(ValidationError, match="is SOLD, not AVAILABLE"):
        _move(firm, "1", _units(firm, "PH002"))
    firm.session.rollback()


def test_a_product_nobody_tracks_by_serial_takes_no_serials(firm: _Firm) -> None:
    ids = _units(firm, "PH001")
    firm.product.track_serial = False
    firm.session.commit()
    with pytest.raises(ValidationError, match="not serial-tracked"):
        _move(firm, "1", ids)
    firm.session.rollback()
    _move(firm, "1", [])


# ---- the transfer document ------------------------------------------------


def test_a_transfer_document_carries_its_units_through_transit(firm: _Firm) -> None:
    service = StockTransferService(firm.session)
    ids = _units(firm, "PH001", "PH002", "PH003", "PH004")
    transfer_id = _draft(firm, "4", ids)
    line = service.responses([service.get(transfer_id, firm_id=firm.firm.id)])[0]
    assert line.lines[0].serial_tracked is True
    assert [s.serial_number for s in line.lines[0].serials] == [
        "PH001",
        "PH002",
        "PH003",
        "PH004",
    ]
    # Picking moves nothing.
    assert _unit(firm, "PH001").status == "AVAILABLE"

    _dispatch(firm, transfer_id)
    assert {_unit(firm, n).status for n in ("PH001", "PH004")} == {"IN_TRANSIT"}

    service.receive(
        transfer_id,
        StockTransferReceive.model_validate(
            {
                "lines": [
                    {
                        "line_number": 1,
                        "received_quantity": "3",
                        "damaged_quantity": "1",
                        "short_serial_ids": [ids[3]],
                        "damaged_serial_ids": [ids[2]],
                    }
                ]
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    depot = firm.depot.id  # type: ignore[attr-defined]
    good, broken, lost = (_unit(firm, n) for n in ("PH001", "PH003", "PH004"))
    assert (good.status, good.warehouse_id) == ("AVAILABLE", depot)
    assert (broken.status, broken.warehouse_id) == ("DAMAGED", depot)
    assert (lost.status, lost.warehouse_id) == ("LOST", firm.warehouse.id)
    trail = serial_trail(firm.session, firm_id=firm.firm.id, serial_id=good.id)
    assert [event.document_type for event in trail.events] == ["STOCK_TRANSFER"]
    assert trail.events[0].document_number.startswith("TO")


def test_dispatch_refuses_until_the_line_names_one_unit_per_unit(firm: _Firm) -> None:
    transfer_id = _draft(firm, "3", _units(firm, "PH001"))
    with pytest.raises(ValidationError, match="pick 2 more on the transfer"):
        _dispatch(firm, transfer_id)
    firm.session.rollback()
    assert _unit(firm, "PH001").status == "AVAILABLE"


def test_dispatch_refuses_a_unit_another_transfer_already_took(firm: _Firm) -> None:
    first = _draft(firm, "1", _units(firm, "PH001"))
    second = _draft(firm, "1", _units(firm, "PH001"))
    _dispatch(firm, first)
    with pytest.raises(ValidationError, match="PH001 is IN_TRANSIT"):
        _dispatch(firm, second)
    firm.session.rollback()


def test_a_draft_refuses_one_unit_on_two_lines_and_a_unit_from_elsewhere(
    firm: _Firm,
) -> None:
    ids = _units(firm, "PH001")
    with pytest.raises(ValidationError, match="picked on line 1 and on line 2"):
        StockTransferService(firm.session).create(
            StockTransferWrite.model_validate(
                {
                    "transfer_date": ON,
                    "from_warehouse_id": firm.warehouse.id,
                    "to_warehouse_id": firm.depot.id,  # type: ignore[attr-defined]
                    "lines": [
                        {
                            "product_id": firm.product.id,
                            "quantity": "1",
                            "serial_ids": ids,
                        },
                        {
                            "product_id": firm.product.id,
                            "quantity": "1",
                            "serial_ids": ids,
                        },
                    ],
                }
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    _move(firm, "1", ids)
    with pytest.raises(ValidationError, match="not in the warehouse"):
        _draft(firm, "1", ids)
    firm.session.rollback()


def test_rewriting_a_draft_replaces_what_it_picked(firm: _Firm) -> None:
    service = StockTransferService(firm.session)
    transfer_id = _draft(firm, "1", _units(firm, "PH001"))
    service.update(
        transfer_id,
        StockTransferWrite.model_validate(
            {
                "transfer_date": ON,
                "from_warehouse_id": firm.warehouse.id,
                "to_warehouse_id": firm.depot.id,  # type: ignore[attr-defined]
                "lines": [
                    {
                        "product_id": firm.product.id,
                        "quantity": "1",
                        "serial_ids": _units(firm, "PH002"),
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    view = service.responses([service.get(transfer_id, firm_id=firm.firm.id)])[0]
    assert [s.serial_number for s in view.lines[0].serials] == ["PH002"]
    picks = firm.session.scalars(
        select(DocumentLineSerial).where(DocumentLineSerial.document_id == transfer_id)
    ).all()
    assert len(picks) == 1


def test_the_receipt_names_which_units_were_short_or_damaged(firm: _Firm) -> None:
    service = StockTransferService(firm.session)
    ids = _units(firm, "PH001", "PH002", "PH005")
    transfer_id = _draft(firm, "2", ids[:2])
    _dispatch(firm, transfer_id)

    def receive(line: dict[str, object]) -> None:
        service.receive(
            transfer_id,
            StockTransferReceive.model_validate(
                {"lines": [{"line_number": 1, **line}]}
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )

    with pytest.raises(ValidationError, match="name 1 of the line's serial"):
        receive({"received_quantity": "1"})
    firm.session.rollback()
    with pytest.raises(ValidationError, match="not one this line sent"):
        receive({"received_quantity": "1", "short_serial_ids": [ids[2]]})
    firm.session.rollback()
    with pytest.raises(ValidationError, match="cannot also be damaged"):
        receive(
            {
                "received_quantity": "1",
                "damaged_quantity": "1",
                "short_serial_ids": [ids[0]],
                "damaged_serial_ids": [ids[0]],
            }
        )
    firm.session.rollback()
    assert _unit(firm, "PH001").status == "IN_TRANSIT"
    # Received as sent: an empty receipt lands every unit in good order.
    service.receive(
        transfer_id,
        StockTransferReceive(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert {_unit(firm, n).status for n in ("PH001", "PH002")} == {"AVAILABLE"}
    assert _unit(firm, "PH002").warehouse_id == firm.depot.id  # type: ignore[attr-defined]


def test_cancelling_a_dispatched_transfer_puts_its_units_back(firm: _Firm) -> None:
    transfer_id = _draft(firm, "2", _units(firm, "PH001", "PH002"))
    _dispatch(firm, transfer_id)
    StockTransferService(firm.session).cancel(
        transfer_id, "Lorry broke down", firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    back = _unit(firm, "PH001")
    assert (back.status, back.warehouse_id) == ("AVAILABLE", firm.warehouse.id)
    # Free to travel again, on another transfer.
    again = _draft(firm, "1", _units(firm, "PH001"))
    _dispatch(firm, again)
    assert _unit(firm, "PH001").status == "IN_TRANSIT"


def test_units_that_arrived_can_be_sent_on_from_where_they_landed(firm: _Firm) -> None:
    ids = _units(firm, "PH001")
    transfer_id = _draft(firm, "1", ids)
    _dispatch(firm, transfer_id)
    StockTransferService(firm.session).receive(
        transfer_id,
        StockTransferReceive(),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    # The defect: PH001 still read "main warehouse", so nothing at the depot
    # could name it. It goes back on a transfer of its own.
    InventoryService(firm.session).transfer_stock(
        StockTransferCreate(
            branch_id=firm.branch.id,
            from_warehouse_id=firm.depot.id,  # type: ignore[attr-defined]
            to_warehouse_id=firm.warehouse.id,
            product_id=firm.product.id,
            quantity=D("1"),
            transaction_date=ON,
            serial_ids=ids,
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert _unit(firm, "PH001").warehouse_id == firm.warehouse.id


# ---- opening stock ----------------------------------------------------------


def _opening(firm: _Firm, quantity: str, serials: list[str] | None) -> UUID:
    line: dict[str, object] = {
        "product_id": firm.product.id,
        "quantity": quantity,
        "unit_cost": "100",
    }
    if serials is not None:
        line["serial_numbers"] = serials
    batch = InventoryService(firm.session).create_opening_stock_batch(
        OpeningStockBatchCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.depot.id,  # type: ignore[attr-defined]
                "reference_number": f"OPN-{quantity}-{len(serials or [])}",
                "posting_date": ON,
                "lines": [line],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    return batch.id


def test_opening_stock_creates_the_units_its_line_typed(firm: _Firm) -> None:
    service = InventoryService(firm.session)
    batch_id = _opening(firm, "2", [" op-1 ", "", "OP-2"])
    draft = service.opening_stock_batch_response(
        service.get_opening_stock_batch(batch_id, firm_scope=firm.firm.id)
    )
    assert draft.lines[0].serial_tracked is True
    assert draft.lines[0].serial_numbers == ["op-1", "OP-2"]
    # A draft is not stock: no unit exists yet.
    assert (
        firm.session.scalar(
            select(SerialNumber).where(SerialNumber.serial_number == "OP-2")
        )
        is None
    )

    service.post_opening_stock_batch(
        batch_id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    unit = _unit(firm, "OP-2")
    assert (unit.status, unit.warehouse_id) == (
        "AVAILABLE",
        firm.depot.id,  # type: ignore[attr-defined]
    )
    assert unit.inventory_id is not None
    trail = serial_trail(firm.session, firm_id=firm.firm.id, serial_id=unit.id)
    assert [event.document_type for event in trail.events] == ["OPENING_STOCK"]
    assert trail.events[0].document_number == "OPN-2-3"


def test_opening_stock_asks_for_one_serial_per_unit_once_any_is_typed(
    firm: _Firm,
) -> None:
    service = InventoryService(firm.session)
    batch_id = _opening(firm, "3", ["OP-1"])
    with pytest.raises(ValidationError, match="enter 2 more"):
        service.post_opening_stock_batch(
            batch_id, firm_scope=firm.firm.id, actor_id=firm.actor_id
        )
    firm.session.rollback()
    # Rewriting the draft replaces what it typed.
    service.update_opening_stock_batch(
        batch_id,
        OpeningStockUpdate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.depot.id,  # type: ignore[attr-defined]
                "reference_number": "OPN-3-1",
                "posting_date": ON,
                "lines": [
                    {
                        "product_id": firm.product.id,
                        "quantity": "3",
                        "unit_cost": "100",
                        "serial_numbers": ["OP-1", "OP-2", "OP-3"],
                    }
                ],
            }
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.post_opening_stock_batch(
        batch_id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    assert _unit(firm, "OP-3").status == "AVAILABLE"


def test_opening_stock_with_no_serials_still_posts_as_a_quantity(firm: _Firm) -> None:
    batch_id = _opening(firm, "2", None)
    posted = InventoryService(firm.session).post_opening_stock_batch(
        batch_id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    assert posted.status == "POSTED"


def test_opening_stock_refuses_a_number_the_firm_already_gave_a_unit(
    firm: _Firm,
) -> None:
    with pytest.raises(ValidationError, match="ph001 already belongs to a unit"):
        _opening(firm, "1", ["ph001"])
    firm.session.rollback()
    with pytest.raises(ValidationError, match="entered twice"):
        _opening(firm, "2", ["OP-9", "op-9"])
    firm.session.rollback()
