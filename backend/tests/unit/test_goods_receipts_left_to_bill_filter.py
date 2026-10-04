"""D-BUY-27: a new bill is offered only receipts with something left to bill.

The bill's receipt list was every completed receipt of the supplier, so a
receipt billed in full was offered beside unbilled ones, at its full value.
``GET /goods-receipts?billable=true`` keeps, in SQL, the receipts with goods
left to bill, and each carries the quantity and value that are left.
"""

from decimal import Decimal

import pytest

from app.goods_receipt.schemas import GoodsReceiptListFilters
from app.goods_receipt.services import GoodsReceiptService
from tests.unit.test_goods_receipt import _Fixture
from tests.unit.test_purchase_return_before_billing import (
    _bill,
    _left_to_bill,
    _received,
    _send_back,
)

pytestmark = pytest.mark.typed_document_numbers

D = Decimal


def _listed(fixture: _Fixture, *, billable: bool) -> list[tuple[str, D, D]]:
    """Return (grn, left quantity, left value) of the receipts the list gives."""
    service = GoodsReceiptService(fixture.session)
    rows, total = service.list_receipts(
        firm_scope=fixture.firm.id,
        filters=GoodsReceiptListFilters(billable=billable),
        page=1,
        page_size=50,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    responses = service.receipt_responses(rows)
    assert total == len(responses)
    return [
        (item.grn_number, item.left_to_bill_quantity, item.left_to_bill_amount)
        for item in responses
    ]


def test_billable_keeps_what_is_left_and_drops_what_is_billed_in_full() -> None:
    """Unbilled 6 is offered at 708; 2 sent back, 4 left at 472; billed, gone."""
    fixture, receipt = _received("LTB1")

    only = _listed(fixture, billable=True)
    assert [(q, a) for _, q, a in only] == [(D("6"), D("708.00"))]

    _send_back(fixture, receipt, "2")
    assert _left_to_bill(fixture, receipt) == (D("4"), D("472.00"))
    only = _listed(fixture, billable=True)
    assert [(q, a) for _, q, a in only] == [(D("4"), D("472.00"))]

    _bill(fixture, receipt, "4", number="SUP-4")
    assert _listed(fixture, billable=True) == []
    # Without the filter the receipt is still listed, with nothing left.
    everything = _listed(fixture, billable=False)
    assert len(everything) == 1
    assert everything[0][1:] == (D("0"), D("0.00"))


def test_a_draft_bill_does_not_use_up_a_receipt() -> None:
    """Only an approved bill has billed anything."""
    fixture, receipt = _received("LTB2")
    _bill(fixture, receipt, "6", number="SUP-D", approve=False)
    assert len(_listed(fixture, billable=True)) == 1


def test_a_cancelled_receipt_is_not_offered_for_billing() -> None:
    """D-BUY-30: it kept its quantities and was listed with them.

    The desktop asks for `status=COMPLETED` beside `billable=true`, so its tick
    list was right; the filter alone listed GRN-000001 and 000006 on QA01.
    """
    fixture, receipt = _received("LTB9")
    GoodsReceiptService(fixture.session).cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="wrong supplier",
    )
    assert _listed(fixture, billable=True) == []
