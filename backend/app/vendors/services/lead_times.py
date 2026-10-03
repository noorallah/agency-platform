"""A supplier's lead time, as quoted and as delivered (BUY-6, decision A105).

Quoted: the ``lead_time_days`` on the supplier's catalogue rows in force.
Delivered: for every completed receipt, the days from the order's date to
the receipt's, and whether it came after the order's expected date. Nothing
is stored -- a receipt cancelled later simply stops counting.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.vendors.services.supplier_catalogue import current_rows

#: A receipt that counts: completed, or completed and since closed.
_LIVE_RECEIPT = ("COMPLETED", "CLOSED")


@dataclass(frozen=True)
class LeadTimeSummary:
    """What a supplier quotes and what its deliveries actually took."""

    vendor_id: UUID
    #: The longest lead time its catalogue quotes today, if any.
    quoted_days: int | None
    receipts: int
    average_days: Decimal | None
    #: Receipts that came after the order's expected date.
    late_receipts: int
    #: Receipts whose order named an expected date at all.
    receipts_with_expected_date: int

    @property
    def on_time_percent(self) -> Decimal | None:
        """Share of dated receipts that came on or before the expected date."""
        if not self.receipts_with_expected_date:
            return None
        on_time = self.receipts_with_expected_date - self.late_receipts
        return (
            Decimal(on_time * 100) / Decimal(self.receipts_with_expected_date)
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def lead_time_summary(
    session: Session, *, firm_id: UUID, vendor_id: UUID
) -> LeadTimeSummary:
    """Return one supplier's quoted and delivered lead time."""
    from app.goods_receipt.models import GoodsReceipt
    from app.purchase.models import PurchaseOrder

    quoted = [
        row.lead_time_days
        for row in current_rows(
            session,
            firm_id=firm_id,
            vendor_id=vendor_id,
            product_ids=None,
            on=utc_now().date(),
        ).values()
        if row.lead_time_days is not None
    ]
    rows = session.execute(
        select(
            GoodsReceipt.receipt_date,
            PurchaseOrder.purchase_date,
            PurchaseOrder.expected_delivery_date,
        )
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .where(
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.vendor_id == vendor_id,
            GoodsReceipt.status.in_(_LIVE_RECEIPT),
            GoodsReceipt.is_deleted.is_(False),
        )
    ).all()
    days = [max((received - ordered).days, 0) for received, ordered, _ in rows]
    dated = [(received, expected) for received, _, expected in rows if expected]
    return LeadTimeSummary(
        vendor_id=vendor_id,
        quoted_days=max(quoted) if quoted else None,
        receipts=len(rows),
        average_days=(
            (Decimal(sum(days)) / Decimal(len(days))).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
            if days
            else None
        ),
        late_receipts=sum(1 for received, expected in dated if received > expected),
        receipts_with_expected_date=len(dated),
    )
