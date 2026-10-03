"""Free goods: received, given away, and what is left (BUY-1, decision A111).

One list in three sections, each grouped in SQL: ``RECEIVED`` -- free-issue
products counted in on completed receipts, per supplier and scheme;
``GIVEN`` -- written off as given free to a customer or as a sample, per
customer and reason, at what it cost; ``ON_HAND`` -- what of each free-issue
product is still held. Received less given is what is held, give or take
anything damaged or lost on the way.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.report_names import vendor_names
from app.core.pagination import ReportWindow
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.models import InventoryRecord, InventoryTransaction, StockLedgerEntry
from app.products.models import Product

_LIVE_RECEIPT = ("COMPLETED", "CLOSED")
_GIVEN = ("FREE_TO_CUSTOMER", "SAMPLE")


class FreeGoodsRecord(BaseModel):
    """One row of the free goods report."""

    model_config = ConfigDict(extra="forbid")

    #: ``RECEIVED``, ``GIVEN`` or ``ON_HAND``.
    section: str
    #: The supplier for a receipt, the customer for a gift, blank on hand.
    party_name: str
    #: The scheme a receipt came under, or the reason it was given.
    detail: str
    product_code: str
    product_name: str
    quantity: Decimal
    #: What it cost, for goods given away.
    value: Decimal | None = None


def free_goods_report(
    session: Session, *, firm_id: UUID, window: ReportWindow
) -> list[FreeGoodsRecord]:
    """Return the free goods report's rows, received then given then held."""
    from app.customers.models import Customer

    products = {
        p.id: p
        for p in session.scalars(
            select(Product).where(
                Product.firm_id == firm_id,
                Product.free_issue_only.is_(True),
                Product.is_deleted.is_(False),
            )
        ).all()
    }
    if not products:
        return []
    ids = list(products)
    rows: list[FreeGoodsRecord] = []

    received = session.execute(
        select(
            GoodsReceipt.vendor_id,
            GoodsReceiptLine.scheme_name,
            GoodsReceiptLine.product_id,
            func.sum(
                GoodsReceiptLine.accepted_quantity + GoodsReceiptLine.free_quantity
            ),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .where(
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.status.in_(_LIVE_RECEIPT),
            GoodsReceipt.is_deleted.is_(False),
            GoodsReceiptLine.is_deleted.is_(False),
            GoodsReceiptLine.product_id.in_(ids),
            *window.dated(GoodsReceipt.receipt_date),
        )
        .group_by(
            GoodsReceipt.vendor_id,
            GoodsReceiptLine.scheme_name,
            GoodsReceiptLine.product_id,
        )
    ).all()
    suppliers = vendor_names(session, (vendor for vendor, *_ in received))
    for vendor, scheme, product_id, quantity in received:
        product = products[product_id]
        rows.append(
            FreeGoodsRecord(
                section="RECEIVED",
                party_name=suppliers.get(vendor, ""),
                detail=scheme or "",
                product_code=product.code,
                product_name=product.name,
                quantity=Decimal(str(quantity or 0)),
            )
        )

    given = session.execute(
        select(
            InventoryTransaction.customer_id,
            InventoryTransaction.reference_type,
            InventoryTransaction.product_id,
            func.sum(InventoryTransaction.quantity),
            func.sum(func.abs(StockLedgerEntry.total_cost)),
        )
        .outerjoin(
            StockLedgerEntry,
            StockLedgerEntry.transaction_id == InventoryTransaction.id,
        )
        .where(
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.reference_type.in_(_GIVEN),
            InventoryTransaction.is_deleted.is_(False),
            *window.dated(InventoryTransaction.transaction_date),
        )
        .group_by(
            InventoryTransaction.customer_id,
            InventoryTransaction.reference_type,
            InventoryTransaction.product_id,
        )
    ).all()
    customer_ids = {customer for customer, *_ in given if customer}
    customers: dict[UUID, str] = {}
    if customer_ids:
        for row_id, name in session.execute(
            select(Customer.id, Customer.display_name).where(
                Customer.id.in_(customer_ids)
            )
        ).all():
            customers[row_id] = name
    for customer, reason, product_id, quantity, value in given:
        given_product = products.get(product_id)
        rows.append(
            FreeGoodsRecord(
                section="GIVEN",
                party_name=customers.get(customer, "") if customer else "",
                detail="Given free" if reason == "FREE_TO_CUSTOMER" else "Sample",
                product_code=given_product.code if given_product else "",
                product_name=given_product.name if given_product else "",
                quantity=Decimal(str(quantity or 0)),
                value=Decimal(str(value or 0)),
            )
        )

    for product_id, held in session.execute(
        select(
            InventoryRecord.product_id,
            func.sum(
                InventoryRecord.current_quantity + InventoryRecord.quarantine_quantity
            ),
        )
        .where(
            InventoryRecord.firm_id == firm_id,
            InventoryRecord.product_id.in_(ids),
            InventoryRecord.is_deleted.is_(False),
        )
        .group_by(InventoryRecord.product_id)
    ).all():
        product = products[product_id]
        rows.append(
            FreeGoodsRecord(
                section="ON_HAND",
                party_name="",
                detail="",
                product_code=product.code,
                product_name=product.name,
                quantity=Decimal(str(held or 0)),
            )
        )
    return rows
