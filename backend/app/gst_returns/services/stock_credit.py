"""Input credit given up on stock that left without a sale (D-CMP-24).

Section 17(5)(h) of the CGST Act allows no input credit on goods lost,
stolen, destroyed, written off, or disposed of by way of gift or free
samples. A firm that claimed the credit when it bought the goods has to give
it back when they go that way, and GSTR-3B reports it in 4(B)(1).

**Which reasons reverse is the firm's own switch**, on each of its stock
adjustment reasons (``stock_adjustment_reasons.reverses_input_credit``). The
ones the section names start switched on: given free to a customer, sample,
loss, damage and expiry. Internal use, staff and display start off, and so
does every reason a firm adds.

**The credit reversed is the input tax of the goods at the cost they left
at.** The cost is the stock ledger's, the value the write-off's own journal
took out of Inventory. The rates are those of the product's latest approved
bill that claimed credit, head by head, so goods bought from another state
give back integrated tax and goods bought locally give back central and
state tax. A product with no such bill in these books (opening stock, goods
whose credit was blocked or never claimed) reverses nothing: there is no
claimed credit here to give back.

Stock that comes back under the same reason -- a sample returned, goods found
again -- is an adjustment inward, and claims back what was reversed on that
product, never more than still stands reversed on it. GSTR-3B takes it in
4(A)(5), as it does credit a rule 42 true-up claims back.

Each movement posts its own journal, from the input-tax accounts to *Input
Tax Not Claimable* (back again for a reclaim), as rules 37 and 42 do.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.gst_returns.models import ItcBasis, ItcMovement, ItcReversal
from app.gst_returns.services.rule37 import HEADS, _bucket
from app.inventory.models import InventoryTransaction
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.tax.services.gst_buckets import GstBuckets

if TYPE_CHECKING:
    from datetime import date

    from app.branches.services.registration import GstinScope
    from app.inventory.models.adjustment_reason import StockAdjustmentReason

#: Movements smaller than this are rounding, not a reversal.
_PAISA = Decimal("0.01")
_HUNDRED = Decimal("100")


class StockCreditService:
    """Reverse, and claim back, the credit on stock that left without a sale."""

    def __init__(self, session: Session) -> None:
        """Keep the firm store's session."""
        self._session = session

    def stage_for_movement(
        self,
        movement: InventoryTransaction,
        *,
        reason: StockAdjustmentReason,
        value_delta: Decimal,
        actor_id: UUID,
    ) -> ItcReversal | None:
        """Give up, or claim back, the credit on one stock movement.

        Flushed, not committed: it is part of the write-off or adjustment
        that calls it, and stands or falls with it.

        Args:
            movement: The write-off or adjustment just staged.
            reason: The firm's reason it named.
            value_delta: The change in stock value at cost, negative when
                the stock left.
            actor_id: The user making the movement.

        Returns:
            The row written, or None when the reason does not reverse, the
            movement carried no value, or no bill of the product claimed
            credit in these books.

        Raises:
            ValidationError: If the firm has no *Input tax not claimable*
                account to take the credit.

        """
        if not reason.reverses_input_credit:
            return None
        value = quantize_ledger(abs(value_delta))
        if value < _PAISA:
            return None
        firm_id = movement.firm_id
        found = self._rates(firm_id, movement.product_id)
        if found is None:
            return None
        bill_id, rates = found
        amounts = {
            head: quantize_ledger(value * rates[head] / _HUNDRED) for head in HEADS
        }
        leaving = value_delta < ZERO
        if not leaving:
            standing = self._standing(firm_id, movement.product_id)
            amounts = {
                head: max(min(amounts[head], standing[head]), ZERO) for head in HEADS
            }
        total = sum(amounts.values(), ZERO)
        if total < _PAISA:
            return None
        posting = DocumentPostingService(self._session)
        if posting._control.missing(
            firm_id, (ControlAccountPurpose.INELIGIBLE_INPUT_TAX,)
        ):
            raise ValidationError(
                f"Stock leaving as {reason.name.lower()} gives up the input "
                "credit taken on it, and this firm has no Input tax not "
                "claimable account to take it. Set it under the firm's control "
                "accounts, or switch off Reverses input credit on the reason."
            )
        row = ItcReversal(
            firm_id=firm_id,
            basis=ItcBasis.STOCK.value,
            purchase_invoice_id=bill_id,
            inventory_transaction_id=movement.id,
            reason_code=reason.code,
            stock_value=value,
            movement=(
                ItcMovement.REVERSAL.value if leaving else ItcMovement.RECLAIM.value
            ),
            movement_date=movement.transaction_date,
            outstanding_amount=ZERO,
            bill_total=ZERO,
            created_by=actor_id,
            updated_by=actor_id,
            **amounts,
        )
        self._session.add(row)
        self._session.flush()
        describe = (
            f"Input credit {'reversed' if leaving else 'claimed back'}, "
            f"{reason.name.lower()}: {movement.reference_number}"
        )
        not_claimable = posting._require_mapping(
            firm_id, (ControlAccountPurpose.INELIGIBLE_INPUT_TAX,)
        )[ControlAccountPurpose.INELIGIBLE_INPUT_TAX]
        lines = [
            JournalLineData(
                ledger_account_id=not_claimable,
                debit_amount=total if leaving else ZERO,
                credit_amount=ZERO if leaving else total,
                description=describe,
            ),
            *posting._input_tax_legs(
                firm_id=firm_id,
                ledger_tax=total,
                tax_by_component={
                    head.upper(): amount for head, amount in amounts.items() if amount
                },
                describe=describe,
                credit=leaving,
            ),
        ]
        context = posting.context_for(firm_id, movement.transaction_date)
        journals = JournalEntryEngine(self._session)
        entry = journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=movement.transaction_date,
            reference_number=self._reference(firm_id, movement.reference_number),
            description=describe,
            lines=lines,
            # Keyed on the row, not the movement: the movement's own journal
            # is found by the movement's id and must stay the only one there.
            source_module="itc_stock",
            source_id=row.id,
            actor_id=actor_id,
        )
        journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
        row.journal_entry_id = entry.id
        self._session.flush()
        record_audit(
            self._session,
            action=f"gst.stock_credit.{row.movement.lower()}",
            entity_type="itc_reversal",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "movement": movement.reference_number,
                "reason": reason.code,
                "stock_value": str(value),
                **{head: str(amount) for head, amount in amounts.items()},
            },
        )
        return row

    def movements_between(
        self,
        *,
        firm_id: UUID,
        from_date: date,
        to_date: date,
        scope: GstinScope | None = None,
    ) -> tuple[GstBuckets, GstBuckets]:
        """Return (reversed, claimed back) in a return period, for GSTR-3B.

        ``scope`` keeps a return for one GSTIN to the stock of its own
        branches, as it keeps it to their bills.
        """
        query = (
            select(
                ItcReversal.movement,
                func.sum(ItcReversal.igst),
                func.sum(ItcReversal.cgst),
                func.sum(ItcReversal.sgst),
                func.sum(ItcReversal.cess),
            )
            .join(
                InventoryTransaction,
                InventoryTransaction.id == ItcReversal.inventory_transaction_id,
            )
            .where(
                ItcReversal.firm_id == firm_id,
                ItcReversal.is_deleted.is_(False),
                ItcReversal.basis == ItcBasis.STOCK.value,
                ItcReversal.movement_date >= from_date,
                ItcReversal.movement_date <= to_date,
            )
            .group_by(ItcReversal.movement)
        )
        if scope is not None:
            query = query.where(scope.applies(InventoryTransaction.branch_id))
        reversed_, reclaimed = GstBuckets(), GstBuckets()
        for movement, igst, cgst, sgst, cess in self._session.execute(query).tuples():
            share = GstBuckets(
                igst=Decimal(str(igst or 0)),
                cgst=Decimal(str(cgst or 0)),
                sgst=Decimal(str(sgst or 0)),
                cess=Decimal(str(cess or 0)),
            )
            if movement == ItcMovement.REVERSAL.value:
                reversed_ = reversed_.plus(share)
            else:
                reclaimed = reclaimed.plus(share)
        return reversed_, reclaimed

    # ------------------------------------------------------------------

    def _rates(
        self, firm_id: UUID, product_id: UUID
    ) -> tuple[UUID, dict[str, Decimal]] | None:
        """Return the product's latest bill that claimed credit, and its rates.

        The rate per GST head, in percent, off the bill line's own tax rows:
        claimable tax the supplier added to the price, or that the firm paid
        itself under reverse charge and claimed. Tax inside the price and tax
        on a blocked or ineligible line were never claimed, so they give no
        rate.
        """
        claimed = (
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.recoverable.is_(True),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
        )
        dated = func.coalesce(
            PurchaseInvoice.supplier_invoice_date, PurchaseInvoice.invoice_date
        )
        line = self._session.execute(
            select(PurchaseInvoiceLine.id, PurchaseInvoice.id)
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.product_id == product_id,
                PurchaseInvoiceLine.itc_eligibility == "ELIGIBLE",
                exists(
                    select(PurchaseInvoiceLineTax.id).where(
                        PurchaseInvoiceLineTax.purchase_invoice_line_id
                        == PurchaseInvoiceLine.id,
                        *claimed,
                    )
                ),
            )
            .order_by(
                dated.desc(),
                PurchaseInvoice.created_at.desc(),
                PurchaseInvoiceLine.line_number,
            )
            .limit(1)
        ).first()
        if line is None:
            return None
        line_id, bill_id = line
        rates = dict.fromkeys(HEADS, ZERO)
        for code, percentage in self._session.execute(
            select(
                PurchaseInvoiceLineTax.component_code,
                PurchaseInvoiceLineTax.percentage,
            ).where(
                PurchaseInvoiceLineTax.purchase_invoice_line_id == line_id, *claimed
            )
        ).tuples():
            share = _bucket(code, Decimal(str(percentage or 0)))
            for head in HEADS:
                rates[head] += getattr(share, head)
        if sum(rates.values(), ZERO) <= ZERO:
            return None
        return bill_id, rates

    def _standing(self, firm_id: UUID, product_id: UUID) -> dict[str, Decimal]:
        """Return what stands reversed on a product: reversals less reclaims."""
        sign = case((ItcReversal.movement == ItcMovement.REVERSAL.value, 1), else_=-1)
        row = self._session.execute(
            select(
                func.sum(ItcReversal.igst * sign),
                func.sum(ItcReversal.cgst * sign),
                func.sum(ItcReversal.sgst * sign),
                func.sum(ItcReversal.cess * sign),
            )
            .join(
                InventoryTransaction,
                InventoryTransaction.id == ItcReversal.inventory_transaction_id,
            )
            .where(
                ItcReversal.firm_id == firm_id,
                ItcReversal.is_deleted.is_(False),
                ItcReversal.basis == ItcBasis.STOCK.value,
                InventoryTransaction.product_id == product_id,
            )
        ).one()
        return {
            head: Decimal(str(amount or 0))
            for head, amount in zip(HEADS, row, strict=True)
        }

    def _reference(self, firm_id: UUID, movement_reference: str) -> str:
        """Return a journal reference no journal has used: ITC-<movement>."""
        journals = JournalEntryEngine(self._session)
        reference = f"ITC-{movement_reference}"[:80]
        number = 1
        while journals.reference_taken(reference, firm_id=firm_id):
            number += 1
            reference = f"ITC-{movement_reference}"[: 80 - len(str(number)) - 1]
            reference = f"{reference}-{number}"
        return reference
