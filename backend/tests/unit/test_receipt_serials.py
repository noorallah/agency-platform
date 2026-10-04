"""Serial numbers captured at receipt (PG-10, backlog 86 #11).

A serial-tracked product's trail starts where it arrives: the receipt line
carries one serial per unit, completing the receipt creates each unit
AVAILABLE in the receipt's warehouse, a purchase return names the units going
back, and cancelling either document undoes what it did -- unless a unit has
moved since.
"""

from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import DocumentLineSerial, SerialNumber
from app.batch_serial.services.serial_history import serial_trail
from app.core.exceptions import ValidationError
from app.goods_receipt.api.router import expand_serial_range
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptUpdate, SerialRangeRequest
from app.goods_receipt.serials import expand_range
from app.goods_receipt.services import GoodsReceiptService
from app.purchase_return.models import PurchaseReturn
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services import PurchaseReturnService
from tests.unit.test_goods_receipt import _Fixture, _session_factory

pytestmark = pytest.mark.typed_document_numbers


def _serialised(code: str) -> tuple[Session, _Fixture]:
    """Build a firm whose one product is tracked by serial."""
    session = _session_factory()()
    fixture = _Fixture(session, code)
    fixture.product.track_serial = True
    session.commit()
    return session, fixture


def _receive(
    fixture: _Fixture, serials: list[str] | None, quantity: str = "4"
) -> GoodsReceipt:
    """Raise a draft receipt for ``quantity`` units naming ``serials``."""
    payload = fixture.receipt_payload(quantity)
    if serials is not None:
        payload.lines[0].serial_numbers = serials
    return GoodsReceiptService(fixture.session).create_receipt(
        payload, firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )


def _complete(fixture: _Fixture, receipt: GoodsReceipt) -> None:
    """Complete a receipt."""
    GoodsReceiptService(fixture.session).complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )


def _units(session: Session, firm_id: UUID) -> list[SerialNumber]:
    """Return the firm's live units, by number."""
    return list(
        session.scalars(
            select(SerialNumber)
            .where(SerialNumber.firm_id == firm_id, SerialNumber.is_deleted.is_(False))
            .order_by(SerialNumber.serial_number)
        ).all()
    )


def _line_serials(fixture: _Fixture, receipt: GoodsReceipt) -> list[str]:
    """Return what the receipt's response says its line holds."""
    response = GoodsReceiptService(fixture.session).receipt_response(receipt)
    return response.lines[0].serial_numbers


def _update(
    fixture: _Fixture, receipt: GoodsReceipt, serials: list[str] | None
) -> None:
    """Save the draft again, sending ``serials`` or leaving them out."""
    line: dict[str, object] = {
        "purchase_order_line_id": fixture.order_line.id,
        "line_number": 1,
        "current_receipt_quantity": "4",
        "unit_price": "100",
        "warehouse_id": fixture.warehouse.id,
    }
    if serials is not None:
        line["serial_numbers"] = serials
    GoodsReceiptService(fixture.session).update_receipt(
        receipt.id,
        GoodsReceiptUpdate.model_validate(
            {
                "purchase_order_id": fixture.order.id,
                "receipt_date": "2026-08-05",
                "lines": [line],
            }
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def test_a_draft_holds_a_short_list_and_completion_refuses_it() -> None:
    """The count is only checked where the units are created."""
    session, fixture = _serialised("PGS1")
    receipt = _receive(fixture, ["SN-1", "SN-2"])
    assert _line_serials(fixture, receipt) == ["SN-1", "SN-2"]
    response = GoodsReceiptService(session).receipt_response(receipt)
    assert response.lines[0].serial_tracked is True

    with pytest.raises(
        ValidationError,
        match=r"Line 1 \(SKU-PGS1\) receives 4 serial-tracked units but 2 "
        r"serial numbers are entered: enter 2 more",
    ):
        _complete(fixture, receipt)
    session.rollback()
    assert _units(session, fixture.firm.id) == []


def test_a_serial_typed_twice_in_one_request_is_refused() -> None:
    """A leading space and lower case do not make a different unit."""
    _session, fixture = _serialised("PGS2")
    with pytest.raises(ValidationError, match="serial SN-1 is entered twice"):
        _receive(fixture, [" sn-1", "SN-1"])


def test_a_serial_already_in_stock_is_refused() -> None:
    """Firm-wide: another receipt's unit already carries the number."""
    session, fixture = _serialised("PGS3")
    first = _receive(fixture, ["A1", "A2", "A3", "A4"])
    _complete(fixture, first)

    with pytest.raises(ValidationError, match="serial a2 already belongs to a unit"):
        _receive(fixture, ["B1", " a2 ", "B3", "B4"])
    session.rollback()


def test_serials_are_trimmed_and_blanks_dropped() -> None:
    """Spaces off each end, blank scans ignored, case kept as typed."""
    _session, fixture = _serialised("PGS4")
    receipt = _receive(fixture, ["  imei-1 ", "", "   ", "IMEI-2"])
    assert _line_serials(fixture, receipt) == ["imei-1", "IMEI-2"]


def test_absent_leaves_the_list_and_an_empty_one_clears_it() -> None:
    """A draft edited without the field keeps what it holds."""
    _session, fixture = _serialised("PGS5")
    receipt = _receive(fixture, ["K1", "K2"])
    _update(fixture, receipt, None)
    assert _line_serials(fixture, receipt) == ["K1", "K2"]
    _update(fixture, receipt, ["K3"])
    assert _line_serials(fixture, receipt) == ["K3"]
    _update(fixture, receipt, [])
    assert _line_serials(fixture, receipt) == []


def test_completion_puts_each_unit_in_stock_and_starts_its_trail() -> None:
    """One AVAILABLE unit per serial, in the receipt's warehouse."""
    session, fixture = _serialised("PGS6")
    receipt = _receive(fixture, ["U1", "U2", "U3", "U4"])
    _complete(fixture, receipt)

    units = _units(session, fixture.firm.id)
    assert [unit.serial_number for unit in units] == ["U1", "U2", "U3", "U4"]
    assert {unit.status for unit in units} == {"AVAILABLE"}
    assert {unit.warehouse_id for unit in units} == {fixture.warehouse.id}
    line = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()
    picks = session.scalars(
        select(DocumentLineSerial).where(DocumentLineSerial.document_line_id == line.id)
    ).all()
    assert len(picks) == 4
    assert {pick.document_type for pick in picks} == {"GOODS_RECEIPT"}
    assert all(pick.moved_at is not None for pick in picks)

    trail = serial_trail(session, firm_id=fixture.firm.id, serial_id=units[0].id)
    first = trail.events[0]
    assert first.document_type == "GOODS_RECEIPT"
    assert first.document_number == receipt.grn_number
    assert first.document_date == date(2026, 8, 5)
    assert first.party_name == "Vendor"


def _return(
    fixture: _Fixture,
    receipt: GoodsReceipt,
    serials: list[str] | None,
    quantity: str = "1",
) -> PurchaseReturn:
    """Raise a draft return of ``quantity`` units off the receipt's line."""
    line = fixture.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()
    return PurchaseReturnService(fixture.session).create_return(
        PurchaseReturnCreate(
            supplier_return_number=f"SUP-RET-{fixture.firm.code}",
            supplier_return_date=date(2026, 8, 7),
            return_date=date(2026, 8, 7),
            warehouse_id=fixture.warehouse.id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=line.id,
                    line_number=1,
                    current_return_quantity=Decimal(quantity),
                    warehouse_id=fixture.warehouse.id,
                    serial_numbers=serials,
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _unit(session: Session, firm_id: UUID, number: str) -> SerialNumber:
    """Return one live unit by its number."""
    return session.scalars(
        select(SerialNumber).where(
            SerialNumber.firm_id == firm_id,
            SerialNumber.serial_number == number,
            SerialNumber.is_deleted.is_(False),
        )
    ).one()


def test_a_purchase_return_marks_its_units_returned_and_cancelling_restores() -> None:
    """The units named go back with the stock; a cancel brings them back."""
    session, fixture = _serialised("PGS7")
    receipt = _receive(fixture, ["R1", "R2", "R3", "R4"])
    _complete(fixture, receipt)
    returns = PurchaseReturnService(session)
    row = _return(fixture, receipt, ["r2"])
    assert returns.return_response(row).lines[0].serial_numbers == ["R2"]
    returns.approve_return(
        row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    returns.complete_return(
        row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    session.expire_all()
    assert _unit(session, fixture.firm.id, "R2").status == "RETURNED"
    assert _unit(session, fixture.firm.id, "R1").status == "AVAILABLE"
    trail = serial_trail(
        session,
        firm_id=fixture.firm.id,
        serial_id=_unit(session, fixture.firm.id, "R2").id,
    )
    assert [event.document_type for event in trail.events] == [
        "GOODS_RECEIPT",
        "PURCHASE_RETURN",
    ]

    returns.cancel_return(
        row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id, reason="kept"
    )
    session.expire_all()
    assert _unit(session, fixture.firm.id, "R2").status == "AVAILABLE"


def test_a_return_refuses_a_unit_not_in_stock() -> None:
    """A unit already sold cannot be sent back to the supplier."""
    session, fixture = _serialised("PGS8")
    receipt = _receive(fixture, ["S1", "S2", "S3", "S4"])
    _complete(fixture, receipt)
    _unit(session, fixture.firm.id, "S3").status = "SOLD"
    session.commit()

    with pytest.raises(ValidationError, match="serial S3 is SOLD, not in stock"):
        _return(fixture, receipt, ["S3"])
    session.rollback()
    with pytest.raises(ValidationError, match="serial S9 is not a unit"):
        _return(fixture, receipt, ["S9"])


def test_a_return_must_name_one_unit_per_unit_going_back() -> None:
    """Completion refuses a return that names fewer units than it sends."""
    session, fixture = _serialised("PGS9")
    receipt = _receive(fixture, ["T1", "T2", "T3", "T4"])
    _complete(fixture, receipt)
    returns = PurchaseReturnService(session)
    row = _return(fixture, receipt, ["T1"], quantity="2")
    returns.approve_return(
        row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    with pytest.raises(ValidationError, match="sends back 2 serial-tracked units"):
        returns.complete_return(
            row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )
    session.rollback()


def test_cancelling_the_receipt_removes_its_units() -> None:
    """The numbers are free to be received again afterwards."""
    session, fixture = _serialised("PGS10")
    receipt = _receive(fixture, ["C1", "C2", "C3", "C4"])
    _complete(fixture, receipt)
    GoodsReceiptService(session).cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="wrong supplier",
    )
    session.expire_all()
    assert _units(session, fixture.firm.id) == []
    again = _receive(fixture, ["C1", "C2", "C3", "C4"])
    _complete(fixture, again)
    assert len(_units(session, fixture.firm.id)) == 4


def test_cancelling_the_receipt_is_refused_once_a_unit_was_sold() -> None:
    """A unit that has left stock cannot be un-received."""
    session, fixture = _serialised("PGS11")
    receipt = _receive(fixture, ["D1", "D2", "D3", "D4"])
    _complete(fixture, receipt)
    _unit(session, fixture.firm.id, "D2").status = "SOLD"
    session.commit()

    with pytest.raises(ValidationError, match="serial D2 has left stock"):
        GoodsReceiptService(session).cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="too late",
        )
    session.rollback()


def test_a_product_without_serials_refuses_a_list() -> None:
    """Naming serials on an untracked product is a mistake, not a preference.

    An empty list is accepted: it says nothing.
    """
    _session, fixture = _serialised("PGS12")
    fixture.product.track_serial = False
    fixture.session.commit()
    with pytest.raises(ValidationError, match="not serial-tracked"):
        _receive(fixture, ["X1"])
    fixture.session.rollback()
    receipt = _receive(fixture, [])
    _complete(fixture, receipt)
    assert _units(fixture.session, fixture.firm.id) == []


def test_a_range_fills_padded_numbers() -> None:
    """The desktop's range fill: a prefix and a zero-padded counter."""
    assert expand_range(prefix="SN", start=98, count=3, width=4) == [
        "SN0098",
        "SN0099",
        "SN0100",
    ]
    assert expand_range(prefix="", start=7, count=2, width=0) == ["7", "8"]
    response = expand_serial_range(
        SerialRangeRequest(prefix="IMEI-", start=1, count=2, width=3),
        scope=cast(Any, None),
    )
    assert response.data is not None
    assert response.data.serial_numbers == ["IMEI-001", "IMEI-002"]
