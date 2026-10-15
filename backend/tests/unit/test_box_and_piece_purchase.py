"""A purchase order and goods receipt typed as boxes and pieces (L5 step 6).

`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.4, 3.6 and section 5. An
order line is written at the item's buying pack, a receipt line comes in at
its order line's, so 10 boxes ordered at 12 to a box are received so after
the box moved to 10. The supplier's minimum and multiple count boxes for a
line typed as boxes and pieces, and a rate contract kept per box prices it
at the box's rate over the pieces in a box and draws boxes, not pieces.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.purchase.models import PurchaseOrder
from app.purchase.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseWorkflowSettingsWrite,
)
from app.purchase.services import PurchaseService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.rate_contracts.models import RateContract
from app.rate_contracts.schemas import RateContractCreate
from app.rate_contracts.services import RateContractService
from app.uom.models import ConversionRule
from app.vendors.schemas.supplier_product import SupplierProductWrite
from app.vendors.services.supplier_catalogue import SupplierCatalogueService
from tests.unit.test_purchase_lines_in_another_unit import DAY, _Buyer

D = Decimal


def _worked_example(buyer: _Buyer, *, approve: bool = True) -> PurchaseOrder:
    """Order 10 boxes + 0 pieces at 8.00 a piece, free 1 box, as typed."""
    service = PurchaseService(buyer.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            buyer.order_payload(
                ordered_quantity="120",
                free_quantity="12",
                unit_price="8",
                pack_size="12",
            )
            | {"box_and_piece_entry": True}
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    if approve:
        service.submit_order(order.id, firm_scope=buyer.firm_id, actor_id=buyer.actor)
        service.approve_order(order.id, firm_scope=buyer.firm_id, actor_id=buyer.actor)
    return order


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


def test_the_worked_example_comes_in_as_132_pieces_at_7_27() -> None:
    """120 bought and 12 free at 8.00: 960.00, and 132 in at 960.00 / 132."""
    buyer = _Buyer()

    order = _worked_example(buyer)

    line = buyer.order_line(order)
    # A line typed as boxes and pieces is in pieces, though it named no unit
    # and the item is bought by the box.
    assert (line.purchase_uom_id, line.ordered_quantity) == (buyer.piece, D("120"))
    assert (line.pack_uom_id, line.pack_size) == (buyer.box, D("12.0000"))
    assert line.gross_amount == D("960.0000")
    answered = PurchaseService(buyer.session).order_response(order)
    assert answered.box_and_piece_entry is True
    assert (answered.lines[0].pack_uom_id, answered.lines[0].pack_size) == (
        buyer.box,
        D("12.0000"),
    )

    receipt = buyer.receive(order, "120", free_quantity="12", pack_size="12")

    received = buyer.receipt_line(receipt)
    assert (received.pack_uom_id, received.pack_size) == (buyer.box, D("12.0000"))
    assert received.gross_amount == D("960.0000")
    pieces, unit_cost, value = buyer.movement(received.inventory_transaction_id)
    assert (pieces, value) == (D("132.0000"), D("960.0000"))
    assert unit_cost.quantize(D("0.01")) == D("7.27")
    assert buyer.receipt_line(receipt).goods_receipt_id == receipt.id
    buyer.session.refresh(receipt)
    assert receipt.box_and_piece_entry is True


def test_a_line_added_up_at_another_pack_size_is_refused() -> None:
    """The item row the screen read went stale: 10 to a box sent, 12 held."""
    buyer = _Buyer()

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        buyer.order(ordered_quantity="120", unit_price="8", pack_size="10")


def test_a_line_typed_as_boxes_and_pieces_cannot_name_the_box() -> None:
    """A pair line is counted in pieces, so naming the box is refused."""
    buyer = _Buyer()

    with pytest.raises(ValidationError, match="counted in the item's stock unit"):
        buyer.order(
            ordered_quantity="120",
            unit_price="8",
            pack_size="12",
            purchase_uom_id=str(buyer.box),
        )


def test_a_line_in_pieces_not_typed_as_a_pair_still_holds_its_pack() -> None:
    """The pack is stored on every line of an item with one, however typed."""
    buyer = _Buyer()

    order = buyer.order(
        ordered_quantity="7", unit_price="8", purchase_uom_id=str(buyer.piece)
    )

    line = buyer.order_line(order)
    assert (line.purchase_uom_id, line.ordered_quantity) == (buyer.piece, D("7"))
    assert (line.pack_uom_id, line.pack_size) == (buyer.box, D("12.0000"))
    assert PurchaseService(buyer.session).order_response(order).box_and_piece_entry is (
        False
    )


def test_a_receipt_after_the_box_changes_comes_in_at_the_orders_pack() -> None:
    """Ordered at 12 to a box, received at 12 once the box holds 10."""
    buyer = _Buyer()
    order = _worked_example(buyer)
    _ten_to_a_box_from(buyer, DAY)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        buyer.receive(order, "24", pack_size="10")
    receipt = buyer.receive(order, "24", pack_size="12")

    received = buyer.receipt_line(receipt)
    assert (received.pack_uom_id, received.pack_size) == (buyer.box, D("12.0000"))
    # A new order is written at the box of the day.
    fresh = buyer.order(ordered_quantity="20", unit_price="8", pack_size="10")
    assert buyer.order_line(fresh).pack_size == D("10.0000")


def test_a_saved_draft_order_keeps_its_pack_after_the_box_changes() -> None:
    """A draft saved at 12 to a box still reads 12 when it is saved again."""
    buyer = _Buyer()
    order = _worked_example(buyer, approve=False)
    _ten_to_a_box_from(buyer, DAY)
    service = PurchaseService(buyer.session)
    body = buyer.order_payload(ordered_quantity="120", unit_price="8", pack_size="12")

    service.update_order(
        order.id,
        PurchaseOrderUpdate.model_validate(body),
        firm_scope=buyer.firm_id,
        actor_id=buyer.actor,
    )

    assert buyer.order_line(order).pack_size == D("12.0000")
    # Absent on an edit keeps the layout the order was saved in.
    assert service.order_response(order).box_and_piece_entry is True


def _minimum_five_boxes(buyer: _Buyer) -> None:
    """Have the supplier sell from 5 boxes, and the firm refuse less."""
    SupplierCatalogueService(buyer.session).add(
        buyer.firm.vendor.id,
        SupplierProductWrite(
            product_id=buyer.firm.product.id,
            minimum_order_quantity=D("5"),
            effective_from=date(2026, 4, 1),
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    PurchaseWorkflowService(buyer.session).update_settings(
        PurchaseWorkflowSettingsWrite(
            purchase_order_stage=True,
            goods_receipt_stage=True,
            order_quantity_policy="REFUSE",
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )


def test_the_suppliers_minimum_counts_boxes_on_a_line_typed_as_a_pair() -> None:
    """3 boxes + 5 is short of 5 boxes; 60 pieces would do; 5 BOX still does."""
    buyer = _Buyer()
    _minimum_five_boxes(buyer)

    with pytest.raises(ValidationError, match=r"minimum 5 boxes of 12\); 60 would do"):
        buyer.order(
            approve=False, ordered_quantity="41", unit_price="8", pack_size="12"
        )
    buyer.order(approve=False, ordered_quantity="60", unit_price="8", pack_size="12")
    # A line in BOX is judged as it always was.
    buyer.order(approve=False, ordered_quantity="5", purchase_uom_id=str(buyer.box))


def test_the_preview_says_the_minimum_in_boxes_and_the_fix_in_pieces() -> None:
    """The warning the editor shows is the same sum as the refusal."""
    buyer = _Buyer()
    _minimum_five_boxes(buyer)

    preview = PurchaseService(buyer.session).preview_order(
        PurchaseOrderCreate.model_validate(
            buyer.order_payload(ordered_quantity="41", unit_price="8", pack_size="12")
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )

    (hint,) = preview.quantity_hints
    assert (hint.quantity, hint.suggested_quantity) == (D("41"), D("60"))
    assert "minimum 5 boxes of 12" in hint.message


def _contract_per_box(buyer: _Buyer) -> RateContract:
    """Agree 96.00 a box, 10 boxes, with the supplier."""
    service = RateContractService(buyer.session)
    row = service.create(
        RateContractCreate.model_validate(
            {
                "vendor_id": buyer.firm.vendor.id,
                "valid_from": "2026-04-01",
                "valid_to": "2027-03-31",
                "reference": "PER-BOX",
                "lines": [
                    {
                        "product_id": buyer.firm.product.id,
                        "uom_id": str(buyer.box),
                        "rate": "96",
                        "contracted_quantity": "10",
                    }
                ],
            }
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    return service.approve(row.id, firm_id=buyer.firm_id, actor_id=buyer.actor)


def test_a_contract_per_box_prices_a_pair_line_per_piece_and_draws_boxes() -> None:
    """96.00 a box is 8.00 a piece; 120 pieces draw 10 boxes, not 120."""
    buyer = _Buyer()
    contract = _contract_per_box(buyer)

    order = buyer.order(ordered_quantity="120", pack_size="12", unit_price=None)

    line = buyer.order_line(order)
    assert (line.unit_price, line.rate_source) == (D("8.0000"), "RATE_CONTRACT")
    assert line.gross_amount == D("960.0000")
    service = RateContractService(buyer.session)
    (answer,) = service.responses([service.get(contract.id, firm_id=buyer.firm_id)])
    assert answer.lines[0].drawn_quantity == D("10")
    # Within the 10 contracted, so no warning.
    assert (
        PurchaseService(buyer.session).order_response(order).rate_contract_warning
        is None
    )
    # One more box, as pieces, takes it past the contract and says so in boxes.
    more = buyer.order(
        approve=False, ordered_quantity="12", pack_size="12", unit_price=None
    )
    warning = PurchaseService(buyer.session).order_response(more).rate_contract_warning
    assert warning is not None and "11 drawn of 10 contracted" in warning


def test_a_line_in_pieces_not_typed_as_a_pair_is_not_priced_from_a_box_contract() -> (
    None
):
    """As before L5: the contract's unit is not the line's, so it is not read."""
    buyer = _Buyer()
    _contract_per_box(buyer)

    order = buyer.order(
        ordered_quantity="120", purchase_uom_id=str(buyer.piece), unit_price=None
    )

    line = buyer.order_line(order)
    assert line.rate_source != "RATE_CONTRACT"
    assert line.rate_contract_line_id is None
