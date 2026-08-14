"""Purchase return backend lifecycle and source-matching tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models.batch_serial import BatchRecord
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import customer as _customer_models  # noqa: F401
from app.document_framework.models import DocumentTypeDefinition
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import InventoryRecord, InventoryTransaction, StockLedgerEntry
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
    PurchaseReturnStatus,
)
from app.purchase_return.services import PurchaseReturnService
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401
from app.vendors.models import Vendor


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
        code="INV-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    # Completing a return posts to the general ledger, so the firm needs its
    # chart of accounts, an open period and its control accounts.
    seed_finance_setup(
        session,
        firm_id=row.id,
        year_starts_on=date(2026, 4, 1),
        actor_id=uuid4(),
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


def _vendor(session: Session, *, firm_id: UUID) -> Vendor:
    row = Vendor(
        firm_id=firm_id,
        code="VEN-001",
        name="Vendor VEN-001",
        display_name="Vendor VEN-001",
        status="ACTIVE",
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


def _purchase_order(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    branch_id: UUID,
    warehouse_id: UUID,
) -> PurchaseOrder:
    row = PurchaseOrder(
        firm_id=firm_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        vendor_id=vendor_id,
        po_number="PO-2026-000001",
        purchase_date=date(2026, 8, 2),
        status="APPROVED",
    )
    session.add(row)
    session.flush()
    line = PurchaseOrderLine(
        purchase_order_id=row.id,
        firm_id=firm_id,
        line_number=1,
        product_id=_product(session, firm_id=firm_id).id,
        ordered_quantity=Decimal("10"),
        free_quantity=Decimal("0"),
        base_quantity=Decimal("10"),
        unit_price=Decimal("100"),
        discount_percent=Decimal("0"),
        discount_amount=Decimal("0"),
        gross_amount=Decimal("1000"),
        tax_amount=Decimal("0"),
        net_amount=Decimal("1000"),
        status="ORDERED",
    )
    session.add(line)
    session.commit()
    return row


def test_purchase_return_direct_po_return_creates_lifecycle_setup() -> None:
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    purchase_order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == purchase_order.id
        )
    )
    assert po_line is not None

    service = PurchaseReturnService(session)
    row = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-1001",
            supplier_return_date=date(2026, 8, 2),
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            allow_direct_purchase_order=True,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.PURCHASE_ORDER,
                    "source_document_id": purchase_order.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.PURCHASE_ORDER,
                    source_document_id=purchase_order.id,
                    source_document_line_id=po_line.id,
                    line_number=1,
                    current_return_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("0"),
                    charges_amount=Decimal("0"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    response = service.return_response(row)
    assert response.status == PurchaseReturnStatus.DRAFT
    assert response.return_number.startswith("PR")
    assert response.grand_total == Decimal("400.0000")
    assert response.duplicate_warning is None
    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm.id,
                DocumentTypeDefinition.code == "PURCHASE_RETURN",
            )
        )
        is not None
    )
    assert (
        session.scalar(select(PurchaseReturn).where(PurchaseReturn.id == row.id))
        is not None
    )
    assert (
        session.scalar(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == row.id
            )
        )
        is not None
    )
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None


def _approved_return(
    session: Session, *, firm_id: UUID, batch_number: str | None = None
) -> tuple[PurchaseReturnService, PurchaseReturn, UUID]:
    """Create and approve a return, stopping before it is completed.

    Completion is what posts the stock, so anything a test needs in place
    first -- a registered batch, a product flag -- goes between the two.

    Returns:
        The service, the approved return, and the product being returned.

    """
    branch = _branch(session, firm_id=firm_id)
    warehouse = _warehouse(session, firm_id=firm_id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm_id)
    purchase_order = _purchase_order(
        session,
        firm_id=firm_id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == purchase_order.id
        )
    )
    assert po_line is not None

    service = PurchaseReturnService(session)
    row = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-2001",
            supplier_return_date=date(2026, 8, 2),
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            allow_direct_purchase_order=True,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.PURCHASE_ORDER,
                    "source_document_id": purchase_order.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.PURCHASE_ORDER,
                    source_document_id=purchase_order.id,
                    source_document_line_id=po_line.id,
                    line_number=1,
                    current_return_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("0"),
                    charges_amount=Decimal("0"),
                    warehouse_id=warehouse.id,
                    batch_number=batch_number,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    service.approve_return(row.id, firm_scope=firm_id, actor_id=uuid4())
    return service, row, po_line.product_id


def _approved_return_with_stock_posted(
    session: Session, *, firm_id: UUID
) -> tuple[PurchaseReturnService, PurchaseReturn]:
    """Create, approve and complete a return so its stock movement exists."""
    service, row, _ = _approved_return(session, firm_id=firm_id)
    service.complete_return(row.id, firm_scope=firm_id, actor_id=uuid4())
    return service, row


def _register_batch(
    session: Session, *, firm_id: UUID, product_id: UUID, batch_number: str
) -> BatchRecord:
    """Register a batch of a product, as a goods receipt would have."""
    batch = BatchRecord(
        firm_id=firm_id,
        product_id=product_id,
        batch_number=batch_number,
        expiry_date=date(2027, 3, 31),
        status="AVAILABLE",
        created_by=uuid4(),
        updated_by=uuid4(),
    )
    session.add(batch)
    session.commit()
    return batch


def test_completing_a_purchase_return_links_its_inventory_movement() -> None:
    """The completed return records which movement it produced.

    Without this link the movements are unattributable, so a later cancellation
    has no way to find the stock it must put back.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, row = _approved_return_with_stock_posted(session, firm_id=firm.id)

    line = session.scalar(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == row.id
        )
    )
    assert line is not None
    assert line.inventory_transaction_id is not None
    movement = session.get(InventoryTransaction, line.inventory_transaction_id)
    assert movement is not None
    assert movement.transaction_type == "RETURN"
    assert movement.current_quantity_delta == Decimal("-4.0000")


def test_cancelling_a_completed_purchase_return_reverses_the_stock() -> None:
    """Cancelling after completion nets the stock movement back to zero.

    Previously cancel only flipped the status, so a cancelled return kept the
    goods off the shelf permanently.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, row = _approved_return_with_stock_posted(session, firm_id=firm.id)
    original_id = session.scalar(
        select(PurchaseReturnLine.inventory_transaction_id).where(
            PurchaseReturnLine.purchase_return_id == row.id
        )
    )
    assert original_id is not None

    service.cancel_return(
        row.id, firm_scope=firm.id, actor_id=uuid4(), reason="vendor refused"
    )

    cancelled = service.get_return(row.id, firm_scope=firm.id)
    assert cancelled.status == PurchaseReturnStatus.CANCELLED.value

    reversal = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reversal_of_transaction_id == original_id
        )
    )
    assert reversal is not None
    assert reversal.transaction_type == "RETURN_REVERSAL"
    assert reversal.current_quantity_delta == Decimal("4.0000")

    net = sum(
        movement.current_quantity_delta
        for movement in session.scalars(
            select(InventoryTransaction).where(InventoryTransaction.firm_id == firm.id)
        ).all()
    )
    assert net == Decimal("0.0000")

    line = session.scalar(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == row.id
        )
    )
    assert line is not None
    assert line.inventory_transaction_id is None


def test_a_return_takes_its_stock_out_of_the_batch_it_names() -> None:
    """The batch number on the line has to reach the stock row and the ledger.

    Goods could arrive in a batch and leave to a customer from one, while the
    return to the supplier came off the product's untracked stock -- so the
    batch went on holding quantity that had physically left the building.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, row, product_id = _approved_return(
        session, firm_id=firm.id, batch_number="B-2026-07"
    )
    batch = _register_batch(
        session, firm_id=firm.id, product_id=product_id, batch_number="B-2026-07"
    )

    service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())

    line = session.scalar(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == row.id
        )
    )
    assert line is not None
    assert line.batch_id == batch.id, "the typed number must resolve to the register"
    movement = session.get(InventoryTransaction, line.inventory_transaction_id)
    assert movement is not None
    assert movement.batch_id == batch.id, "the ledger must know which batch went back"
    stock = session.get(InventoryRecord, movement.inventory_id)
    assert stock is not None
    assert (
        stock.batch_id == batch.id
    ), "the stock has to come out of that batch's row, not the product's"
    assert stock.current_quantity == Decimal("-4.0000")


def test_a_return_cannot_name_a_batch_that_was_never_received() -> None:
    """A number nobody received names stock that was never taken in.

    Receiving creates an unknown batch because the goods are on the dock.
    Issuing must not: inventing the batch here would write a delivery that did
    not happen, and leave the new batch holding a negative quantity.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(
        session, firm_id=firm.id, batch_number="NEVER-ARRIVED"
    )

    with pytest.raises(ValidationError, match="was never received"):
        service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())


def test_a_batch_only_product_cannot_be_returned_without_a_batch() -> None:
    """A return to the supplier is stock leaving, so the flag applies to it.

    Dispatch already refuses to ship such a product untracked. A return that
    did not would be the same hole in the same guarantee, one document along.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, row, product_id = _approved_return(session, firm_id=firm.id)
    product = session.get(Product, product_id)
    assert product is not None
    product.require_batch_on_issue = True
    session.commit()

    with pytest.raises(ValidationError, match="may only be issued from a batch"):
        service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())


def test_completing_a_purchase_return_posts_it_to_the_ledger() -> None:
    """Goods going back reach the ledger, or they do not go back.

    Purchase returns moved stock and posted nothing, so the inventory control
    account overstated by the value returned and nothing on screen said so.
    The supplier owes the whole credit note, so payables is debited with tax
    included; the input tax claimed on the way in is reversed with the goods;
    and inventory is credited with what the stock actually cost.
    """
    session = _session_factory()()
    firm = _firm(session)
    _, row = _approved_return_with_stock_posted(session, firm_id=firm.id)

    postings = {
        code: (debit, credit)
        for code, debit, credit in session.execute(
            select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
            .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(JournalEntry.source_id == row.id)
        ).all()
    }

    assert postings, "the return wrote no journal at all"
    payable_debit = postings["2100"][0]
    assert payable_debit == row.grand_total, "the supplier owes the whole credit note"
    if row.tax_total > Decimal("0.00"):
        assert postings["1300"][1] == row.tax_total, "input tax reversed with the goods"

    # Inventory is credited with what the stock ledger says the goods cost --
    # not with what the return is priced at. In this fixture the stock was
    # never costed, so that figure is zero and the whole goods value lands in
    # the variance; the contract is that the two always come from those two
    # different places.
    recorded_cost = session.scalar(
        select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
            StockLedgerEntry.transaction_type == "RETURN",
            StockLedgerEntry.is_deleted.is_(False),
        )
    )
    assert postings["1200"][1] == Decimal(recorded_cost).quantize(Decimal("0.01"))

    # Whatever the split, the entry balances -- the engine refuses it otherwise,
    # and the variance leg is what absorbs a return price that differs from the
    # average the stock was carried at.
    debits = sum(debit for debit, _ in postings.values())
    credits = sum(credit for _, credit in postings.values())
    assert debits == credits


def test_a_return_priced_above_cost_books_the_difference_as_a_variance() -> None:
    """Stock leaves at what it cost, not at what the supplier will credit.

    Goods bought at several prices sit at one moving average, and a return is
    priced at whatever the supplier agrees to. Crediting inventory at the return
    price would leave stock valued at something no movement ever paid, so the
    gap goes to purchase price variance -- the same account an invoice uses when
    it disagrees with the receipt it clears.
    """
    session = _session_factory()()
    firm = _firm(session)
    _, row = _approved_return_with_stock_posted(session, firm_id=firm.id)

    stock_credit = session.scalar(
        select(func.coalesce(func.sum(GLPosting.credit_amount), 0))
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
        .where(JournalEntry.source_id == row.id, LedgerAccount.code == "1200")
    )
    goods_value = row.grand_total - row.tax_total
    variance = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
        .where(JournalEntry.source_id == row.id, LedgerAccount.code == "5400")
    )
    # Inventory plus the variance is what the supplier is crediting for goods.
    assert Decimal(stock_credit) - Decimal(variance) == goods_value
