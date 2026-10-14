"""A supplier's bill at another rate than its receipt, onto the lot (L2 step 8).

A firm costing by lot took the goods into a lot at the receipt's cost. When
the supplier's bill charges another rate, the share of the difference for
the units still in the lot corrects the lot -- Dr or Cr Inventory -- and the
share for units already gone stays purchase price variance, as all of it
does on Average (`docs/design/LOT_COST_DESIGN.md`, section 3.3, decision 3).

The correction is a ``COST_CORRECTION`` movement on the lot, dated the bill,
with no quantity. Cancelling the bill takes back what the lot still holds of
it; what left with units sold since stays where those units took it, and the
reversal sends it to variance. Nothing here touches a firm on Average.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utils.money import ZERO, quantize_ledger
from app.finance.currency import is_foreign
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.inventory.schemas import InventoryTransactionType
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.lots import costs_by_lot
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine

#: The movements a bill's approval wrote, and the ones its cancel wrote.
CORRECTED = "PURCHASE_INVOICE"
TAKEN_BACK = "PURCHASE_INVOICE_CANCEL"


def stage_bill_rate_onto_lots(
    session: Session, row: PurchaseInvoice, *, firm_id: UUID, actor_id: UUID
) -> Decimal:
    """Put each bill line's rate difference onto its lot; return the total.

    Per bill line raised off a receipt line whose lot is valued: the
    receipt's cost for the units billed is that line's movement cost pro
    rata by quantity, as the accrual clears it; the bill's value is the
    line's net before tax, in rupees. The difference, times the share of the
    receipt line's units the lot still holds, goes onto the lot. A lot is
    never taken below nothing. Stages only; the caller posts and commits.
    """
    if not costs_by_lot(session, firm_id):
        return ZERO
    rate = (
        row.exchange_rate
        if is_foreign(row.currency_code) and row.exchange_rate is not None
        else Decimal("1")
    )
    pairs = session.execute(
        select(PurchaseInvoiceLine, GoodsReceiptLine, GoodsReceipt)
        .join(
            GoodsReceiptLine,
            GoodsReceiptLine.id == PurchaseInvoiceLine.source_document_line_id,
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .where(
            PurchaseInvoiceLine.purchase_invoice_id == row.id,
            PurchaseInvoiceLine.is_deleted.is_(False),
            PurchaseInvoiceLine.is_capital_goods.is_(False),
            GoodsReceiptLine.batch_id.is_not(None),
            GoodsReceiptLine.inventory_transaction_id.is_not(None),
        )
        .order_by(PurchaseInvoiceLine.line_number)
    ).all()
    if not pairs:
        return ZERO
    costs: dict[UUID, Decimal] = {
        transaction_id: Decimal(str(cost))
        for transaction_id, cost in session.execute(
            select(
                StockLedgerEntry.transaction_id,
                func.coalesce(func.sum(StockLedgerEntry.total_cost), 0),
            )
            .where(
                StockLedgerEntry.transaction_id.in_(
                    [
                        receipt_line.inventory_transaction_id
                        for _, receipt_line, _ in pairs
                    ]
                )
            )
            .group_by(StockLedgerEntry.transaction_id)
        ).all()
    }
    inventory = InventoryService(session)
    total = ZERO
    for line, receipt_line, receipt in pairs:
        in_lot = inventory.lot_on_hand(
            firm_scope=firm_id,
            product_id=receipt_line.product_id,
            batch_id=receipt_line.batch_id,
        )
        accepted = Decimal(str(receipt_line.accepted_quantity or 0))
        billed = Decimal(str(line.current_invoice_quantity or 0))
        if in_lot is None or in_lot <= ZERO or accepted <= ZERO or billed <= ZERO:
            continue
        counted = min(billed, accepted)
        value = (
            (Decimal(str(line.net_amount)) - Decimal(str(line.tax_amount)))
            * rate
            * counted
            / billed
        )
        cost = costs.get(receipt_line.inventory_transaction_id, ZERO)
        difference = value - cost * counted / accepted
        factor = Decimal(str(receipt_line.conversion_factor or 1))
        received = (accepted + Decimal(str(receipt_line.free_quantity or 0))) * factor
        held = quantize_ledger(difference * min(in_lot, received) / received)
        if held < ZERO:
            lot_value = inventory.value_of_lot(receipt_line.batch_id)
            held = max(held, -quantize_ledger(lot_value))
        if held == ZERO:
            continue
        inventory.stage_revaluation(
            firm_scope=firm_id,
            branch_id=receipt.branch_id,
            warehouse_id=receipt_line.warehouse_id,
            product_id=receipt_line.product_id,
            batch_id=receipt_line.batch_id,
            amount=held,
            reference_number=row.invoice_number,
            transaction_date=row.invoice_date,
            remarks=f"Bill rate on {row.invoice_number}, receipt {receipt.grn_number}",
            actor_id=actor_id,
            transaction_type=InventoryTransactionType.COST_CORRECTION,
            reference_type=CORRECTED,
        )
        total += held
    return total


def take_bill_rate_off_lots(
    session: Session, row: PurchaseInvoice, *, firm_id: UUID, actor_id: UUID
) -> tuple[Decimal, Decimal]:
    """Take a cancelled bill's corrections back off its lots.

    Returns ``(corrected, taken back)``: what the approval put onto lots and
    what came off them now, which is less where units have left since. The
    caller reverses the journal at the second and sends the gap to variance.
    Stages only.
    """
    moved = session.execute(
        select(InventoryTransaction, StockLedgerEntry)
        .join(
            StockLedgerEntry, StockLedgerEntry.transaction_id == InventoryTransaction.id
        )
        .where(
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.transaction_type
            == InventoryTransactionType.COST_CORRECTION.value,
            InventoryTransaction.reference_type == CORRECTED,
            InventoryTransaction.reference_number == row.invoice_number,
        )
        .order_by(InventoryTransaction.created_at)
    ).all()
    inventory = InventoryService(session)
    corrected = taken = ZERO
    for movement, entry in moved:
        corrected += Decimal(str(entry.total_cost or 0))
        left = inventory.value_left_in_lot(movement.id)
        back = quantize_ledger(left) if left is not None else ZERO
        if back == ZERO:
            continue
        inventory.stage_revaluation(
            firm_scope=firm_id,
            branch_id=movement.branch_id,
            warehouse_id=movement.warehouse_id,
            product_id=movement.product_id,
            batch_id=movement.batch_id,
            amount=-back,
            reference_number=row.invoice_number,
            transaction_date=row.invoice_date,
            remarks=f"Bill {row.invoice_number} cancelled",
            actor_id=actor_id,
            transaction_type=InventoryTransactionType.COST_CORRECTION,
            reference_type=TAKEN_BACK,
        )
        taken += back
    return corrected, taken
