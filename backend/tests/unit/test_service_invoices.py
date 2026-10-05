"""A service is billed with no stock behind it (backlog §87 #3, SG-3).

Freight, repair or installation rides the same chain as goods -- order, note,
bill -- but nothing is reserved, nothing leaves a warehouse and no cost of
goods sold is posted. The cases here drive a counter bill, which raises the
order and the note through the real services, so every step is exercised.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.delivery_note.models import DeliveryNote
from app.finance.models import JournalEntry
from app.inventory.models import InventoryTransaction
from app.products.models import Product
from app.products.services.stockless import stockless_products
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory


def _counter() -> tuple[Session, _Firm, Product]:
    """Return a firm that types only the bill, and a service it sells."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = Product(
        firm_id=setup.firm.id,
        code="SVC-INSTALL",
        name="Installation",
        product_type="SERVICE",
        status="ACTIVE",
        hsn_sac="998739",
    )
    session.add(service)
    session.commit()
    return session, setup, service


def _bill(setup: _Firm, *products: UUID) -> SalesInvoiceCreate:
    """Describe a counter bill of two units of each product at 100."""
    return setup.bare_bill().model_copy(
        update={
            "lines": [
                SalesInvoiceLineWrite(
                    product_id=product_id,
                    line_number=number,
                    current_invoice_quantity=Decimal("2"),
                    unit_price=Decimal("100"),
                )
                for number, product_id in enumerate(products, start=1)
            ]
        }
    )


def _approved(session: Session, setup: _Firm, data: SalesInvoiceCreate) -> SalesInvoice:
    """Save and approve a counter bill."""
    service = SalesInvoiceService(session)
    actor = uuid4()
    draft = service.create_invoice(data, firm_id=setup.firm.id, actor_id=actor)
    return service.approve_invoice(draft.id, firm_scope=setup.firm.id, actor_id=actor)


def _movements(session: Session, product_id: UUID) -> int:
    """Count the stock movements of one product."""
    return len(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.product_id == product_id
            )
        ).all()
    )


def test_only_a_service_is_stockless() -> None:
    """The helper names the services among a document's products."""
    session, setup, service = _counter()

    assert stockless_products(session, [service.id, setup.product.id]) == {service.id}
    assert stockless_products(session, []) == set()


def test_a_service_bill_moves_no_stock_and_posts_no_cost() -> None:
    """Revenue and tax are posted; nothing is reserved, shipped or costed."""
    session, setup, service = _counter()

    invoice = _approved(session, setup, _bill(setup, service.id))

    assert invoice.status == "APPROVED"
    assert _movements(session, service.id) == 0
    note = session.scalar(select(DeliveryNote))
    assert note is not None and note.status == "DISPATCHED"
    assert (
        session.scalar(
            select(JournalEntry).where(JournalEntry.source_module == "delivery_note")
        )
        is None
    ), "no cost of goods sold for a service"
    assert (
        session.scalar(
            select(JournalEntry).where(JournalEntry.source_module == "sales_invoice")
        )
        is not None
    ), "revenue is still posted"
    [line] = session.scalars(select(SalesOrderLine)).all()
    assert line.reserved_quantity == Decimal("0"), "the nominal hold is let go"


def test_a_service_needs_no_stock_on_hand() -> None:
    """More units than any warehouse could hold are billed without a refusal."""
    session, setup, service = _counter()
    data = _bill(setup, service.id)
    data.lines[0].current_invoice_quantity = Decimal("5000")

    assert _approved(session, setup, data).status == "APPROVED"


def test_a_mixed_bill_ships_its_goods_and_bills_its_service() -> None:
    """The goods line moves and is costed; the service line beside it is not."""
    session, setup, service = _counter()
    before = _movements(session, setup.product.id)

    invoice = _approved(session, setup, _bill(setup, setup.product.id, service.id))

    assert invoice.status == "APPROVED"
    assert _movements(session, setup.product.id) > before
    assert _movements(session, service.id) == 0
    issue = session.scalar(
        select(JournalEntry).where(JournalEntry.source_module == "delivery_note")
    )
    assert issue is not None, "the goods are still costed"
    billed = session.scalars(
        select(SalesInvoiceLine.hsn_sac).where(
            SalesInvoiceLine.sales_invoice_id == invoice.id,
            SalesInvoiceLine.product_id == service.id,
        )
    ).all()
    assert billed == ["998739"], "the SAC is what GSTR-1 folds the line under"


def test_an_ordered_service_holds_no_stock_and_is_never_a_back_order() -> None:
    """A typed order marks the line ready to deliver without moving anything."""
    session = _session_factory()()
    setup = _Firm(session)
    service = Product(
        firm_id=setup.firm.id,
        code="SVC-REPAIR",
        name="Repair",
        product_type="SERVICE",
        status="ACTIVE",
    )
    session.add(service)
    session.commit()
    orders = SalesOrderService(session)
    actor = uuid4()
    order = orders.stage_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=service.id,
                    quantity=Decimal("5000"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    orders.stage_approval(order.id, firm_scope=setup.firm.id, actor_id=actor)
    session.commit()

    [line] = session.scalars(select(SalesOrderLine)).all()
    assert line.reserved_quantity == line.reservable_quantity == Decimal("5000")
    assert _movements(session, service.id) == 0
    assert orders.back_orders(firm_scope=setup.firm.id) == []

    orders.cancel_order(order.id, firm_scope=setup.firm.id, actor_id=actor)
    session.refresh(line)
    assert line.reserved_quantity == Decimal("0")
    assert _movements(session, service.id) == 0
