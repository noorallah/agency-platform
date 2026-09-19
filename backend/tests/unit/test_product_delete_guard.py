"""A product holding stock, or still on a document in flight, is not deleted.

D-MST-1: ``delete_product`` checked nothing, while the stock summary filters
deleted products out and every movement of one is refused -- so 45 units in
MAIN and 5 in a bin sat on the books where no screen showed them and no
write-off could reach them. TEST01 held 13 such products, 432 units between
them.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Warehouse, WarehouseStorageNode
from app.business.models import BusinessProfile
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.products.schemas import ProductCreate
from app.products.services import ProductService
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine


def _session() -> Session:
    """Open one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Add a firm and the default profile a product needs."""
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    if session.scalar(select(BusinessProfile.id).limit(1)) is None:
        session.add(
            BusinessProfile(
                code="GENERIC",
                name="Generic",
                industry_type="GENERIC",
                status="ACTIVE",
                is_default=True,
                default_settings={},
                created_by=uuid4(),
                updated_by=uuid4(),
            )
        )
    session.commit()
    return firm


def _product(service: ProductService, firm: Firm, code: str) -> Product:
    """Create one plain stock item."""
    return service.create_product(
        ProductCreate.model_validate(
            {"code": code, "name": code, "product_type": "STOCK_ITEM"}
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )


def _warehouse(session: Session, firm: Firm, code: str = "MAIN") -> Warehouse:
    """Add a warehouse row to name in a refusal."""
    row = Warehouse(
        firm_id=firm.id,
        branch_id=uuid4(),
        code=code,
        name=code,
        display_name=code,
    )
    session.add(row)
    session.commit()
    return row


def _stock(
    session: Session,
    *,
    firm: Firm,
    warehouse: Warehouse,
    product_id: UUID,
    on_hand: str,
    reserved: str = "0",
    node_id: UUID | None = None,
) -> InventoryRecord:
    """Put a quantity of one product somewhere."""
    row = InventoryRecord(
        firm_id=firm.id,
        branch_id=warehouse.branch_id,
        warehouse_id=warehouse.id,
        storage_node_id=node_id,
        storage_locator="MAIN" if node_id is None else str(node_id),
        product_id=product_id,
        current_quantity=Decimal(on_hand),
        reserved_quantity=Decimal(reserved),
        available_quantity=Decimal(on_hand) - Decimal(reserved),
    )
    session.add(row)
    session.commit()
    return row


def _sales_order(
    session: Session, *, firm: Firm, product_id: UUID, number: str, status: str
) -> SalesOrder:
    """Add a one-line sales order in the given status."""
    order = SalesOrder(
        firm_id=firm.id,
        customer_id=uuid4(),
        branch_id=uuid4(),
        warehouse_id=uuid4(),
        order_number=number,
        order_date=date(2026, 9, 19),
        status=status,
    )
    session.add(order)
    session.flush()
    session.add(
        SalesOrderLine(
            sales_order_id=order.id,
            firm_id=firm.id,
            line_number=1,
            product_id=product_id,
            quantity=Decimal("1"),
        )
    )
    session.commit()
    return order


def _completed_receipt(
    session: Session, *, firm: Firm, product_id: UUID, number: str
) -> GoodsReceiptLine:
    """Add a completed one-line goods receipt and return its line."""
    receipt = GoodsReceipt(
        firm_id=firm.id,
        purchase_order_id=uuid4(),
        purchase_order_number="PO-1",
        vendor_id=uuid4(),
        branch_id=uuid4(),
        warehouse_id=uuid4(),
        grn_number=number,
        receipt_date=date(2026, 9, 19),
        status="COMPLETED",
    )
    session.add(receipt)
    session.flush()
    line = GoodsReceiptLine(
        goods_receipt_id=receipt.id,
        firm_id=firm.id,
        line_number=1,
        purchase_order_line_id=uuid4(),
        purchase_order_line_number=1,
        product_id=product_id,
        ordered_quantity=Decimal("10"),
        accepted_quantity=Decimal("10"),
        warehouse_id=receipt.warehouse_id,
    )
    session.add(line)
    session.commit()
    return line


def _bill(session: Session, *, firm: Firm, line: GoodsReceiptLine, status: str) -> None:
    """Add a purchase invoice naming the receipt line."""
    invoice = PurchaseInvoice(
        firm_id=firm.id,
        vendor_id=uuid4(),
        branch_id=uuid4(),
        invoice_number=f"PI-{status}",
        invoice_date=date(2026, 9, 19),
        supplier_invoice_number=f"SUP-{status}",
        supplier_invoice_date=date(2026, 9, 19),
        status=status,
    )
    session.add(invoice)
    session.flush()
    session.add(
        PurchaseInvoiceLine(
            purchase_invoice_id=invoice.id,
            firm_id=firm.id,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=line.goods_receipt_id,
            source_document_number="GRN",
            source_document_line_id=line.id,
            source_document_line_number=1,
            product_id=line.product_id,
            received_quantity=Decimal("10"),
        )
    )
    session.commit()


def test_a_product_holding_stock_is_refused_by_quantity_and_place() -> None:
    """The refusal names how much is held and where, the bin included."""
    session = _session()
    firm = _firm(session, "PDG1")
    service = ProductService(session)
    product = _product(service, firm, "PDG-P1")
    warehouse = _warehouse(session, firm)
    node = WarehouseStorageNode(
        warehouse_id=warehouse.id,
        node_type="BIN",
        code="BIN-1",
        name="Bin 1",
        path="BIN-1",
    )
    session.add(node)
    session.commit()
    _stock(session, firm=firm, warehouse=warehouse, product_id=product.id, on_hand="45")
    _stock(
        session,
        firm=firm,
        warehouse=warehouse,
        product_id=product.id,
        on_hand="5",
        reserved="2",
        node_id=node.id,
    )

    with pytest.raises(ValidationError) as refused:
        service.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())

    message = str(refused.value)
    assert "PDG-P1 cannot be deleted" in message
    assert "45 in MAIN" in message
    assert "5 in MAIN / BIN-1 (2 reserved)" in message
    session.rollback()
    assert session.get(Product, product.id).is_deleted is False  # type: ignore[union-attr]
    assert (
        session.scalar(select(AuditLog.id).where(AuditLog.action == "product.deleted"))
        is None
    )


def test_a_reservation_alone_refuses_the_delete() -> None:
    """Nothing on hand but a quantity promised is still a quantity owed."""
    session = _session()
    firm = _firm(session, "PDG2")
    service = ProductService(session)
    product = _product(service, firm, "PDG-P2")
    warehouse = _warehouse(session, firm)
    _stock(
        session,
        firm=firm,
        warehouse=warehouse,
        product_id=product.id,
        on_hand="0",
        reserved="3",
    )

    with pytest.raises(ValidationError, match="3 reserved"):
        service.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())


def test_an_open_order_refuses_and_a_finished_one_does_not() -> None:
    """An approved order names the product; a cancelled or closed one is done."""
    session = _session()
    firm = _firm(session, "PDG3")
    service = ProductService(session)
    busy = _product(service, firm, "PDG-BUSY")
    done = _product(service, firm, "PDG-DONE")
    _sales_order(
        session, firm=firm, product_id=busy.id, number="SO-OPEN", status="APPROVED"
    )
    _sales_order(
        session, firm=firm, product_id=done.id, number="SO-GONE", status="CANCELLED"
    )
    _sales_order(
        session, firm=firm, product_id=done.id, number="SO-SHUT", status="CLOSED"
    )

    with pytest.raises(ValidationError) as refused:
        service.delete_product(busy.id, firm_scope=firm.id, actor_id=uuid4())
    assert "1 sales order (SO-OPEN)" in str(refused.value)
    session.rollback()

    service.delete_product(done.id, firm_scope=firm.id, actor_id=uuid4())
    assert session.get(Product, done.id).is_deleted is True  # type: ignore[union-attr]


def test_an_unbilled_receipt_refuses_until_a_live_bill_names_it() -> None:
    """Goods taken in and not billed are open; a cancelled bill does not count."""
    session = _session()
    firm = _firm(session, "PDG4")
    service = ProductService(session)
    product = _product(service, firm, "PDG-P4")
    line = _completed_receipt(
        session, firm=firm, product_id=product.id, number="GRN-UNBILLED"
    )

    with pytest.raises(ValidationError, match="1 goods receipt \\(GRN-UNBILLED\\)"):
        service.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())
    session.rollback()

    _bill(session, firm=firm, line=line, status="CANCELLED")
    with pytest.raises(ValidationError, match="GRN-UNBILLED"):
        service.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())
    session.rollback()

    _bill(session, firm=firm, line=line, status="APPROVED")
    service.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())
    assert session.get(Product, product.id).is_deleted is True  # type: ignore[union-attr]


def test_another_firms_stock_and_orders_do_not_hold_a_product() -> None:
    """The guard reads the product's own firm, not the store."""
    session = _session()
    firm = _firm(session, "PDG5")
    other = _firm(session, "PDG5B")
    service = ProductService(session)
    product = _product(service, firm, "PDG-P5")
    warehouse = _warehouse(session, other, "OTHER")
    _stock(session, firm=other, warehouse=warehouse, product_id=product.id, on_hand="9")
    _sales_order(
        session, firm=other, product_id=product.id, number="SO-OTHER", status="DRAFT"
    )

    service.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())
    assert session.get(Product, product.id).is_deleted is True  # type: ignore[union-attr]


def test_a_bulk_delete_checks_every_row_before_it_touches_one() -> None:
    """One product holding stock stops the batch, and nothing is deleted."""
    session = _session()
    firm = _firm(session, "PDG6")
    service = ProductService(session)
    free = _product(service, firm, "PDG-FREE")
    held = _product(service, firm, "PDG-HELD")
    warehouse = _warehouse(session, firm)
    _stock(session, firm=firm, warehouse=warehouse, product_id=held.id, on_hand="7")

    with pytest.raises(ValidationError, match="PDG-HELD cannot be deleted"):
        service.bulk_delete([free.id, held.id], firm_scope=firm.id, actor_id=uuid4())
    session.rollback()

    assert session.get(Product, free.id).is_deleted is False  # type: ignore[union-attr]
    assert session.get(Product, held.id).is_deleted is False  # type: ignore[union-attr]
    assert (
        session.scalar(select(AuditLog.id).where(AuditLog.action == "product.deleted"))
        is None
    )
