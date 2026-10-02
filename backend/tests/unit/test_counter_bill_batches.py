"""Choosing batches on a counter bill (backlog 79 row 2, decision A38).

A counter bill raises its own order and delivery note, and its approval
dispatches that note. The bill line's ``batches`` are handed to the note it
raises, as ``serial_ids`` are, so the chosen batch is the one that leaves;
on an edit they are restated on the note's line. Batches on a bill that bills
somebody else's note are refused -- that note chose its own.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.batch_serial.models.batch_serial import BatchRecord
from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNoteLineBatch
from app.delivery_note.schemas import DeliveryNoteBatchPick
from app.inventory.models import InventoryTransaction
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory


class _Counter(_Firm):
    """A counter firm with a batch-tracked product in two batches."""

    def __init__(self) -> None:
        """Stock EARLY and LATE, ten each, of a batch-tracked product."""
        super().__init__(_session_factory()())
        self.stages(quotation=False, sales_order=False, delivery_note=False)
        self.actor = uuid4()
        self.drug = Product(
            firm_id=self.firm.id,
            code="SKU-BATCH",
            name="Batched product",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            track_batch=True,
            track_expiry=True,
        )
        self.session.add(self.drug)
        self.session.commit()
        self.batches: dict[str, BatchRecord] = {}
        for number, expiry in (
            ("EARLY", date(2027, 1, 31)),
            ("LATE", date(2027, 9, 30)),
        ):
            batch = BatchRecord(
                firm_id=self.firm.id,
                product_id=self.drug.id,
                batch_number=number,
                expiry_date=expiry,
                status="AVAILABLE",
                created_by=self.actor,
                updated_by=self.actor,
            )
            self.session.add(batch)
            self.session.flush()
            self.batches[number] = batch
            InventoryService(self.session).record_goods_receipt(
                firm_scope=self.firm.id,
                actor_id=self.actor,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                storage_node_id=None,
                product_id=self.drug.id,
                reference_number=f"GRN-{number}",
                transaction_date=date(2026, 8, 1),
                total_quantity=Decimal("10"),
                unit_cost=Decimal("50"),
                batch_id=batch.id,
            )
        self.session.commit()
        self.bills = SalesInvoiceService(self.session)

    def bill(self, batches: list[DeliveryNoteBatchPick] | None) -> SalesInvoiceCreate:
        """Describe a counter sale of four, with these batches chosen."""
        return SalesInvoiceCreate(
            customer_id=self.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    product_id=self.drug.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    batches=batches,
                )
            ],
        )

    def pick(self, name: str, quantity: str = "4") -> DeliveryNoteBatchPick:
        """Name one batch and how much of it."""
        return DeliveryNoteBatchPick(
            batch_id=self.batches[name].id, quantity=Decimal(quantity)
        )

    def drawn(self) -> dict[str, Decimal]:
        """Return what dispatch drew of the batched product, by batch name."""
        names = {batch.id: name for name, batch in self.batches.items()}
        rows = self.session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH",
                InventoryTransaction.product_id == self.drug.id,
            )
        ).all()
        return {
            names[row.batch_id]: abs(row.current_quantity_delta)
            for row in rows
            if row.batch_id is not None
        }


def test_the_batch_chosen_on_a_counter_bill_is_the_one_that_leaves() -> None:
    """LATE chosen over EARLY: approval dispatches LATE, and the line says so."""
    shop = _Counter()

    draft = shop.bills.create_invoice(
        shop.bill([shop.pick("LATE")]), firm_id=shop.firm.id, actor_id=shop.actor
    )
    [line] = shop.bills.invoice_response(draft).lines
    assert [(pick.batch_id, pick.quantity) for pick in line.batches] == [
        (shop.batches["LATE"].id, Decimal("4.0000"))
    ]

    shop.bills.approve_invoice(draft.id, firm_scope=shop.firm.id, actor_id=shop.actor)

    assert shop.drawn() == {"LATE": Decimal("4.0000")}


def test_no_choice_still_draws_earliest_expiry_first() -> None:
    """A counter bill that names no batch behaves exactly as before."""
    shop = _Counter()
    draft = shop.bills.create_invoice(
        shop.bill(None), firm_id=shop.firm.id, actor_id=shop.actor
    )

    shop.bills.approve_invoice(draft.id, firm_scope=shop.firm.id, actor_id=shop.actor)

    assert shop.drawn() == {"EARLY": Decimal("4.0000")}


def test_an_edited_draft_restates_its_batches_on_its_own_note() -> None:
    """Change the choice on the draft: the note's line is what changes."""
    shop = _Counter()
    draft = shop.bills.create_invoice(
        shop.bill([shop.pick("LATE")]), firm_id=shop.firm.id, actor_id=shop.actor
    )
    [line] = shop.bills.invoice_response(draft).lines
    edited = SalesInvoiceCreate(
        customer_id=shop.customer.id,
        invoice_date=date(2026, 8, 4),
        lines=[
            SalesInvoiceLineWrite(
                source_document_type="DELIVERY_NOTE",
                source_document_id=line.source_document_id,
                source_document_line_id=line.source_document_line_id,
                line_number=1,
                current_invoice_quantity=Decimal("4"),
                unit_price=Decimal("100"),
                batches=[shop.pick("EARLY", "1"), shop.pick("LATE", "3")],
            )
        ],
    )

    shop.bills.update_invoice(
        draft.id, edited, firm_id=shop.firm.id, actor_id=shop.actor
    )
    shop.session.commit()

    stored = {
        row.batch_id: row.quantity
        for row in shop.session.scalars(
            select(DeliveryNoteLineBatch).where(
                DeliveryNoteLineBatch.delivery_note_line_id
                == line.source_document_line_id
            )
        )
    }
    assert stored == {
        shop.batches["EARLY"].id: Decimal("1.0000"),
        shop.batches["LATE"].id: Decimal("3.0000"),
    }
    shop.bills.approve_invoice(draft.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    assert shop.drawn() == {"EARLY": Decimal("1.0000"), "LATE": Decimal("3.0000")}


def test_another_products_batch_is_refused_by_line() -> None:
    """The same check the note's own editor makes, in the bill's words."""
    shop = _Counter()
    stranger = BatchRecord(
        firm_id=shop.firm.id,
        product_id=shop.product.id,
        batch_number="OTHER",
        status="AVAILABLE",
        created_by=shop.actor,
        updated_by=shop.actor,
    )
    shop.session.add(stranger)
    shop.session.commit()

    with pytest.raises(ValidationError, match="Line 1: that batch is not"):
        shop.bills.create_invoice(
            shop.bill(
                [DeliveryNoteBatchPick(batch_id=stranger.id, quantity=Decimal("4"))]
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )
