"""A lot's prices changed on its own page (L3 step 5).

`docs/design/LOT_MARGINS_DESIGN.md`, section 3.6: a firm costing by lot may
change a lot's two prices on the batch master without the BATCH_PTR_PTS
feature, the margins move with the prices, and the lot's answer carries its
margins and the MRP warning.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.batch_serial.schemas import BatchUpdate
from app.batch_serial.services import BatchSerialService
from app.goods_receipt.models import GoodsReceiptLine
from tests.unit.test_lot_receiving import _batches, _receive, _shop

pytestmark = pytest.mark.typed_document_numbers


def test_a_price_changed_on_the_lot_moves_its_margin() -> None:
    """130 on a cost of 100 is 30 %; 110 is 10 %; a price cleared, no margin."""
    fixture = _shop("LPP1", by_lot=True, track_batch=False)
    _receive(fixture, "4", ptr="130.00", pts="120.00")
    (lot,) = _batches(fixture.session)
    service = BatchSerialService(fixture.session)

    service.update_batch(
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        batch_id=lot.id,
        data=BatchUpdate(ptr=Decimal("110.00"), pts=None),
    )

    assert (lot.ptr, lot.retail_margin_percent) == (Decimal("110.00"), Decimal("10"))
    assert (lot.pts, lot.wholesale_margin_percent) == (None, None)
    answer = service.batch_response(lot, firm_scope=fixture.firm.id)
    assert answer.retail_margin_percent == Decimal("10")
    assert answer.wholesale_margin_percent is None


def test_the_lot_page_warns_above_the_mrp_with_tax() -> None:
    """The receipt line's tax is the rate judged: 130 at 18 % is 153.40."""
    fixture = _shop("LPP2", by_lot=True, track_batch=False)
    _receive(fixture, "4", ptr="130.00", pts="120.00", mrp="140.00")
    (lot,) = _batches(fixture.session)
    service = BatchSerialService(fixture.session)
    assert service.batch_response(lot, firm_scope=fixture.firm.id).mrp_warning is None
    line = fixture.session.scalars(select(GoodsReceiptLine)).one()
    line.tax_amount = Decimal("72")  # 18 % of 400
    fixture.session.commit()

    warning = service.batch_response(lot, firm_scope=fixture.firm.id).mrp_warning

    assert warning is not None
    assert "Retail price (PTR) 130.00 is 153.40 with tax" in warning
    assert "Wholesale price (PTS) 120.00 is 141.60 with tax" in warning
    service.update_batch(
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        batch_id=lot.id,
        data=BatchUpdate(ptr=Decimal("110.00"), pts=Decimal("100.00")),
    )
    assert service.batch_response(lot, firm_scope=fixture.firm.id).mrp_warning is None
