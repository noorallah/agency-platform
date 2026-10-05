"""A firm can skip the stages it does not staff, and the books still hold.

The chain is quotation, sales order, delivery note, invoice. A firm run by one
person raises only the last of those; the services raise the rest. What must
stay true whichever stages are switched off: stock leaves once, cost of goods
sold is posted against it, revenue is posted against the customer, and a bill
that fails leaves none of it behind.

That last one is the reason this file exists. Before the `stage_*` split every
step committed on its own, so a failure at invoice approval left an approved
order and a **dispatched** delivery note written -- goods gone from the
warehouse with nothing owed for them.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import SerialNumber
from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    ProductValuation,
)
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.promotions.models import Promotion, PromotionAction, PromotionCoupon
from app.promotions.schemas import PromotionActionType, PromotionStatus
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceStatus,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesWorkflowSettings
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService


def _session_factory() -> sessionmaker[Session]:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Firm:
    """The masters one counter-selling firm needs."""

    def __init__(self, session: Session) -> None:
        """Build a firm with a default branch, warehouse, customer and stock."""
        self.session = session
        self.firm = Firm(
            name="Counter Firm",
            code="CS-FIRM",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        # `is_default` on both, because a firm that types no delivery note
        # never sees a field to name a warehouse in.
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-001",
            name="Branch BR-001",
            display_name="Branch BR-001",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
            is_default=True,
        )
        session.add(self.branch)
        session.commit()
        self.warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code="WH-001",
            name="Warehouse WH-001",
            display_name="Warehouse WH-001",
            status="ACTIVE",
            is_default=True,
        )
        session.add(self.warehouse)
        session.commit()
        self.customer = Customer(
            firm_id=self.firm.id,
            code="CUS-001",
            customer_type="RETAIL",
            name="Customer CUS-001",
            display_name="Customer CUS-001",
            currency_code="INR",
            status="ACTIVE",
            credit_limit=Decimal("50000"),
            opening_balance=Decimal("0"),
        )
        session.add(self.customer)
        session.commit()
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-001",
            name="Product SKU-001",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        session.add(self.product)
        session.commit()
        InventoryService(session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                product_id=self.product.id,
                quantity=Decimal("100"),
                reference_number="ADJ-OPENING",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 1),
            ),
            firm_scope=self.firm.id,
            actor_id=uuid4(),
        )
        # Give the opening stock a cost. An adjustment carries no price, and
        # `post_goods_issue` deliberately writes no journal for a movement
        # worth nothing -- so without this the sale would post revenue and no
        # cost of goods sold, and the test would be asserting the wrong thing.
        valuation = session.scalar(
            select(ProductValuation).where(
                ProductValuation.firm_id == self.firm.id,
                ProductValuation.product_id == self.product.id,
            )
        )
        assert valuation is not None
        valuation.average_cost = Decimal("60")
        valuation.total_value = valuation.quantity_on_hand * Decimal("60")
        session.commit()
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=uuid4(),
        )

    def stages(
        self,
        *,
        quotation: bool = True,
        sales_order: bool = True,
        delivery_note: bool = True,
    ) -> None:
        """Record which stages this firm fills in by hand."""
        self.session.add(
            SalesWorkflowSettings(
                firm_id=self.firm.id,
                quotation_stage=quotation,
                sales_order_stage=sales_order,
                delivery_note_stage=delivery_note,
            )
        )
        self.session.commit()

    def bare_bill(self, quantity: Decimal = Decimal("4")) -> SalesInvoiceCreate:
        """Describe a counter sale: a customer, a product and a price."""
        return SalesInvoiceCreate(
            customer_id=self.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    product_id=self.product.id,
                    line_number=1,
                    current_invoice_quantity=quantity,
                    unit_price=Decimal("100"),
                )
            ],
        )


def _counts(session: Session) -> tuple[int, int, int, int]:
    """Count the documents and stock movements the chain would write."""
    return (
        len(session.scalars(select(SalesOrder)).all()),
        len(session.scalars(select(DeliveryNote)).all()),
        len(session.scalars(select(SalesInvoice)).all()),
        len(session.scalars(select(InventoryTransaction)).all()),
    )


def test_a_bare_bill_raises_the_whole_chain_behind_it() -> None:
    """One form becomes an order, a dispatched note and an approved bill."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _, notes_before, _, movements_before = _counts(session)

    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )
    approved = service.approve_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=actor
    )

    assert approved.status == SalesInvoiceStatus.APPROVED.value
    orders, notes, invoices, movements = _counts(session)
    assert orders == 1, "the bill must raise the order it bills"
    assert notes == notes_before + 1, "and the note that shipped the goods"
    assert invoices == 1
    assert movements > movements_before, "the goods must actually leave"

    # The bill bills the note, never the order: the note is what knows what
    # left the warehouse.
    note = session.scalar(select(DeliveryNote))
    assert note is not None
    assert note.status == "DISPATCHED"

    # Both halves of the money: cost against the movement, revenue against the
    # customer. A sale that posts one without the other is the defect this
    # design exists to avoid.
    issue = session.scalar(
        select(JournalEntry).where(JournalEntry.source_module == "delivery_note")
    )
    revenue = session.scalar(
        select(JournalEntry).where(JournalEntry.source_module == "sales_invoice")
    )
    assert issue is not None, "cost of goods sold must be posted"
    assert revenue is not None, "revenue must be posted"
    assert issue.status == JournalStatus.POSTED.value
    assert revenue.status == JournalStatus.POSTED.value


def test_a_firm_on_the_whole_chain_still_has_to_name_its_source() -> None:
    """The default configuration is unchanged, which is most firms."""
    session = _session_factory()()
    setup = _Firm(session)
    # No settings row at all: every stage is on, as it always was.

    with pytest.raises(ValidationError) as refused:
        SalesInvoiceService(session).create_invoice(
            setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
        )
    assert "must name the document it bills" in str(refused.value)


def test_a_bill_cannot_mix_bare_lines_with_billed_documents() -> None:
    """Two provenances on one bill is a question nothing can answer."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)

    bill = setup.bare_bill()
    bill.lines.append(
        SalesInvoiceLineWrite(
            source_document_type="DELIVERY_NOTE",
            source_document_id=uuid4(),
            source_document_line_id=uuid4(),
            line_number=2,
            current_invoice_quantity=Decimal("1"),
            unit_price=Decimal("100"),
        )
    )
    with pytest.raises(ValidationError) as refused:
        SalesInvoiceService(session).create_invoice(
            bill, firm_id=setup.firm.id, actor_id=uuid4()
        )
    assert "never a mixture" in str(refused.value)


def test_a_failed_bill_leaves_no_order_no_note_and_no_movement() -> None:
    """The whole reason the chain is staged rather than committed step by step.

    Six commits meant a failure at the last step left an approved order and a
    dispatched delivery note behind it: goods gone from the warehouse, nothing
    owed for them, and no bill to explain either.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    before = _counts(session)

    # A bare line naming no product fails after the chain has started.
    bill = setup.bare_bill()
    bill.lines[0].product_id = None
    with pytest.raises(ValidationError):
        SalesInvoiceService(session).create_invoice(
            bill, firm_id=setup.firm.id, actor_id=uuid4()
        )
    session.rollback()

    assert _counts(session) == before, (
        "a refused counter sale must leave no order, no delivery note, no "
        "invoice and no stock movement behind it"
    )


def test_a_refused_approval_ships_nothing() -> None:
    """The dispatch belongs to the approval's transaction, so it goes with it.

    More than the firm holds: the draft saves -- a draft moves nothing -- and
    the approval is refused at dispatch, leaving the stock where it was.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(quantity=Decimal("500")),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    before = _counts(session)

    with pytest.raises(ValidationError):
        service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)
    session.rollback()

    assert _counts(session) == before
    assert (
        service.get_invoice(invoice.id, firm_scope=setup.firm.id).status
        == SalesInvoiceStatus.DRAFT
    )


def _dispatches(session: Session) -> int:
    """Count the stock movements that took goods out of the warehouse."""
    return len(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH"
            )
        ).all()
    )


def test_a_draft_bill_ships_nothing_until_it_is_approved() -> None:
    """D-SELL-13: saving a draft dispatched the goods and posted their cost.

    Driven 2026-09-19 on ``fx_t0919go59_s``: a draft bill of
    SO-2026-2027-000002 left DN-...-000001 DISPATCHED and the order
    DELIVERED, and cancelling the draft left both so. A draft is a proposal;
    the stock leaves when the bill is approved, in the approval's own
    transaction.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()

    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )

    note = session.scalar(select(DeliveryNote))
    assert note is not None
    assert note.status == "APPROVED", "the note waits for the bill"
    assert _dispatches(session) == 0, "a draft must move no stock"
    assert (
        session.scalar(
            select(JournalEntry).where(JournalEntry.source_module == "delivery_note")
        )
        is None
    ), "nor post any cost of goods sold"

    service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)

    session.refresh(note)
    assert note.status == "DISPATCHED"
    assert _dispatches(session) == 1
    line = session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    )
    assert line is not None
    # Costed from the dispatch the approval made: 4 at the average of 60.
    assert line.cost_amount == Decimal("240.0000")


def test_cancelling_a_draft_bill_withdraws_the_note_it_raised() -> None:
    """The note was raised to carry this bill's goods; the sale is off."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )

    service.cancel_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=actor, reason="walked out"
    )

    note = session.scalar(select(DeliveryNote))
    assert note is not None
    assert note.status == "CANCELLED"
    assert _dispatches(session) == 0


def _reserved(session: Session) -> Decimal:
    """Sum what every stock row of the firm holds reserved."""
    session.expire_all()
    return sum(
        (
            record.reserved_quantity
            for record in session.scalars(select(InventoryRecord)).all()
        ),
        Decimal("0"),
    )


def _request_session() -> Session:
    """Open a session as a request does: one that does not flush on a read."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)()


def test_cancelling_a_draft_bill_withdraws_its_order_and_frees_the_stock() -> None:
    """D-SELL-54: the hidden order stayed APPROVED with the quantity reserved.

    Driven 2026-10-05 on a firm with both stages off: a draft counter bill of
    7 reserved 7; cancelling it cancelled the note it raised and left
    SO-2026-2027-000027 APPROVED holding the 7, with no UNRESERVE in the
    ledger -- until every later sale of the product was refused for stock.
    """
    session = _request_session()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(Decimal("7")), firm_id=setup.firm.id, actor_id=actor
    )
    order = session.scalar(select(SalesOrder))
    assert order is not None
    assert order.raised_by_sales_invoice_id == invoice.id, "the bill stamps its order"
    assert _reserved(session) == Decimal("7.0000")

    service.cancel_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=actor, reason="walked out"
    )

    session.refresh(order)
    assert order.status == "CANCELLED", "the order was this bill's and goes with it"
    assert _reserved(session) == Decimal("0.0000"), "and gives the stock back"
    released = session.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.transaction_type == "UNRESERVE"
        )
    ).all()
    assert len(released) == 1, "with the release on the stock ledger"
    # The same seven can be sold again straight away.
    again = service.create_invoice(
        setup.bare_bill(Decimal("100")), firm_id=setup.firm.id, actor_id=actor
    )
    service.approve_invoice(again.id, firm_scope=setup.firm.id, actor_id=actor)


def test_cancelling_a_draft_bill_leaves_an_order_a_person_raised() -> None:
    """A bill that only dispatched somebody's order does not cancel that order.

    With the order stage on and the note stage off, the order is a document a
    person typed and approved; the bill raises the note alone, and cancelling
    the draft takes back only that.
    """
    session = _request_session()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=True, delivery_note=False)
    actor = uuid4()
    orders = SalesOrderService(session)
    order = orders.stage_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    orders.stage_approval(order.id, firm_scope=setup.firm.id, actor_id=actor)
    session.commit()
    order_line = session.scalar(select(SalesOrderLine))
    assert order_line is not None
    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type="SALES_ORDER",
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )

    service.cancel_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=actor, reason="walked out"
    )

    note = session.scalar(select(DeliveryNote))
    assert note is not None
    assert note.status == "CANCELLED"
    session.refresh(order)
    assert order.raised_by_sales_invoice_id is None
    assert order.status == "APPROVED", "a person's order is theirs to cancel"
    assert _reserved(session) == Decimal("4.0000"), "and still holds its goods"


def test_cancelling_an_approved_counter_bill_leaves_no_stock_reserved() -> None:
    """The goods left at approval, so the order stays and holds nothing."""
    session = _request_session()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )
    service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)
    assert _reserved(session) == Decimal("0.0000")

    service.cancel_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=actor, reason="keyed twice"
    )

    order = session.scalar(select(SalesOrder))
    note = session.scalar(select(DeliveryNote))
    assert order is not None and note is not None
    assert note.status == "DISPATCHED", "the goods left; a return brings them back"
    assert order.status == "DELIVERED"
    assert _reserved(session) == Decimal("0.0000")
    assert _dispatches(session) == 1


def _persons_note(setup: _Firm) -> DeliveryNote:
    """Raise and approve an order and a note by hand, dispatching nothing."""
    actor = uuid4()
    orders = SalesOrderService(setup.session)
    order = orders.stage_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    orders.stage_approval(order.id, firm_scope=setup.firm.id, actor_id=actor)
    order_line = setup.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None
    notes = DeliveryNoteService(setup.session)
    note = notes.stage_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 3),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    notes.stage_approval(note.id, firm_scope=setup.firm.id, actor_id=actor)
    setup.session.commit()
    return note


def _bill_of(setup: _Firm, note: DeliveryNote) -> SalesInvoiceCreate:
    """Describe a bill for every line of a note."""
    line = setup.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None
    return SalesInvoiceCreate(
        customer_id=setup.customer.id,
        invoice_date=date(2026, 8, 4),
        lines=[
            SalesInvoiceLineWrite(
                source_document_type="DELIVERY_NOTE",
                source_document_id=note.id,
                source_document_line_id=line.id,
                line_number=1,
                current_invoice_quantity=Decimal("4"),
            )
        ],
    )


def test_a_note_a_person_raised_is_not_adopted_when_the_stage_goes_off() -> None:
    """D-CFG-16: "the stage is off now" is not "this bill raised the note".

    Driven 2026-09-19 on ``fx_t0919jsu8_s``: a note raised and approved by
    hand, the delivery-note stage then switched off, and a draft bill naming
    the undispatched note was saved (SI-2026-2027-000001) -- skipping
    D-SELL-3's check -- and cancelling the draft **cancelled the person's
    note**. It is billed like any other note: once dispatched.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(delivery_note=True)
    note = _persons_note(setup)
    settings = session.scalar(select(SalesWorkflowSettings))
    assert settings is not None
    settings.delivery_note_stage = False
    session.commit()

    with pytest.raises(ValidationError, match="only a dispatched delivery note"):
        SalesInvoiceService(session).create_invoice(
            _bill_of(setup, note), firm_id=setup.firm.id, actor_id=uuid4()
        )
    session.rollback()
    session.refresh(note)
    assert note.status == "APPROVED"
    assert note.raised_by_sales_invoice_id is None


def test_a_draft_ships_and_withdraws_only_the_note_it_stamped() -> None:
    """The bill's own note carries its id; a note without it is not its to move.

    A draft saved before the stamp existed, or one naming a note somebody else
    raised, is refused at approval like any bill naming an undispatched note,
    and cancelling it leaves the note alone.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )
    note = session.scalar(select(DeliveryNote))
    assert note is not None
    assert note.raised_by_sales_invoice_id == invoice.id, "the bill stamps its note"
    assert invoice.allow_direct_sales_order is True

    # The same note, as though a person had raised it.
    note.raised_by_sales_invoice_id = None
    session.commit()

    with pytest.raises(ValidationError, match="only a dispatched delivery note"):
        service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)
    session.rollback()
    service.cancel_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=actor, reason="walked out"
    )

    session.refresh(note)
    assert note.status == "APPROVED", "a note the bill did not raise stays"
    assert _dispatches(session) == 0


def test_a_bill_naming_no_serials_cannot_dispatch_a_serial_tracked_product() -> None:
    """The document that moves the goods names the units, and here that is it.

    Dispatch refuses a serial-tracked line that names no units (D-STK-4), so
    a note the chain raised for a bill naming none could never ship. The bill
    is refused by name before anything is staged, and nothing is left behind.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.product.track_serial = True
    session.commit()
    before = _counts(session)

    with pytest.raises(ValidationError, match="SKU-001 is serial-tracked"):
        SalesInvoiceService(session).create_invoice(
            setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
        )
    session.rollback()

    assert _counts(session) == before


def test_a_bill_naming_its_serials_ships_exactly_those_units() -> None:
    """A counter sale of a serial-tracked product names its units on the bill.

    The chain hands them to the note it raises, so they leave SOLD exactly as
    if a storekeeper had picked them on a typed note.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.product.track_serial = True
    units = [
        SerialNumber(
            firm_id=setup.firm.id,
            product_id=setup.product.id,
            warehouse_id=setup.warehouse.id,
            branch_id=setup.branch.id,
            serial_number=f"SKU-{n}",
        )
        for n in range(1, 4)
    ]
    session.add_all(units)
    session.commit()
    bill = setup.bare_bill(quantity=Decimal("2"))
    bill.lines[0].serial_ids = [units[0].id, units[2].id]

    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(bill, firm_id=setup.firm.id, actor_id=actor)
    service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)

    for unit in units:
        session.refresh(unit)
    assert [unit.status for unit in units] == ["SOLD", "AVAILABLE", "SOLD"]


def test_editing_a_draft_bill_restates_the_units_its_own_note_ships() -> None:
    """D-SELL-33: an edited draft had nowhere to change its serial picks.

    The chain moves the bill's picks onto the note it raises, so the saved
    draft bills that note -- and an edit naming serials was refused as though
    the note had shipped. The draft shows the units its note ships, and an
    edit restates them there.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.product.track_serial = True
    units = [
        SerialNumber(
            firm_id=setup.firm.id,
            product_id=setup.product.id,
            warehouse_id=setup.warehouse.id,
            branch_id=setup.branch.id,
            serial_number=f"SKU-{n}",
        )
        for n in range(1, 4)
    ]
    session.add_all(units)
    session.commit()
    bill = setup.bare_bill(quantity=Decimal("2"))
    bill.lines[0].serial_ids = [units[0].id, units[2].id]
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(bill, firm_id=setup.firm.id, actor_id=actor)

    [line] = service.invoice_response(invoice).lines
    assert line.picks_serials is True
    assert sorted(item.serial_number for item in line.serials) == ["SKU-1", "SKU-3"]

    service.update_invoice(
        invoice.id,
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=line.source_document_type,
                    source_document_id=line.source_document_id,
                    source_document_line_id=line.source_document_line_id,
                    line_number=1,
                    current_invoice_quantity=Decimal("2"),
                    serial_ids=[units[1].id, units[2].id],
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)

    for unit in units:
        session.refresh(unit)
    assert [unit.status for unit in units] == ["AVAILABLE", "SOLD", "SOLD"]


def test_switching_a_stage_off_does_not_move_an_existing_document() -> None:
    """Configuration governs new documents, never the ones already in flight.

    A firm that turns the delivery-note stage off while notes are open must
    keep them workable, or the work already under way is stranded.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )
    note = session.scalar(select(DeliveryNote))
    assert note is not None

    settings = session.scalar(select(SalesWorkflowSettings))
    assert settings is not None
    settings.delivery_note_stage = True
    session.commit()

    # The documents raised under the old configuration are untouched and the
    # bill they belong to still reads back.
    assert session.get(DeliveryNote, note.id) is not None
    assert (
        service.get_invoice(invoice.id, firm_scope=setup.firm.id).status
        == SalesInvoiceStatus.DRAFT
    )


def _firm_ids(session: Session) -> set[UUID]:
    """Return every firm id the store holds."""
    return {row.id for row in session.scalars(select(Firm)).all()}


def test_the_configuration_belongs_to_one_firm() -> None:
    """One firm's shorter chain must not shorten another's."""
    session = _session_factory()()
    first = _Firm(session)
    first.stages(quotation=False, sales_order=False, delivery_note=False)

    second = Firm(
        name="Chain Firm",
        code="CH-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(second)
    session.commit()
    assert len(_firm_ids(session)) == 2

    # The second firm never configured anything, so it keeps the whole chain
    # even though the first has switched every stage off.
    with pytest.raises(ValidationError):
        SalesInvoiceService(session).create_invoice(
            SalesInvoiceCreate(
                customer_id=first.customer.id,
                invoice_date=date(2026, 8, 4),
                lines=[
                    SalesInvoiceLineWrite(
                        product_id=first.product.id,
                        line_number=1,
                        current_invoice_quantity=Decimal("1"),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=second.id,
            actor_id=uuid4(),
        )


def _coupon_offer(setup: _Firm, code: str = "SAVE10") -> None:
    """Publish a ten-percent offer that only a coupon unlocks."""
    promotion = Promotion(
        firm_id=setup.firm.id,
        code="TENOFF",
        name="Ten percent off",
        priority=10,
        status=PromotionStatus.ACTIVE.value,
        allow_stacking=True,
        requires_coupon=True,
        version_group_id=uuid4(),
        version_number=1,
    )
    setup.session.add(promotion)
    setup.session.flush()
    setup.session.add_all(
        [
            PromotionAction(
                firm_id=setup.firm.id,
                promotion_id=promotion.id,
                sequence=1,
                action_type=PromotionActionType.LINE_DISCOUNT_PERCENT.value,
                parameters={"percent": "10"},
            ),
            PromotionCoupon(
                firm_id=setup.firm.id,
                promotion_id=promotion.id,
                code=code,
                status=PromotionStatus.ACTIVE.value,
            ),
        ]
    )
    setup.session.commit()


def test_a_bill_typed_straight_in_honours_the_customers_coupon() -> None:
    """D-SELL-40: the coupon reaches the order the bill raises, and its price.

    A firm with its sales stages off types only the bill, so the bill is the
    one place its people can take a coupon. It prices the order raised behind
    it, where the claim is counted at approval like any order's.
    """
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _coupon_offer(setup)
    service = SalesInvoiceService(session)

    plain = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
    )
    with_coupon = service.create_invoice(
        setup.bare_bill().model_copy(update={"coupon_code": "save10"}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    def taxable(invoice: SalesInvoice) -> Decimal:
        """Sum what the bill's lines are taxed on."""
        return sum(
            (
                line.net_amount
                for line in session.scalars(
                    select(SalesInvoiceLine).where(
                        SalesInvoiceLine.sales_invoice_id == invoice.id
                    )
                )
            ),
            Decimal("0"),
        )

    assert taxable(plain) == Decimal("400.0000")
    assert taxable(with_coupon) == Decimal("360.0000")
    coupons = session.scalars(select(SalesOrder.coupon_code)).all()
    assert sorted(code or "" for code in coupons) == ["", "SAVE10"]


def test_a_coupon_on_a_bill_of_documents_already_priced_is_refused() -> None:
    """A field that gives money away must not be accepted and do nothing."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
    )
    note = session.scalars(select(DeliveryNote)).one()
    line = session.scalars(select(SalesInvoiceLine)).one()
    sourced = SalesInvoiceCreate(
        customer_id=setup.customer.id,
        invoice_date=date(2026, 8, 4),
        coupon_code="SAVE10",
        lines=[
            SalesInvoiceLineWrite(
                source_document_type="DELIVERY_NOTE",
                source_document_id=note.id,
                source_document_line_id=line.source_document_line_id,
                line_number=1,
                current_invoice_quantity=Decimal("4"),
            )
        ],
    )

    with pytest.raises(ValidationError, match="coupon"):
        service.update_invoice(
            invoice.id, sourced, firm_id=setup.firm.id, actor_id=uuid4()
        )


def test_an_invoice_line_keeps_the_hsn_it_was_billed_under() -> None:
    """D-CMP-22: the line is stamped with the product's code when written."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.product.hsn_sac = "10063020"
    session.commit()

    SalesInvoiceService(session).create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
    )
    setup.product.hsn_sac = "99999999"
    session.commit()

    line = session.scalars(select(SalesInvoiceLine)).one()
    assert line.hsn_sac == "10063020"


def test_money_taken_at_the_counter_settles_the_bill_on_approval() -> None:
    """Backlog 64 row 5: the bill carries the cash, approval records it."""
    from app.settlements.models.settlement import Settlement, SettlementAllocation

    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    draft = service.create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=actor
    )
    total = draft.grand_total
    [line] = service.invoice_response(draft).lines

    def resave(**extra: object) -> None:
        """Save the draft again as the editor does: its own lines, plus extra."""
        service.update_invoice(
            draft.id,
            SalesInvoiceCreate(
                customer_id=setup.customer.id,
                invoice_date=draft.invoice_date,
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=line.source_document_type,
                        source_document_id=line.source_document_id,
                        source_document_line_id=line.source_document_line_id,
                        line_number=1,
                        current_invoice_quantity=line.current_invoice_quantity,
                    )
                ],
                **extra,
            ),
            firm_id=setup.firm.id,
            actor_id=actor,
        )

    resave(received_now_amount=total, received_now_method="CASH")
    # A save that never mentions the counter payment leaves it alone.
    resave()
    stored = session.get(SalesInvoice, draft.id)
    assert stored is not None
    assert stored.received_now_amount == total

    approved = service.approve_invoice(
        draft.id, firm_scope=setup.firm.id, actor_id=actor
    )

    receipt = session.get(Settlement, approved.received_now_settlement_id)
    assert receipt is not None
    assert receipt.amount == total
    assert receipt.method == "CASH"
    allocated = session.scalar(
        select(SettlementAllocation.amount).where(
            SettlementAllocation.settlement_id == receipt.id,
            SettlementAllocation.sales_invoice_id == approved.id,
        )
    )
    assert allocated == total
    receipt_journal = session.get(JournalEntry, receipt.journal_entry_id)
    assert receipt_journal is not None, "the cash must reach the books"
    assert receipt_journal.status == JournalStatus.POSTED.value


def test_more_than_the_bill_is_refused_and_nothing_is_approved() -> None:
    """Change is handed back: an overpayment is not quietly an advance."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    actor = uuid4()
    draft = service.create_invoice(
        setup.bare_bill().model_copy(update={"received_now_amount": Decimal("100000")}),
        firm_id=setup.firm.id,
        actor_id=actor,
    )

    with pytest.raises(ValidationError, match="change is handed back"):
        service.approve_invoice(draft.id, firm_scope=setup.firm.id, actor_id=actor)
    session.rollback()

    refused = session.get(SalesInvoice, draft.id)
    assert refused is not None
    assert refused.status == "DRAFT"
    assert _dispatches(session) == 0
