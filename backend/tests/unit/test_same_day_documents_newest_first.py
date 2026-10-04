"""D-UI-10: a day's documents are listed newest first, not in id order.

Found in purchasing round 2 on QA01: the receipts list, sorted by receipt
date, read 07, 09, 05, 08, 06 -- every receipt was dated that day, and the only
tie-break was the id, which is random. Six of the eight document lists already
broke a tie on `created_at`; the goods receipt and purchase invoice lists did
not.
"""

from datetime import timedelta

import pytest

from app.core.utils.dates import utc_now
from app.goods_receipt.schemas import GoodsReceiptListFilters
from app.goods_receipt.services import GoodsReceiptService
from tests.unit.test_purchase_return_before_billing import _received

pytestmark = pytest.mark.typed_document_numbers


def test_receipts_of_one_day_list_newest_first() -> None:
    """Six receipts dated alike come back in the order they were made, newest first."""
    fixture, first = _received("SDN1", "1")
    receipts = GoodsReceiptService(fixture.session)
    made = [first]
    for _ in range(5):
        receipt = receipts.create_receipt(
            fixture.receipt_payload("1"),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
        made.append(receipt)
    start = utc_now() - timedelta(hours=1)
    for minutes, receipt in enumerate(made):
        receipt.created_at = start + timedelta(minutes=minutes)
    fixture.session.commit()

    rows, _ = receipts.list_receipts(
        firm_scope=fixture.firm.id,
        filters=GoodsReceiptListFilters(),
        page=1,
        page_size=50,
        search=None,
        sort_by="receipt_date",
        descending=True,
    )
    assert [row.id for row in rows] == [row.id for row in reversed(made)]
