"""Purchase price variance: where a bill's rate differs from its receipt's (65.5).

Goods are valued into stock at the receipt's rate; when the supplier's bill
charges a different rate the difference posts to Purchase Price Variance and
is otherwise seen only as one P&L line. This lists it bill line by bill line
-- supplier, product, the two rates, the quantity billed and the variance --
so a buyer can take it up with the supplier.

The rates compared are the lines' own unit prices before discount, in the
unit each line was entered in; a bill entered in another unit than its
receipt is flagged rather than compared.

The bill's own screen asks the same question of one bill (65 row 5), through
the same method with ``purchase_invoice_id``: one answer, so the screen and
the report cannot disagree. A bill asked about by id is answered whatever its
status, because a draft is exactly when a buyer can still query the rate.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination.reports import ReportWindow
from app.goods_receipt.models import GoodsReceiptLine
from app.products.models import Product
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.vendors.models import Vendor

BILLED = ("APPROVED", "CLOSED")


@dataclass(frozen=True)
class PriceVarianceRow:
    """One bill line whose rate is not its receipt's."""

    invoice_date: date
    invoice_number: str
    line_number: int
    supplier_invoice_number: str
    supplier_name: str
    receipt_number: str
    product_code: str
    product_name: str
    quantity: Decimal
    receipt_rate: Decimal
    bill_rate: Decimal
    #: (bill rate - receipt rate) x quantity: positive when billed dearer.
    variance: Decimal
    #: Set when the bill and the receipt were entered in different units, so
    #: the two rates are not comparable as they stand.
    note: str


class PriceVarianceService:
    """List bill lines charged at a rate other than the receipt's."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def report(
        self,
        firm_id: UUID,
        window: ReportWindow,
        *,
        purchase_invoice_id: UUID | None = None,
    ) -> list[PriceVarianceRow]:
        """Return every approved or closed bill line in the window with a variance.

        With ``purchase_invoice_id``, that one bill's lines, in any status.
        """
        scoped = (
            [PurchaseInvoice.id == purchase_invoice_id]
            if purchase_invoice_id is not None
            else [PurchaseInvoice.status.in_(BILLED)]
        )
        rows = self._session.execute(
            select(
                PurchaseInvoice,
                PurchaseInvoiceLine,
                GoodsReceiptLine,
                Vendor.name,
                Product.code,
                Product.name,
            )
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
            )
            .join(
                GoodsReceiptLine,
                GoodsReceiptLine.id == PurchaseInvoiceLine.source_document_line_id,
            )
            .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .join(Product, Product.id == PurchaseInvoiceLine.product_id)
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                *scoped,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.source_document_type == "GOODS_RECEIPT",
                *window.dated(PurchaseInvoice.invoice_date),
            )
            .order_by(
                PurchaseInvoice.invoice_date,
                PurchaseInvoice.invoice_number,
                PurchaseInvoiceLine.line_number,
            )
        ).all()
        result: list[PriceVarianceRow] = []
        for bill, line, receipt_line, supplier, code, name in rows:
            bill_rate = Decimal(str(line.unit_price))
            receipt_rate = Decimal(str(receipt_line.unit_price))
            bill_unit = line.purchase_uom_id
            receipt_unit = receipt_line.purchase_uom_id
            different_units = (
                bill_unit is not None
                and receipt_unit is not None
                and bill_unit != receipt_unit
            )
            if bill_rate == receipt_rate and not different_units:
                continue
            quantity = Decimal(str(line.current_invoice_quantity))
            result.append(
                PriceVarianceRow(
                    invoice_date=bill.invoice_date,
                    invoice_number=bill.invoice_number,
                    line_number=line.line_number,
                    supplier_invoice_number=bill.supplier_invoice_number,
                    supplier_name=supplier,
                    receipt_number=line.source_document_number,
                    product_code=code,
                    product_name=name,
                    quantity=quantity,
                    receipt_rate=receipt_rate,
                    bill_rate=bill_rate,
                    variance=(
                        Decimal("0")
                        if different_units
                        else ((bill_rate - receipt_rate) * quantity).quantize(
                            Decimal("0.01")
                        )
                    ),
                    note=(
                        "Billed in another unit than received; compare by hand."
                        if different_units
                        else ""
                    ),
                )
            )
        return result
