"""The lot's page and its trail (L2 step 11).

`docs/design/LOT_COST_DESIGN.md`, section 6 row 11: the lot's page with its
trace -- receipt, supplier's bill, sales, returns -- and cost shown only to
somebody allowed to see cost. The arrival comes first; quantities are signed
in the stock unit; a bill moves nothing and reads zero.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.batch_serial.api.router import get_lot_trail
from app.batch_serial.models import BatchRecord
from app.batch_serial.schemas.batch_serial import LotTrail
from app.batch_serial.services.lot_history import _sales_bills
from app.core.exceptions import ResourceNotFoundError
from app.goods_receipt.models import GoodsReceipt
from app.purchase_invoice.models import PurchaseInvoiceLine
from tests.unit.test_goods_receipt import _bill, _Fixture
from tests.unit.test_lot_cost_correction import _write_off
from tests.unit.test_lot_receiving import _receive, _shop
from tests.unit.test_lot_returns import _returned, _sold
from tests.unit.test_lot_selling import _ByLot
from tests.unit.test_sales_analysis_rest import _scope

# The receipt and return fixtures type their numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal
COST = "PRODUCT_VIEW_COST_PRICE"


def _bought() -> tuple[_Fixture, GoodsReceipt]:
    """Receive ten at 100, write four off, then the supplier bills 110."""
    fixture = _shop("LOTT1", by_lot=True, track_batch=False)
    receipt = _receive(fixture, "10")
    _write_off(fixture, "4")
    _bill(
        fixture.session,
        fixture,
        receipt,
        quantity="10",
        unit_price="110",
        supplier_number="S-1",
    )
    fixture.session.expire_all()
    return fixture, receipt


def _lot_of(fixture: _Fixture, receipt: GoodsReceipt) -> BatchRecord:
    """Return the lot the receipt made."""
    return fixture.session.scalars(
        select(BatchRecord).where(BatchRecord.source_document_id == receipt.id)
    ).one()


def _trail(session: object, firm_id: object, batch_id: object, *codes: str) -> LotTrail:
    """Call the route as a caller holding ``codes``."""
    return get_lot_trail(
        batch_id=batch_id,  # type: ignore[arg-type]
        scope=_scope(firm_id, "BATCH_VIEW", *codes),  # type: ignore[arg-type]
        db=session,  # type: ignore[arg-type]
    ).data


def test_the_receipt_comes_first_then_the_write_off_the_bill_and_its_cost() -> None:
    """In at 10, out 4, the bill at zero and the 60 it moved onto the lot."""
    fixture, receipt = _bought()
    lot = _lot_of(fixture, receipt)

    trail = _trail(fixture.session, fixture.firm.id, lot.id, COST)

    assert [(e.document_type, e.quantity) for e in trail.events] == [
        ("GOODS_RECEIPT", D("10")),
        ("ADJUSTMENT", D("-4")),
        ("PURCHASE_INVOICE", D("0")),
        ("COST_CORRECTION", D("0")),
    ]
    arrival, written_off, bill, correction = trail.events
    assert arrival.document_id == receipt.id
    assert arrival.document_number == receipt.grn_number
    assert arrival.party_name == "Vendor"
    assert arrival.cost_amount == D("1000")
    assert written_off.party_name is None
    assert written_off.cost_amount == D("400")
    [line] = fixture.session.scalars(select(PurchaseInvoiceLine)).all()
    assert bill.document_id == line.purchase_invoice_id
    assert bill.party_name == "Vendor"
    assert bill.line_number == 1
    assert bill.cost_amount == D(line.net_amount) - D(line.tax_amount)
    assert correction.document_id == line.purchase_invoice_id
    assert correction.cost_amount == D("60")
    assert trail.source_type == "GOODS_RECEIPT"
    assert trail.lot_reference == lot.lot_reference
    assert trail.received_on == lot.received_on
    assert trail.unit_cost == D("110")
    assert trail.batch.id == lot.id
    assert trail.batch.quantity == D("6")


def test_a_lot_with_no_printed_batch_says_so() -> None:
    """The goods carried none, so the lot reads has_printed_batch false."""
    fixture, receipt = _bought()

    trail = _trail(fixture.session, fixture.firm.id, _lot_of(fixture, receipt).id)

    assert trail.has_printed_batch is False


def test_without_the_cost_permission_every_cost_is_left_out() -> None:
    """The events stand; the unit cost and each event's amount are None."""
    fixture, receipt = _bought()

    trail = _trail(fixture.session, fixture.firm.id, _lot_of(fixture, receipt).id)

    assert len(trail.events) == 4
    assert trail.unit_cost is None
    assert all(event.cost_amount is None for event in trail.events)


def test_the_sale_its_bill_and_the_return_follow_the_arrivals() -> None:
    """EARLY: two receipts in, four out on the note, its bill, two back."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})
    return_id = _returned(shop, line, "6")
    early = shop.batches["EARLY"]

    trail = _trail(shop.session, shop.firm.id, early.id, COST)

    assert [(e.document_type, e.quantity) for e in trail.events] == [
        ("GOODS_RECEIPT", D("10")),
        ("GOODS_RECEIPT", D("10")),
        ("DELIVERY_NOTE", D("-4")),
        ("SALES_INVOICE", D("0")),
        ("SALES_RETURN", D("2")),
    ]
    _, _, note, bill, back = trail.events
    customer = shop.customer.display_name
    assert note.party_name == bill.party_name == back.party_name == customer
    assert note.cost_amount == D("160")
    assert bill.document_id == line.sales_invoice_id
    assert bill.line_number == 1
    # Half the line's taxable value: EARLY gave four of its eight.
    taxable = D(line.net_amount) - D(line.tax_amount)
    assert bill.cost_amount is not None
    assert bill.cost_amount.quantize(D("0.01")) == (taxable / 2).quantize(D("0.01"))
    assert back.document_id == return_id
    assert back.document_date == date(2026, 8, 6)
    assert trail.has_printed_batch is True


def test_a_bills_share_of_a_lot_is_shown_to_four_places() -> None:
    """D-STK-75: one of three units is a third of the line, to four places."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "1", "LATE": "2"})
    early = shop.batches["EARLY"]

    trail = _trail(shop.session, shop.firm.id, early.id, COST)

    [bill] = [e for e in trail.events if e.document_type == "SALES_INVOICE"]
    taxable = D(line.net_amount) - D(line.tax_amount)
    assert bill.cost_amount == (taxable / 3).quantize(D("0.0001"))
    assert bill.cost_amount.as_tuple().exponent == -4


def test_another_firms_lot_is_not_found() -> None:
    """A lot is read only inside the firm that owns it."""
    fixture, receipt = _bought()

    with pytest.raises(ResourceNotFoundError):
        _trail(fixture.session, uuid4(), _lot_of(fixture, receipt).id, COST)


class _PostgresSums:
    """A session answering the bill query as PostgreSQL does, unrounded.

    SQLite hands the sum back through the column's four-place type, so the
    suite's own database cannot show the 24 places PostgreSQL returns.
    """

    def execute(self, statement: object) -> "_PostgresSums":
        """Accept the bill query."""
        return self

    def all(self) -> list[tuple[object, ...]]:
        """Return one bill line whose share ran to 24 places."""
        return [
            (
                uuid4(),
                "SI-1",
                date(2026, 8, 4),
                uuid4(),
                datetime(2026, 8, 4, tzinfo=UTC),
                1,
                D("33.333333333333333333333333"),
            )
        ]


def test_an_unrounded_share_from_the_database_is_rounded_to_four() -> None:
    """D-STK-75: the bill's share is quantized, whatever the database returns."""
    [event] = _sales_bills(_PostgresSums(), uuid4(), uuid4())  # type: ignore[arg-type]
    assert event.cost_amount == D("33.3333")
