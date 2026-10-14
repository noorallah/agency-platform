"""Returns by lot (L2 step 6).

`docs/design/LOT_COST_DESIGN.md`, sections 3.2, 3.5 and 4.2. A firm costing
by lot takes a customer's goods back into the lots the source line shipped,
the last taken first refilled, each at the cost its units left with; a
cancel takes out exactly what came in. A purchase return leaves the lot its
receipt line made. A firm on Average returns exactly as before.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.core.exceptions import ValidationError
from app.delivery_note.schemas import DeliveryNoteBatchPick
from app.goods_receipt.models import GoodsReceiptLine
from app.inventory.models import BatchValuation, InventoryTransaction
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services import PurchaseReturnService
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_return.models import SalesReturnLine, SalesReturnLineBatch
from app.sales_return.schemas import SalesReturnCreate
from app.sales_return.services import SalesReturnService
from tests.unit.test_lot_receiving import _batches, _receive, _shop, _worth
from tests.unit.test_lot_selling import _ByLot

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _sold(shop: _ByLot, picks: dict[str, str]) -> SalesInvoiceLine:
    """Bill one line drawn from these lots and approve it; return the line."""
    quantity = sum((Decimal(value) for value in picks.values()), Decimal("0"))
    invoice_id = shop.approved(
        SalesInvoiceCreate(
            customer_id=shop.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    product_id=shop.drug.id,
                    line_number=1,
                    current_invoice_quantity=quantity,
                    unit_price=Decimal("100"),
                    batches=[
                        DeliveryNoteBatchPick(
                            batch_id=shop.batches[name].id, quantity=Decimal(value)
                        )
                        for name, value in picks.items()
                    ],
                )
            ],
        )
    )
    return shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice_id)
    ).one()


def _returned(
    shop: _ByLot, line: SalesInvoiceLine, quantity: str, **extra: object
) -> UUID:
    """Return part of a bill line and complete it; return the return's id."""
    service = SalesReturnService(shop.session)
    row = service.create_return(
        SalesReturnCreate.model_validate(
            {
                "warehouse_id": shop.warehouse.id,
                "return_date": date(2026, 8, 6),
                "lines": [
                    {
                        "source_document_type": "SALES_INVOICE",
                        "source_document_id": line.sales_invoice_id,
                        "source_document_line_id": line.id,
                        "line_number": 1,
                        "current_return_quantity": quantity,
                    }
                    | extra
                ],
            }
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    service.approve_return(row.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    service.complete_return(row.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    shop.session.expire_all()
    return row.id


def _lots_back(shop: _ByLot, return_id: UUID) -> dict[str, tuple[Decimal, Decimal]]:
    """Return what each lot took back on one return, by batch number."""
    rows = shop.session.execute(
        select(BatchRecord.batch_number, SalesReturnLineBatch)
        .join(BatchRecord, BatchRecord.id == SalesReturnLineBatch.batch_id)
        .join(
            SalesReturnLine,
            SalesReturnLine.id == SalesReturnLineBatch.sales_return_line_id,
        )
        .where(
            SalesReturnLine.sales_return_id == return_id,
            SalesReturnLineBatch.is_deleted.is_(False),
        )
    ).all()
    return {
        number: (Decimal(row.quantity), Decimal(row.cost_amount or 0))
        for number, row in rows
    }


def _lot_worth(shop: _ByLot, name: str) -> tuple[Decimal, Decimal]:
    """Return what one lot holds and is worth."""
    row = shop.session.scalars(
        select(BatchValuation).where(BatchValuation.batch_id == shop.batches[name].id)
    ).one()
    return Decimal(row.quantity_on_hand), Decimal(row.total_value)


def test_the_last_lot_taken_is_the_first_refilled_at_its_own_cost() -> None:
    """Four from EARLY at 40 and four from LATE at 36 went; six come back.

    LATE left last, so it takes its four back at 36 (144) and EARLY two at
    40 (80): 224 back into stock, not six at either lot's figure.
    """
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})

    return_id = _returned(shop, line, "6")

    assert _lots_back(shop, return_id) == {
        "LATE": (Decimal("4"), Decimal("144")),
        "EARLY": (Decimal("2"), Decimal("80")),
    }
    assert _lot_worth(shop, "LATE") == (Decimal("10"), Decimal("360"))
    assert _lot_worth(shop, "EARLY") == (Decimal("8"), Decimal("320"))
    movements = shop.session.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.transaction_type == "SALES_RETURN"
        )
    ).all()
    assert {movement.batch_id for movement in movements} == {
        shop.batches["EARLY"].id,
        shop.batches["LATE"].id,
    }


def test_a_second_return_refills_only_what_the_first_left() -> None:
    """After six came back, the last two of the eight go into EARLY."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})
    _returned(shop, line, "6")

    second = _returned(shop, line, "2")

    assert _lots_back(shop, second) == {"EARLY": (Decimal("2"), Decimal("80"))}
    assert _lot_worth(shop, "EARLY") == (Decimal("10"), Decimal("400"))


def test_cancelling_the_return_takes_out_what_came_in() -> None:
    """Both lots go back to what they held before the return, to the paisa."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})
    before = (_lot_worth(shop, "EARLY"), _lot_worth(shop, "LATE"))
    return_id = _returned(shop, line, "6")

    SalesReturnService(shop.session).cancel_return(
        return_id, firm_scope=shop.firm.id, actor_id=shop.actor, reason="wrong"
    )
    shop.session.expire_all()

    assert (_lot_worth(shop, "EARLY"), _lot_worth(shop, "LATE")) == before
    assert _lots_back(shop, return_id) == {}
    # And the goods may come back again, into the same lots.
    again = _returned(shop, line, "6")
    assert _lots_back(shop, again) == {
        "LATE": (Decimal("4"), Decimal("144")),
        "EARLY": (Decimal("2"), Decimal("80")),
    }


def test_a_named_batch_goes_back_only_into_that_lot() -> None:
    """Three named EARLY go into EARLY, though LATE left last."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})

    return_id = _returned(shop, line, "3", batch_number="EARLY")

    assert _lots_back(shop, return_id) == {"EARLY": (Decimal("3"), Decimal("120"))}


def test_a_batch_the_line_did_not_ship_is_refused() -> None:
    """Goods sold from EARLY cannot come back into LATE."""
    shop = _ByLot()
    line = _sold(shop, {"EARLY": "4"})

    with pytest.raises(ValidationError, match="did not leave on the delivery"):
        _returned(shop, line, "2", batch_number="LATE")


def test_a_firm_on_average_returns_as_before() -> None:
    """One movement, no lot named, at the average."""
    shop = _ByLot(by_lot=False)
    line = _sold(shop, {"EARLY": "4", "LATE": "4"})

    return_id = _returned(shop, line, "6")

    [movement] = shop.session.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.transaction_type == "SALES_RETURN"
        )
    ).all()
    assert movement.batch_id is None
    assert _lots_back(shop, return_id) == {}


def test_a_purchase_return_leaves_the_lot_its_receipt_made() -> None:
    """Goods with no printed batch go back out of the second delivery's lot.

    They carry no number, so before step 6 the return named no batch and
    took the goods off the item's untracked stock, which held none.
    """
    fixture = _shop("LOTR1", by_lot=True, track_batch=False)
    _receive(fixture, "4")
    second = _receive(fixture, "4", unit_price="80")
    first_lot, second_lot = _batches(fixture.session)
    receipt_line = fixture.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == second.id)
    ).one()
    service = PurchaseReturnService(fixture.session)
    row = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-RET-1",
            supplier_return_date=date(2026, 8, 6),
            return_date=date(2026, 8, 6),
            warehouse_id=fixture.warehouse.id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": second.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=second.id,
                    source_document_line_id=receipt_line.id,
                    line_number=1,
                    current_return_quantity=Decimal("2"),
                    warehouse_id=fixture.warehouse.id,
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.approve_return(
        row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.complete_return(
        row.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.expire_all()

    assert _worth(fixture.session, second_lot) == (Decimal("2"), Decimal("160"))
    assert _worth(fixture.session, first_lot) == (Decimal("4"), Decimal("400"))
