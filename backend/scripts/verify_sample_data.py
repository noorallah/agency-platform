"""Verify enterprise sample data integrity and business consistency."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from sqlalchemy import func, select

from app.api.dependencies.settings import get_settings
from app.core.database.engine import DatabaseManager
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.document_framework.models import DocumentLifecycleEvent
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.models import InventoryRecord, InventoryTransaction, StockLedgerEntry
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoiceSource
from app.sales_invoice.models import SalesInvoiceSource
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.uom.models import ConversionRule, PackagingType, ProductUomConfig, Uom


def _check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> None:
    settings = get_settings()
    database = DatabaseManager.from_settings(settings)
    errors: list[str] = []
    checks = Counter[str]()
    try:
        with database.sessions().session() as session:
            firms = session.scalars(
                select(Firm).where(Firm.is_deleted.is_(False))
            ).all()
            _check(errors, len(firms) == 1, "Expected exactly one seeded firm.")
            if firms:
                _check(
                    errors, firms[0].code == "NAVK_CPL", "Expected firm code NAVK_CPL."
                )
                checks["firm"] += 1

            required_counts = {
                "uoms": select(func.count()).select_from(Uom),
                "packaging_types": select(func.count()).select_from(PackagingType),
                "uom_conversion_rules": select(func.count()).select_from(
                    ConversionRule
                ),
                "product_uom_configs": select(func.count()).select_from(
                    ProductUomConfig
                ),
                "purchase_orders": select(func.count()).select_from(PurchaseOrder),
                "goods_receipts": select(func.count()).select_from(GoodsReceipt),
                "sales_orders": select(func.count()).select_from(SalesOrder),
                "delivery_notes": select(func.count()).select_from(DeliveryNote),
                "inventory_transactions": select(func.count()).select_from(
                    InventoryTransaction
                ),
                "document_lifecycle_events": select(func.count()).select_from(
                    DocumentLifecycleEvent
                ),
            }
            for key, stmt in required_counts.items():
                value = int(session.scalar(stmt) or 0)
                _check(errors, value > 0, f"Expected {key} to have seeded records.")
                checks[key] = value

            status_values: set[str] = set()
            for model in (PurchaseOrder, GoodsReceipt, SalesOrder, DeliveryNote):
                values = session.scalars(select(model.status).distinct()).all()
                status_values.update(str(item).upper() for item in values)
            expected_lifecycle = {
                "DRAFT",
                "APPROVED",
                "COMPLETED",
                "CANCELLED",
                "CLOSED",
            }
            _check(
                errors,
                expected_lifecycle.issubset(status_values),
                "Lifecycle coverage missing one of Draft/Approved/Completed/Cancelled/Closed.",
            )
            checks["status_values"] = len(status_values)

            po_number = "PO/NVK/2026/0001"
            po_id = session.scalar(
                select(PurchaseOrder.id).where(PurchaseOrder.po_number == po_number)
            )
            _check(errors, po_id is not None, "Missing PO/NVK/2026/0001.")
            if po_id is not None:
                ordered_qty = session.scalar(
                    select(
                        func.coalesce(func.sum(PurchaseOrderLine.ordered_quantity), 0)
                    ).where(PurchaseOrderLine.purchase_order_id == po_id)
                ) or Decimal("0")
                received_qty = session.scalar(
                    select(
                        func.coalesce(
                            func.sum(GoodsReceiptLine.current_receipt_quantity), 0
                        )
                    )
                    .join(
                        GoodsReceipt,
                        GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id,
                    )
                    .where(
                        GoodsReceipt.purchase_order_id == po_id,
                        GoodsReceipt.status == "COMPLETED",
                    )
                ) or Decimal("0")
                _check(
                    errors,
                    received_qty < ordered_qty,
                    "Expected partial receipt against PO/NVK/2026/0001.",
                )
                checks["po_partial_receipt"] += 1

            so_number = "SO/NVK/2026/0001"
            so_id = session.scalar(
                select(SalesOrder.id).where(SalesOrder.order_number == so_number)
            )
            _check(errors, so_id is not None, "Missing SO/NVK/2026/0001.")
            if so_id is not None:
                ordered_qty = session.scalar(
                    select(func.coalesce(func.sum(SalesOrderLine.quantity), 0)).where(
                        SalesOrderLine.sales_order_id == so_id
                    )
                ) or Decimal("0")
                delivered_qty = session.scalar(
                    select(
                        func.coalesce(
                            func.sum(DeliveryNoteLine.current_delivery_quantity), 0
                        )
                    )
                    .join(
                        DeliveryNote,
                        DeliveryNote.id == DeliveryNoteLine.delivery_note_id,
                    )
                    .where(
                        DeliveryNote.sales_order_id == so_id,
                        DeliveryNote.status == "COMPLETED",
                    )
                ) or Decimal("0")
                _check(
                    errors,
                    delivered_qty < ordered_qty,
                    "Expected partial delivery against SO/NVK/2026/0001.",
                )
                checks["so_partial_delivery"] += 1

            grn_id = session.scalar(
                select(GoodsReceipt.id).where(
                    GoodsReceipt.grn_number == "GRN/NVK/2026/0001"
                )
            )
            if grn_id is not None:
                invoice_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(PurchaseInvoiceSource)
                        .where(
                            PurchaseInvoiceSource.source_document_type
                            == "GOODS_RECEIPT",
                            PurchaseInvoiceSource.source_document_id == grn_id,
                        )
                    )
                    or 0
                )
                _check(
                    errors,
                    invoice_count >= 2,
                    "Expected multiple purchase invoices linked to GRN/NVK/2026/0001.",
                )
                checks["multi_purchase_invoice"] = invoice_count

            dn_id = session.scalar(
                select(DeliveryNote.id).where(
                    DeliveryNote.delivery_note_number == "DN/NVK/2026/0001"
                )
            )
            if dn_id is not None:
                invoice_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(SalesInvoiceSource)
                        .where(
                            SalesInvoiceSource.source_document_type == "DELIVERY_NOTE",
                            SalesInvoiceSource.source_document_id == dn_id,
                        )
                    )
                    or 0
                )
                _check(
                    errors,
                    invoice_count >= 2,
                    "Expected multiple sales invoices linked to DN/NVK/2026/0001.",
                )
                checks["multi_sales_invoice"] = invoice_count

            inventory_ids = session.scalars(select(InventoryRecord.id)).all()
            for inventory_id in inventory_ids:
                tx_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(InventoryTransaction)
                        .where(InventoryTransaction.inventory_id == inventory_id)
                    )
                    or 0
                )
                ledger_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(StockLedgerEntry)
                        .where(StockLedgerEntry.inventory_id == inventory_id)
                    )
                    or 0
                )
                _check(
                    errors,
                    tx_count == ledger_count,
                    f"Inventory {inventory_id} transaction/ledger mismatch: {tx_count} vs {ledger_count}.",
                )
            checks["inventory_rows"] = len(inventory_ids)

    finally:
        database.dispose()

    if errors:
        print("Sample data verification failed:")
        for item in errors:
            print(f"- {item}")
        raise SystemExit(1)

    print("Sample data verification passed.")
    for key, value in sorted(checks.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
