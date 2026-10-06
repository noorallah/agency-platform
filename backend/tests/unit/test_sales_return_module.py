"""Sales return lifecycle, stock intake and ledger tests.

A customer could always be credit-noted for goods they sent back, which moved
the money and nothing else: the units stayed counted as sold. These tests are
about the other two books -- what the shelf holds and what the ledger says it
is worth -- because those are the ones that were silently wrong.
"""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.credit_note.models import CreditNote
from app.credit_note.schemas import (
    CreditNoteCreate,
    CreditNoteLineWrite,
    CreditNoteReasonEnum,
)
from app.credit_note.services import CreditNoteService
from app.customers.models import Customer, CustomerReceivableTransaction
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.document_framework.models import DocumentTypeDefinition
from app.finance.models import (
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    LedgerAccount,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.gst_returns.services.gstr_service import GstReturnService
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
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine, SalesInvoiceLineTax
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_return.billing import billed_part, credits_a_bill
from app.sales_return.models import (
    SalesReturn,
    SalesReturnBillPlacement,
    SalesReturnLine,
    SalesReturnLineTax,
)
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnImportRequest,
    SalesReturnLineWrite,
    SalesReturnSourceType,
    SalesReturnStatus,
)
from app.sales_return.services import SalesReturnService
from app.settlements.services.net_sales import invoiced_net
from app.settlements.services.settlement_service import (
    credited_against,
    returned_units_against,
    settled_against,
)
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

    def __init__(
        self,
        session: Session,
        *,
        ordered: Decimal = Decimal("4"),
        billed: Decimal = Decimal("4"),
        approve_bill: bool = True,
    ) -> None:
        """Stock a warehouse, sell four units, and dispatch them.

        ``ordered`` leaves room on the order for a second note: nothing may
        ship past the order line (D-SELL-31). ``billed`` is how many of the
        four the bill charges for -- zero raises no bill at all -- and
        ``approve_bill`` false leaves that bill a draft.
        """
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
                            quantity=ordered,
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
        if billed <= 0:
            return
        self.invoice = self.bill(billed)
        if approve_bill:
            self.invoice = SalesInvoiceService(session).approve_invoice(
                self.invoice.id, firm_scope=self.firm.id, actor_id=self.actor_id
            )
        session.refresh(self.customer)

    def bill(self, quantity: Decimal) -> SalesInvoice:
        """Raise a draft bill for some of the dispatched line."""
        return SalesInvoiceService(self.session).create_invoice(
            SalesInvoiceCreate(
                invoice_date=date(2026, 8, 4),
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=self.note.id,
                        source_document_line_id=self.note_line.id,
                        line_number=1,
                        current_invoice_quantity=quantity,
                        unit_price=PRICE,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def payload(
        self,
        *,
        quantity: Decimal = Decimal("2"),
        damaged: Decimal = Decimal("0"),
        scrap: Decimal = Decimal("0"),
    ) -> SalesReturnCreate:
        """Build a return of the dispatched line."""
        return SalesReturnCreate(
            warehouse_id=self.warehouse.id,
            return_date=date(2026, 8, 5),
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


def test_a_return_cannot_lift_its_own_cap() -> None:
    """D-SELL-29: the request body used to carry a switch for the cap.

    Driven 2026-09-19 on ``fx_t09194xes_s``: 50 returned against a note for
    5 with ``allow_over_return`` true, approved and completed -- 50 back on
    the shelf and 4,832.10 credited. The write schema no longer takes it.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    body = setup.payload(quantity=Decimal("5")).model_dump(mode="json")
    body["allow_over_return"] = True

    with pytest.raises(PydanticValidationError, match="allow_over_return"):
        SalesReturnCreate.model_validate(body)


def test_a_preview_prices_the_return_and_saves_nothing() -> None:
    """The return screen's credit is the save's, and nothing lands."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    returns = session.scalar(select(func.count()).select_from(SalesReturn))
    audits = session.scalar(select(func.count()).select_from(AuditLog))

    preview = service.preview_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert preview.sales_return.grand_total == Decimal("200.0000")
    assert preview.interstate is False
    assert preview.lines[0].product_id == setup.note_line.product_id
    assert session.scalar(select(func.count()).select_from(SalesReturn)) == returns
    assert session.scalar(select(func.count()).select_from(AuditLog)) == audits
    saved = service.create_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert saved.return_number == preview.sales_return.return_number


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


def _undispatched_note(setup: _Dispatch) -> DeliveryNoteLine:
    """Approve a second note for one more unit, and leave it in the warehouse.

    The setup must have ordered at least five: a note can no longer ship past
    its order line, which it used to by setting ``allow_over_delivery``.
    """
    notes = DeliveryNoteService(setup.session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=setup.note.sales_order_id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=setup.note_line.sales_order_line_id,
                    line_number=1,
                    current_delivery_quantity=Decimal("1"),
                    unit_price=PRICE,
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    notes.approve_note(note.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    line = setup.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None
    return line


def test_goods_that_never_left_cannot_come_back() -> None:
    """D-SELL-6: a return against an approved note that never dispatched.

    Driven 2026-09-19: completing it shelved a unit that had never gone out,
    posted the return journals and credited the customer for it.
    """
    session = _session_factory()()
    setup = _Dispatch(session, ordered=Decimal("5"))
    kept = _undispatched_note(setup)
    payload = setup.payload(quantity=Decimal("1"))
    payload.lines[0].source_document_id = kept.delivery_note_id
    payload.lines[0].source_document_line_id = kept.id

    with pytest.raises(ValidationError, match="only goods on a dispatched delivery"):
        SalesReturnService(session).create_return(
            payload, firm_id=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_dispatched_note_cannot_front_for_another_notes_line() -> None:
    """The line has to be the named document's own, or the check is bypassed."""
    session = _session_factory()()
    setup = _Dispatch(session, ordered=Decimal("5"))
    kept = _undispatched_note(setup)
    payload = setup.payload(quantity=Decimal("1"))
    payload.lines[0].source_document_line_id = kept.id

    with pytest.raises(ValidationError, match="line of the source document"):
        SalesReturnService(session).create_return(
            payload, firm_id=setup.firm.id, actor_id=setup.actor_id
        )


def _invoice_return(setup: _Dispatch) -> SalesReturnCreate:
    """Describe a return of two against the bill rather than the note."""
    line = setup.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == setup.invoice.id
        )
    )
    assert line is not None
    payload = setup.payload(quantity=Decimal("2"))
    payload.lines[0].source_document_type = SalesReturnSourceType.SALES_INVOICE
    payload.lines[0].source_document_id = setup.invoice.id
    payload.lines[0].source_document_line_id = line.id
    return payload


@pytest.mark.parametrize("status", ["DRAFT", "CANCELLED"])
def test_a_bill_that_does_not_stand_takes_no_return(status: str) -> None:
    """A draft sold nothing yet, and a cancelled bill sold nothing at all.

    WHOLE01 SR-2026-2027-000002 was raised against SI-2026-2027-000008, since
    cancelled (D-SELL-6).
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    invoice = session.get(SalesInvoice, setup.invoice.id)
    assert invoice is not None
    invoice.status = status
    session.commit()

    with pytest.raises(ValidationError, match="only goods on an approved sales"):
        SalesReturnService(session).create_return(
            _invoice_return(setup), firm_id=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_return_saved_before_the_check_does_not_complete() -> None:
    """Asked again where the stock arrives and the customer is credited."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    row = service.create_return(
        _invoice_return(setup), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    # What a bill cancelled under a return looked like before the refusal.
    invoice = session.get(SalesInvoice, setup.invoice.id)
    assert invoice is not None
    invoice.status = "CANCELLED"
    session.commit()

    with pytest.raises(ValidationError, match="is cancelled"):
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
    # Each id the register carries is named beside it, or the grid -- which
    # derives its columns from the row -- shows UUIDs (D-RPT-17).
    assert (register[0].customer_id, register[0].customer_name) == (
        setup.customer.id,
        setup.customer.display_name,
    )
    assert (register[0].branch_id, register[0].branch_name) == (
        setup.branch.id,
        setup.branch.name,
    )
    assert (register[0].warehouse_id, register[0].warehouse_name) == (
        setup.warehouse.id,
        setup.warehouse.name,
    )
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


def test_the_list_finds_a_return_by_its_customer_and_names_them() -> None:
    """Search by the shop as well as the return, and each row says whose it is.

    The owner asked the Sales Returns list to name the customer and be
    searchable by one, as the other sales lists are (2026-09-27).
    """
    from app.sales_return.schemas import SalesReturnListFilters

    session = _session_factory()()
    setup = _Dispatch(session)
    service, row = setup.completed(quantity=Decimal("2"))

    for search, expected in ((setup.customer.code, 1), ("nobody by this name", 0)):
        _, found = service.list_returns(
            firm_scope=setup.firm.id,
            filters=SalesReturnListFilters(),
            page=1,
            page_size=20,
            search=search,
            sort_by="created_at",
            descending=True,
        )
        assert found == expected, search

    response = service.return_response(row)
    assert response.customer_name == setup.customer.display_name
    assert response.customer_code == setup.customer.code


def test_cancelling_a_return_that_became_an_advance_puts_both_balances_back() -> None:
    """A credit larger than the balance splits, and the undo has to unsplit it.

    `post_receivable_transaction` applies a credit note up to what the customer
    owes and books the rest as an unapplied advance: 500 against an outstanding
    300 is 300 off the balance and 200 of advance. Cancelling posted a fresh
    INVOICE for the whole 500, which put all of it back on the balance and left
    the advance standing -- so the customer owed more than before the return
    ever happened, and held an advance no money ever paid for.

    Net exposure (`outstanding - advance`) still came out right, which is why
    nothing noticed. The two figures were individually wrong and cancelled each
    other out. An aging report reads `outstanding` on its own, and an advance
    can be applied to a real invoice.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    row = service.create_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)

    # Owe less than the return is worth, so the credit note has to split.
    credit = Decimal(str(row.grand_total))
    setup.customer.current_outstanding = credit - Decimal("100")
    setup.customer.unapplied_advance_balance = Decimal("0")
    session.commit()
    outstanding_before = Decimal(str(setup.customer.current_outstanding))

    service.complete_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")
    assert Decimal(str(setup.customer.unapplied_advance_balance)) == Decimal("100")

    service.cancel_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="undo"
    )
    session.refresh(setup.customer)

    assert Decimal(str(setup.customer.current_outstanding)) == outstanding_before
    assert Decimal(str(setup.customer.unapplied_advance_balance)) == Decimal("0")


def _inventory_account(session: Session, firm_id: UUID) -> Decimal:
    """Return what the inventory control account holds."""
    total = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .select_from(GLPosting)
        .join(
            FirmControlAccount,
            FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
        )
        .where(
            FirmControlAccount.firm_id == firm_id,
            FirmControlAccount.purpose == ControlAccountPurpose.INVENTORY.value,
            FirmControlAccount.is_deleted.is_(False),
            GLPosting.is_deleted.is_(False),
        )
    )
    return Decimal(str(total or 0))


def _warehouse_value(session: Session, firm_id: UUID) -> Decimal:
    """Return what the warehouse says all its stock is worth."""
    total = session.scalar(
        select(func.coalesce(func.sum(ProductValuation.total_value), 0)).where(
            ProductValuation.firm_id == firm_id,
            ProductValuation.is_deleted.is_(False),
        )
    )
    return Decimal(str(total or 0))


def test_goods_returned_into_another_branchs_warehouse_land_on_its_row() -> None:
    """A return restocks the warehouse's own branch, not the document's.

    The return takes its branch from what it credits. Taking goods back into
    a warehouse of another branch paired the two, and completing the return
    was refused: "Warehouse does not belong to the selected branch." (found
    beside plan item 9.12, 2026-09-13).
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    head_office = Branch(
        firm_id=setup.firm.id,
        code="BR-HO",
        name="Head Office",
        display_name="Head Office",
        status="ACTIVE",
    )
    session.add(head_office)
    session.commit()
    depot = Warehouse(
        firm_id=setup.firm.id,
        branch_id=head_office.id,
        code="WH-DEPOT",
        name="Depot",
        display_name="Depot",
        status="ACTIVE",
    )
    session.add(depot)
    session.commit()
    setup.warehouse = depot

    _, row = setup.completed(quantity=Decimal("2"))

    rows = session.scalars(
        select(InventoryRecord).where(
            InventoryRecord.warehouse_id == depot.id,
            InventoryRecord.product_id == setup.product.id,
        )
    ).all()
    assert [r.branch_id for r in rows] == [head_office.id]
    assert Decimal(str(rows[0].current_quantity)) == Decimal("2")


def _against_the_bill(setup: _Dispatch, quantity: str) -> SalesReturnCreate:
    """Describe a return of the same goods through the bill that charged them."""
    line = setup.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == setup.invoice.id
        )
    )
    assert line is not None
    payload = setup.payload(quantity=Decimal(quantity))
    payload.lines[0].source_document_type = SalesReturnSourceType.SALES_INVOICE
    payload.lines[0].source_document_id = setup.invoice.id
    payload.lines[0].source_document_line_id = line.id
    return payload


def test_goods_back_through_the_note_are_not_returned_again_through_the_bill() -> None:
    """D-SELL-7: the cap was per source line, and these are one set of goods.

    Driven 2026-09-19: 5 dispatched and billed, 5 returned against the note and
    5 more against the bill, both completed -- 10 back on the shelf and the
    customer credited twice.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    service.create_return(
        setup.payload(quantity=Decimal("3")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    with pytest.raises(ValidationError, match="exceeds what left on DN"):
        service.create_return(
            _against_the_bill(setup, "2"),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    session.rollback()
    # What is left of the four still comes back either way.
    assert service.create_return(
        _against_the_bill(setup, "1"), firm_id=setup.firm.id, actor_id=setup.actor_id
    )


def test_goods_back_through_the_bill_are_not_returned_again_through_the_note() -> None:
    """The same count read from the other side."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    service.create_return(
        _against_the_bill(setup, "3"), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(ValidationError, match="3 already returned"):
        service.create_return(
            setup.payload(quantity=Decimal("2")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_bill_whose_goods_came_back_through_the_note_cannot_be_cancelled() -> None:
    """Or the customer is credited for the return and the whole bill besides."""
    session = _session_factory()()
    setup = _Dispatch(session)
    returned = SalesReturnService(session).create_return(
        setup.payload(quantity=Decimal("1")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    with pytest.raises(ValidationError, match=returned.return_number):
        SalesInvoiceService(session).cancel_invoice(
            setup.invoice.id,
            firm_scope=setup.firm.id,
            actor_id=setup.actor_id,
            reason="Raised in error.",
        )


def _charge_gst(setup: _Dispatch) -> SalesInvoiceLine:
    """Record that the bill charged 18% GST on its line, as CGST and SGST.

    The unit suite configures no tax rules, so the rules would charge nothing
    today: whatever a return reverses can only have come off the bill.
    """
    line = setup.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == setup.invoice.id
        )
    )
    assert line is not None
    line.tax_amount = Decimal("72")  # 18% of 4 x 100
    for sequence, code in enumerate(("CGST", "SGST"), start=1):
        setup.session.add(
            SalesInvoiceLineTax(
                sales_invoice_line_id=line.id,
                firm_id=setup.firm.id,
                sequence=sequence,
                component_code=code,
                component_label=f"{code} 9%",
                percentage=Decimal("9"),
                base_amount=Decimal("400"),
                amount=Decimal("36"),
            )
        )
    setup.session.commit()
    return line


def _components(session: Session, row: SalesReturn) -> list[tuple[str, Decimal]]:
    """Return what each component of a return reversed, in order."""
    return [
        (tax.component_code, tax.amount)
        for tax in session.scalars(
            select(SalesReturnLineTax)
            .join(
                SalesReturnLine,
                SalesReturnLine.id == SalesReturnLineTax.sales_return_line_id,
            )
            .where(SalesReturnLine.sales_return_id == row.id)
            .order_by(SalesReturnLineTax.sequence)
        ).all()
    ]


def test_a_return_reverses_the_tax_the_bill_charged() -> None:
    """D-SELL-21: the tax was worked out again through today's rules.

    Driven 2026-09-19 on a fixture: a rule cutting GST 18% to 12% after the
    sale made a return of goods billed at 18% reverse 12% -- a different tax
    from the one collected. The bill charged CGST 36 + SGST 36 on four; two
    coming back take half of each, whatever the rules say now.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    _charge_gst(setup)

    row = SalesReturnService(session).create_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert row.tax_total == Decimal("36.0000")
    assert _components(session, row) == [
        ("CGST", Decimal("18.0000")),
        ("SGST", Decimal("18.0000")),
    ]


def test_a_return_raised_on_the_bill_reverses_its_tax_too() -> None:
    """The same goods named through the bill's own line."""
    session = _session_factory()()
    setup = _Dispatch(session)
    charged = _charge_gst(setup)
    payload = setup.payload(quantity=Decimal("1"))
    payload.lines[0].source_document_type = SalesReturnSourceType.SALES_INVOICE
    payload.lines[0].source_document_id = setup.invoice.id
    payload.lines[0].source_document_line_id = charged.id

    row = SalesReturnService(session).create_return(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    assert row.tax_total == Decimal("18.0000")
    assert _components(session, row) == [
        ("CGST", Decimal("9.0000")),
        ("SGST", Decimal("9.0000")),
    ]


def test_a_return_not_yet_completed_has_returned_nothing() -> None:
    """Only completing brings the goods back, so only completed returns count.

    `_SPENT_STATUSES` is CANCELLED alone -- rightly, for the claim a draft
    holds on the source line -- and the three reports read it, so a DRAFT
    return was reported as returned and its `restock_quantity` as back on the
    shelf while the goods were still with the customer (SR-2026-2027-000001,
    DRAFT: 2 returned, 2 restocked; D-RPT-10).
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    row = service.create_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert service.by_customer_report(firm_scope=setup.firm.id) == []
    assert service.by_product_report(firm_scope=setup.firm.id) == []
    assert service.reconciliation_report(firm_scope=setup.firm.id) == []
    # It still holds its claim on the dispatched line, so a second return of
    # the same goods is refused -- that is the claim, not the report.
    assert len(service.register_report(firm_scope=setup.firm.id)) == 1

    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    assert service.by_product_report(firm_scope=setup.firm.id) == []

    service.complete_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    [product] = service.by_product_report(firm_scope=setup.firm.id)
    assert product.return_quantity == Decimal("2.0000")
    assert service.by_customer_report(firm_scope=setup.firm.id)[0].return_count == 1
    assert len(service.reconciliation_report(firm_scope=setup.firm.id)) == 1


def test_the_return_reports_take_a_window_and_a_page() -> None:
    """D-RPT-18: every report was the firm's whole history.

    All four are read on the return's own `return_date`, both ends inclusive,
    with `total_records` counting the matches rather than the page, and a
    page above the cap refused with a 422.
    """
    from app.sales_return.api.router import (
        router,
        sales_return_reconciliation,
        sales_return_register,
        sales_returns_by_customer,
        sales_returns_by_product,
    )
    from tests.unit.report_windows import assert_page_size_is_bounded, report_scope

    session = _session_factory()()
    setup = _Dispatch(session)
    days = [date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 7)]
    for day in days:
        _service, row = setup.completed(quantity=Decimal("1"))
        row.return_date = day
    session.commit()
    scope = report_scope(setup.firm.id)

    page = sales_return_register(
        scope=scope,
        db=session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=1,
    )
    assert page.pagination.total_records == 2
    assert [record.return_date for record in page.data] == [days[2]]

    [customer] = sales_returns_by_customer(
        scope=scope, db=session, from_date=days[0], to_date=days[0]
    ).data
    assert customer.return_count == 1
    [product] = sales_returns_by_product(scope=scope, db=session, to_date=days[1]).data
    assert product.return_count == 2
    lines = sales_return_reconciliation(
        scope=scope, db=session, from_date=days[1], page=2, page_size=1
    )
    assert lines.pagination.total_records == 2
    assert [record.return_date for record in lines.data] == [days[1]]

    assert_page_size_is_bounded(
        router,
        "/api/v1/sales-returns/reports/register",
        "/api/v1/sales-returns/reports/by-customer",
        "/api/v1/sales-returns/reports/by-product",
        "/api/v1/sales-returns/reports/reconciliation",
    )


def _credits(session: Session) -> list[CustomerReceivableTransaction]:
    """Return the rows sales returns put on customers' accounts."""
    return list(
        session.scalars(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.reference_type == "SALES_RETURN"
            )
        ).all()
    )


def _left_to_bill(setup: _Dispatch) -> Decimal:
    """Read what the note still offers for billing, as the bill screen does."""
    documents = SalesInvoiceService(setup.session).billable_documents(
        firm_scope=setup.firm.id
    )
    return sum(
        (
            line.remaining_quantity
            for document in documents
            if document.source_document_id == setup.note.id
            for line in document.lines
        ),
        Decimal("0"),
    )


def test_goods_back_before_billing_credit_nothing_and_reverse_no_tax() -> None:
    """D-SELL-55: a return against a note never billed credited its full price.

    Driven 2026-10-05: an order of 5 dispatched and never billed, returned
    whole -- the customer came out 590.00 in advance, the journal debited
    Sales Returns 500 and reversed 90 of output tax never raised, and the note
    still offered all 5 for billing. Goods back before billing move stock and
    cost only (the selling twin of D-BUY-26).
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("0"))
    on_hand_before = _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    )
    returns_before = _account_movement(session, setup.firm.id, "sales return")
    cost_before = _account_movement(session, setup.firm.id, "cost of goods")

    _service, row = setup.completed(quantity=Decimal("3"))

    assert row.status == SalesReturnStatus.COMPLETED.value
    assert row.grand_total == Decimal("300.0000"), "the document still states it"
    # The shelf and its cost move.
    assert _on_hand(
        session, firm_id=setup.firm.id, product_id=setup.product.id
    ) == on_hand_before + Decimal("3")
    assert row.cost_journal_entry_id is not None
    assert _account_movement(
        session, setup.firm.id, "cost of goods"
    ) - cost_before == -(COST * 3)
    # The customer's account and the sales side do not.
    assert _credits(session) == []
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")
    assert Decimal(str(setup.customer.unapplied_advance_balance)) == Decimal("0")
    assert row.journal_entry_id is None
    assert _account_movement(session, setup.firm.id, "sales return") == returns_before
    line = session.scalar(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == row.id)
    )
    assert line is not None and line.unbilled_quantity == Decimal("3.0000")
    # And the note has one left to bill, not four.
    assert _left_to_bill(setup) == Decimal("1.0000")
    with pytest.raises(
        ValidationError,
        # Counted plainly: "3.0000 of the 4.0000 delivered" (D-PRC-62).
        match="3 of the 4 delivered came back before being billed, so 1 is left",
    ):
        setup.bill(Decimal("4"))
    session.rollback()
    assert setup.bill(Decimal("1")).grand_total == Decimal("100.0000")
    # No credit note for the tax returns to declare.
    assert session.scalars(select(SalesReturn).where(credits_a_bill())).all() == []


def test_a_part_billed_note_is_credited_only_for_the_share_billed() -> None:
    """Returned goods are taken first from the part nobody was billed for.

    Four delivered, three billed, two come back: one was never charged and
    one was. The customer is credited for one, and nothing is left to bill.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("3"))
    owed_before = Decimal(str(setup.customer.current_outstanding))
    returns_before = _account_movement(session, setup.firm.id, "sales return")

    _service, row = setup.completed(quantity=Decimal("2"))

    line = session.scalar(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == row.id)
    )
    assert line is not None and line.unbilled_quantity == Decimal("1.0000")
    [credit] = _credits(session)
    assert credit.amount == Decimal("100.00")
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == owed_before - 100
    assert _account_movement(
        session, setup.firm.id, "sales return"
    ) - returns_before == Decimal("100.00")
    assert _left_to_bill(setup) == Decimal("0")
    # The reports that net returns off billed sales read the billed part.
    assert session.scalars(select(SalesReturn).where(credits_a_bill())).all() == [row]
    billed_value = session.scalar(
        select(func.sum(billed_part(SalesReturnLine.net_amount))).where(
            SalesReturnLine.sales_return_id == row.id
        )
    )
    assert Decimal(str(billed_value)).quantize(Decimal("0.01")) == Decimal("100.00")


def test_goods_back_after_the_bill_was_cancelled_credit_nothing() -> None:
    """A cancelled bill charged nothing, so its note is unbilled again."""
    session = _session_factory()()
    setup = _Dispatch(session)
    SalesInvoiceService(session).cancel_invoice(
        setup.invoice.id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
        reason="Raised in error.",
    )
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")

    _service, row = setup.completed(quantity=Decimal("2"))

    assert _credits(session) == []
    assert row.journal_entry_id is None
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.unapplied_advance_balance)) == Decimal("0")
    assert _left_to_bill(setup) == Decimal("2.0000")


def test_a_draft_bill_is_refused_for_goods_that_came_back_while_it_waited() -> None:
    """A draft has charged nothing, so the return is before billing."""
    session = _session_factory()()
    setup = _Dispatch(session, approve_bill=False)

    _service, row = setup.completed(quantity=Decimal("1"))

    assert _credits(session) == []
    with pytest.raises(ValidationError, match="came back before being billed"):
        SalesInvoiceService(session).approve_invoice(
            setup.invoice.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_cancelling_a_return_before_billing_puts_the_goods_back_to_bill() -> None:
    """The goods are the customer's again, so the note may bill them."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("0"))
    service, row = setup.completed(quantity=Decimal("3"))
    assert _left_to_bill(setup) == Decimal("1.0000")

    service.cancel_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="Miskeyed."
    )

    assert _left_to_bill(setup) == Decimal("4.0000")
    assert _credits(session) == []
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")


def test_the_return_reports_value_a_return_at_what_was_credited() -> None:
    """D-SELL-74: five returns read 1,770.00 for a customer credited 472.00.

    The reports summed the documents' totals. Four delivered, three billed,
    two back: one unit was credited and one came back as stock alone, so the
    figures are 100.00 credited and a quantity of 1 with no value.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("3"))
    service, row = setup.completed(quantity=Decimal("2"))
    assert row.grand_total == Decimal("200.0000")

    [listed] = service.register_report(firm_scope=setup.firm.id)
    assert (listed.grand_total, listed.credited_amount, listed.unbilled_quantity) == (
        Decimal("200.0000"),
        Decimal("100.0000"),
        Decimal("1.0000"),
    )
    [customer] = service.by_customer_report(firm_scope=setup.firm.id)
    assert (customer.return_amount, customer.unbilled_quantity) == (
        Decimal("100.0000"),
        Decimal("1.0000"),
    )
    [product] = service.by_product_report(firm_scope=setup.firm.id)
    assert (
        product.return_quantity,
        product.return_amount,
        product.unbilled_quantity,
    ) == (Decimal("2.0000"), Decimal("100.0000"), Decimal("1.0000"))
    assert service.summary(firm_scope=setup.firm.id).total_return_value == Decimal(
        "100.0000"
    )


def test_a_return_before_billing_is_reported_as_quantity_with_no_value() -> None:
    """Wholly before billing: nothing credited anywhere, the quantity shown."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("0"))
    service, _row = setup.completed(quantity=Decimal("3"))

    [listed] = service.register_report(firm_scope=setup.firm.id)
    assert (listed.credited_amount, listed.unbilled_quantity) == (
        Decimal("0.0000"),
        Decimal("3.0000"),
    )
    [customer] = service.by_customer_report(firm_scope=setup.firm.id)
    assert customer.return_amount == Decimal("0.0000")
    [product] = service.by_product_report(firm_scope=setup.firm.id)
    assert (product.return_quantity, product.return_amount) == (
        Decimal("3.0000"),
        Decimal("0.0000"),
    )
    assert service.summary(firm_scope=setup.firm.id).total_return_value == Decimal(
        "0.0000"
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


def _charge_on_the_header(setup: _Dispatch, charges: str) -> None:
    """Record that the note and its bill charged this much on their headers.

    A return gives back only header charges its source made (D-PRC-64), so a
    test about a return carrying some needs a source that charged them.
    """
    setup.note.additional_charges = Decimal(charges)
    invoice = getattr(setup, "invoice", None)
    if invoice is not None:
        invoice.additional_charges = Decimal(charges)
    setup.session.commit()


def _completed_with_header(
    setup: _Dispatch, *, quantity: str, charges: str, round_off: str
) -> tuple[SalesReturnService, SalesReturn]:
    """Complete a return that carries charges and rounding on its header."""
    _charge_on_the_header(setup, charges)
    service = SalesReturnService(setup.session)
    row = service.create_return(
        setup.payload(quantity=Decimal(quantity)).model_copy(
            update={
                "additional_charges": Decimal(charges),
                "round_off": Decimal(round_off),
            }
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    return service, service.complete_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )


def test_the_summary_counts_no_header_charge_of_a_return_that_credited_nothing() -> (
    None
):
    """D-SELL-80: 50.00 of charges and 0.40 of rounding read as returned value.

    Driven 2026-10-05: goods back before billing, with additional charges on
    the return. Nothing was credited and the register said so, but the
    summary took the unbilled share of the lines off the document total and
    kept what sat on the header.
    """
    session = _request_session()
    setup = _Dispatch(session, billed=Decimal("0"))
    service, row = _completed_with_header(
        setup, quantity="3", charges="50", round_off="0.40"
    )
    assert row.grand_total == Decimal("350.4000"), "the document still states it"
    assert _credits(session) == []

    [listed] = service.register_report(firm_scope=setup.firm.id)
    assert listed.credited_amount == Decimal("0.0000")
    assert service.summary(firm_scope=setup.firm.id).total_return_value == Decimal(
        "0.0000"
    )


def test_the_summary_agrees_with_the_register_on_a_part_billed_return() -> None:
    """The summary reads the figure the register and the account read.

    Four delivered, three billed, two back with 20.00 of charges: one unit
    is credited and the charge goes with it. Beside it a draft, which has
    credited nothing yet: it is stated apart, as pending, and leaves the
    credited figure where the register has it (D-SELL-84).
    """
    session = _request_session()
    setup = _Dispatch(session, billed=Decimal("3"))
    service, _row = _completed_with_header(
        setup, quantity="2", charges="20", round_off="-0.25"
    )
    [credit] = _credits(session)

    [listed] = service.register_report(firm_scope=setup.firm.id)
    assert listed.credited_amount == Decimal("119.7500")
    assert credit.amount == Decimal("119.75")
    assert (
        service.summary(firm_scope=setup.firm.id).total_return_value
        == listed.credited_amount
    )

    draft = service.create_return(
        setup.payload(quantity=Decimal("1")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    summary = service.summary(firm_scope=setup.firm.id)
    assert summary.total_return_value == listed.credited_amount
    assert summary.pending_return_value == draft.grand_total


def _credited_in_register(service: SalesReturnService, firm_id: UUID) -> Decimal:
    """Add up what the register says the firm's returns credited."""
    return sum(
        (row.credited_amount for row in service.register_report(firm_scope=firm_id)),
        Decimal("0"),
    )


def test_the_summary_values_a_return_the_same_at_every_step_of_its_life() -> None:
    """D-SELL-84: a never-billed return read 640.00 as a draft, then nothing.

    Driven 2026-10-06: five delivered, never billed, five back with 50.00 of
    charges. The summary added 640.00 while the return was a draft and while
    it was approved, and took it off again at completion, because the split
    between billed and unbilled goods is stamped on the lines only then. The
    register read 0.00 throughout. Now the value is what completed returns
    credited -- the register's own total -- and what is still on its way is
    stated beside it.
    """
    session = _request_session()
    setup = _Dispatch(session, billed=Decimal("0"))
    _charge_on_the_header(setup, "50")
    service = SalesReturnService(session)
    firm = setup.firm.id
    row = service.create_return(
        setup.payload(quantity=Decimal("3")).model_copy(
            update={"additional_charges": Decimal("50")}
        ),
        firm_id=firm,
        actor_id=setup.actor_id,
    )
    stated = Decimal(str(row.grand_total))
    assert stated == Decimal("350.0000")

    for step in ("draft", "approved"):
        if step == "approved":
            service.approve_return(row.id, firm_scope=firm, actor_id=setup.actor_id)
        summary = service.summary(firm_scope=firm)
        assert summary.total_return_value == Decimal("0.0000"), step
        assert summary.total_return_value == _credited_in_register(service, firm)
        assert summary.pending_return_value == stated, step

    service.complete_return(row.id, firm_scope=firm, actor_id=setup.actor_id)
    summary = service.summary(firm_scope=firm)
    assert summary.total_return_value == Decimal("0.0000")
    assert summary.total_return_value == _credited_in_register(service, firm)
    assert summary.pending_return_value == Decimal("0.0000")


def test_a_billed_return_adds_its_value_only_when_it_completes() -> None:
    """A draft against a bill is pending; completing it moves it to credited."""
    session = _request_session()
    setup = _Dispatch(session)
    service = SalesReturnService(session)
    firm = setup.firm.id
    row = service.create_return(
        setup.payload(quantity=Decimal("2")), firm_id=firm, actor_id=setup.actor_id
    )
    stated = Decimal(str(row.grand_total))

    summary = service.summary(firm_scope=firm)
    assert (summary.total_return_value, summary.pending_return_value) == (
        Decimal("0.0000"),
        stated,
    )
    assert _credited_in_register(service, firm) == Decimal("0")

    service.approve_return(row.id, firm_scope=firm, actor_id=setup.actor_id)
    service.complete_return(row.id, firm_scope=firm, actor_id=setup.actor_id)
    summary = service.summary(firm_scope=firm)
    assert (summary.total_return_value, summary.pending_return_value) == (
        stated,
        Decimal("0.0000"),
    )
    assert summary.total_return_value == _credited_in_register(service, firm)


def test_a_return_on_a_note_names_the_bill_it_credits() -> None:
    """D-SELL-75: "against invoice" was blank though the return credited one.

    A return raised against a delivery note reverses the bill that charged
    the note's line; the GST sales register and GSTR-1's CDNR both read the
    bill off this credit, and showed none.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    _service, row = setup.completed(quantity=Decimal("2"))
    bill_line = session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == setup.invoice.id
        )
    )
    assert bill_line is not None

    [credit] = GstReturnService(session)._returns_as_credits([row])

    assert credit.against_invoice_ids == [setup.invoice.id]
    assert credit.against_invoice_number == setup.invoice.invoice_number
    assert [item[1] for item in credit.items] == [bill_line.id]


# ---- a return after a credit note (D-SELL-88) -------------------------------
#
# The fifth pricing check (2026-10-06): a bill of 2,832.00 took a
# rate-difference credit note of 472.00 and was then returned in full for
# 2,832.00 -- 3,304.00 credited against a bill of 2,832.00. Here the bill is
# four at 100.00 with 72.00 of GST, 472.00 in all.


def _credit_note(setup: _Dispatch, taxable: str, *, approve: bool = True) -> CreditNote:
    """Credit the bill's line some value with no goods coming back."""
    line = setup.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == setup.invoice.id
        )
    )
    assert line is not None
    service = CreditNoteService(setup.session)
    note = service.create_note(
        CreditNoteCreate(
            sales_invoice_id=setup.invoice.id,
            credit_note_date=date(2026, 8, 5),
            reason=CreditNoteReasonEnum.RATE_DIFFERENCE,
            lines=[
                CreditNoteLineWrite(
                    sales_invoice_line_id=line.id,
                    line_number=1,
                    quantity=Decimal("4"),
                    taxable_amount=Decimal(taxable),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    if approve:
        service.approve_note(note.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    setup.session.commit()
    return note


def _returned(
    setup: _Dispatch, payload: SalesReturnCreate, *, complete: bool = True
) -> SalesReturn:
    """Raise and approve a return, and complete it unless told not to."""
    service = SalesReturnService(setup.session)
    row = service.create_return(payload, firm_id=setup.firm.id, actor_id=setup.actor_id)
    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    if complete:
        row = service.complete_return(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )
    return row


def _credited_on_the_bill(setup: _Dispatch) -> Decimal:
    """Return everything returns and credit notes have taken off the bill."""
    return credited_against(
        setup.session, firm_id=setup.firm.id, invoice_ids=[setup.invoice.id]
    ).get(setup.invoice.id, Decimal("0"))


def test_a_return_after_a_credit_note_credits_what_the_bill_is_still_worth() -> None:
    """80.00 credited off 400.00, then all four back: 320.00, not 400.00.

    With the tax that follows each, the note is 94.40 and the return 377.60:
    472.00 between them, which is the bill and not a rupee more.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    _charge_gst(setup)
    _credit_note(setup, "80")

    row = _returned(setup, _against_the_bill(setup, "4"))

    line = session.scalars(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == row.id)
    ).one()
    assert (line.gross_amount, line.bill_discount_amount) == (
        Decimal("400.0000"),
        Decimal("80.0000"),
    )
    assert (row.subtotal, row.tax_total) == (Decimal("320.0000"), Decimal("57.6000"))
    assert row.grand_total == Decimal("377.6000")
    assert [credit.amount for credit in _credits(session)] == [Decimal("377.60")]
    assert _credited_on_the_bill(setup) == Decimal("472.00")


def test_a_credit_note_is_spread_over_the_units_still_out() -> None:
    """One back is a quarter of what is left; the last three take the rest."""
    session = _session_factory()()
    setup = _Dispatch(session)
    _charge_gst(setup)
    _credit_note(setup, "80")

    first = _returned(setup, _against_the_bill(setup, "1"))
    rest = _returned(setup, _against_the_bill(setup, "3"))

    assert (first.subtotal, rest.subtotal) == (
        Decimal("80.0000"),
        Decimal("240.0000"),
    )
    assert _credited_on_the_bill(setup) == Decimal("472.00")


def test_goods_back_before_the_credit_note_leave_it_to_the_rest() -> None:
    """Two back at full price, 150.00 credited, then the other two: 50.00.

    The note can only be about the goods the customer kept, so the whole of
    it comes off them -- pro-rated over all four, the last two would have
    come back at 125.00 and the bill been credited 475.00 of its 400.00.
    """
    session = _session_factory()()
    setup = _Dispatch(session)
    _charge_gst(setup)

    first = _returned(setup, _against_the_bill(setup, "2"))
    _credit_note(setup, "150")
    rest = _returned(setup, _against_the_bill(setup, "2"))

    assert (first.subtotal, rest.subtotal) == (
        Decimal("200.0000"),
        Decimal("50.0000"),
    )
    assert _credited_on_the_bill(setup) == Decimal("472.00")


def test_goods_back_through_the_note_are_worth_what_the_bill_is_too() -> None:
    """The same goods by the other door credit the same 320.00."""
    session = _session_factory()()
    setup = _Dispatch(session)
    _charge_gst(setup)
    _credit_note(setup, "80")

    row = _returned(setup, setup.payload(quantity=Decimal("4")))

    assert (row.subtotal, row.tax_total) == (Decimal("320.0000"), Decimal("57.6000"))


def test_a_draft_credit_note_takes_nothing_off_a_return() -> None:
    """A note nobody approved has credited nothing yet."""
    session = _session_factory()()
    setup = _Dispatch(session)
    _credit_note(setup, "80", approve=False)

    row = _returned(setup, _against_the_bill(setup, "4"), complete=False)

    assert row.subtotal == Decimal("400.0000")


def test_a_return_priced_before_a_credit_note_does_not_complete() -> None:
    """The note approved in between took 80.00 of what the return credits."""
    session = _session_factory()()
    setup = _Dispatch(session)
    row = _returned(setup, _against_the_bill(setup, "4"), complete=False)
    _credit_note(setup, "80")

    with pytest.raises(ValidationError, match="credited since this return was saved"):
        SalesReturnService(session).complete_return(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


# ---- a return priced above its bill (D-PRC-64) ------------------------------
#
# The sixth pricing check (2026-10-06): on a bill of 2,832.00 with no credit
# note, a return typed 1,500.00 a box credited 3,540.00, a line charge of
# 500.00 credited 3,422.00 and a header charge of 500.00 credited 3,332.00.
# The cap of D-SELL-88 only ran once a credit note existed. Here the bill is
# four at 100.00.


def _priced(payload: SalesReturnCreate, **typed: Decimal) -> SalesReturnCreate:
    """Type a price or a charge on the one line of a return."""
    for name, value in typed.items():
        setattr(payload.lines[0], name, value)
    return payload


def test_a_price_typed_above_the_bill_is_refused_by_name() -> None:
    """125.00 a unit against a bill at 100.00, with no credit note at all."""
    session = _session_factory()()
    setup = _Dispatch(session)
    service = SalesReturnService(session)

    with pytest.raises(ValidationError) as refusal:
        service.create_return(
            _priced(_against_the_bill(setup, "4"), unit_price=Decimal("125")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )

    message = str(refusal.value)
    assert "Line 1: the return credits 500.00" in message
    assert f"{setup.invoice.invoice_number} billed at 400.00" in message
    assert "still worth 400.00" in message


def test_a_charge_typed_on_a_line_the_bill_never_charged_is_refused() -> None:
    """The goods at the bill's price and 50.00 of charges on top of them."""
    session = _session_factory()()
    setup = _Dispatch(session)

    with pytest.raises(ValidationError, match="credits 250.00 .* billed at 200.00"):
        SalesReturnService(session).create_return(
            _priced(_against_the_bill(setup, "2"), charges_amount=Decimal("50")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_price_above_the_bill_is_refused_through_the_note_too() -> None:
    """The same goods by the other door are worth the same bill."""
    session = _session_factory()()
    setup = _Dispatch(session)

    with pytest.raises(ValidationError, match="credits 250.00 .* billed at 200.00"):
        SalesReturnService(session).create_return(
            _priced(setup.payload(quantity=Decimal("2")), unit_price=Decimal("125")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_price_typed_below_the_bill_stands() -> None:
    """A restocking deduction: 90.00 credited for a unit billed at 100.00."""
    session = _session_factory()()
    setup = _Dispatch(session)

    row = _returned(
        setup, _priced(_against_the_bill(setup, "4"), unit_price=Decimal("90"))
    )

    assert row.subtotal == Decimal("360.0000")
    assert [credit.amount for credit in _credits(session)] == [Decimal("360.00")]


def test_header_charges_the_bill_never_made_are_refused() -> None:
    """50.00 of additional charges on a return of a bill that charged none."""
    session = _session_factory()()
    setup = _Dispatch(session)

    with pytest.raises(ValidationError) as refusal:
        SalesReturnService(session).create_return(
            _against_the_bill(setup, "4").model_copy(
                update={"additional_charges": Decimal("50")}
            ),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )

    message = str(refusal.value)
    assert "credits 50.00 of additional charges" in message
    assert f"{setup.invoice.invoice_number} charged 0.00" in message


def test_header_charges_come_back_once_and_no_more() -> None:
    """The bill charged 50.00: 30.00 back, then 20.00 is all that is left."""
    session = _session_factory()()
    setup = _Dispatch(session)
    _charge_on_the_header(setup, "50")
    service = SalesReturnService(session)
    service.create_return(
        _against_the_bill(setup, "1").model_copy(
            update={"additional_charges": Decimal("30")}
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    with pytest.raises(
        ValidationError, match="charged 50.00 of them, 30.00 already given back"
    ):
        service.create_return(
            _against_the_bill(setup, "1").model_copy(
                update={"additional_charges": Decimal("30")}
            ),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    session.rollback()
    row = service.create_return(
        _against_the_bill(setup, "1").model_copy(
            update={"additional_charges": Decimal("20")}
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert row.grand_total == Decimal("120.0000")


def test_a_return_saved_above_its_bill_does_not_complete() -> None:
    """One saved before the cap ran on every line is asked again."""
    session = _session_factory()()
    setup = _Dispatch(session)
    row = _returned(setup, _against_the_bill(setup, "4"), complete=False)
    line = session.scalars(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == row.id)
    ).one()
    # As a return written before this fix kept it: 125.00 a unit.
    line.unit_price = Decimal("125")
    line.gross_amount = Decimal("500")
    line.net_amount = Decimal("500")
    session.commit()

    with pytest.raises(ValidationError, match="credits 500.00 .* billed at 400.00"):
        SalesReturnService(session).complete_return(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_goods_no_bill_has_charged_come_back_at_the_notes_price_at_most() -> None:
    """Never billed: the note sent them at 100.00, and 125.00 is refused."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("0"))
    service = SalesReturnService(session)

    with pytest.raises(ValidationError, match="sent at 200.00, and no bill"):
        service.create_return(
            _priced(setup.payload(quantity=Decimal("2")), unit_price=Decimal("125")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    session.rollback()
    row = service.create_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert row.subtotal == Decimal("200.0000")


# ---- a note billed in parts (D-PRC-65) --------------------------------------
#
# The sixth pricing check (2026-10-06): one delivery note billed as two bills
# of 1,416.00. A return raised off the note was priced on the earliest bill
# alone, so a credit note on the second bill was never netted (472.00 over)
# and one on the first was netted twice (472.00 short). Here the note of four
# at 100.00 is billed as two bills of two.


def _billed_in_two(session: Session) -> tuple[_Dispatch, SalesInvoice]:
    """Bill the note of four as two bills of two; return the second too."""
    setup = _Dispatch(session, billed=Decimal("2"))
    second = SalesInvoiceService(session).approve_invoice(
        setup.bill(Decimal("2")).id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )
    return setup, second


def _bill_line(session: Session, invoice: SalesInvoice) -> SalesInvoiceLine:
    """Return the one line of a bill."""
    return session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    ).one()


def _credit_note_on(
    setup: _Dispatch, invoice: SalesInvoice, taxable: str, *, approve: bool = True
) -> CreditNote:
    """Credit one bill's line some value with no goods coming back."""
    service = CreditNoteService(setup.session)
    note = service.create_note(
        CreditNoteCreate(
            sales_invoice_id=invoice.id,
            credit_note_date=date(2026, 8, 5),
            reason=CreditNoteReasonEnum.RATE_DIFFERENCE,
            lines=[
                CreditNoteLineWrite(
                    sales_invoice_line_id=_bill_line(setup.session, invoice).id,
                    line_number=1,
                    quantity=Decimal("1"),
                    taxable_amount=Decimal(taxable),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    if approve:
        service.approve_note(note.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    setup.session.commit()
    return note


def _on_the_line_of(
    setup: _Dispatch, invoice: SalesInvoice, quantity: str
) -> SalesReturnCreate:
    """Describe a return of some units through one bill's own line."""
    payload = setup.payload(quantity=Decimal(quantity))
    payload.lines[0].source_document_type = SalesReturnSourceType.SALES_INVOICE
    payload.lines[0].source_document_id = invoice.id
    payload.lines[0].source_document_line_id = _bill_line(setup.session, invoice).id
    return payload


def test_a_credit_note_on_the_second_bill_is_netted_off_the_note_too() -> None:
    """80.00 credited on the later bill, then all four back off the note.

    Read on the earliest bill alone the return was 400.00: 480.00 credited
    against 400.00 billed.
    """
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    _credit_note_on(setup, second, "80")

    row = _returned(setup, setup.payload(quantity=Decimal("4")))

    assert row.subtotal == Decimal("320.0000")
    assert [credit.amount for credit in _credits(session)] == [Decimal("320.00")]


def test_a_credit_note_on_the_first_bill_is_netted_once() -> None:
    """80.00 credited on the earlier bill comes off its two units alone.

    Spread over all four as if the first bill had charged them, it took
    160.00 off: the customer returned everything and still owed 80.00.
    """
    session = _session_factory()()
    setup, _second = _billed_in_two(session)
    _credit_note_on(setup, setup.invoice, "80")

    row = _returned(setup, setup.payload(quantity=Decimal("4")))

    assert row.subtotal == Decimal("320.0000")


def test_units_off_the_note_fill_the_earliest_bill_first() -> None:
    """Three back off the note: the first bill's two, and one of the second's.

    So the first bill has nothing left to credit and the second has one unit
    worth 100.00 -- a credit note is capped by exactly that on each.
    """
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    _returned(setup, setup.payload(quantity=Decimal("3")))

    with pytest.raises(ValidationError, match="200.00 already returned"):
        _credit_note_on(setup, setup.invoice, "10")
    session.rollback()
    with pytest.raises(ValidationError, match="100.00 already returned"):
        _credit_note_on(setup, second, "150")
    session.rollback()
    _credit_note_on(setup, second, "100")

    last = _returned(setup, setup.payload(quantity=Decimal("1")))
    assert last.subtotal == Decimal("0.0000")


def test_a_note_billed_in_parts_is_asked_again_of_every_bill_at_completion() -> None:
    """A credit note on the later bill, approved after the return was priced."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    row = _returned(setup, setup.payload(quantity=Decimal("4")), complete=False)
    _credit_note_on(setup, second, "80")

    with pytest.raises(ValidationError, match="credited since this return was saved"):
        SalesReturnService(session).complete_return(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_return_off_the_note_that_waits_gives_way_to_a_named_unit() -> None:
    """A return off the note that has not completed gives way to a named unit.

    Two off the note, approved and no more: nothing has been credited, so
    its split is not settled. One named on the first bill's own line takes
    that bill's unit, and the waiting return is then worth one unit of each
    bill -- 400.00 in all for the four once the last comes back too.
    """
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    waiting = _returned(setup, setup.payload(quantity=Decimal("2")), complete=False)

    named = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    SalesReturnService(session).complete_return(
        waiting.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    last = _returned(setup, _on_the_line_of(setup, second, "1"))

    assert (named.subtotal, last.subtotal) == (
        Decimal("100.0000"),
        Decimal("100.0000"),
    )
    assert sum(credit.amount for credit in _credits(session)) == Decimal("400.00")
    assert _placed(session, waiting) == [
        (setup.invoice.id, Decimal("1.0000"), Decimal("100.0000")),
        (second.id, Decimal("1.0000"), Decimal("100.0000")),
    ]


# ---- a completed return stays on the bill it was set against (D-PRC-72) -----
#
# The seventh pricing check (2026-10-06): two bills of 1,416.00, a credit note
# of 472.00 on the second, one box back off the note and then one box named
# on the first bill's own line. The split of the return off the note was
# worked out afresh on every read, so the named box pushed it onto the second
# bill -- where its value did not fit -- and was itself priced at the first
# bill's full worth: 3,304.00 credited against 2,832.00, and 472.00 short
# with the note on the first bill. The split is written down at completion
# now. Here the note of four at 100.00 is billed as two bills of two.


def _placed(session: Session, row: SalesReturn) -> list[tuple[UUID, Decimal, Decimal]]:
    """Return the bill, units and value of each placement a return wrote."""
    found = session.scalars(
        select(SalesReturnBillPlacement).where(
            SalesReturnBillPlacement.sales_return_id == row.id,
            SalesReturnBillPlacement.is_deleted.is_(False),
        )
    ).all()
    dated = {
        bill.id: (bill.invoice_date, bill.invoice_number)
        for bill in session.scalars(select(SalesInvoice)).all()
    }
    return [
        (item.sales_invoice_id, item.quantity, item.taxable_amount)
        for item in sorted(found, key=lambda item: dated[item.sales_invoice_id])
    ]


def _credited_in_all(setup: _Dispatch, *bills: SalesInvoice) -> Decimal:
    """Return what returns and credit notes took off these bills together."""
    return sum((_off_the_bill(setup, bill) for bill in bills), Decimal("0"))


@pytest.mark.parametrize("noted", ["second", "first"])
def test_units_back_off_the_note_do_not_come_back_again_on_the_bills_line(
    noted: str,
) -> None:
    """Two off the note took the first bill's two; they are not its again.

    With 80.00 credited on the second bill the two named on the first were
    priced at its full 200.00 -- 480.00 against bills of 400.00 -- and with
    it on the first, 320.00. Refused by name now, and the same goods off the
    note are credited on the bill that still carries them: 400.00 either way.
    """
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    _credit_note_on(setup, second if noted == "second" else setup.invoice, "80")
    first = _returned(setup, setup.payload(quantity=Decimal("2")))
    on_the_first = Decimal("200.0000") if noted == "second" else Decimal("120.0000")
    assert _placed(session, first) == [
        (setup.invoice.id, Decimal("2.0000"), on_the_first)
    ]

    with pytest.raises(ValidationError) as refusal:
        _returned(setup, _on_the_line_of(setup, setup.invoice, "2"))
    session.rollback()

    message = str(refusal.value)
    assert f"{setup.invoice.invoice_number} line 1 billed 2" in message
    assert "2 of that has already come back" in message
    assert f"Raise the return off {setup.note.delivery_note_number}" in message
    rest = _returned(setup, setup.payload(quantity=Decimal("2")))
    assert rest.subtotal == Decimal("400") - Decimal("80") - on_the_first
    assert _placed(session, first) == [
        (setup.invoice.id, Decimal("2.0000"), on_the_first)
    ]
    assert _off_the_bill(setup, setup.invoice) == Decimal("200.00")
    assert _off_the_bill(setup, second) == Decimal("200.00")


def test_the_other_bills_own_line_takes_the_units_still_out() -> None:
    """Two off the note, then the second bill's two by name: 400.00 in all."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    _credit_note_on(setup, second, "80")
    _returned(setup, setup.payload(quantity=Decimal("2")))

    named = _returned(setup, _on_the_line_of(setup, second, "2"))

    assert named.subtotal == Decimal("120.0000")
    assert _credited_in_all(setup, setup.invoice, second) == Decimal("400.00")


def test_a_bills_own_line_first_and_the_note_second() -> None:
    """Named on the first bill, then the rest off the note: the second's."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    _credit_note_on(setup, setup.invoice, "80")

    named = _returned(setup, _on_the_line_of(setup, setup.invoice, "2"))
    rest = _returned(setup, setup.payload(quantity=Decimal("2")))

    assert (named.subtotal, rest.subtotal) == (
        Decimal("120.0000"),
        Decimal("200.0000"),
    )
    assert _placed(session, rest) == [
        (second.id, Decimal("2.0000"), Decimal("200.0000"))
    ]
    assert _credited_in_all(setup, setup.invoice, second) == Decimal("400.00")


def test_one_unit_off_the_note_leaves_the_bills_other_unit_to_be_named() -> None:
    """One of the first bill's two came back off the note; one is still out."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    first = _returned(setup, setup.payload(quantity=Decimal("1")))

    named = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    with pytest.raises(ValidationError, match="0 is left to return against this bill"):
        _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.rollback()
    rest = _returned(setup, setup.payload(quantity=Decimal("2")))

    assert named.subtotal == Decimal("100.0000")
    assert _placed(session, first) == [
        (setup.invoice.id, Decimal("1.0000"), Decimal("100.0000"))
    ]
    assert _placed(session, rest) == [
        (second.id, Decimal("2.0000"), Decimal("200.0000"))
    ]
    came_back = returned_units_against(
        session, firm_id=setup.firm.id, invoice_ids=[setup.invoice.id, second.id]
    )
    assert {
        line_id: sum(units.quantity for units in found)
        for line_id, found in came_back.items()
    } == {
        _bill_line(session, setup.invoice).id: Decimal("2.0000"),
        _bill_line(session, second).id: Decimal("2.0000"),
    }


@pytest.mark.parametrize("noted", [0, 1, 2])
def test_three_bills_are_each_credited_what_they_charged(noted: int) -> None:
    """Bills of one, one and two, with 40.00 credited on each in turn.

    One off the note, one named on the third bill, then the last two off the
    note: every bill is credited exactly what it charged, whichever carries
    the credit note.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("1"))
    invoices = SalesInvoiceService(session)
    bills = [setup.invoice] + [
        invoices.approve_invoice(
            setup.bill(Decimal(quantity)).id,
            firm_scope=setup.firm.id,
            actor_id=setup.actor_id,
        )
        for quantity in ("1", "2")
    ]
    _credit_note_on(setup, bills[noted], "40")

    first = _returned(setup, setup.payload(quantity=Decimal("1")))
    named = _returned(setup, _on_the_line_of(setup, bills[2], "1"))
    rest = _returned(setup, setup.payload(quantity=Decimal("2")))

    assert first.subtotal + named.subtotal + rest.subtotal == Decimal("360.0000")
    assert [_off_the_bill(setup, bill) for bill in bills] == [
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("200.00"),
    ]
    assert [bill for bill, _units, _value in _placed(session, rest)] == [
        bills[1].id,
        bills[2].id,
    ]


def test_a_cancelled_return_gives_its_units_back_to_the_bill() -> None:
    """Two off the note, cancelled: the first bill's two can be named again."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    first = _returned(setup, setup.payload(quantity=Decimal("2")))
    SalesReturnService(session).cancel_return(
        first.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="Mistake"
    )
    assert _placed(session, first) == []
    assert _off_the_bill(setup, setup.invoice) == Decimal("0")

    named = _returned(setup, _on_the_line_of(setup, setup.invoice, "2"))
    rest = _returned(setup, setup.payload(quantity=Decimal("2")))

    assert (named.subtotal, rest.subtotal) == (
        Decimal("200.0000"),
        Decimal("200.0000"),
    )
    assert _off_the_bill(setup, setup.invoice) == Decimal("200.00")
    assert _off_the_bill(setup, second) == Decimal("200.00")


def test_a_bill_dated_earlier_does_not_take_a_completed_returns_units() -> None:
    """A return set against a bill stays there when an earlier bill appears.

    Two of four billed. Two come back before billing and credit nothing; one
    more comes back and is the bill's. The first return is cancelled, and
    the two units it freed are billed on a bill **dated before** the first.
    Worked out afresh, the completed return moved onto that earlier bill.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    unbilled = _returned(setup, setup.payload(quantity=Decimal("2")))
    kept = _returned(setup, setup.payload(quantity=Decimal("1")))
    SalesReturnService(session).cancel_return(
        unbilled.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="Kept"
    )
    earlier = setup.bill(Decimal("2"))
    earlier.invoice_date = date(2026, 8, 3)
    session.commit()
    earlier = SalesInvoiceService(session).approve_invoice(
        earlier.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    _credit_note_on(setup, earlier, "40")

    rest = _returned(setup, setup.payload(quantity=Decimal("3")))

    assert _placed(session, kept) == [
        (setup.invoice.id, Decimal("1.0000"), Decimal("100.0000"))
    ]
    assert _placed(session, rest) == [
        (earlier.id, Decimal("2.0000"), Decimal("160.0000")),
        (setup.invoice.id, Decimal("1.0000"), Decimal("100.0000")),
    ]
    assert _off_the_bill(setup, setup.invoice) == Decimal("200.00")
    assert _off_the_bill(setup, earlier) == Decimal("200.00")


def test_a_completed_return_with_nothing_written_is_still_worked_out() -> None:
    """One that completed before the split was written down reads as it did."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    row = _returned(setup, setup.payload(quantity=Decimal("3")))
    session.query(SalesReturnBillPlacement).delete()
    session.commit()

    assert _placed(session, row) == []
    assert _off_the_bill(setup, setup.invoice) == Decimal("200.00")
    assert _off_the_bill(setup, second) == Decimal("100.00")


def _backfill_0346(session: Session) -> None:
    """Run the backfill of ``20261006_0346`` over the session's store."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261006_0346_sales_return_bill_placements.py"
    )
    spec = importlib.util.spec_from_file_location("_placements_0346", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bind = session.connection()
    module._backfill(bind, inspect(bind))
    session.commit()


@pytest.mark.parametrize("noted", ["second", "first"])
def test_the_migration_places_a_completed_return_where_it_read(noted: str) -> None:
    """Returns completed before the split was kept are given the one they read.

    Two named on the first bill, three off the note in two returns, and a
    credit note: the backfill writes exactly what completion writes now, so
    every bill reads after it what it read before. Run again, it adds
    nothing.
    """
    session = _session_factory()()
    setup, second = _billed_in_two(session)
    _credit_note_on(setup, second if noted == "second" else setup.invoice, "40")
    _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    rows = [
        _returned(setup, setup.payload(quantity=Decimal("2"))),
        _returned(setup, setup.payload(quantity=Decimal("1"))),
    ]
    written = [_placed(session, row) for row in rows]
    assert [len(found) for found in written] == [2, 1]
    session.query(SalesReturnBillPlacement).delete()
    session.commit()

    _backfill_0346(session)

    assert [_placed(session, row) for row in rows] == written
    assert _credited_in_all(setup, setup.invoice, second) == Decimal("400.00")
    _backfill_0346(session)
    assert session.scalar(select(func.count(SalesReturnBillPlacement.id))) == 3


def test_each_bills_own_tax_is_reversed_on_its_share() -> None:
    """The first bill charged 18% and the second none: 36.00 back, not 72.00.

    All four off the note: the first bill's two reverse its CGST and SGST,
    the second bill's two reverse nothing.
    """
    session = _session_factory()()
    setup, _second = _billed_in_two(session)
    line = _bill_line(session, setup.invoice)
    line.tax_amount = Decimal("36")
    for sequence, code in enumerate(("CGST", "SGST"), start=1):
        session.add(
            SalesInvoiceLineTax(
                sales_invoice_line_id=line.id,
                firm_id=setup.firm.id,
                sequence=sequence,
                component_code=code,
                component_label=f"{code} 9%",
                percentage=Decimal("9"),
                base_amount=Decimal("200"),
                amount=Decimal("18"),
            )
        )
    session.commit()

    row = _returned(setup, setup.payload(quantity=Decimal("4")))

    assert (row.subtotal, row.tax_total) == (Decimal("400.0000"), Decimal("36.0000"))
    assert _components(session, row) == [
        ("CGST", Decimal("18.0000")),
        ("SGST", Decimal("18.0000")),
    ]


# ---- a return off the note counts against its bill (D-PRC-66) ---------------
#
# The sixth pricing check (2026-10-06): 7 of 24 pieces returned off the
# delivery note after the bill existed. The customer's account and the journal
# were right; the bill went on reading 2,832.00 outstanding, the sales target
# counted the returned goods and the salesman was paid on them. Only a return
# raised from the bill's own lines was read as having come off it.


def _off_the_bill(setup: _Dispatch, invoice: SalesInvoice) -> Decimal:
    """Return what returns and credit notes have taken off one bill."""
    return credited_against(
        setup.session, firm_id=setup.firm.id, invoice_ids=[invoice.id]
    ).get(invoice.id, Decimal("0"))


def test_goods_back_off_the_note_come_off_what_the_bill_owes() -> None:
    """Two of four back off the note: the bill owes 200.00, not 400.00.

    And the customer's account is credited once -- the bill's figure is read
    off the return, it is not a second credit.
    """
    session = _session_factory()()
    setup = _Dispatch(session)

    setup.completed(quantity=Decimal("2"))

    assert _off_the_bill(setup, setup.invoice) == Decimal("200.00")
    assert settled_against(
        session, firm_id=setup.firm.id, invoice_ids=[setup.invoice.id]
    ) == {setup.invoice.id: Decimal("200.00")}
    # Asked of the whole firm, as the ageing asks, it is the same answer.
    assert credited_against(session, firm_id=setup.firm.id, invoice_ids=None) == {
        setup.invoice.id: Decimal("200.00")
    }
    [sale] = invoiced_net(
        session,
        firm_id=setup.firm.id,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
    )
    assert sale.amount == Decimal("200.0000")
    assert [credit.amount for credit in _credits(session)] == [Decimal("200.00")]
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("200.00")


def test_the_units_back_off_the_note_are_counted_on_the_bill_line() -> None:
    """What a per-unit commission stops paying on: the two that came back."""
    session = _session_factory()()
    setup = _Dispatch(session)
    line = _bill_line(session, setup.invoice)

    setup.completed(quantity=Decimal("2"))

    came_back = returned_units_against(
        session, firm_id=setup.firm.id, invoice_ids=[setup.invoice.id]
    )
    assert [units.quantity for units in came_back[line.id]] == [Decimal("2.0000")]


def test_goods_back_off_a_note_billed_in_parts_come_off_each_bill() -> None:
    """Three of four back: the first bill's two and one of the second's."""
    session = _session_factory()()
    setup, second = _billed_in_two(session)

    _returned(setup, setup.payload(quantity=Decimal("3")))

    assert _off_the_bill(setup, setup.invoice) == Decimal("200.00")
    assert _off_the_bill(setup, second) == Decimal("100.00")
    came_back = returned_units_against(
        session, firm_id=setup.firm.id, invoice_ids=[setup.invoice.id, second.id]
    )
    assert {
        line_id: sum(units.quantity for units in found)
        for line_id, found in came_back.items()
    } == {
        _bill_line(session, setup.invoice).id: Decimal("2.0000"),
        _bill_line(session, second).id: Decimal("1.0000"),
    }


def test_only_the_billed_part_of_a_return_off_the_note_comes_off_the_bill() -> None:
    """Four delivered, three billed, two back: one was never charged."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("3"))

    setup.completed(quantity=Decimal("2"))

    assert _off_the_bill(setup, setup.invoice) == Decimal("100.00")
    [units] = returned_units_against(
        session, firm_id=setup.firm.id, invoice_ids=[setup.invoice.id]
    )[_bill_line(session, setup.invoice).id]
    assert units.quantity == Decimal("1.0000")


def test_goods_back_before_any_bill_count_against_no_bill() -> None:
    """Returned off a note nobody had billed, then the rest billed.

    The return credited nothing, so the bill raised afterwards for the goods
    the customer kept owes all of itself.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("0"))
    setup.completed(quantity=Decimal("2"))
    bill = SalesInvoiceService(session).approve_invoice(
        setup.bill(Decimal("2")).id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert _off_the_bill(setup, bill) == Decimal("0")
    assert (
        returned_units_against(session, firm_id=setup.firm.id, invoice_ids=[bill.id])
        == {}
    )
    assert _credits(session) == []


def test_an_unpriced_note_is_measured_against_its_order_line() -> None:
    """A note written before its lines carried a price: the order's is used.

    Never billed, and the note line states no value. The order sold these at
    100.00, so that is the most they can come back at (D-PRC-64).
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("0"))
    setup.note_line.gross_amount = Decimal("0")
    session.commit()
    service = SalesReturnService(session)

    with pytest.raises(ValidationError, match="sent at 200.00, and no bill"):
        service.create_return(
            _priced(setup.payload(quantity=Decimal("2")), unit_price=Decimal("125")),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    session.rollback()
    row = service.create_return(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert row.subtotal == Decimal("200.0000")


def test_a_draft_return_off_the_note_takes_nothing_off_the_bill() -> None:
    """Nothing has been credited until the return completes."""
    session = _session_factory()()
    setup = _Dispatch(session)

    _returned(setup, setup.payload(quantity=Decimal("2")), complete=False)

    assert _off_the_bill(setup, setup.invoice) == Decimal("0")
