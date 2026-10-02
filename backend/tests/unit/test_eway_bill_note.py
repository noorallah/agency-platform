"""An e-way bill for a delivery note no invoice bills yet (backlog 77 row 9).

Job work, goods on approval, a van loaded before its sales are made: the
consignment moves on its challan, and the challan raises the bill. Once an
invoice bills the note, the bill is the invoice's.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.einvoice.services.eway_bills import EWayBillService
from tests.unit.test_batch_picker import _Shop


def _approved_note(shop: _Shop, *, reason: str = "JOB_WORK") -> object:
    """Raise and approve a note for the order's eight, with a challan reason."""
    note = shop.note(None)
    note.challan_reason = reason
    shop.session.commit()
    return shop.notes.approve_note(
        note.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )


def _raise(shop: _Shop, note: object) -> object:
    """Raise the note's e-way bill in the sandbox."""
    return EWayBillService(
        shop.session, mode="SANDBOX", provider="SANDBOX"
    ).generate_for_note(
        note.id,  # type: ignore[attr-defined]
        distance_km=Decimal("80"),
        transport_mode="ROAD",
        transporter_id=None,
        transporter_name=None,
        vehicle_number="TN01AB1234",
        firm_scope=shop.firm_id,
        actor_id=shop.actor_id,
    )


def test_a_job_work_challan_raises_its_own_bill() -> None:
    """The challan's reason sets the supply type: job work is 4."""
    shop = _Shop()
    note = _approved_note(shop)

    bill = _raise(shop, note)

    assert bill.status == "GENERATED"  # type: ignore[attr-defined]
    payload = bill.request_payload or {}  # type: ignore[attr-defined]
    assert payload["docType"] == "CHL"
    assert payload["subSupplyType"] == "4"
    assert bill.delivery_note_id == note.id  # type: ignore[attr-defined]
    with pytest.raises(ConflictError, match="already has e-way bill"):
        _raise(shop, note)


def test_a_draft_note_has_no_bill_yet() -> None:
    """Goods not approved to move travel on nothing."""
    shop = _Shop()
    draft = shop.note(None)

    with pytest.raises(ValidationError, match="approved to move"):
        _raise(shop, draft)


def test_a_withdrawn_note_bill_can_be_raised_again() -> None:
    """Cancel, then raise anew on the same row."""
    shop = _Shop()
    note = _approved_note(shop)
    _raise(shop, note)
    service = EWayBillService(shop.session, mode="SANDBOX", provider="SANDBOX")

    cancelled = service.cancel_for_note(
        note.id,  # type: ignore[attr-defined]
        reason="vehicle changed",
        firm_scope=shop.firm_id,
        actor_id=shop.actor_id,
    )
    assert cancelled.status == "CANCELLED"
    assert _raise(shop, note).status == "GENERATED"  # type: ignore[attr-defined]
