"""Landed cost vouchers (BUY-16, decision A129).

Freight, loading and clearing paid to a third party belong in what the goods
cost, or every margin on them reads too high. The way Zoho and ERPNext do it:

* the charge's own bill is booked to *Expenses Included in Valuation*, an
  expense the voucher empties;
* a voucher names completed goods receipts and lists the charges;
* the total is spread over the receipts' lines by value, quantity or weight;
* each line's share is split by how much of the product is still on hand:
  that part revalues the stock -- its moving average rises, with no quantity
  moving -- and the part already sold goes to cost of goods sold;
* the journal is Dr inventory and Dr cost of goods sold, Cr expenses included
  in valuation.

Cancelling reverses the journal and takes the on-hand value back off the
average. A receipt may carry several vouchers -- freight one week, the
clearing agent's bill the next.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO, quantize_money
from app.core.utils.pricing import apportion
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.services.inventory_service import InventoryService
from app.landed_costs.models import (
    LandedCostAllocation,
    LandedCostCharge,
    LandedCostVoucher,
)
from app.products.models import Product
from app.vendors.models import Vendor

BASES = ("VALUE", "QUANTITY", "WEIGHT")
_DONE = ("COMPLETED", "CLOSED")


class LandedCostChargeWrite(BaseModel):
    """One charge to spread."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    vendor_id: UUID | None = None
    bill_reference: str | None = Field(default=None, max_length=100)


class LandedCostWrite(BaseModel):
    """A voucher: the receipts it lands on, the charges and how to spread them."""

    model_config = ConfigDict(extra="forbid")

    voucher_date: date
    basis: str = Field(default="VALUE", pattern="^(VALUE|QUANTITY|WEIGHT)$")
    goods_receipt_ids: list[UUID] = Field(min_length=1, max_length=50)
    charges: list[LandedCostChargeWrite] = Field(min_length=1, max_length=20)
    remarks: str | None = Field(default=None, max_length=1000)


class LandedCostCancel(BaseModel):
    """Why a voucher is withdrawn."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class LandedCostChargeResponse(BaseModel):
    """One charge as posted."""

    model_config = ConfigDict(extra="forbid")

    line_number: int
    description: str
    amount: Decimal
    vendor_id: UUID | None
    vendor_name: str | None
    bill_reference: str | None


class LandedCostAllocationResponse(BaseModel):
    """What one receipt line carried."""

    model_config = ConfigDict(extra="forbid")

    goods_receipt_id: UUID
    grn_number: str
    goods_receipt_line_id: UUID
    product_id: UUID
    product_name: str
    quantity: Decimal
    basis_measure: Decimal
    amount: Decimal
    inventory_amount: Decimal
    cogs_amount: Decimal


class LandedCostResponse(BaseModel):
    """One voucher, its charges and its spread."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    voucher_number: str
    voucher_date: date
    basis: str
    total_amount: Decimal
    inventory_amount: Decimal
    cogs_amount: Decimal
    status: str
    remarks: str | None
    cancel_reason: str | None
    version: int
    charges: list[LandedCostChargeResponse]
    allocations: list[LandedCostAllocationResponse]


class LandedCostService(TransactionalDocumentService):
    """Post and cancel landed cost vouchers."""

    DOCUMENT = DocumentTypeSpec(
        code="LANDED_COST",
        name="Landed Cost Voucher",
        description="Freight and clearing added to the cost of received goods.",
        category="PURCHASE",
        module="landed_costs",
        prefix="LCV",
        rule_code="LANDED_COST_DEFAULT",
        rule_name="Landed Cost Default Numbering",
        states=(
            DocumentStateSpec("POSTED", "Posted", 10),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def post(
        self, data: LandedCostWrite, *, firm_id: UUID, actor_id: UUID
    ) -> LandedCostVoucher:
        """Spread the charges, revalue the stock, post the journal; commit.

        Raises:
            ValidationError: If a receipt is not the firm's completed one, a
                charge names a stranger, or the basis measures nothing.

        """
        receipts = self._receipts(data.goods_receipt_ids, firm_id)
        lines = list(
            self._session.scalars(
                select(GoodsReceiptLine)
                .where(
                    GoodsReceiptLine.goods_receipt_id.in_(list(receipts)),
                    GoodsReceiptLine.is_deleted.is_(False),
                )
                .order_by(
                    GoodsReceiptLine.goods_receipt_id, GoodsReceiptLine.line_number
                )
            ).all()
        )
        stocked = [(line, _stock_quantity(line)) for line in lines]
        stocked = [(line, quantity) for line, quantity in stocked if quantity > ZERO]
        if not stocked:
            raise ValidationError("Those receipts brought in no stock to carry a cost.")
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_({line.product_id for line, _ in stocked})
                )
            ).all()
        }
        measures = [
            _measure(data.basis, line, quantity, products.get(line.product_id))
            for line, quantity in stocked
        ]
        if not any(measure > ZERO for measure in measures):
            named = {"WEIGHT": "weight", "VALUE": "value", "QUANTITY": "quantity"}
            raise ValidationError(
                f"None of the received goods has a {named[data.basis]} to spread "
                "the cost by; choose another basis."
            )
        self._check_vendors(data.charges, firm_id)
        total = sum((charge.amount for charge in data.charges), ZERO)
        shares = apportion(total, measures)

        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=LandedCostVoucher.voucher_number,
            firm_id=firm_id,
            document_date=data.voucher_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        row = LandedCostVoucher(
            firm_id=firm_id,
            voucher_number=number,
            voucher_date=data.voucher_date,
            basis=data.basis,
            total_amount=total,
            status="POSTED",
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Landed cost voucher number already exists.")
        for line_number, charge in enumerate(data.charges, start=1):
            self._session.add(
                LandedCostCharge(
                    voucher_id=row.id,
                    firm_id=firm_id,
                    line_number=line_number,
                    description=charge.description,
                    amount=charge.amount,
                    vendor_id=charge.vendor_id,
                    bill_reference=charge.bill_reference,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

        inventory = InventoryService(self._session)
        # On hand is read once per product, before any line revalues it:
        # two lines of one product share what is left of it.
        left: dict[UUID, Decimal] = {}
        for line, _ in stocked:
            if line.product_id not in left:
                left[line.product_id] = Decimal(
                    str(
                        inventory.valuation_for(
                            firm_scope=firm_id, product_id=line.product_id
                        ).quantity_on_hand
                    )
                )
        held_total = sold_total = ZERO
        for (line, quantity), measure, share in zip(
            stocked, measures, shares, strict=True
        ):
            on_hand = max(min(left[line.product_id], quantity), ZERO)
            left[line.product_id] -= on_hand
            held = quantize_money(share * on_hand / quantity) if share else ZERO
            sold = share - held
            transaction_id: UUID | None = None
            if held > ZERO:
                receipt = receipts[line.goods_receipt_id]
                moved = inventory.stage_revaluation(
                    firm_scope=firm_id,
                    branch_id=receipt.branch_id,
                    warehouse_id=line.warehouse_id,
                    product_id=line.product_id,
                    batch_id=line.batch_id,
                    amount=held,
                    reference_number=number,
                    transaction_date=data.voucher_date,
                    remarks=f"Landed cost {number} on {receipt.grn_number}",
                    actor_id=actor_id,
                )
                transaction_id = moved.id
            self._session.add(
                LandedCostAllocation(
                    voucher_id=row.id,
                    firm_id=firm_id,
                    goods_receipt_id=line.goods_receipt_id,
                    goods_receipt_line_id=line.id,
                    product_id=line.product_id,
                    quantity=quantity,
                    basis_measure=measure,
                    amount=share,
                    inventory_amount=held,
                    cogs_amount=sold,
                    inventory_transaction_id=transaction_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            held_total += held
            sold_total += sold
        row.inventory_amount = held_total
        row.cogs_amount = sold_total
        entry = DocumentPostingService(self._session).post_landed_cost(
            firm_id=firm_id,
            voucher_id=row.id,
            reference_number=number,
            voucher_date=data.voucher_date,
            inventory_amount=held_total,
            cogs_amount=sold_total,
            actor_id=actor_id,
        )
        row.journal_entry_id = entry.id
        self._audit("landed_cost.posted", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self, voucher_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> LandedCostVoucher:
        """Reverse the journal and take the added value back off; commit.

        The on-hand share comes back off the product's value at today's
        quantity: what was sold since keeps the cost it was sold at.

        Raises:
            ValidationError: If already cancelled, or no reason is given.

        """
        row = self.get(voucher_id, firm_id=firm_id)
        if row.status != "POSTED":
            raise ValidationError("This voucher was already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the voucher is cancelled.")
        inventory = InventoryService(self._session)
        receipts = {
            receipt.id: receipt
            for receipt in self._session.scalars(
                select(GoodsReceipt).where(
                    GoodsReceipt.id.in_(
                        select(LandedCostAllocation.goods_receipt_id).where(
                            LandedCostAllocation.voucher_id == row.id
                        )
                    )
                )
            ).all()
        }
        for allocation in self._allocations([row.id]):
            held = Decimal(str(allocation.inventory_amount))
            if held <= ZERO:
                continue
            line = self._session.get(GoodsReceiptLine, allocation.goods_receipt_line_id)
            receipt = receipts[allocation.goods_receipt_id]
            if line is None:
                continue
            inventory.stage_revaluation(
                firm_scope=firm_id,
                branch_id=receipt.branch_id,
                warehouse_id=line.warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                amount=-held,
                reference_number=row.voucher_number,
                transaction_date=row.voucher_date,
                remarks=f"Landed cost {row.voucher_number} cancelled",
                actor_id=actor_id,
            )
        if row.journal_entry_id is not None:
            JournalEntryEngine(self._session).reverse_entry(
                row.journal_entry_id,
                firm_id=firm_id,
                reference_number=f"LCV-{row.voucher_number}-REV",
                actor_id=actor_id,
            )
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("landed_cost.cancelled", row, actor_id)
        self._session.commit()
        return row

    # ---- reads ---------------------------------------------------------

    def get(self, voucher_id: UUID, *, firm_id: UUID) -> LandedCostVoucher:
        """Return one of the firm's vouchers."""
        row = self._session.get(LandedCostVoucher, voucher_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Landed cost voucher not found.")
        return row

    def list_rows(self, firm_id: UUID) -> list[LandedCostVoucher]:
        """Return the firm's vouchers, newest first."""
        return list(
            self._session.scalars(
                select(LandedCostVoucher)
                .where(
                    LandedCostVoucher.firm_id == firm_id,
                    LandedCostVoucher.is_deleted.is_(False),
                )
                .order_by(
                    LandedCostVoucher.voucher_date.desc(),
                    LandedCostVoucher.voucher_number.desc(),
                    LandedCostVoucher.id.desc(),
                )
            ).all()
        )

    def responses(self, rows: list[LandedCostVoucher]) -> list[LandedCostResponse]:
        """Shape vouchers with their charges and spread, one read per table."""
        if not rows:
            return []
        ids = [row.id for row in rows]
        charges = list(
            self._session.scalars(
                select(LandedCostCharge)
                .where(
                    LandedCostCharge.voucher_id.in_(ids),
                    LandedCostCharge.is_deleted.is_(False),
                )
                .order_by(LandedCostCharge.line_number)
            ).all()
        )
        allocations = self._allocations(ids)
        vendor_ids = {c.vendor_id for c in charges if c.vendor_id is not None}
        vendors: dict[UUID, str] = (
            {
                vendor_id: name
                for vendor_id, name in self._session.execute(
                    select(Vendor.id, Vendor.name).where(Vendor.id.in_(vendor_ids))
                ).all()
            }
            if vendor_ids
            else {}
        )
        product_ids = {a.product_id for a in allocations}
        products: dict[UUID, str] = (
            {
                product_id: name
                for product_id, name in self._session.execute(
                    select(Product.id, Product.name).where(Product.id.in_(product_ids))
                ).all()
            }
            if product_ids
            else {}
        )
        receipt_ids = {a.goods_receipt_id for a in allocations}
        numbers: dict[UUID, str] = (
            {
                receipt_id: number
                for receipt_id, number in self._session.execute(
                    select(GoodsReceipt.id, GoodsReceipt.grn_number).where(
                        GoodsReceipt.id.in_(receipt_ids)
                    )
                ).all()
            }
            if receipt_ids
            else {}
        )
        return [
            LandedCostResponse(
                id=row.id,
                voucher_number=row.voucher_number,
                voucher_date=row.voucher_date,
                basis=row.basis,
                total_amount=row.total_amount,
                inventory_amount=row.inventory_amount,
                cogs_amount=row.cogs_amount,
                status=row.status,
                remarks=row.remarks,
                cancel_reason=row.cancel_reason,
                version=row.version,
                charges=[
                    LandedCostChargeResponse(
                        line_number=charge.line_number,
                        description=charge.description,
                        amount=charge.amount,
                        vendor_id=charge.vendor_id,
                        vendor_name=(
                            vendors.get(charge.vendor_id) if charge.vendor_id else None
                        ),
                        bill_reference=charge.bill_reference,
                    )
                    for charge in charges
                    if charge.voucher_id == row.id
                ],
                allocations=[
                    LandedCostAllocationResponse(
                        goods_receipt_id=allocation.goods_receipt_id,
                        grn_number=numbers.get(allocation.goods_receipt_id, ""),
                        goods_receipt_line_id=allocation.goods_receipt_line_id,
                        product_id=allocation.product_id,
                        product_name=products.get(allocation.product_id, ""),
                        quantity=allocation.quantity,
                        basis_measure=allocation.basis_measure,
                        amount=allocation.amount,
                        inventory_amount=allocation.inventory_amount,
                        cogs_amount=allocation.cogs_amount,
                    )
                    for allocation in allocations
                    if allocation.voucher_id == row.id
                ],
            )
            for row in rows
        ]

    # ---- helpers -------------------------------------------------------

    def _receipts(self, ids: list[UUID], firm_id: UUID) -> dict[UUID, GoodsReceipt]:
        """Return the named receipts, refusing any not completed or not the firm's."""
        if len(set(ids)) != len(ids):
            raise ValidationError("A receipt is named twice.")
        found = {
            receipt.id: receipt
            for receipt in self._session.scalars(
                select(GoodsReceipt).where(
                    GoodsReceipt.id.in_(ids),
                    GoodsReceipt.firm_id == firm_id,
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        }
        if set(ids) - set(found):
            raise ValidationError("A receipt is not one of this firm's.")
        open_ones = [r.grn_number for r in found.values() if r.status not in _DONE]
        if open_ones:
            raise ValidationError(
                "Only a completed receipt carries a landed cost: "
                + ", ".join(sorted(open_ones))
                + "."
            )
        return found

    def _check_vendors(
        self, charges: list[LandedCostChargeWrite], firm_id: UUID
    ) -> None:
        """Refuse a charge billed by a supplier that is not the firm's."""
        ids = {charge.vendor_id for charge in charges if charge.vendor_id}
        if not ids:
            return
        known = set(
            self._session.scalars(
                select(Vendor.id).where(
                    Vendor.id.in_(ids),
                    Vendor.firm_id == firm_id,
                    Vendor.is_deleted.is_(False),
                )
            ).all()
        )
        if ids - known:
            raise ValidationError("A charge names a supplier that is not the firm's.")

    def _allocations(self, voucher_ids: list[UUID]) -> list[LandedCostAllocation]:
        """Return the vouchers' allocations."""
        return list(
            self._session.scalars(
                select(LandedCostAllocation).where(
                    LandedCostAllocation.voucher_id.in_(voucher_ids),
                    LandedCostAllocation.is_deleted.is_(False),
                )
            ).all()
        )

    def _audit(self, action: str, row: LandedCostVoucher, actor_id: UUID) -> None:
        """Write one audit row for a voucher."""
        record_audit(
            self._session,
            action=action,
            entity_type="landed_cost_voucher",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "voucher_number": row.voucher_number,
                "total_amount": str(row.total_amount),
                "inventory_amount": str(row.inventory_amount),
                "cogs_amount": str(row.cogs_amount),
                "status": row.status,
            },
        )


def _stock_quantity(line: GoodsReceiptLine) -> Decimal:
    """Return what a receipt line put into stock, in the stock unit."""
    factor = Decimal(str(line.conversion_factor or 1))
    received = Decimal(str(line.accepted_quantity or 0)) + Decimal(
        str(line.free_quantity or 0)
    )
    return received * factor


def _measure(
    basis: str, line: GoodsReceiptLine, quantity: Decimal, product: Product | None
) -> Decimal:
    """Return what a line weighs in the spread on the chosen basis."""
    if basis == "QUANTITY":
        return quantity
    if basis == "WEIGHT":
        weight = Decimal(str(product.weight or 0)) if product is not None else ZERO
        return quantity * weight
    return Decimal(str(line.net_amount or 0)) - Decimal(str(line.tax_amount or 0))
