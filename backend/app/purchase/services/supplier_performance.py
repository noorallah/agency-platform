"""Which supplier delivers late, short or bad, and at what price (BUY-12).

Decision A107. One row per supplier over a window, every figure grouped in
SQL from the documents and nothing stored:

* **On time** -- completed receipts dated in the window that came on or
  before their order's expected date, out of those whose order had one.
* **Rejected** -- rejected and damaged quantity out of what those receipts
  counted in.
* **Returned** -- quantity sent back on completed purchase returns dated in
  the window, out of what was received.
* **Short** -- on orders dated in the window that are finished (received in
  full or closed), what was ordered and never received.

The price trend is a separate read: one supplier's average billed rate per
month, for one product or for everything it sold the firm.
"""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.common.report_names import vendor_names
from app.core.pagination import ReportWindow
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import SupplierPerformanceRecord, SupplierPriceTrendPoint
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

ZERO = Decimal("0")
_LIVE_RECEIPT = ("COMPLETED", "CLOSED")
_LIVE_RETURN = ("COMPLETED", "CLOSED")
_LIVE_BILL = ("APPROVED", "CLOSED")
_FINISHED_ORDER = ("RECEIVED", "CLOSED")


def _percent(part: Decimal, whole: Decimal) -> Decimal | None:
    """Return part of whole as a percentage to one place, or None."""
    if whole <= ZERO:
        return None
    return (part * 100 / whole).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def supplier_performance(
    session: Session, *, firm_id: UUID, window: ReportWindow
) -> list[SupplierPerformanceRecord]:
    """Return one row per supplier with receipts, returns or finished orders."""
    receipts: dict[UUID, tuple[int, int, int]] = {}
    on_time = case(
        (
            PurchaseOrder.expected_delivery_date.is_not(None)
            & (GoodsReceipt.receipt_date <= PurchaseOrder.expected_delivery_date),
            1,
        ),
        else_=0,
    )
    dated = case((PurchaseOrder.expected_delivery_date.is_not(None), 1), else_=0)
    for vendor, count, timely, with_date in session.execute(
        select(
            GoodsReceipt.vendor_id,
            func.count(GoodsReceipt.id),
            func.sum(on_time),
            func.sum(dated),
        )
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .where(
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.status.in_(_LIVE_RECEIPT),
            GoodsReceipt.is_deleted.is_(False),
            *window.dated(GoodsReceipt.receipt_date),
        )
        .group_by(GoodsReceipt.vendor_id)
    ).all():
        receipts[vendor] = (int(count), int(timely or 0), int(with_date or 0))

    quantities: dict[UUID, tuple[Decimal, Decimal]] = {}
    for vendor, received, rejected in session.execute(
        select(
            GoodsReceipt.vendor_id,
            func.sum(GoodsReceiptLine.current_receipt_quantity),
            func.sum(
                GoodsReceiptLine.rejected_quantity + GoodsReceiptLine.damaged_quantity
            ),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .where(
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.status.in_(_LIVE_RECEIPT),
            GoodsReceipt.is_deleted.is_(False),
            GoodsReceiptLine.is_deleted.is_(False),
            *window.dated(GoodsReceipt.receipt_date),
        )
        .group_by(GoodsReceipt.vendor_id)
    ).all():
        quantities[vendor] = (
            Decimal(str(received or 0)),
            Decimal(str(rejected or 0)),
        )

    returned: dict[UUID, Decimal] = {}
    for vendor, quantity in session.execute(
        select(
            PurchaseReturn.vendor_id,
            func.sum(PurchaseReturnLine.current_return_quantity),
        )
        .join(
            PurchaseReturn, PurchaseReturn.id == PurchaseReturnLine.purchase_return_id
        )
        .where(
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.status.in_(_LIVE_RETURN),
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturnLine.is_deleted.is_(False),
            *window.dated(PurchaseReturn.return_date),
        )
        .group_by(PurchaseReturn.vendor_id)
    ).all():
        returned[vendor] = Decimal(str(quantity or 0))

    # What finished orders asked for, and what their live receipts brought.
    ordered: dict[UUID, Decimal] = {}
    for vendor, quantity in session.execute(
        select(PurchaseOrder.vendor_id, func.sum(PurchaseOrderLine.ordered_quantity))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(
            PurchaseOrder.firm_id == firm_id,
            PurchaseOrder.status.in_(_FINISHED_ORDER),
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrderLine.is_deleted.is_(False),
            *window.dated(PurchaseOrder.purchase_date),
        )
        .group_by(PurchaseOrder.vendor_id)
    ).all():
        ordered[vendor] = Decimal(str(quantity or 0))
    brought: dict[UUID, Decimal] = {}
    for vendor, quantity in session.execute(
        select(
            PurchaseOrder.vendor_id, func.sum(GoodsReceiptLine.current_receipt_quantity)
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .where(
            PurchaseOrder.firm_id == firm_id,
            PurchaseOrder.status.in_(_FINISHED_ORDER),
            PurchaseOrder.is_deleted.is_(False),
            GoodsReceipt.status.in_(_LIVE_RECEIPT),
            GoodsReceipt.is_deleted.is_(False),
            GoodsReceiptLine.is_deleted.is_(False),
            *window.dated(PurchaseOrder.purchase_date),
        )
        .group_by(PurchaseOrder.vendor_id)
    ).all():
        brought[vendor] = Decimal(str(quantity or 0))

    vendors = set(receipts) | set(returned) | set(ordered)
    names = vendor_names(session, vendors)
    rows: list[SupplierPerformanceRecord] = []
    for vendor in vendors:
        count, timely, with_date = receipts.get(vendor, (0, 0, 0))
        received, rejected = quantities.get(vendor, (ZERO, ZERO))
        back = returned.get(vendor, ZERO)
        asked = ordered.get(vendor, ZERO)
        short = max(asked - brought.get(vendor, ZERO), ZERO)
        rows.append(
            SupplierPerformanceRecord(
                vendor_id=vendor,
                vendor_name=names.get(vendor, str(vendor)),
                receipts=count,
                on_time_receipts=timely,
                receipts_with_expected_date=with_date,
                on_time_percent=_percent(Decimal(timely), Decimal(with_date)),
                received_quantity=received,
                rejected_quantity=rejected,
                rejected_percent=_percent(rejected, received),
                returned_quantity=back,
                returned_percent=_percent(back, received),
                ordered_quantity=asked,
                short_quantity=short,
                short_percent=_percent(short, asked),
            )
        )
    rows.sort(key=lambda row: row.vendor_name.lower())
    return rows


def supplier_price_trend(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    product_id: UUID | None,
    window: ReportWindow,
) -> list[SupplierPriceTrendPoint]:
    """Return the supplier's average billed rate per month, oldest first.

    The average is weighted by quantity: what was billed before tax, less
    each line's discount, over how much was billed.
    """
    query = (
        select(
            PurchaseInvoice.invoice_date,
            PurchaseInvoiceLine.current_invoice_quantity,
            PurchaseInvoiceLine.unit_price,
            PurchaseInvoiceLine.discount_amount,
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.vendor_id == vendor_id,
            PurchaseInvoice.status.in_(_LIVE_BILL),
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoiceLine.is_deleted.is_(False),
            *window.dated(PurchaseInvoice.invoice_date),
        )
    )
    if product_id is not None:
        query = query.where(PurchaseInvoiceLine.product_id == product_id)
    months: dict[date, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for billed_on, quantity, price, discount in session.execute(query).all():
        qty = Decimal(str(quantity or 0))
        bucket = months[billed_on.replace(day=1)]
        bucket[0] += qty
        bucket[1] += qty * Decimal(str(price or 0)) - Decimal(str(discount or 0))
    return [
        SupplierPriceTrendPoint(
            month=first.strftime("%Y-%m"),
            quantity=quantity,
            average_rate=(value / quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        )
        for first, (quantity, value) in sorted(months.items())
        if quantity > ZERO
    ]
