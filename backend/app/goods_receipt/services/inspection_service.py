"""Quality inspection of received goods (BUY-9, decision A100).

A product -- or its category -- marked ``inspection_required`` has its
received goods moved into quarantine by the goods receipt that brought them
in. They are owned and valued as received, but cannot be sold or issued
until an inspection decides them: what passes is released to stock; what is
rejected is either written off at once or left in quarantine for a purchase
return (condition ``QUARANTINE``) to send back.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.common.report_names import vendor_names
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.schemas import (
    QuarantineAction,
    StockQuarantineCreate,
    StockWriteOffCreate,
    WriteOffReason,
)
from app.inventory.services import InventoryService
from app.products.models import Product

ZERO = Decimal("0")

#: How many inspections one list call returns, newest receipt first.
INSPECTION_LIST_LIMIT = 500


@dataclass(frozen=True)
class InspectionRow:
    """One received line waiting for, or decided by, an inspection."""

    goods_receipt_id: UUID
    grn_number: str
    receipt_date: date
    vendor_id: UUID
    vendor_name: str
    line_id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    batch_number: str | None
    warehouse_id: UUID
    quantity: Decimal
    status: str
    passed_quantity: Decimal | None
    rejected_quantity: Decimal | None
    rejected_action: str | None
    inspected_at: datetime | None
    remarks: str | None


class GoodsInspectionService:
    """List and decide the inspections goods receipts raised."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    def list_inspections(
        self, *, firm_id: UUID, status: Literal["PENDING", "DONE"] = "PENDING"
    ) -> list[InspectionRow]:
        """Return the firm's inspections in one status, newest receipt first."""
        rows = self._session.execute(
            select(GoodsReceiptLine, GoodsReceipt)
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(
                GoodsReceiptLine.firm_id == firm_id,
                GoodsReceiptLine.inspection_status == status,
                GoodsReceiptLine.is_deleted.is_(False),
                GoodsReceipt.is_deleted.is_(False),
            )
            .order_by(
                GoodsReceipt.receipt_date.desc(),
                GoodsReceipt.grn_number.asc(),
                GoodsReceiptLine.line_number.asc(),
            )
            .limit(INSPECTION_LIST_LIMIT)
        ).all()
        suppliers = vendor_names(self._session, (r.vendor_id for _, r in rows))
        product_ids = {line.product_id for line, _ in rows}
        products = (
            {
                p.id: p
                for p in self._session.scalars(
                    select(Product).where(Product.id.in_(product_ids))
                ).all()
            }
            if product_ids
            else {}
        )
        return [self._row(line, receipt, suppliers, products) for line, receipt in rows]

    def inspect(
        self,
        receipt_id: UUID,
        line_id: UUID,
        *,
        passed_quantity: Decimal,
        rejected_quantity: Decimal,
        rejected_action: Literal["WRITE_OFF", "RETURN"] | None,
        remarks: str | None,
        firm_id: UUID,
        actor_id: UUID,
    ) -> InspectionRow:
        """Pass and/or reject everything one line holds in quarantine.

        Raises:
            ResourceNotFoundError: If the line is not this firm's.
            ValidationError: If it is not waiting, the two quantities do not
                add up to what is held, or a rejection names no action.

        """
        line = self._session.get(GoodsReceiptLine, line_id)
        receipt = self._session.get(GoodsReceipt, receipt_id)
        if (
            line is None
            or receipt is None
            or line.is_deleted
            or line.goods_receipt_id != receipt_id
            or receipt.firm_id != firm_id
        ):
            raise ResourceNotFoundError("Goods receipt line not found.")
        if line.inspection_status != "PENDING":
            raise ValidationError(
                f"Line {line.line_number} of {receipt.grn_number} is not waiting "
                "for an inspection."
            )
        held = Decimal(str(line.inspection_quantity or ZERO))
        if passed_quantity + rejected_quantity != held:
            raise ValidationError(
                f"Line {line.line_number} holds {held.normalize():f}; passed and "
                f"rejected together must come to that, not "
                f"{(passed_quantity + rejected_quantity).normalize():f}."
            )
        if rejected_quantity > ZERO and rejected_action is None:
            raise ValidationError(
                "Say what happens to the rejected goods: write them off, or "
                "keep them for a return to the supplier."
            )
        inventory = InventoryService(self._session)
        on = firm_today(self._session, firm_id)
        released = passed_quantity + (
            rejected_quantity if rejected_action == "WRITE_OFF" else ZERO
        )
        if released > ZERO:
            inventory.stage_quarantine(
                StockQuarantineCreate(
                    branch_id=receipt.branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    batch_id=line.batch_id,
                    action=QuarantineAction.RELEASE,
                    quantity=released,
                    reference_number=f"{receipt.grn_number}-QC{line.line_number}-R",
                    transaction_date=on,
                    remarks=f"Inspected: {receipt.grn_number}",
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
            )
        line.inspection_status = "DONE"
        line.inspection_passed_quantity = passed_quantity
        line.inspection_rejected_quantity = rejected_quantity
        line.inspection_rejected_action = (
            rejected_action if rejected_quantity > ZERO else None
        )
        line.inspected_at = utc_now()
        line.inspected_by = actor_id
        line.inspection_remarks = remarks
        line.updated_by = actor_id
        record_audit(
            self._session,
            action="goods_receipt.inspected",
            entity_type="goods_receipt_line",
            entity_id=line.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "grn_number": receipt.grn_number,
                "line_number": line.line_number,
                "passed_quantity": str(passed_quantity),
                "rejected_quantity": str(rejected_quantity),
                "rejected_action": line.inspection_rejected_action,
            },
        )
        if rejected_quantity > ZERO and rejected_action == "WRITE_OFF":
            # Posts the loss and commits everything above with it.
            inventory.write_off_stock(
                StockWriteOffCreate(
                    branch_id=receipt.branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    batch_id=line.batch_id,
                    reason=WriteOffReason.DAMAGE,
                    quantity=rejected_quantity,
                    reference_number=f"{receipt.grn_number}-QC{line.line_number}-W",
                    transaction_date=on,
                    remarks=f"Failed inspection: {receipt.grn_number}"
                    + (f" -- {remarks}" if remarks else ""),
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
            )
        else:
            self._session.commit()
        suppliers = vendor_names(self._session, [receipt.vendor_id])
        product = self._session.get(Product, line.product_id)
        return self._row(
            line, receipt, suppliers, {product.id: product} if product else {}
        )

    @staticmethod
    def _row(
        line: GoodsReceiptLine,
        receipt: GoodsReceipt,
        suppliers: dict[UUID, str],
        products: dict[UUID, Product],
    ) -> InspectionRow:
        """Build one inspection row."""
        product = products.get(line.product_id)
        return InspectionRow(
            goods_receipt_id=receipt.id,
            grn_number=receipt.grn_number,
            receipt_date=receipt.receipt_date,
            vendor_id=receipt.vendor_id,
            vendor_name=suppliers.get(receipt.vendor_id, ""),
            line_id=line.id,
            line_number=line.line_number,
            product_id=line.product_id,
            product_code=product.code if product else "",
            product_name=product.name if product else "",
            batch_number=line.batch_number,
            warehouse_id=line.warehouse_id,
            quantity=Decimal(str(line.inspection_quantity or ZERO)),
            status=line.inspection_status or "",
            passed_quantity=line.inspection_passed_quantity,
            rejected_quantity=line.inspection_rejected_quantity,
            rejected_action=line.inspection_rejected_action,
            inspected_at=line.inspected_at,
            remarks=line.inspection_remarks,
        )
