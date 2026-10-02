"""The e-way bill on a goods receipt, and the warning without one (78.6).

The receipt is `test_goods_receipt`'s: 4 x 100, no tax, so 400 -- above a
firm limit of 300 and below the national 50,000.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.goods_receipt.schemas import GoodsReceiptEwayBillWrite
from app.goods_receipt.services import GoodsReceiptService
from app.tax.models import GstComplianceSettings
from tests.unit.test_goods_receipt import _Fixture, _session_factory

pytestmark = pytest.mark.typed_document_numbers

EWB = "331234567890"


def _fixture(code: str, *, limit: str | None = "300") -> _Fixture:
    """Return a firm, its order, and the e-way bill limit set."""
    session = _session_factory()()
    fixture = _Fixture(session, code)
    if limit is not None:
        session.add(
            GstComplianceSettings(firm_id=fixture.firm.id, eway_bill_limit=limit)
        )
        session.commit()
    return fixture


def test_an_eway_bill_number_is_twelve_digits() -> None:
    assert (
        GoodsReceiptEwayBillWrite(eway_bill_number="3312 3456 7890").eway_bill_number
        == EWB
    )
    assert GoodsReceiptEwayBillWrite(eway_bill_number=" ").eway_bill_number is None
    with pytest.raises(SchemaError, match="12 digits"):
        GoodsReceiptEwayBillWrite(eway_bill_number="EWB-1")


def test_goods_above_the_limit_with_no_eway_bill_are_warned() -> None:
    fixture = _fixture("EW1")
    service = GoodsReceiptService(fixture.session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    warning = service.receipt_response(receipt).eway_bill_warning

    assert warning is not None
    assert "rule 138" in warning
    # The vendor has no GSTIN, so the e-way bill is the buyer's to raise.
    assert "yours to raise" in warning


def test_a_registered_supplier_is_asked_for_its_number() -> None:
    fixture = _fixture("EW2")
    fixture.vendor.gstin = "33AABCU9603R1ZM"
    fixture.session.commit()
    service = GoodsReceiptService(fixture.session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    warning = service.receipt_response(receipt).eway_bill_warning
    assert warning is not None
    assert "supplier's e-way bill" in warning


def test_no_warning_below_the_limit_or_with_a_number() -> None:
    fixture = _fixture("EW3", limit=None)
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert service.receipt_response(receipt).eway_bill_warning is None

    fixture = _fixture("EW4")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4", eway_bill_number=EWB, eway_bill_date="2026-08-04"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    response = service.receipt_response(receipt)
    assert (response.eway_bill_number, response.eway_bill_date) == (
        EWB,
        date(2026, 8, 4),
    )
    assert response.eway_bill_warning is None


def test_an_edit_that_omits_the_eway_bill_keeps_it_and_null_clears_it() -> None:
    fixture = _fixture("EW5")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4", eway_bill_number=EWB),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    row = service.update_receipt(
        receipt.id,
        fixture.receipt_payload("5"),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert row.eway_bill_number == EWB

    row = service.update_receipt(
        receipt.id,
        fixture.receipt_payload("5", eway_bill_number=None),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert row.eway_bill_number is None


def test_a_completed_receipt_takes_the_number_and_it_is_audited() -> None:
    fixture = _fixture("EW6")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    row = service.set_eway_bill(
        receipt.id,
        number=EWB,
        on=date(2026, 8, 4),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    assert row.eway_bill_number == EWB
    assert service.receipt_response(row).eway_bill_warning is None
    assert fixture.session.scalar(
        select(AuditLog).where(
            AuditLog.action == "goods_receipt.eway_bill_set",
            AuditLog.entity_id == receipt.id,
        )
    )
    # Clearing the number clears its date with it.
    row = service.set_eway_bill(
        receipt.id,
        number=None,
        on=date(2026, 8, 4),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert (row.eway_bill_number, row.eway_bill_date) == (None, None)


def test_a_cancelled_receipt_is_neither_changed_nor_warned() -> None:
    fixture = _fixture("EW7")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="Wrong order.",
    )

    assert service.receipt_response(receipt).eway_bill_warning is None
    with pytest.raises(ValidationError, match="cancelled"):
        service.set_eway_bill(
            receipt.id,
            number=EWB,
            on=None,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
        )


def test_the_value_judged_is_the_receipts_total() -> None:
    fixture = _fixture("EW8", limit="400")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    # Exactly at the limit is not above it.
    assert Decimal(str(receipt.grand_total)) == Decimal("400")
    assert service.receipt_response(receipt).eway_bill_warning is None
