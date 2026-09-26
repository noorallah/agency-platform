"""Purchase return backend lifecycle and source-matching tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
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
from app.finance.models import (
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    LedgerAccount,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    ProductValuation,
    StockLedgerEntry,
)
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoiceLine
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
)
from app.purchase_invoice.services import PurchaseInvoiceService
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

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


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


def _received(
    session: Session, po_line: PurchaseOrderLine
) -> tuple[GoodsReceipt, GoodsReceiptLine]:
    """Record the whole order line as received, on a completed receipt.

    Built as rows rather than through the receipt service so no stock or
    journal moves: these cases are about the return, and what they assert of
    the stock and the ledger is the return's own movement. A return is
    raised against a receipt or a bill, never the order (D-BUY-14).
    """
    order = session.get(PurchaseOrder, po_line.purchase_order_id)
    assert order is not None
    receipt = GoodsReceipt(
        firm_id=order.firm_id,
        purchase_order_id=order.id,
        purchase_order_number=order.po_number,
        vendor_id=order.vendor_id,
        branch_id=order.branch_id,
        warehouse_id=order.warehouse_id,
        grn_number="GRN-2026-000001",
        receipt_date=date(2026, 8, 2),
        status="COMPLETED",
    )
    session.add(receipt)
    session.flush()
    line = GoodsReceiptLine(
        goods_receipt_id=receipt.id,
        firm_id=order.firm_id,
        line_number=1,
        purchase_order_line_id=po_line.id,
        purchase_order_line_number=po_line.line_number,
        product_id=po_line.product_id,
        ordered_quantity=po_line.ordered_quantity,
        current_receipt_quantity=po_line.ordered_quantity,
        accepted_quantity=po_line.ordered_quantity,
        unit_price=po_line.unit_price,
        warehouse_id=order.warehouse_id,
    )
    session.add(line)
    session.commit()
    return receipt, line


def test_purchase_return_creates_lifecycle_setup() -> None:
    """Returning against a goods receipt builds the document type too.

    This used to return against the purchase order directly, a path that no
    longer exists (D-BUY-14).
    """
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
    receipt, receipt_line = _received(session, po_line)

    service = PurchaseReturnService(session)
    row = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-1001",
            supplier_return_date=date(2026, 8, 2),
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=receipt_line.id,
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
    receipt, receipt_line = _received(session, po_line)

    service = PurchaseReturnService(session)
    row = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-2001",
            supplier_return_date=date(2026, 8, 2),
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=receipt_line.id,
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


def test_a_preview_prices_the_return_and_saves_nothing() -> None:
    """The return screen's figures are the save's, and nothing lands."""
    session = _session_factory()()
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
    receipt, receipt_line = _received(session, po_line)
    payload = PurchaseReturnCreate(
        return_date=date(2026, 8, 2),
        warehouse_id=warehouse.id,
        source_documents=[
            {
                "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                "source_document_id": receipt.id,
            }
        ],
        lines=[
            PurchaseReturnLineWrite(
                source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                source_document_id=receipt.id,
                source_document_line_id=receipt_line.id,
                line_number=1,
                current_return_quantity=Decimal("4"),
                warehouse_id=warehouse.id,
            )
        ],
    )
    service = PurchaseReturnService(session)
    audits = session.scalar(select(func.count()).select_from(AuditLog))

    preview = service.preview_return(payload, firm_id=firm.id, actor_id=uuid4())

    # Four at the receipt's 100, as a blank price takes.
    assert preview.purchase_return.subtotal == Decimal("400.0000")
    assert preview.interstate is False
    assert preview.lines[0].product_id == po_line.product_id
    assert session.scalar(select(func.count()).select_from(PurchaseReturn)) == 0
    assert session.scalar(select(func.count()).select_from(AuditLog)) == audits
    saved = service.create_return(payload, firm_id=firm.id, actor_id=uuid4())
    assert saved.return_number == preview.purchase_return.return_number


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


def test_a_return_cannot_lift_its_own_cap() -> None:
    """D-SELL-29: the request body used to carry a switch for the cap.

    ``allow_over_return`` true let a return send back more than was received,
    and ``over_return_percent`` beside it was never read. The write schema no
    longer takes either.
    """
    body = {
        "return_date": "2026-08-02",
        "warehouse_id": str(uuid4()),
        "allow_over_return": True,
        "lines": [
            {
                "source_document_type": "GOODS_RECEIPT",
                "source_document_id": str(uuid4()),
                "source_document_line_id": str(uuid4()),
                "line_number": 1,
                "current_return_quantity": "50",
            }
        ],
    }

    with pytest.raises(PydanticValidationError, match="allow_over_return"):
        PurchaseReturnCreate.model_validate(body)
    body.pop("allow_over_return")
    PurchaseReturnCreate.model_validate(body)


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


def _return_against(
    session: Session,
    service: PurchaseReturnService,
    row: PurchaseReturn,
    *,
    firm_id: UUID,
    supplier_return_number: str,
    is_damaged: bool = False,
    is_expired: bool = False,
    reason_code: str | None = None,
) -> PurchaseReturn:
    """Raise and approve a second return against the same source line.

    The reports read every live line in the firm, so the interesting case is
    two returns that differ only in the condition recorded against them.
    """
    line = session.scalar(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == row.id
        )
    )
    assert line is not None
    second = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number=supplier_return_number,
            supplier_return_date=date(2026, 8, 3),
            return_date=date(2026, 8, 3),
            warehouse_id=row.warehouse_id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": line.source_document_id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=line.source_document_id,
                    source_document_line_id=line.source_document_line_id,
                    line_number=1,
                    current_return_quantity=Decimal("2"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("0"),
                    charges_amount=Decimal("0"),
                    warehouse_id=row.warehouse_id,
                    is_damaged=is_damaged,
                    is_expired=is_expired,
                    reason_code=reason_code,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    service.approve_return(second.id, firm_scope=firm_id, actor_id=uuid4())
    return second


def test_the_damaged_report_shows_only_the_lines_recorded_as_damaged() -> None:
    """It used to filter on quantity, so it answered "anything returned"."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    damaged = _return_against(
        session,
        service,
        row,
        firm_id=firm.id,
        supplier_return_number="SUP-2002",
        is_damaged=True,
        reason_code="DAMAGED",
    )

    rows = service.reconciliation_report(firm_scope=firm.id, damaged_only=True)

    # Two returns exist and only one of them says the goods were damaged.
    assert len(service.reconciliation_report(firm_scope=firm.id)) == 2
    assert [record.return_id for record in rows] == [damaged.id]
    assert rows[0].reason_code == "DAMAGED"
    assert rows[0].is_damaged is True


def test_the_expired_report_shows_only_the_lines_recorded_as_expired() -> None:
    """It used to filter ``pending_quantity >= 0``, which is nearly every row."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    expired = _return_against(
        session,
        service,
        row,
        firm_id=firm.id,
        supplier_return_number="SUP-2003",
        is_expired=True,
    )

    rows = service.reconciliation_report(firm_scope=firm.id, expired_only=True)

    assert [record.return_id for record in rows] == [expired.id]
    assert rows[0].is_expired is True


def test_a_damaged_line_is_not_an_expired_one() -> None:
    """The two conditions are recorded separately and must not bleed."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    _return_against(
        session,
        service,
        row,
        firm_id=firm.id,
        supplier_return_number="SUP-2004",
        is_damaged=True,
    )

    assert service.reconciliation_report(firm_scope=firm.id, expired_only=True) == []


def test_the_by_product_report_is_grouped_by_product() -> None:
    """It used to answer the per-line reconciliation, which carries no product."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, product_id = _approved_return(session, firm_id=firm.id)
    _return_against(
        session, service, row, firm_id=firm.id, supplier_return_number="SUP-2005"
    )

    rows = service.by_product_report(firm_scope=firm.id)

    assert len(rows) == 1
    assert rows[0].product_id == product_id
    assert rows[0].product_code == "SKU-001"
    # Four on the first return and two on the second, across two lines.
    assert rows[0].return_quantity == Decimal("6.00")
    assert rows[0].return_count == 2


def test_a_reconciliation_row_names_the_product_that_was_returned() -> None:
    """A row carrying only source-line ids cannot be read by anyone."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)

    record = service.reconciliation_report(firm_scope=firm.id)[0]

    assert record.product_name == "Product SKU-001"
    assert record.return_number == row.return_number
    assert record.return_date == date(2026, 8, 2)


def test_the_register_names_the_supplier_branch_and_warehouse() -> None:
    """D-RPT-17: the grid derives its columns from the row.

    The register answered `vendor_id`, `branch_id` and `warehouse_id` with
    nothing to read them by, so the screen showed three columns of UUIDs.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, _row, _ = _approved_return(session, firm_id=firm.id)
    vendor = session.scalar(select(Vendor).where(Vendor.firm_id == firm.id))
    branch = session.scalar(select(Branch).where(Branch.firm_id == firm.id))
    warehouse = session.scalar(select(Warehouse).where(Warehouse.firm_id == firm.id))
    assert vendor is not None and branch is not None and warehouse is not None

    [record] = service.register_report(firm_scope=firm.id)

    assert (record.vendor_id, record.vendor_name) == (vendor.id, vendor.display_name)
    assert (record.branch_id, record.branch_name) == (branch.id, branch.name)
    assert (record.warehouse_id, record.warehouse_name) == (
        warehouse.id,
        warehouse.name,
    )


def test_the_by_vendor_report_totals_what_was_returned() -> None:
    """Named for what it holds: returned value, not a balance still owing."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    _return_against(
        session, service, row, firm_id=firm.id, supplier_return_number="SUP-2006"
    )

    rows = service.by_vendor_report(firm_scope=firm.id)

    assert len(rows) == 1
    assert rows[0].vendor_name == "Vendor VEN-001"
    assert rows[0].return_count == 2


def test_a_cancelled_return_is_left_out_of_the_line_reports() -> None:
    """It never counted towards the vendor totals; now it counts nowhere."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    service.cancel_return(
        row.id, firm_scope=firm.id, actor_id=uuid4(), reason="raised in error"
    )

    assert service.reconciliation_report(firm_scope=firm.id) == []
    assert service.by_product_report(firm_scope=firm.id) == []
    assert service.by_vendor_report(firm_scope=firm.id) == []


def _inventory_account_balance(session: Session, firm_id: UUID) -> Decimal:
    """Return what the inventory control account currently holds."""
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
    """Return what the warehouse says its stock is worth."""
    total = session.scalar(
        select(func.coalesce(func.sum(ProductValuation.total_value), 0)).where(
            ProductValuation.firm_id == firm_id,
            ProductValuation.is_deleted.is_(False),
        )
    )
    return Decimal(str(total or 0))


def test_cancelling_a_completed_purchase_return_takes_its_journal_back() -> None:
    """The goods came back on the shelf and every posting stayed on the books.

    Completing a return debits payables for the supplier's credit note,
    reverses the input tax and credits inventory. `cancel_return` reversed the
    stock and never touched the ledger, so the firm still showed the supplier
    owing it for goods it had kept -- the same defect `goods_receipt` carried
    until 2026-08-18, sitting unfixed in its mirror module.

    Found on 2026-08-22 by cancelling one on a seeded store: balanced before,
    199.07 out afterwards.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, row = _approved_return_with_stock_posted(session, firm_id=firm.id)
    session.expire_all()
    before_stock = _warehouse_value(session, firm.id)
    before_ledger = _inventory_account_balance(session, firm.id)
    assert before_stock == before_ledger, "the two books start in step"

    service.cancel_return(
        row.id, firm_scope=firm.id, actor_id=uuid4(), reason="vendor refused"
    )
    session.expire_all()

    # The invariant `scripts/verify_sample_data.py` checks first.
    assert _warehouse_value(session, firm.id) == _inventory_account_balance(
        session, firm.id
    )

    entries = list(
        session.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.source_module == "purchase_return",
                JournalEntry.source_id == row.id,
                JournalEntry.is_deleted.is_(False),
            )
            .order_by(JournalEntry.created_at)
        ).all()
    )
    assert len(entries) == 2, "cancelling has to raise a reversal"
    original, reversal = entries
    assert reversal.reversal_of_id == original.id
    assert reversal.total_debit == reversal.total_credit
    # Payables nets to nothing: the credit note is void either way.
    payable = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .select_from(GLPosting)
        .join(
            FirmControlAccount,
            FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
        )
        .where(
            FirmControlAccount.firm_id == firm.id,
            FirmControlAccount.purpose == ControlAccountPurpose.ACCOUNTS_PAYABLE.value,
            FirmControlAccount.is_deleted.is_(False),
            GLPosting.is_deleted.is_(False),
        )
    )
    assert Decimal(str(payable or 0)) == Decimal("0")


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        (None, Decimal("100")),
        (Decimal("0"), Decimal("0")),
        (Decimal("80"), Decimal("80")),
    ],
)
def test_a_return_with_no_price_goes_back_at_the_source_lines_price(
    stated: Decimal | None, expected: Decimal
) -> None:
    """Silence takes the source line's price; a stated price, zero included, wins.

    D-BUY-3: the price defaulted to zero, so every return raised without one --
    all the seeder's, and the test fixture's -- took its stock out at nothing,
    sent the value to the write-off account and debited the supplier 0.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)
    line: dict[str, object] = {
        "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
        "source_document_id": receipt.id,
        "source_document_line_id": receipt_line.id,
        "line_number": 1,
        "current_return_quantity": Decimal("4"),
        "warehouse_id": warehouse.id,
    }
    if stated is not None:
        line["unit_price"] = stated

    row = PurchaseReturnService(session).create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-PRICE",
            supplier_return_date=date(2026, 8, 2),
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[PurchaseReturnLineWrite.model_validate(line)],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    saved = session.scalar(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == row.id
        )
    )
    assert saved is not None
    assert saved.unit_price == expected
    assert saved.gross_amount == expected * 4


def test_only_a_completed_return_can_be_closed() -> None:
    """D-BUY-13: a DRAFT or APPROVED return could be closed.

    Driven on TEST01 on 2026-09-18: PR-2026-2027-000004 went from DRAFT to
    CLOSED though no goods had gone out and nothing had posted.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, approved, _ = _approved_return(session, firm_id=firm.id)
    with pytest.raises(ValidationError, match="Only completed purchase returns"):
        service.close_return(approved.id, firm_scope=firm.id, actor_id=uuid4())


def test_a_return_cannot_skip_the_receipt() -> None:
    """D-BUY-14: the request body used to carry a switch past the receipt.

    Driven 2026-09-19 on TEST01 (fixture ``po-approved``, suffix t0919d4tq):
    four returned against PO-TEST01-HO-2026-2027-000011, on which nothing had
    arrived, with ``allow_direct_purchase_order`` true -- approved and
    completed, the shelf at -4 and the supplier debited 472. The field is
    gone, and a return naming the order -- as its source or on a line -- is
    refused whatever the body says.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, _ = _received(session, po_line)

    def _return(source_id: UUID) -> dict[str, object]:
        source_type = (
            PurchaseReturnSourceType.GOODS_RECEIPT
            if source_id == receipt.id
            else PurchaseReturnSourceType.PURCHASE_ORDER
        )
        return PurchaseReturnCreate(
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            source_documents=[
                {"source_document_type": source_type, "source_document_id": source_id}
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.PURCHASE_ORDER,
                    source_document_id=source_id,
                    source_document_line_id=po_line.id,
                    line_number=1,
                    current_return_quantity=Decimal("4"),
                    warehouse_id=warehouse.id,
                )
            ],
        ).model_dump(mode="json")

    straight = _return(order.id)
    with pytest.raises(PydanticValidationError, match="allow_direct_purchase_order"):
        PurchaseReturnCreate.model_validate(
            {**straight, "allow_direct_purchase_order": True}
        )

    service = PurchaseReturnService(session)
    # Straight against the order, and a line naming the order behind a
    # receipt's back: both refused before anything is looked up.
    for body in (straight, _return(receipt.id)):
        with pytest.raises(ValidationError, match="never straight against"):
            service.create_return(
                PurchaseReturnCreate.model_validate(body),
                firm_id=firm.id,
                actor_id=uuid4(),
            )
    assert session.scalar(select(PurchaseReturn.id)) is None


def test_a_return_off_the_receipt_leaves_a_supplier_credit_until_cancelled() -> None:
    """D-FIN-19: completing it credits the supplier; cancelling takes that back.

    A return raised from the goods receipt names no bill, so its payables debit
    is a credit on the supplier's account. Set against a bill, the bill owes
    less; cancelling the return reverses the debit, so what was set against
    the bill is withdrawn and the bill owes it again.
    """
    from app.purchase_invoice.models import PurchaseInvoice
    from app.settlements.services import PaymentService
    from app.settlements.services.supplier_credits import (
        apply_supplier_credit,
        supplier_credits,
    )

    session = _session_factory()()
    firm = _firm(session)
    service, row = _approved_return_with_stock_posted(session, firm_id=firm.id)
    credits = supplier_credits(session, firm_id=firm.id, vendor_id=row.vendor_id)
    assert [(credit.return_number, credit.available_amount) for credit in credits] == [
        (row.return_number, Decimal("400.00"))
    ]
    bill = PurchaseInvoice(
        firm_id=firm.id,
        vendor_id=row.vendor_id,
        branch_id=row.branch_id,
        invoice_number="PI-NEXT",
        invoice_date=date(2026, 8, 3),
        supplier_invoice_number="SUP-NEXT",
        supplier_invoice_date=date(2026, 8, 3),
        status="APPROVED",
        grand_total=Decimal("1000.00"),
    )
    session.add(bill)
    session.commit()
    apply_supplier_credit(
        session,
        firm_id=firm.id,
        purchase_return_id=row.id,
        invoice_id=bill.id,
        amount=Decimal("400"),
        actor_id=uuid4(),
    )
    session.commit()

    def _owed() -> Decimal:
        return next(
            record.outstanding_amount
            for record in PaymentService(session).outstanding_invoices(
                firm_id=firm.id, party_id=row.vendor_id
            )
            if record.invoice_id == bill.id
        )

    assert _owed() == Decimal("600.00")

    service.cancel_return(row.id, firm_scope=firm.id, actor_id=uuid4(), reason="x")

    assert _owed() == Decimal("1000.00")
    assert supplier_credits(session, firm_id=firm.id) == []


def _other_receipt_line(
    session: Session,
    receipt: GoodsReceipt,
    *,
    number: str,
    status: str,
    firm_id: UUID | None = None,
) -> GoodsReceiptLine:
    """Record a second receipt beside ``receipt`` and return its line.

    Same order line, so the only thing wrong with naming it from a line of
    ``receipt`` is that it is not ``receipt``'s line -- which is the case.
    """
    firm = firm_id or receipt.firm_id
    other = GoodsReceipt(
        firm_id=firm,
        purchase_order_id=receipt.purchase_order_id,
        purchase_order_number=receipt.purchase_order_number,
        vendor_id=receipt.vendor_id,
        branch_id=receipt.branch_id,
        warehouse_id=receipt.warehouse_id,
        grn_number=number,
        receipt_date=date(2026, 8, 2),
        status=status,
    )
    session.add(other)
    session.flush()
    template = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()
    line = GoodsReceiptLine(
        goods_receipt_id=other.id,
        firm_id=firm,
        line_number=1,
        purchase_order_line_id=template.purchase_order_line_id,
        purchase_order_line_number=template.purchase_order_line_number,
        product_id=template.product_id,
        ordered_quantity=template.ordered_quantity,
        current_receipt_quantity=template.current_receipt_quantity,
        accepted_quantity=template.accepted_quantity,
        unit_price=template.unit_price,
        warehouse_id=template.warehouse_id,
    )
    session.add(line)
    session.commit()
    return line


def test_a_return_line_cannot_front_for_another_documents_line() -> None:
    """D-BUY-17: a return line was looked up by its id alone.

    Driven 2026-09-19 on TEST01: PR-2026-2027-000007 named the completed
    GRN-TEST01-HO-2026-2027-000020 (6) and carried the line id of the DRAFT
    GRN-TEST01-HO-2026-2027-000024 of another order -- created, approved and
    completed, that product's shelf at -10 for goods that never came in.
    A line must be one of the named receipt's own lines, in the same firm;
    a bill it is returned against must stand; and a return saved before the
    check cannot complete through a line it does not own.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)
    draft_line = _other_receipt_line(
        session, receipt, number="GRN-2026-000002", status="DRAFT"
    )
    elsewhere = Firm(
        name="Elsewhere",
        code="ELSEWHERE",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(elsewhere)
    session.commit()
    foreign_line = _other_receipt_line(
        session,
        receipt,
        number="GRN-2026-000003",
        status="COMPLETED",
        firm_id=elsewhere.id,
    )
    service = PurchaseReturnService(session)

    def _return(
        line_id: UUID,
        source_type: PurchaseReturnSourceType = PurchaseReturnSourceType.GOODS_RECEIPT,
        source_id: UUID | None = None,
    ) -> PurchaseReturnCreate:
        named = source_id or receipt.id
        return PurchaseReturnCreate(
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            source_documents=[
                {"source_document_type": source_type, "source_document_id": named}
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=source_type,
                    source_document_id=named,
                    source_document_line_id=line_id,
                    line_number=1,
                    current_return_quantity=Decimal("4"),
                    warehouse_id=warehouse.id,
                )
            ],
        )

    for line_id in (draft_line.id, foreign_line.id):
        with pytest.raises(ValidationError, match="GRN-2026-000001 has no line"):
            service.create_return(_return(line_id), firm_id=firm.id, actor_id=uuid4())
        session.rollback()
    assert session.scalar(select(PurchaseReturn.id)) is None

    # A cancelled supplier bill takes no return, by name.
    bills = PurchaseInvoiceService(session)
    bill = bills.create_invoice(
        PurchaseInvoiceCreate(
            supplier_invoice_number="SUP-GONE",
            supplier_invoice_date=date(2026, 8, 2),
            invoice_date=date(2026, 8, 2),
            source_documents=[
                {
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=receipt_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    bills.cancel_invoice(bill.id, firm_scope=firm.id, actor_id=uuid4())
    bill_line = session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    with pytest.raises(ValidationError, match="is cancelled, so nothing can be"):
        service.create_return(
            _return(
                bill_line.id,
                PurchaseReturnSourceType.PURCHASE_INVOICE,
                bill.id,
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
    session.rollback()

    # A return saved before the check, pointing at the draft receipt's line,
    # does not complete.
    saved = service.create_return(
        _return(receipt_line.id), firm_id=firm.id, actor_id=uuid4()
    )
    service.approve_return(saved.id, firm_scope=firm.id, actor_id=uuid4())
    line = session.scalars(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == saved.id
        )
    ).one()
    line.source_document_line_id = draft_line.id
    session.commit()
    with pytest.raises(ValidationError, match="GRN-2026-000001 has no line"):
        service.complete_return(saved.id, firm_scope=firm.id, actor_id=uuid4())


def test_the_return_reports_take_a_window_and_a_page() -> None:
    """D-RPT-18: every report was the firm's whole history.

    Every report here is read on the return's own `return_date`, both ends
    inclusive, with `total_records` counting the matches rather than the page,
    and a page above the cap refused with a 422.
    """
    from app.purchase_return.api.router import (
        damaged_goods_report,
        expired_goods_report,
        purchase_return_reconciliation,
        purchase_return_register,
        returns_by_product,
        returns_by_vendor,
        router,
    )
    from tests.unit.report_windows import assert_page_size_is_bounded, report_scope

    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)  # 2026-08-02
    _return_against(  # 2026-08-03
        session,
        service,
        row,
        firm_id=firm.id,
        supplier_return_number="SUP-W1",
        is_damaged=True,
    )
    expired = _return_against(
        session,
        service,
        row,
        firm_id=firm.id,
        supplier_return_number="SUP-W2",
        is_expired=True,
    )
    expired.return_date = date(2026, 8, 4)
    session.commit()
    first, second, third = date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)
    scope = report_scope(firm.id)

    page = purchase_return_register(
        scope=scope, db=session, from_date=second, to_date=third, page=1, page_size=1
    )
    assert page.pagination.total_records == 2
    assert [record.return_date for record in page.data] == [third]

    [vendor] = returns_by_vendor(
        scope=scope, db=session, from_date=first, to_date=first
    ).data
    assert vendor.return_count == 1
    [product] = returns_by_product(scope=scope, db=session, from_date=second).data
    assert product.return_count == 2

    lines = purchase_return_reconciliation(
        scope=scope, db=session, from_date=second, page=2, page_size=1
    )
    assert lines.pagination.total_records == 2
    assert [record.return_date for record in lines.data] == [second]
    assert (
        damaged_goods_report(
            scope=scope, db=session, from_date=first, to_date=first
        ).data
        == []
    )
    assert damaged_goods_report(scope=scope, db=session, from_date=second).data
    assert expired_goods_report(scope=scope, db=session, to_date=second).data == []

    assert_page_size_is_bounded(
        router,
        "/api/v1/purchase-returns/reports/register",
        "/api/v1/purchase-returns/reports/by-vendor",
        "/api/v1/purchase-returns/reports/by-product",
        "/api/v1/purchase-returns/reports/reconciliation",
        "/api/v1/purchase-returns/reports/damaged",
        "/api/v1/purchase-returns/reports/expired",
    )
