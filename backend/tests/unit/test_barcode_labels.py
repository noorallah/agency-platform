"""Price and barcode labels for products and receipts (STK-16, decision A65).

A label carries the product's barcode, else its code; a sheet holds 65 or 24
of them and a thermal roll one per page; a partly used sheet is fed again
with the used positions skipped; and a goods receipt labels every piece it
stocked, with the delivery's batch, expiry and MRP.
"""

# ruff: noqa: D103

import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.goods_receipt.api.router import goods_receipt_labels
from app.goods_receipt.services import GoodsReceiptService
from app.products.api.router import print_product_labels
from app.products.schemas.labels import ProductLabelRequest
from app.products.services.barcode_labels import (
    MAX_LABELS,
    BarcodeLabelRenderer,
    BarcodeLabelService,
    LabelContent,
    LabelLayout,
    LabelRequestItem,
    barcode_value,
)
from tests.unit.test_goods_receipt import _Fixture, _session_factory

pytestmark = pytest.mark.typed_document_numbers


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", pdf))


def _label(copies: int) -> LabelContent:
    return LabelContent(
        name="Paracetamol 500 mg strip of 10",
        barcode="8901234567890",
        mrp=Decimal("32.50"),
        price=Decimal("30"),
        batch_number="B-17",
        expiry_date=date(2027, 3, 31),
        copies=copies,
    )


@pytest.mark.parametrize(
    ("layout", "copies", "skip", "pages"),
    [
        (LabelLayout.A4_65, 65, 0, 1),
        (LabelLayout.A4_65, 66, 0, 2),
        (LabelLayout.A4_65, 60, 6, 2),
        (LabelLayout.A4_65, 60, 5, 1),
        (LabelLayout.A4_24, 25, 0, 2),
        (LabelLayout.ROLL_50X25, 3, 0, 3),
    ],
)
def test_labels_fill_the_stock_page_by_page(
    layout: LabelLayout, copies: int, skip: int, pages: int
) -> None:
    pdf = BarcodeLabelRenderer(layout).render([_label(copies)], skip=skip)
    assert pdf.startswith(b"%PDF")
    assert _pages(pdf) == pages


def test_skip_past_the_sheet_and_too_many_labels_are_refused() -> None:
    renderer = BarcodeLabelRenderer(LabelLayout.A4_24)
    with pytest.raises(ValidationError, match="between 0 and 23"):
        renderer.render([_label(1)], skip=24)
    with pytest.raises(ValidationError, match=f"at most {MAX_LABELS}"):
        renderer.render([_label(MAX_LABELS + 1)])
    with pytest.raises(ValidationError, match="nothing to print"):
        renderer.render([])


def test_a_roll_ignores_skip() -> None:
    pdf = BarcodeLabelRenderer(LabelLayout.ROLL_50X25).render([_label(2)], skip=9)
    assert _pages(pdf) == 2


def test_a_long_barcode_is_narrowed_to_fit_the_label() -> None:
    label = LabelContent(name="X", barcode="A" * 40, mrp=None, price=None, copies=1)
    pdf = BarcodeLabelRenderer(LabelLayout.A4_65).render([label])
    assert _pages(pdf) == 1


def test_the_barcode_falls_back_to_the_code_and_refuses_what_it_cannot_encode() -> None:
    fixture = _Fixture(_session_factory()(), "LBL1")
    product = fixture.product
    product.barcode = None
    assert barcode_value(product) == "SKU-LBL1"
    product.barcode = " 8901234567890 "
    assert barcode_value(product) == "8901234567890"
    product.barcode = "दवा"
    with pytest.raises(ValidationError, match="no barcode or code"):
        barcode_value(product)


def test_product_labels_print_through_the_route() -> None:
    fixture = _Fixture(_session_factory()(), "LBL2")
    fixture.product.mrp = Decimal("120")
    fixture.product.selling_price = Decimal("110")
    fixture.session.commit()
    scope = type("Scope", (), {"firm_id": fixture.firm.id})()

    response = print_product_labels(
        ProductLabelRequest.model_validate(
            {
                "items": [{"product_id": str(fixture.product.id), "copies": 3}],
                "layout": "ROLL_50X25",
            }
        ),
        scope,  # type: ignore[arg-type]
        fixture.session,
    )
    assert response.media_type == "application/pdf"

    with pytest.raises(ResourceNotFoundError):
        BarcodeLabelService(fixture.session).product_labels(
            [LabelRequestItem(uuid4(), 1)],
            firm_id=fixture.firm.id,
            layout=LabelLayout.A4_65,
        )


def test_a_receipt_labels_every_piece_with_its_batch_and_mrp() -> None:
    fixture = _Fixture(_session_factory()(), "LBL3")
    fixture.product.mrp = Decimal("120")
    fixture.product.selling_price = Decimal("110")
    # The free piece is the order's to give (D-BUY-67).
    fixture.order_line.free_quantity = Decimal("1")
    fixture.session.commit()
    payload = fixture.receipt_payload("4")
    data = payload.model_dump()
    data["lines"][0].update(
        batch_number="B-901",
        expiry_date=date(2027, 6, 30),
        mrp=Decimal("125"),
        free_quantity=Decimal("1"),
    )
    receipt = GoodsReceiptService(fixture.session).create_receipt(
        type(payload).model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    labels, number = BarcodeLabelService(fixture.session).receipt_label_contents(
        receipt.id, firm_id=fixture.firm.id
    )
    assert number == receipt.grn_number
    [label] = labels
    assert label.copies == 5
    assert label.batch_number == "B-901"
    assert label.expiry_date == date(2027, 6, 30)
    assert label.mrp == Decimal("125")
    assert label.price == Decimal("110")

    hidden, _ = BarcodeLabelService(fixture.session).receipt_label_contents(
        receipt.id, firm_id=fixture.firm.id, show_price=False
    )
    assert hidden[0].price is None

    scope = type("Scope", (), {"firm_id": fixture.firm.id})()
    response = goods_receipt_labels(
        receipt.id,
        scope,  # type: ignore[arg-type]
        LabelLayout.A4_24,
        0,
        True,
        fixture.session,
    )
    assert response.media_type == "application/pdf"


def test_a_cancelled_receipt_has_nothing_to_label() -> None:
    fixture = _Fixture(_session_factory()(), "LBL4")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    receipt.status = "CANCELLED"
    fixture.session.commit()
    with pytest.raises(ValidationError, match="cancelled"):
        BarcodeLabelService(fixture.session).receipt_label_contents(
            receipt.id, firm_id=fixture.firm.id
        )
