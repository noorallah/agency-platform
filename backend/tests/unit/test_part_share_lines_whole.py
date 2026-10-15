"""A part share of an offer moves whole (design section 3.7).

5.5 charged and 0.5 free is six whole pieces. Half of it is no number of
pieces, so a note and a bill take all of such a line at once, and a return of
part of it comes back in the line's own proportion: 3 of the 6 are 2.75
charged and 0.25 free, where "charged first" credited 3 of the 2.75 paid for.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.finance.services.opening_setup import seed_finance_setup
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesOrderOffer
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_order.services.part_share import part_share_order_lines
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services import SalesReturnService
from app.uom.models import Uom
from app.uom.services import counts_in_whole_numbers
from tests.unit.test_sales_invoice_module import (
    _branch,
    _customer,
    _firm,
    _product,
    _session_factory,
    _warehouse,
)

PRICE = Decimal("100")
CHARGED = Decimal("5.5")
FREE = Decimal("0.5")


class _PartShare:
    """An approved order of 5.5 charged and 0.5 free, in whole pieces."""

    def __init__(self, *, marked: bool = True) -> None:
        """Build the masters, raise and approve the order, and mark its line."""
        session = _session_factory()()
        self.session = session
        self.firm = _firm(session)
        self.branch = _branch(session, firm_id=self.firm.id)
        self.warehouse = _warehouse(
            session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.customer = _customer(session, firm_id=self.firm.id)
        self.product = _product(session, firm_id=self.firm.id)
        piece = Uom(
            code="PIECE",
            name="Piece",
            dimension="COUNT",
            status="ACTIVE",
            is_decimal_allowed=False,
        )
        session.add(piece)
        session.flush()
        self.product.base_uom_id = piece.id
        self.product.inventory_uom_id = piece.id
        session.commit()
        InventoryService(session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                product_id=self.product.id,
                quantity=Decimal("100"),
                reference_number="ADJ-PART",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 3),
            ),
            firm_scope=self.firm.id,
            actor_id=uuid4(),
        )
        orders = SalesOrderService(session)
        self.order: SalesOrder = orders.create_order(
            SalesOrderCreate(
                customer_id=self.customer.id,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                order_date=date(2026, 8, 3),
                lines=[
                    SalesOrderLineWrite(
                        line_number=1,
                        product_id=self.product.id,
                        quantity=CHARGED,
                        free_quantity=FREE,
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=uuid4(),
        )
        line = session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == self.order.id)
        )
        assert line is not None
        self.order_line = line
        if marked:
            session.add(
                SalesOrderOffer(
                    firm_id=self.firm.id,
                    sales_order_id=self.order.id,
                    sales_order_line_id=line.id,
                    source="promotion",
                    code="B10G1",
                    name="Buy 10 get 1",
                    state="APPLIED",
                    free_quantity=FREE,
                    discount_amount=Decimal("0"),
                    part_share=True,
                )
            )
            session.commit()
        orders.approve_order(self.order.id, firm_scope=self.firm.id, actor_id=uuid4())

    def note(
        self, quantity: Decimal, free: Decimal | None, *, dispatch: bool = True
    ) -> DeliveryNote:
        """Raise a note of the order line, approved and dispatched."""
        notes = DeliveryNoteService(self.session)
        note = notes.create_note(
            DeliveryNoteCreate(
                sales_order_id=self.order.id,
                delivery_date=date(2026, 8, 4),
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=self.order_line.id,
                        line_number=1,
                        current_delivery_quantity=quantity,
                        free_quantity=free,
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=uuid4(),
        )
        if dispatch:
            notes.approve_note(note.id, firm_scope=self.firm.id, actor_id=uuid4())
            notes.dispatch_note(note.id, firm_scope=self.firm.id, actor_id=uuid4())
        return note

    def note_line(self, note: DeliveryNote) -> DeliveryNoteLine:
        """Return the note's only line."""
        line = self.session.scalar(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
        assert line is not None
        return line

    def bill(
        self, note: DeliveryNote, quantity: Decimal, free: Decimal | None = None
    ) -> SalesInvoice:
        """Bill the note's line."""
        return SalesInvoiceService(self.session).create_invoice(
            SalesInvoiceCreate(
                customer_id=self.customer.id,
                branch_id=self.branch.id,
                invoice_date=date(2026, 8, 5),
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                        source_document_line_id=self.note_line(note).id,
                        line_number=1,
                        current_invoice_quantity=quantity,
                        free_quantity=free,
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=uuid4(),
        )

    def returned(
        self,
        *,
        source_type: SalesReturnSourceType,
        document_id: UUID,
        line_id: UUID,
        quantity: Decimal,
        free: Decimal | None = None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Raise a return and give its line's whole quantity, free and gross."""
        service = SalesReturnService(self.session)
        row = service.create_return(
            SalesReturnCreate(
                warehouse_id=self.warehouse.id,
                return_date=date(2026, 8, 6),
                lines=[
                    SalesReturnLineWrite(
                        source_document_type=source_type,
                        source_document_id=document_id,
                        source_document_line_id=line_id,
                        line_number=1,
                        current_return_quantity=quantity,
                        free_quantity=free,
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=uuid4(),
        )
        line = service.return_response(row).lines[0]
        return line.current_return_quantity, line.free_quantity, line.gross_amount


def test_the_marking_is_read_in_one_statement_and_an_empty_question_asks_none() -> None:
    """Only live part-share rows count, and nothing asked is nothing read."""
    setup = _PartShare()

    assert (
        part_share_order_lines(setup.session, firm_id=setup.firm.id, order_line_ids=[])
        == set()
    )
    assert part_share_order_lines(
        setup.session,
        firm_id=setup.firm.id,
        order_line_ids=[setup.order_line.id, uuid4()],
    ) == {setup.order_line.id}
    assert counts_in_whole_numbers(
        setup.session,
        uom_id=None,
        product_id=setup.product.id,
        firm_id=setup.firm.id,
    )


def test_a_note_of_part_of_a_part_share_line_is_refused() -> None:
    """Three of six whole pieces is a fraction of the offer's share."""
    setup = _PartShare()

    with pytest.raises(ValidationError) as refused:
        setup.note(Decimal("3"), Decimal("0"), dispatch=False)

    assert (
        "Line 1 is a part share of an offer (5.5 + 0.5 free): it is delivered "
        "whole, all 6 at once." in str(refused.value)
    )


def test_a_note_of_the_whole_part_share_line_is_accepted() -> None:
    """All six at once ship, the free half inherited from the order."""
    setup = _PartShare()

    note = setup.note(CHARGED, None)

    line = setup.note_line(note)
    assert line.current_delivery_quantity == CHARGED
    assert line.free_quantity == FREE


def test_an_unmarked_line_still_ships_in_parts() -> None:
    """A line no offer gave as a part share splits as it always did."""
    setup = _PartShare(marked=False)

    note = setup.note(Decimal("3"), Decimal("0"))

    assert setup.note_line(note).current_delivery_quantity == Decimal("3")


def test_a_part_bill_of_a_part_share_line_is_refused() -> None:
    """The note shipped six whole; a bill of three of them is refused."""
    setup = _PartShare()
    note = setup.note(CHARGED, None)

    with pytest.raises(ValidationError) as refused:
        setup.bill(note, Decimal("3"), Decimal("0"))

    assert "it is billed whole, all 6 at once" in str(refused.value)


def test_the_whole_bill_of_a_part_share_line_is_accepted() -> None:
    """5.5 charged and the 0.5 free carried: all of the line, once."""
    setup = _PartShare()
    note = setup.note(CHARGED, None)

    invoice = setup.bill(note, CHARGED)

    line = setup.session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    )
    assert line is not None
    assert line.current_invoice_quantity == CHARGED
    assert line.free_quantity == FREE


def test_an_unmarked_line_still_bills_in_parts() -> None:
    """Three of a plain line bill as before."""
    setup = _PartShare(marked=False)
    note = setup.note(Decimal("3"), Decimal("0"))

    invoice = setup.bill(note, Decimal("2"), Decimal("0"))

    assert invoice.id is not None


def test_a_return_of_part_of_a_part_share_line_comes_back_in_proportion() -> None:
    """Three of six are 2.75 charged and 0.25 free, credited at 2.75."""
    setup = _PartShare()
    note = setup.note(CHARGED, None)

    total, free, gross = setup.returned(
        source_type=SalesReturnSourceType.DELIVERY_NOTE,
        document_id=note.id,
        line_id=setup.note_line(note).id,
        quantity=Decimal("3"),
    )

    assert free == Decimal("0.25")
    assert total == Decimal("3")
    assert gross == Decimal("2.75") * PRICE


def test_a_return_off_the_bill_traces_the_marking_through_the_note() -> None:
    """Bill line, note line, order line: the proportion still holds."""
    setup = _PartShare()
    note = setup.note(CHARGED, None)
    seed_finance_setup(
        setup.session,
        firm_id=setup.firm.id,
        year_starts_on=date(2026, 4, 1),
        actor_id=uuid4(),
    )
    invoice = SalesInvoiceService(setup.session).approve_invoice(
        setup.bill(note, CHARGED).id, firm_scope=setup.firm.id, actor_id=uuid4()
    )
    bill_line = setup.session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    )
    assert bill_line is not None

    total, free, gross = setup.returned(
        source_type=SalesReturnSourceType.SALES_INVOICE,
        document_id=invoice.id,
        line_id=bill_line.id,
        quantity=Decimal("3"),
    )

    assert total == Decimal("3")
    assert free == Decimal("0.25")
    assert gross == Decimal("2.75") * PRICE


def test_a_typed_free_figure_still_wins_on_a_part_share_return() -> None:
    """Three back with nothing free typed is three charged, as typed."""
    setup = _PartShare()
    note = setup.note(CHARGED, None)

    total, free, gross = setup.returned(
        source_type=SalesReturnSourceType.DELIVERY_NOTE,
        document_id=note.id,
        line_id=setup.note_line(note).id,
        quantity=Decimal("3"),
        free=Decimal("0"),
    )

    assert total == Decimal("3")
    assert free == Decimal("0")
    assert gross == Decimal("3") * PRICE


def test_an_unmarked_return_takes_the_charged_units_first() -> None:
    """A plain line of 5.5 + 0.5 returns 3 charged, as it always did."""
    setup = _PartShare(marked=False)
    note = setup.note(CHARGED, None)

    _, free, gross = setup.returned(
        source_type=SalesReturnSourceType.DELIVERY_NOTE,
        document_id=note.id,
        line_id=setup.note_line(note).id,
        quantity=Decimal("3"),
    )

    assert free == Decimal("0")
    assert gross == Decimal("3") * PRICE
