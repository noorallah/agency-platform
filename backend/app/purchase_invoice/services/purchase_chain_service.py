"""Raise the buying documents a firm has chosen not to type itself.

The chain is purchase order, goods receipt, supplier bill, and a firm decides
per stage which of them its people fill in (`purchase_workflow_settings`,
backlog §38). This is what fills in the rest: a bill arriving with bare product
lines is turned into an order and a receipt and then the bill, and a bill
arriving against an order is given the receipt that order never got.

Three things it deliberately does not do, each the buying twin of
`SalesChainService`:

* It does not move stock or post to the ledger. It drives the same services a
  person would, so goods still arrive at the goods receipt and the accrual
  still passes through goods received not invoiced.
* It does not complete the receipt. The receipt it raises is left a draft, and
  the bill's own approval completes it: a draft bill is a proposal, and a
  proposal must not put stock on the shelf. Cancelling the draft bill cancels
  the receipt (and the order it raised), and nothing has to be reversed.
* It never commits. Everything it stages belongs to the caller's transaction,
  so a bill that fails leaves no order and no receipt behind it.

The order it raises is submitted and approved by the bill. Approval stays a
control wherever a person raises the order; here nobody would ever see the
order, and the bill's approval is the decision.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate, GoodsReceiptLineWrite
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.products.models import Product
from app.purchase.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseWorkflowSettings,
)
from app.purchase.schemas import PurchaseLineWrite, PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
    PurchaseInvoiceSourceWrite,
)
from app.uom.services import UomService, buying_units_of

ZERO = Decimal("0")
_QUANTUM = Decimal("0.0001")


class PurchaseChainService:
    """Synthesise the buying documents a firm's configuration skips."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        #: What this call raised for the bill, and only that. The bill stamps
        #: itself on them once it exists; only it may bill a draft receipt,
        #: complete it on approval, or withdraw both when a draft is cancelled.
        self.raised_receipts: list[GoodsReceipt] = []
        self.raised_orders: list[PurchaseOrder] = []

    def ensure_invoice_source(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseInvoiceCreate:
        """Return a bill payload whose every line names a goods-receipt line.

        Unchanged for a firm on the whole chain, which is every firm until one
        switches a stage off: the product-line and order-sourced paths below
        are the only ones that write anything.
        """
        settings = PurchaseWorkflowService(self._session).settings_for(firm_id)
        bare = [line for line in data.lines if line.source_document_line_id is None]
        if not bare:
            if settings.goods_receipt_stage:
                return data
            return self._receipt_for_order(data, firm_id=firm_id, actor_id=actor_id)
        if len(bare) != len(data.lines):
            raise ValidationError(
                "A bill lists either the goods receipts it bills or products, "
                "never a mixture of the two."
            )
        return self._order_and_receipt(
            data, firm_id=firm_id, actor_id=actor_id, settings=settings
        )

    def _order_and_receipt(
        self,
        data: PurchaseInvoiceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        settings: PurchaseWorkflowSettings,
    ) -> PurchaseInvoiceCreate:
        """Raise the order and the receipt a bill of products implies."""
        if settings.purchase_order_stage or settings.goods_receipt_stage:
            raise ValidationError(
                "This firm raises a purchase order and a goods receipt before "
                "it records the supplier's bill, so each bill line must name "
                "the goods receipt it bills."
            )
        if data.vendor_id is None:
            raise ValidationError("A bill of products must name the supplier.")
        branch_id, warehouse_id = self._resolve_place(
            firm_id=firm_id,
            branch_id=data.branch_id or settings.default_branch_id,
            configured_warehouse_id=settings.default_warehouse_id,
        )
        prices = self._purchase_prices(
            data.lines, firm_id=firm_id, on=data.invoice_date
        )
        orders = PurchaseService(self._session)
        order = orders.stage_order(
            PurchaseOrderCreate(
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                vendor_id=data.vendor_id,
                purchase_date=data.invoice_date,
                payment_terms=data.payment_terms,
                currency_code=data.currency_code,
                exchange_rate=data.exchange_rate,
                reference_number=data.supplier_invoice_number,
                remarks=data.remarks,
                lines=[
                    PurchaseLineWrite(
                        product_id=self._product_of(line),
                        purchase_uom_id=line.invoice_uom_id or line.purchase_uom_id,
                        ordered_quantity=line.current_invoice_quantity,
                        free_quantity=line.free_quantity or ZERO,
                        unit_price=(
                            line.unit_price
                            if line.unit_price is not None
                            else prices[index]
                        ),
                        discount_percent=line.discount_percent or ZERO,
                        discount_amount=line.discount_amount or ZERO,
                        tax_profile_id=line.tax_profile_id,
                        manufacturing_date=line.manufacturing_date,
                        expiry_date=line.expiry_date,
                        warehouse_id=line.warehouse_id or warehouse_id,
                        storage_node_id=line.storage_node_id,
                        remarks=line.remarks,
                    )
                    for index, line in enumerate(data.lines)
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
            check_quantities=False,
        )
        orders.stage_submit(order.id, firm_scope=firm_id, actor_id=actor_id)
        # Nobody typed this order, so no approval limit governs it (68 row 4).
        orders.stage_approval(
            order.id, firm_scope=firm_id, actor_id=actor_id, enforce_limit=False
        )
        self.raised_orders.append(order)
        order_lines = self._order_lines(order.id)
        # The order's lines were written one per bill line, in the bill's
        # order, so position is what pairs them.
        pairs = list(zip(order_lines, data.lines, strict=True))
        return self._raise_and_rebind(
            data,
            order=order,
            pairs=pairs,
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def _receipt_for_order(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseInvoiceCreate:
        """Receive the order a bill names, for a firm that types no receipts.

        The order is the firm's own document here -- somebody raised and
        approved it -- so only the receipt is missing, and it brings in
        exactly what the bill charges for.
        """
        order_ids = {
            line.source_document_id
            for line in data.lines
            if line.source_document_type == PurchaseInvoiceSourceType.PURCHASE_ORDER
        }
        if not order_ids:
            return data
        if len(order_ids) > 1 or len(order_ids) != len(
            {line.source_document_id for line in data.lines}
        ):
            raise ValidationError(
                "A bill that receives its own goods bills one purchase order "
                "at a time."
            )
        order = self._session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == order_ids.pop(),
                PurchaseOrder.firm_id == firm_id,
                PurchaseOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Purchase order not found.")
        by_id = {line.id: line for line in self._order_lines(order.id)}
        pairs: list[tuple[PurchaseOrderLine, PurchaseInvoiceLineWrite]] = []
        for line in data.lines:
            order_line = (
                by_id.get(line.source_document_line_id)
                if line.source_document_line_id is not None
                else None
            )
            if order_line is None:
                raise ValidationError(
                    f"Line {line.line_number} names a line that is not on "
                    f"{order.po_number}."
                )
            if line.invoice_uom_id not in (None, order_line.purchase_uom_id):
                # The receipt counts in the order's unit; a bill line in
                # another one would receive the wrong quantity.
                raise ValidationError(
                    f"Line {line.line_number} bills in a different unit from "
                    f"{order.po_number}. Bill it in the order's unit."
                )
            pairs.append((order_line, line))
        return self._raise_and_rebind(
            data, order=order, pairs=pairs, firm_id=firm_id, actor_id=actor_id
        )

    def _raise_and_rebind(
        self,
        data: PurchaseInvoiceCreate,
        *,
        order: PurchaseOrder,
        pairs: list[tuple[PurchaseOrderLine, PurchaseInvoiceLineWrite]],
        firm_id: UUID,
        actor_id: UUID,
    ) -> PurchaseInvoiceCreate:
        """Raise the receipt as a draft, then bill it instead.

        The receipt takes the deal off the persisted order line -- price and
        discount -- so the two documents cannot disagree about what was agreed,
        and the batch and dates off the bill line, which is the only place a
        one-person firm types them.
        """
        receipt = GoodsReceiptService(self._session).stage_receipt(
            GoodsReceiptCreate(
                purchase_order_id=order.id,
                receipt_date=data.invoice_date,
                invoice_reference=data.supplier_invoice_number,
                remarks=data.remarks,
                lines=[
                    self._receipt_line(order_line, bill_line)
                    for order_line, bill_line in pairs
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.raised_receipts.append(receipt)
        receipt_lines = {
            line.purchase_order_line_id: line
            for line in self._session.scalars(
                select(GoodsReceiptLine).where(
                    GoodsReceiptLine.goods_receipt_id == receipt.id,
                    GoodsReceiptLine.is_deleted.is_(False),
                )
            ).all()
        }
        lines = [
            bill_line.model_copy(
                update={
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                    "source_document_line_id": receipt_lines[order_line.id].id,
                    "product_id": None,
                    "free_quantity": None,
                    "invoice_uom_id": order_line.purchase_uom_id,
                    "purchase_uom_id": None,
                }
            )
            for order_line, bill_line in pairs
        ]
        return data.model_copy(
            update={
                "source_documents": [
                    PurchaseInvoiceSourceWrite(
                        source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                        source_document_id=receipt.id,
                    )
                ],
                "lines": lines,
            }
        )

    @staticmethod
    def _receipt_line(
        order_line: PurchaseOrderLine, bill_line: PurchaseInvoiceLineWrite
    ) -> GoodsReceiptLineWrite:
        """Receive one order line, carrying the deal the order already struck.

        A discount stated as an amount on the order is for the whole ordered
        quantity, so receiving part of it takes the matching share.
        """
        quantity = bill_line.current_invoice_quantity
        discount_amount = order_line.discount_amount
        if (
            discount_amount > ZERO
            and order_line.ordered_quantity > ZERO
            and quantity != order_line.ordered_quantity
        ):
            discount_amount = (
                discount_amount * quantity / order_line.ordered_quantity
            ).quantize(_QUANTUM)
        free = (
            bill_line.free_quantity
            if bill_line.free_quantity is not None
            else order_line.free_quantity
        )
        return GoodsReceiptLineWrite(
            purchase_order_line_id=order_line.id,
            line_number=order_line.line_number,
            description=order_line.description,
            current_receipt_quantity=quantity,
            free_quantity=free,
            unit_price=order_line.unit_price,
            discount_percent=order_line.discount_percent,
            discount_amount=discount_amount,
            tax_profile_id=order_line.tax_profile_id,
            purchase_uom_id=order_line.purchase_uom_id,
            inventory_uom_id=order_line.inventory_uom_id,
            warehouse_id=order_line.warehouse_id,
            storage_node_id=order_line.storage_node_id,
            batch_number=bill_line.batch_number,
            expiry_date=bill_line.expiry_date or order_line.expiry_date,
            manufacturing_date=(
                bill_line.manufacturing_date or order_line.manufacturing_date
            ),
            remarks=bill_line.remarks,
        )

    def _order_lines(self, order_id: UUID) -> list[PurchaseOrderLine]:
        """Return an order's live lines in their order."""
        return list(
            self._session.scalars(
                select(PurchaseOrderLine)
                .where(
                    PurchaseOrderLine.purchase_order_id == order_id,
                    PurchaseOrderLine.is_deleted.is_(False),
                )
                .order_by(PurchaseOrderLine.line_number.asc())
            ).all()
        )

    def _purchase_prices(
        self, lines: list[PurchaseInvoiceLineWrite], *, firm_id: UUID, on: date
    ) -> list[Decimal]:
        """Return the price each line starts at if it names none, in order.

        The product's standing purchase price **in the unit the line is
        billed in**. That price is per stock unit, and the order raised
        behind the bill counts the line in the unit it names, else the
        product's buying unit: a bill of 2 with no price, for a product
        bought by the box of 12 at 60.00 a piece, was charged 60.00 a box --
        120.00 for 24 pieces. It is 720.00 a box, at the factor the order
        line converts with.
        """
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_({self._product_of(line) for line in lines})
                )
            ).all()
        }
        units = UomService(self._session)
        prices: list[Decimal] = []
        for line in lines:
            product = products.get(self._product_of(line))
            if product is None or line.unit_price is not None:
                prices.append(ZERO)
                continue
            unit, stock_unit = buying_units_of(
                product,
                unit=line.invoice_uom_id
                or line.purchase_uom_id
                or product.purchase_uom_id,
                stock_unit=None,
            )
            factor = units.unit_factor(
                product_id=product.id,
                from_uom_id=unit,
                to_uom_id=stock_unit,
                on_date=on,
                firm_scope=firm_id,
            )
            prices.append(
                ((product.purchase_price or ZERO) * factor).quantize(_QUANTUM)
            )
        return prices

    @staticmethod
    def _product_of(line: PurchaseInvoiceLineWrite) -> UUID:
        """Return the product a bare line names."""
        if line.product_id is None:
            raise ValidationError(
                f"Line {line.line_number} names neither a goods receipt nor a "
                "product."
            )
        return line.product_id

    def _resolve_place(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID | None,
        configured_warehouse_id: UUID | None,
    ) -> tuple[UUID, UUID]:
        """Decide where a synthesised receipt puts the goods.

        The request wins, then the firm's configured defaults, then the branch
        and warehouse the firm marked default. Receiving refuses a line with no
        warehouse, and a firm on automatic never sees a field to type one into
        -- so failing here, by name, beats failing at approval with a sentence
        about a receipt nobody saw. The configured warehouse counts only inside
        the chosen branch, as on the sales side (D-CFG-14).
        """
        if branch_id is None:
            branch_id = self._session.scalar(
                select(Branch.id).where(
                    Branch.firm_id == firm_id,
                    Branch.is_default.is_(True),
                    Branch.is_deleted.is_(False),
                )
            )
        if branch_id is None:
            raise ValidationError(
                "This firm has no default branch, so a bill cannot decide where "
                "its goods are received."
            )
        warehouse_id: UUID | None = None
        if configured_warehouse_id is not None:
            warehouse_id = self._session.scalar(
                select(Warehouse.id).where(
                    Warehouse.id == configured_warehouse_id,
                    Warehouse.branch_id == branch_id,
                    Warehouse.is_deleted.is_(False),
                )
            )
        if warehouse_id is None:
            warehouse_id = self._session.scalar(
                select(Warehouse.id).where(
                    Warehouse.branch_id == branch_id,
                    Warehouse.is_default.is_(True),
                    Warehouse.is_deleted.is_(False),
                )
            )
        if warehouse_id is None:
            raise ValidationError(
                "This branch has no default warehouse, so a bill cannot decide "
                "where its goods are received."
            )
        return branch_id, warehouse_id
