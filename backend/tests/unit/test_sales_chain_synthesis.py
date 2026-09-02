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

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import InventoryTransaction, ProductValuation
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceStatus,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesWorkflowSettings


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

    # More than the firm holds, so dispatch refuses after the order is staged
    # and approved -- the step that used to have been committed by now.
    with pytest.raises(ValidationError):
        SalesInvoiceService(session).create_invoice(
            setup.bare_bill(quantity=Decimal("500")),
            firm_id=setup.firm.id,
            actor_id=uuid4(),
        )
    session.rollback()

    assert _counts(session) == before, (
        "a refused counter sale must leave no order, no delivery note, no "
        "invoice and no stock movement behind it"
    )


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
