"""Sales return lifecycle, stock intake and ledger tests.

A customer could always be credit-noted for goods they sent back, which moved
the money and nothing else: the units stayed counted as sold. These tests are
about the other two books -- what the shelf holds and what the ledger says it
is worth -- because those are the ones that were silently wrong.
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
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.document_framework.models import DocumentTypeDefinition
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
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
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_return.models import SalesReturn, SalesReturnLine
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnImportRequest,
    SalesReturnLineWrite,
    SalesReturnSourceType,
    SalesReturnStatus,
)
from app.sales_return.services import SalesReturnService
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401

#: What the goods cost coming in, and what they sell for going out. They are
#: deliberately different so a test can tell the two journals apart.
COST = Decimal("60")
PRICE = Decimal("100")


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Return Firm",
        code="SR-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    # Completing a return posts twice, so the firm needs its chart of
    # accounts, an open period and its control accounts.
    seed_finance_setup(
        session, firm_id=row.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    session.commit()
    return row


def _branch(session: Session, *, firm_id: UUID) -> Branch:
    row = Branch(
        firm_id=firm_id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _warehouse(session: Session, *, firm_id: UUID, branch_id: UUID) -> Warehouse:
    row = Warehouse(
        firm_id=firm_id,
        branch_id=branch_id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, *, firm_id: UUID) -> Customer:
    row = Customer(
        firm_id=firm_id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("500000"),
        opening_balance=Decimal("0"),
    )
    session.add(row)
    session.commit()
    return row


def _product(session: Session, *, firm_id: UUID) -> Product:
    row = Product(
        firm_id=firm_id,
        code="SKU-001",
        name="Product SKU-001",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


class _Dispatch:
    """Everything a sales return needs to exist: goods that already went out."""

    def __init__(self, session: Session) -> None:
        """Stock a warehouse, sell four units, and dispatch them."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = _firm(session)
        self.branch = _branch(session, firm_id=self.firm.id)
        self.warehouse = _warehouse(
            session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.customer = _customer(session, firm_id=self.firm.id)
        self.product = _product(session, firm_id=self.firm.id)

        inventory = InventoryService(session)
        # An adjustment carries no price, so the stock would sit at an average
        # of zero and every cost journal below would be worth nothing. Seeding
        # the running valuation is what a goods receipt does on the way in;
        # doing it directly keeps this test about returns.
        valuation = inventory.valuation_for(
            firm_scope=self.firm.id, product_id=self.product.id
        )
        valuation.average_cost = COST
        session.commit()
        inventory.create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                product_id=self.product.id,
                quantity=Decimal("10"),
                reference_number="ADJ-1",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 3),
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        )

        orders = SalesOrderService(session)
        order = orders.approve_order(
            orders.create_order(
                SalesOrderCreate(
                    customer_id=self.customer.id,
                    branch_id=self.branch.id,
                    warehouse_id=self.warehouse.id,
                    order_date=date(2026, 8, 3),
                    lines=[
                        SalesOrderLineWrite(
                            line_number=1,
                            product_id=self.product.id,
                            quantity=Decimal("4"),
                            unit_price=PRICE,
                        )
                    ],
                ),
                firm_id=self.firm.id,
                actor_id=self.actor_id,
            ).id,
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        )
        order_line = session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        )
        assert order_line is not None

        notes = DeliveryNoteService(session)
        note = notes.create_note(
            DeliveryNoteCreate(
                sales_order_id=order.id,
                delivery_date=date(2026, 8, 4),
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=order_line.id,
                        line_number=1,
                        current_delivery_quantity=Decimal("4"),
                        free_quantity=Decimal("0"),
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        notes.approve_note(note.id, firm_scope=self.firm.id, actor_id=self.actor_id)
        self.note = notes.dispatch_note(
            note.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )
        line = session.scalar(
            select(DeliveryNoteLine).where(
                DeliveryNoteLine.delivery_note_id == self.note.id
            )
        )
        assert line is not None
        self.note_line = line

        # Bill it. A return normally follows an invoice, and only then does it
        # reduce something: crediting a customer who owes nothing leaves them
        # in advance instead, which is true but not what these tests are about.
        invoices = SalesInvoiceService(session)
        invoice = invoices.create_invoice(
            SalesInvoiceCreate(
                invoice_date=date(2026, 8, 4),
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=self.note.id,
                        source_document_line_id=self.note_line.id,
                        line_number=1,
                        current_invoice_quantity=Decimal("4"),
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.invoice = invoices.approve_invoice(
            invoice.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )
        session.refresh(self.customer)

    def payload(
        self,
        *,
        quantity: Decimal = Decimal("2"),
        damaged: Decimal = Decimal("0"),
        scrap: Decimal = Decimal("0"),
        allow_over_return: bool = False,
    ) -> SalesReturnCreate:
        """Build a return of the dispatched line."""
        return SalesReturnCreate(
            warehouse_id=self.warehouse.id,
            return_date=date(2026, 8, 5),
            allow_over_return=allow_over_return,
            lines=[
                SalesReturnLineWrite(
                    source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                    source_document_id=self.note.id,
                    source_document_line_id=self.note_line.id,
                    line_number=1,
                    current_return_quantity=quantity,
                    damaged_quantity=damaged,
                    scrap_quantity=scrap,
                    unit_price=PRICE,
                )
            ],
        )

    def completed(self, **kwargs: Decimal) -> tuple[SalesReturnService, SalesReturn]:
        """Create, approve and complete a return of the dispatched line."""
        service = SalesReturnService(self.session)
        row = service.create_return(
            self.payload(**kwargs), firm_id=self.firm.id, actor_id=self.actor_id
        )
        service.approve_return(row.id, firm_scope=self.firm.id, actor_id=self.actor_id)
        return service, service.complete_return(
            row.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )


def _on_hand(session: Session, *, firm_id: UUID, product_id: UUID) -> Decimal:
    record = session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == firm_id,
            InventoryRecord.product_id == product_id,
        )
    )
    assert record is not None
    return Decimal(str(record.current_quantity))


def _account_movement(session: Session, firm_id: UUID, name_fragment: str) -> Decimal:
    """Net debit less credit across the accounts whose name contains a word."""
    accounts = [
        account
        for account in session.scalars(
            select(LedgerAccount).where(LedgerAccount.firm_id == firm_id)
        ).all()
        if name_fragment.lower() in account.name.lower()
    ]
    assert accounts, f"no ledger account named like {name_fragment!r}"
    total = Decimal("0")
    for account in accounts:
        for posting in session.scalars(
            select(GLPosting).where(GLPosting.ledger_account_id == account.id)
        ).all():
            total += Decimal(str(posting.debit_amount)) - Decimal(
                str(posting.credit_amount)
            )
    return total


def test_a_completed_return_puts_the_goods_back_and_credits_the_customer() -> None:
    """The whole point: three books move together or the document is a lie."""
    session = _session_factory()()
    setup = _Dispatch(session)
    owed_before = Decimal(str(setup.customer.current_outstanding))
    on_hand_before = _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    )
    # Dispatching already posted the cost of all four units, so what matters
    # is how far each account moves from here, not where it lands.
    returns_before = _account_movement(session, setup.firm.id, "sales return")
    cost_before = _account_movement(session, setup.firm.id, "cost of goods")

    service, row = setup.completed(quantity=Decimal("2"))

    assert row.status == SalesReturnStatus.COMPLETED.value
    assert row.return_number.startswith("SR")
    # The shelf.
    assert _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    ) == on_hand_before + Decimal("2")
    movement = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_type == "SALES_RETURN",
            InventoryTransaction.reference_number == row.return_number,
        )
    )
    assert movement is not None
    assert movement.current_quantity_delta == Decimal("2.0000")
    # The customer's account.
    session.refresh(setup.customer)
    assert (
        Decimal(str(setup.customer.current_outstanding))
        == owed_before - row.grand_total
    )
    # Both ledgers: the credit at selling price, the cost at what stock cost.
    assert row.journal_entry_id is not None
    assert row.cost_journal_entry_id is not None
    assert _account_movement(
        session, setup.firm.id, "sales return"
    ) - returns_before == Decimal("200.00")
    assert _account_movement(
        session, setup.firm.id, "cost of goods"
    ) - cost_before == -(COST * 2)
    assert session.scalar(select(AuditLog.id)) is not None
    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == setup.firm.id,
                DocumentTypeDefinition.code == "SALES_RETURN",
            )
        )
        is not None
    )
    assert service.summary(firm_scope=setup.firm.id).completed_returns == 1


def test_the_credit_is_the_selling_price_and_the_stock_is_the_cost() -> None:
    """Two numbers answering two questions, and they must not be swapped."""
    session = _session_factory()()
    setup = _Dispatch(session)

    _service, row = setup.completed(quantity=Decimal("2"))

    # Sold at 100, carried at 60. A single journal at either number would put
    # one of inventory or receivables 80.00 out on a two-unit return.
    assert row.grand_total == Decimal("200.0000")
    credit = session.get(JournalEntry, row.journal_entry_id)
    cost = session.get(JournalEntry, row.cost_journal_entry_id)
    assert credit is not None and cost is not None
    assert credit.total_debit == Decimal("200.00")
    assert cost.total_debit == Decimal("120.00")


def test_damaged_goods_come_back_owned_but_not_sellable() -> None:
    """They are still the firm's and still worth what they cost."""
    session = _session_factory()()
    setup = _Dispatch(session)
    on_hand_before = _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    )
    cost_before = _account_movement(session, setup.firm.id, "cost of goods")

    _service, row = setup.completed(quantity=Decimal("2"), damaged=Decimal("2"))

    # Nothing goes back on the shelf...
    assert (
        _on_hand(session, firm_id=setup.firm.id, product_id=setup.product.id)
        == on_hand_before
    )
    movement = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_number == row.return_number
        )
    )
    assert movement is not None
    assert movement.current_quantity_delta == Decimal("0.0000")
    assert movement.damaged_quantity_delta == Decimal("2.0000")
    # ...but the firm owns it, so its cost still leaves cost of sales. Coming
    # back at nothing would have understated inventory by the whole line.
    assert _account_movement(
        session, setup.firm.id, "cost of goods"
    ) - cost_before == -(COST * 2)


def test_a_return_larger_than_the_dispatch_is_refused() -> None:
    """Four went out, so five cannot come back."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)

    with pytest.raises(ValidationError, match="exceeds what was dispatched"):
        service.create_return(
            setup.payload(quantity=Decimal("5")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_second_return_counts_the_first_one() -> None:
    """Two returns of three against a dispatch of four is still five."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    service.create_return(
        setup.payload(quantity=Decimal("3")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    with pytest.raises(ValidationError, match="exceeds what was dispatched"):
        service.create_return(
            setup.payload(quantity=Decimal("3")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_editing_a_draft_does_not_count_its_own_lines() -> None:
    """Saving an unchanged return twice must not read as returning it twice."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    row = service.create_return(
        setup.payload(quantity=Decimal("4")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    updated = service.update_return(
        row.id,
        setup.payload(quantity=Decimal("4")),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert updated.total_current_return_quantity == Decimal("4.0000")


def test_cancelling_a_completed_return_undoes_all_three() -> None:
    """Otherwise the firm holds goods it has already been paid for."""
    session = _session_factory()()
    setup = _Dispatch(session)
    on_hand_before = _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    )
    owed_before = Decimal(str(setup.customer.current_outstanding))
    returns_before = _account_movement(session, setup.firm.id, "sales return")
    cost_before = _account_movement(session, setup.firm.id, "cost of goods")
    service, row = setup.completed(quantity=Decimal("2"))

    cancelled = service.cancel_return(
        row.id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
        reason="raised in error",
    )

    assert cancelled.status == SalesReturnStatus.CANCELLED.value
    assert (
        _on_hand(session, firm_id=setup.firm.id, product_id=setup.product.id)
        == on_hand_before
    )
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == owed_before
    # Both journals were mirrored, so neither account has moved on balance.
    assert _account_movement(session, setup.firm.id, "sales return") == returns_before
    assert _account_movement(session, setup.firm.id, "cost of goods") == cost_before


def test_a_draft_return_cannot_be_completed() -> None:
    """Approval is the point at which somebody agreed to take the goods."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    row = service.create_return(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(ValidationError, match="Only approved"):
        service.complete_return(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_line_whose_buckets_do_not_add_up_is_refused() -> None:
    """Three of two came back is not a quantity anybody can put anywhere."""
    with pytest.raises(ValueError, match="cannot exceed the returned quantity"):
        SalesReturnLineWrite(
            source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
            source_document_id=uuid4(),
            source_document_line_id=uuid4(),
            line_number=1,
            current_return_quantity=Decimal("2"),
            damaged_quantity=Decimal("3"),
        )


def test_the_reports_read_the_completed_return() -> None:
    """Register, by-customer, by-product and reconciliation off one document."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service, row = setup.completed(quantity=Decimal("2"), damaged=Decimal("1"))

    register = service.register_report(firm_scope=setup.firm.id)
    by_customer = service.by_customer_report(firm_scope=setup.firm.id)
    by_product = service.by_product_report(firm_scope=setup.firm.id)
    reconciliation = service.reconciliation_report(firm_scope=setup.firm.id)

    assert [record.return_number for record in register] == [row.return_number]
    assert by_customer[0].customer_name == "Customer CUS-001"
    assert by_customer[0].return_count == 1
    assert by_product[0].product_code == "SKU-001"
    assert by_product[0].return_quantity == Decimal("2.0000")
    # One of the two came back broken, so only one is sellable again.
    assert by_product[0].restock_quantity == Decimal("1.0000")
    assert reconciliation[0].product_name == "Product SKU-001"
    assert reconciliation[0].dispatched_quantity == Decimal("4.0000")
    assert reconciliation[0].pending_quantity == Decimal("2.0000")


def test_a_cancelled_return_leaves_the_reports() -> None:
    """A cancelled return did not happen, so it counts nowhere."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service, row = setup.completed(quantity=Decimal("2"))
    service.cancel_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="error"
    )

    assert service.by_customer_report(firm_scope=setup.firm.id) == []
    assert service.by_product_report(firm_scope=setup.firm.id) == []
    assert service.reconciliation_report(firm_scope=setup.firm.id) == []
    # The register still shows it: the document exists and was cancelled, which
    # is a different fact from it never having been raised.
    assert len(service.register_report(firm_scope=setup.firm.id)) == 1


def test_the_quantity_a_cancelled_return_claimed_is_released() -> None:
    """Cancelling four returned of four dispatched must free them again."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    first = service.create_return(
        setup.payload(quantity=Decimal("4")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    service.cancel_return(
        first.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="error"
    )

    second = service.create_return(
        setup.payload(quantity=Decimal("4")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert second.total_current_return_quantity == Decimal("4.0000")
    assert session.scalar(
        select(SalesReturnLine.already_returned_quantity).where(
            SalesReturnLine.sales_return_id == second.id
        )
    ) == Decimal("0.0000")


def test_a_return_can_only_name_a_document_it_was_raised_against() -> None:
    """A line pointing somewhere the header never selected is a mistake."""
    session = _session_factory()()
    setup = _Dispatch(session)
    payload = setup.payload()
    payload.lines[0].source_document_id = uuid4()

    with pytest.raises(Exception, match="not found|must reference"):
        SalesReturnService(session).create_return(
            payload, firm_id=setup.firm.id, actor_id=setup.actor_id
        )


def test_the_timeline_records_every_step() -> None:
    """A document nobody can reconstruct is a document nobody trusts."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service, row = setup.completed()

    actions = [
        event.action for event in service.timeline(row.id, firm_scope=setup.firm.id)
    ]

    assert actions == ["CREATED", "APPROVED", "COMPLETED"]


def test_a_return_is_visible_only_inside_its_own_firm() -> None:
    """Firm scope is the boundary every read here goes through."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service, row = setup.completed()

    with pytest.raises(Exception, match="not found"):
        service.get_return(row.id, firm_scope=uuid4())

    assert (
        session.scalar(select(SalesReturn).where(SalesReturn.id == row.id)) is not None
    )


def test_a_return_worth_nothing_still_brings_the_goods_back() -> None:
    """Found by driving the real API, where every seeded note is priced at zero.

    Free samples and warranty replacements go out at no charge and come back
    the same way. The credit is nothing to say to the ledger, which refuses a
    journal whose legs are both nil -- and that used to fail the whole return
    with the stock already counted back onto the shelf.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    on_hand_before = _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    )
    owed_before = Decimal(str(setup.customer.current_outstanding))
    service = SalesReturnService(session)
    payload = setup.payload(quantity=Decimal("2"))
    payload.lines[0].unit_price = Decimal("0")
    row = service.create_return(payload, firm_id=setup.firm.id, actor_id=setup.actor_id)
    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)

    completed = service.complete_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    assert completed.status == SalesReturnStatus.COMPLETED.value
    assert completed.grand_total == Decimal("0.0000")
    # No credit to post, so no journal -- but the goods are back, and their
    # cost still leaves cost of sales because the firm owns them again.
    assert completed.journal_entry_id is None
    assert completed.cost_journal_entry_id is not None
    assert _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    ) == on_hand_before + Decimal("2")
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == owed_before


def _stock_value(session: Session, *, firm_id: UUID, product_id: UUID) -> Decimal:
    row = session.scalar(
        select(ProductValuation).where(
            ProductValuation.firm_id == firm_id,
            ProductValuation.product_id == product_id,
        )
    )
    assert row is not None
    return Decimal(str(row.total_value))


def test_cancelling_a_return_of_damaged_goods_takes_their_value_back() -> None:
    """Found by ``scripts/verify_sample_data.py`` against the running backend.

    The movement owned two units and shelved one, so reversing it by the
    sellable bucket alone backed the quantity out and left the value: stock was
    worth 203.16 more than the inventory control account said it was. The
    owned delta is persisted now so the reversal can undo what was applied
    rather than what the buckets imply.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    value_before = _stock_value(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    )
    service, row = setup.completed(quantity=Decimal("2"), damaged=Decimal("1"))
    # Both units came back owned, so both were valued -- that is the point.
    assert (
        _stock_value(session, firm_id=setup.firm.id, product_id=setup.product.id)
        == value_before + COST * 2
    )

    service.cancel_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="error"
    )

    assert (
        _stock_value(session, firm_id=setup.firm.id, product_id=setup.product.id)
        == value_before
    )


def test_a_batch_import_lands_whole_and_carries_the_returns_it_names() -> None:
    """Two returns arrive in one transaction and both are real documents."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)

    rows = service.import_returns(
        SalesReturnImportRequest(
            records=[
                setup.payload(quantity=Decimal("1")),
                setup.payload(quantity=Decimal("2")),
            ]
        ),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert [row.total_current_return_quantity for row in rows] == [
        Decimal("1.0000"),
        Decimal("2.0000"),
    ]
    # Distinct numbers: the second record has to see the counter the first one
    # advanced, which it only does because both are staged on one session.
    assert len({row.return_number for row in rows}) == 2
    assert session.query(SalesReturn).count() == 2


def test_a_refused_batch_leaves_nothing_behind() -> None:
    """The failure that makes a per-row import impossible to finish.

    A loop over ``create_return`` commits as it goes, so a batch whose later
    row is refused returns an error with the earlier rows already written --
    and the corrected file then fails on those as duplicates. The whole batch
    has to land or none of it, and the second record here over-returns the
    dispatch, which is refused.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)

    with pytest.raises(ValidationError):
        service.import_returns(
            SalesReturnImportRequest(
                records=[
                    setup.payload(quantity=Decimal("2")),
                    setup.payload(quantity=Decimal("9")),
                ]
            ),
            firm_scope=setup.firm.id,
            actor_id=setup.actor_id,
        )

    assert session.query(SalesReturn).count() == 0
    assert session.query(SalesReturnLine).count() == 0


def test_the_export_names_every_return_it_lists() -> None:
    """The CSV carries the header plus one row per return."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service, row = setup.completed(quantity=Decimal("2"))

    content = service.export_returns_csv(firm_scope=setup.firm.id)

    lines = [line for line in content.splitlines() if line.strip()]
    assert lines[0].startswith("return_number,customer_return_number,return_date")
    assert len(lines) == 2
    assert row.return_number in lines[1]
    assert str(setup.customer.id) in lines[1]
