"""A branch bills an order placed on its main office (backlog 140, row F9).

A firm that types no goods receipts bills an approved order, and the bill
raises the receipt behind it. Where the bill is in the name of another
office of the supplier company the order is on, the receipt nobody typed is
from that office too, so the two documents name the same supplier.
"""

# ruff: noqa: D103

from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseWorkflowSettingsWrite
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services import PurchaseInvoiceService
from tests.unit.test_goods_receipt import _Fixture
from tests.unit.test_supplier_branches import _fixture, _supplier

pytestmark = pytest.mark.typed_document_numbers


def _orders_only(fixture: _Fixture) -> None:
    PurchaseWorkflowService(fixture.session).update_settings(
        PurchaseWorkflowSettingsWrite(
            purchase_order_stage=True, goods_receipt_stage=False
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _bill_the_order(fixture: _Fixture, vendor_id: UUID | None) -> PurchaseInvoice:
    line = fixture.session.scalars(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == fixture.order.id
        )
    ).first()
    assert line is not None
    return PurchaseInvoiceService(fixture.session).create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "vendor_id": vendor_id,
                "invoice_date": "2026-08-10",
                "supplier_invoice_number": "S-140",
                "supplier_invoice_date": "2026-08-09",
                "lines": [
                    {
                        "source_document_type": "PURCHASE_ORDER",
                        "source_document_id": fixture.order.id,
                        "source_document_line_id": line.id,
                        "line_number": 1,
                        "current_invoice_quantity": "4",
                    }
                ],
            }
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _receipts(fixture: _Fixture) -> list[GoodsReceipt]:
    return list(
        fixture.session.scalars(
            select(GoodsReceipt).where(
                GoodsReceipt.purchase_order_id == fixture.order.id
            )
        )
    )


def test_a_branchs_bill_for_the_order_receives_the_goods_from_the_branch() -> None:
    fixture = _fixture("F9A")
    _orders_only(fixture)
    branch = _supplier(fixture, "BR-CBE", fixture.vendor.id)

    bill = _bill_the_order(fixture, branch.id)

    assert bill.vendor_id == branch.id
    (receipt,) = _receipts(fixture)
    assert receipt.vendor_id == branch.id
    # The order stays on the company it was placed on.
    assert fixture.order.vendor_id == fixture.vendor.id


def test_a_bill_that_names_no_office_is_the_orders_supplier_as_before() -> None:
    fixture = _fixture("F9B")
    _orders_only(fixture)
    _supplier(fixture, "BR-CBE", fixture.vendor.id)

    bill = _bill_the_order(fixture, None)

    assert bill.vendor_id == fixture.vendor.id
    (receipt,) = _receipts(fixture)
    assert receipt.vendor_id == fixture.vendor.id


def test_a_bill_from_outside_the_company_is_refused_in_the_bills_words() -> None:
    fixture = _fixture("F9C")
    _orders_only(fixture)
    stranger = _supplier(fixture, "STRANGER")

    with pytest.raises(ValidationError, match="must match all source documents"):
        _bill_the_order(fixture, stranger.id)
