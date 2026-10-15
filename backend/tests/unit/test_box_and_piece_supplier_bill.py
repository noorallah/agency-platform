"""A supplier's bill and a purchase return typed as boxes and pieces (L5 step 7).

`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.4 and 3.6. A bill line is
billed at its receipt line's pack, and a bill typed straight in hands its
layout and each line's pack size to the order and receipt it raises, so the
three are written at one pack. A return line goes back at its receipt or
bill line's pack, free goods included, so a box taken in at 12 goes back at
12 after the box moved to 10.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceCreate, PurchaseInvoiceUpdate
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.services import PurchaseReturnService
from app.uom.models import ConversionRule
from tests.unit.test_box_and_piece_purchase import _worked_example
from tests.unit.test_purchase_lines_in_another_unit import DAY, _Buyer

D = Decimal


def _ten_to_a_box_from(buyer: _Buyer, starts: date) -> None:
    """Move the box from 12 to 10, as a new version of the rule."""
    buyer.session.add(
        ConversionRule(
            firm_id=buyer.firm_id,
            product_id=buyer.firm.product.id,
            from_uom_id=buyer.box,
            to_uom_id=buyer.piece,
            conversion_factor=D("10"),
            rounding_mode="HALF_UP",
            precision_scale=4,
            effective_from=starts,
            version_number=2,
        )
    )
    buyer.session.commit()


def _received(buyer: _Buyer) -> GoodsReceipt:
    """Take the worked example's purchase in: 120 bought, 12 free, at 12."""
    order = _worked_example(buyer)
    return buyer.receive(order, "120", free_quantity="12", pack_size="12")


def _direct_payload(**line: object) -> dict[str, object]:
    """Return a bill of products typed as boxes and pieces."""
    return {
        "invoice_date": DAY,
        "supplier_invoice_number": "S-PAIR",
        "supplier_invoice_date": DAY,
        "box_and_piece_entry": True,
        "lines": [
            {
                "line_number": 1,
                "current_invoice_quantity": "120",
                "free_quantity": "12",
                "unit_price": "8",
                "pack_size": "12",
            }
            | line
        ],
    }


def _direct_bill(
    buyer: _Buyer, *, approve: bool = True, **line: object
) -> PurchaseInvoice:
    """Type the worked example's purchase straight onto a bill."""
    service = PurchaseInvoiceService(buyer.session)
    payload = _direct_payload(product_id=buyer.firm.product.id, **line)
    bill = service.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            payload | {"vendor_id": buyer.firm.vendor.id}
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    if approve:
        service.approve_invoice(bill.id, firm_scope=buyer.firm_id, actor_id=buyer.actor)
    return bill


def test_the_worked_example_is_billed_at_its_receipts_pack() -> None:
    """120 pieces billed off the receipt: at 12 to a box, 960.00, in boxes."""
    buyer = _Buyer()
    receipt = _received(buyer)

    bill = buyer.bill(receipt, "120", pack_size="12")

    line = buyer.bill_line(bill)
    assert (line.pack_uom_id, line.pack_size) == (buyer.box, D("12.0000"))
    assert (line.current_invoice_quantity, line.gross_amount) == (
        D("120.0000"),
        D("960.0000"),
    )
    answered = PurchaseInvoiceService(buyer.session).invoice_response(bill)
    # Silence takes the layout of the receipt it bills.
    assert answered.box_and_piece_entry is True
    assert (answered.lines[0].pack_uom_id, answered.lines[0].pack_size) == (
        buyer.box,
        D("12.0000"),
    )


def test_a_bill_after_the_box_changes_is_billed_at_the_receipts_pack() -> None:
    """Taken in at 12 to a box, billed at 12 once the box holds 10."""
    buyer = _Buyer()
    receipt = _received(buyer)
    _ten_to_a_box_from(buyer, DAY)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        buyer.bill(receipt, "24", pack_size="10")
    bill = buyer.bill(receipt, "24", pack_size="12")

    assert buyer.bill_line(bill).pack_size == D("12.0000")


def test_a_bill_line_typed_as_boxes_and_pieces_cannot_be_in_the_box() -> None:
    """A pair line is counted in pieces, so billing it in BOX is refused."""
    buyer = _Buyer()
    receipt = _received(buyer)

    with pytest.raises(ValidationError, match="counted in the item's stock unit"):
        buyer.bill(receipt, "2", pack_size="12", invoice_uom_id=str(buyer.box))


def test_a_bill_typed_straight_in_hands_its_pack_to_the_order_and_receipt() -> None:
    """Stages off: order, receipt and bill all at 12 to a box, 132 in at 7.27."""
    buyer = _Buyer()
    buyer.firm.stages(order=False, receipt=False)

    bill = _direct_bill(buyer)

    order_line = buyer.session.scalars(select(PurchaseOrderLine)).one()
    receipt_line = buyer.session.scalars(select(GoodsReceiptLine)).one()
    bill_line = buyer.bill_line(bill)
    for line in (order_line, receipt_line, bill_line):
        assert (line.pack_uom_id, line.pack_size) == (buyer.box, D("12.0000"))
    # In pieces, though it named no unit and the item is bought by the box.
    assert (order_line.purchase_uom_id, order_line.ordered_quantity) == (
        buyer.piece,
        D("120.0000"),
    )
    assert bill_line.gross_amount == D("960.0000")
    assert buyer.stock() == D("132.0000")
    pieces, unit_cost, value = buyer.movement(receipt_line.inventory_transaction_id)
    assert (pieces, value) == (D("132.0000"), D("960.0000"))
    assert unit_cost.quantize(D("0.01")) == D("7.27")
    buyer.session.expire_all()
    assert buyer.session.scalars(select(PurchaseOrder)).one().box_and_piece_entry
    assert buyer.session.scalars(select(GoodsReceipt)).one().box_and_piece_entry
    assert buyer.session.get(PurchaseInvoice, bill.id).box_and_piece_entry


def test_a_pair_line_with_no_price_is_priced_per_piece() -> None:
    """24 pieces at the product's 60.00 a piece, not 60.00 a box of 12."""
    buyer = _Buyer()
    buyer.firm.stages(order=False, receipt=False)

    bill = _direct_bill(
        buyer, current_invoice_quantity="24", free_quantity="0", unit_price=None
    )

    line = buyer.bill_line(bill)
    assert (line.unit_price, line.gross_amount) == (D("60.0000"), D("1440.0000"))
    assert buyer.stock() == D("24.0000")


def test_a_bill_typed_straight_in_at_a_stale_pack_is_refused() -> None:
    """The order it raises asks the item: 10 sent where a box holds 12."""
    buyer = _Buyer()
    buyer.firm.stages(order=False, receipt=False)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        _direct_bill(buyer, pack_size="10")


def test_a_draft_bill_edited_after_the_box_changes_keeps_its_pack() -> None:
    """The order raised again on an edit keeps 12, though it is dated today."""
    buyer = _Buyer()
    buyer.firm.stages(order=False, receipt=False)
    bill = _direct_bill(buyer, approve=False)
    _ten_to_a_box_from(buyer, date(2000, 1, 1))
    service = PurchaseInvoiceService(buyer.session)
    body = _direct_payload(product_id=buyer.firm.product.id)
    body.pop("box_and_piece_entry")

    service.update_invoice(
        bill.id,
        PurchaseInvoiceUpdate.model_validate(
            body | {"vendor_id": buyer.firm.vendor.id}
        ),
        firm_scope=buyer.firm_id,
        actor_id=buyer.actor,
    )

    buyer.session.expire_all()
    assert buyer.bill_line(bill).pack_size == D("12.0000")
    # The order raised first is withdrawn, the one raised again is at 12.
    lines = buyer.session.scalars(select(PurchaseOrderLine)).all()
    assert [line.pack_size for line in lines] == [D("12.0000"), D("12.0000")]
    # Absent on an edit keeps the bill's layout, and the order raised again
    # takes it.
    assert service.invoice_response(bill).box_and_piece_entry is True


def test_a_box_and_a_piece_go_back_at_the_receipts_pack() -> None:
    """13 pieces sent back off the receipt, at 12 to a box, in boxes."""
    buyer = _Buyer()
    receipt = _received(buyer)

    sent = buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        "13",
        pack_size="12",
    )

    line = buyer.return_line(sent)
    assert (line.pack_uom_id, line.pack_size) == (buyer.box, D("12.0000"))
    assert line.current_return_quantity == D("13.0000")
    assert buyer.stock() == D("119.0000")
    answered = PurchaseReturnService(buyer.session).return_response(sent)
    assert answered.box_and_piece_entry is True
    assert answered.lines[0].pack_size == D("12.0000")


def test_a_free_box_goes_back_to_the_supplier_at_its_pack() -> None:
    """The free box alone, typed as 0 + 0 bought and 1 box + 0 free."""
    buyer = _Buyer()
    receipt = _received(buyer)

    sent = buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        "0",
        free_quantity="12",
        pack_size="12",
    )

    line = buyer.return_line(sent)
    assert (line.current_return_quantity, line.free_quantity) == (
        D("0.0000"),
        D("12.0000"),
    )
    assert (line.pack_uom_id, line.pack_size) == (buyer.box, D("12.0000"))
    assert line.gross_amount == D("0.0000")
    assert buyer.stock() == D("120.0000")


def test_a_return_off_the_bill_goes_back_at_the_bills_pack() -> None:
    """Sent back off the bill line after the box moved: at 12, not 10."""
    buyer = _Buyer()
    receipt = _received(buyer)
    bill = buyer.bill(receipt, "120", pack_size="12")
    _ten_to_a_box_from(buyer, DAY)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        buyer.send_back(
            "PURCHASE_INVOICE", bill.id, buyer.bill_line(bill).id, "10", pack_size="10"
        )
    sent = buyer.send_back(
        "PURCHASE_INVOICE", bill.id, buyer.bill_line(bill).id, "12", pack_size="12"
    )

    assert buyer.return_line(sent).pack_size == D("12.0000")


def test_a_return_line_in_pieces_not_typed_as_a_pair_still_holds_its_pack() -> None:
    """The pack is stored on every line of an item with one, however typed."""
    buyer = _Buyer()
    receipt = _received(buyer)

    sent = buyer.send_back(
        "GOODS_RECEIPT", receipt.id, buyer.receipt_line(receipt).id, "5"
    )

    assert buyer.return_line(sent).pack_size == D("12.0000")
    assert (
        PurchaseReturnService(buyer.session).return_response(sent).box_and_piece_entry
        is True
    )
