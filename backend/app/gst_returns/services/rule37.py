"""Rule 37: credit on a bill unpaid 180 days after its date (backlog 78 row 4).

A buyer must pay a supplier the value of a supply and the tax on it within 180
days of the invoice date. Credit taken on a bill still unpaid after that is
reversed in proportion to what is unpaid, and claimed back as it is paid
(CGST rule 37, as amended from 1 October 2022; interest under s.50 is the
firm's to work out and is not computed here).

**What a bill owes is read, never stored**: from `PaymentService`, the one
derivation every screen uses, so a payment, a return or a debit note all count.
**What stands reversed is summed** from `itc_reversals`, never held in a
column. The difference between what *should* stand reversed today and what
does is the work: a positive difference on a bill past 180 days is a
reversal, a negative one is a reclaim.

Only credit actually claimed is at stake: eligible, recoverable tax, not
included in the price and not reverse charge -- the rows GSTR-3B claims in
4(A)(5). Blocked and ineligible tax was never claimed, so it is never reversed.

The firm chooses (``gst_compliance_settings.rule37_mode``): OFF, REPORT (the
list only; the default, as the reversal is the firm's call with its CA), or
POST (the list, and posting from it). A posted reversal moves the credit from
the input-tax accounts to *Input Tax Not Claimable*; a reclaim moves it back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.gst_returns.models import ItcMovement, ItcReversal
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.tax.services.gst_buckets import GstBuckets
from app.vendors.models import Vendor

DAYS = 180
HEADS = ("igst", "cgst", "sgst", "cess")
#: Movements smaller than this are rounding, not a reversal.
_PAISA = Decimal("0.01")


def _bucket(code: str, amount: Decimal) -> GstBuckets:
    """Return one tax row in its GST head; UTGST is filed as state tax."""
    upper = (code or "").upper()
    if upper == "IGST":
        return GstBuckets(igst=amount)
    if upper == "CGST":
        return GstBuckets(cgst=amount)
    if upper in ("SGST", "UTGST"):
        return GstBuckets(sgst=amount)
    if upper.startswith("CESS") or upper == "COMPENSATION_CESS":
        return GstBuckets(cess=amount)
    return GstBuckets()


@dataclass(slots=True)
class Rule37Row:
    """One bill: what it owes, the credit at stake, and what to move."""

    purchase_invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str | None
    vendor_name: str
    bill_date: date
    days: int
    bill_total: Decimal
    outstanding: Decimal
    credit: dict[str, Decimal]
    reversed: dict[str, Decimal]
    #: Positive: reverse this much more. Negative: reclaim this much.
    move: dict[str, Decimal] = field(default_factory=dict)

    @property
    def action(self) -> str:
        """REVERSE, RECLAIM or NONE."""
        total = sum(self.move.values(), ZERO)
        if total >= _PAISA:
            return "REVERSE"
        if total <= -_PAISA:
            return "RECLAIM"
        return "NONE"


class Rule37Service:
    """List and post rule 37 reversals and reclaims for one firm."""

    def __init__(self, session: Session) -> None:
        """Keep the firm store's session."""
        self._session = session

    def mode(self, firm_id: UUID) -> str:
        """Return the firm's choice: OFF, REPORT or POST."""
        from app.tax.services.gst_compliance import GstComplianceService

        return (
            GstComplianceService(self._session).settings_response(firm_id).rule37_mode
        )

    def rows(self, *, firm_id: UUID, as_of: date) -> list[Rule37Row]:
        """Return every bill with something to reverse or reclaim on ``as_of``.

        A bill dated more than 180 days before ``as_of`` with credit claimed
        and money unpaid is due a reversal of the unpaid share, less what
        already stands reversed. A bill that stands reversed and has been paid
        since is due a reclaim, whatever its age.
        """
        credit = self._claimed_credit(firm_id)
        standing = self._standing(firm_id)
        candidates = set(credit) & (
            {bill for bill, _ in self._old_bills(firm_id, as_of)} | set(standing)
        )
        if not candidates:
            return []
        from app.settlements.services.settlement_service import PaymentService

        owed = {
            record.invoice_id: Decimal(str(record.outstanding_amount))
            for record in PaymentService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=None
            )
        }
        bills = {
            row.id: (row, name)
            for row, name in self._session.execute(
                select(PurchaseInvoice, Vendor.name)
                .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id, isouter=True)
                .where(PurchaseInvoice.id.in_(candidates))
            ).tuples()
        }
        result: list[Rule37Row] = []
        for bill_id in candidates:
            bill, vendor_name = bills[bill_id]
            on = bill.supplier_invoice_date or bill.invoice_date
            days = (as_of - on).days
            total = Decimal(str(bill.grand_total))
            outstanding = max(owed.get(bill_id, ZERO), ZERO)
            past = days > DAYS
            share = (outstanding / total if past and total > ZERO else ZERO).min(
                Decimal("1")
            )
            claimed = credit[bill_id]
            held = standing.get(bill_id, dict.fromkeys(HEADS, ZERO))
            due = {head: quantize_ledger(claimed[head] * share) for head in HEADS}
            row = Rule37Row(
                purchase_invoice_id=bill_id,
                invoice_number=bill.invoice_number,
                supplier_invoice_number=bill.supplier_invoice_number,
                vendor_name=vendor_name or "",
                bill_date=on,
                days=days,
                bill_total=total,
                outstanding=outstanding,
                credit=claimed,
                reversed=held,
                move={head: due[head] - held[head] for head in HEADS},
            )
            if row.action != "NONE":
                result.append(row)
        result.sort(key=lambda item: (item.bill_date, item.invoice_number))
        return result

    def post(
        self,
        *,
        firm_id: UUID,
        as_of: date,
        actor_id: UUID,
        bill_ids: list[UUID] | None = None,
    ) -> list[ItcReversal]:
        """Post the reversals and reclaims due on ``as_of``, one journal each.

        Raises:
            ValidationError: Unless the firm chose POST, or when an input-tax
                or *Input Tax Not Claimable* account is not mapped, or the
                date's period is not open.

        """
        if self.mode(firm_id) != "POST":
            raise ValidationError(
                "Rule 37 reversals are reported, not posted, for this firm. "
                "Choose Report and post under Settings > Tax > GST Documents."
            )
        wanted = set(bill_ids) if bill_ids else None
        posting = DocumentPostingService(self._session)
        journals = JournalEntryEngine(self._session)
        made: list[ItcReversal] = []
        for row in self.rows(firm_id=firm_id, as_of=as_of):
            if wanted is not None and row.purchase_invoice_id not in wanted:
                continue
            reversal = row.action == "REVERSE"
            amounts = {head: abs(row.move[head]) for head in HEADS}
            total = sum(amounts.values(), ZERO)
            by_component = {
                head.upper(): amount for head, amount in amounts.items() if amount
            }
            describe = (
                f"Rule 37 {'reversal' if reversal else 'reclaim'}: "
                f"{row.invoice_number} ({row.vendor_name})"
            )
            not_claimable = posting._require_mapping(
                firm_id, (ControlAccountPurpose.INELIGIBLE_INPUT_TAX,)
            )[ControlAccountPurpose.INELIGIBLE_INPUT_TAX]
            lines = [
                JournalLineData(
                    ledger_account_id=not_claimable,
                    debit_amount=total if reversal else ZERO,
                    credit_amount=ZERO if reversal else total,
                    description=describe,
                ),
                *posting._input_tax_legs(
                    firm_id=firm_id,
                    ledger_tax=total,
                    tax_by_component=by_component,
                    describe=describe,
                    credit=reversal,
                ),
            ]
            context = posting.context_for(firm_id, as_of)
            entry = journals.create_entry(
                firm_id=firm_id,
                journal_type_id=context.journal_type_id,
                voucher_type_id=context.voucher_type_id,
                accounting_period_id=context.accounting_period_id,
                journal_date=as_of,
                reference_number=self._reference(firm_id, row.invoice_number),
                description=describe,
                lines=lines,
                source_module="rule37",
                source_id=row.purchase_invoice_id,
                actor_id=actor_id,
            )
            journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
            movement = ItcReversal(
                firm_id=firm_id,
                purchase_invoice_id=row.purchase_invoice_id,
                movement=(
                    ItcMovement.REVERSAL.value
                    if reversal
                    else ItcMovement.RECLAIM.value
                ),
                movement_date=as_of,
                outstanding_amount=row.outstanding,
                bill_total=row.bill_total,
                journal_entry_id=entry.id,
                created_by=actor_id,
                updated_by=actor_id,
                **amounts,
            )
            self._session.add(movement)
            self._session.flush()
            record_audit(
                self._session,
                action=f"gst.rule37.{movement.movement.lower()}",
                entity_type="itc_reversal",
                entity_id=movement.id,
                actor_id=actor_id,
                firm_id=firm_id,
                after_data={
                    "bill": row.invoice_number,
                    "outstanding": str(row.outstanding),
                    **{head: str(amount) for head, amount in amounts.items()},
                },
            )
            made.append(movement)
        return made

    def movements_between(
        self, *, firm_id: UUID, from_date: date, to_date: date
    ) -> tuple[GstBuckets, GstBuckets]:
        """Return (reversed, reclaimed) in a return period, for GSTR-3B."""
        reversed_, reclaimed = GstBuckets(), GstBuckets()
        for row in self._session.scalars(
            select(ItcReversal).where(
                ItcReversal.firm_id == firm_id,
                ItcReversal.is_deleted.is_(False),
                ItcReversal.movement_date >= from_date,
                ItcReversal.movement_date <= to_date,
            )
        ):
            share = GstBuckets(
                igst=Decimal(str(row.igst)),
                cgst=Decimal(str(row.cgst)),
                sgst=Decimal(str(row.sgst)),
                cess=Decimal(str(row.cess)),
            )
            if row.movement == ItcMovement.REVERSAL.value:
                reversed_ = reversed_.plus(share)
            else:
                reclaimed = reclaimed.plus(share)
        return reversed_, reclaimed

    # ------------------------------------------------------------------

    def _old_bills(self, firm_id: UUID, as_of: date) -> list[tuple[UUID, date]]:
        """Return live bills dated more than 180 days before ``as_of``."""
        cutoff = as_of - timedelta(days=DAYS)
        dated = func.coalesce(
            PurchaseInvoice.supplier_invoice_date, PurchaseInvoice.invoice_date
        )
        return [
            (bill_id, on)
            for bill_id, on in self._session.execute(
                select(PurchaseInvoice.id, dated).where(
                    PurchaseInvoice.firm_id == firm_id,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                    dated < cutoff,
                )
            ).tuples()
        ]

    def _claimed_credit(self, firm_id: UUID) -> dict[UUID, dict[str, Decimal]]:
        """Return the credit each live bill claimed, by head, as 3B claims it."""
        credit: dict[UUID, dict[str, Decimal]] = {}
        for bill_id, code, amount in self._session.execute(
            select(
                PurchaseInvoice.id,
                PurchaseInvoiceLineTax.component_code,
                PurchaseInvoiceLineTax.amount,
            )
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.itc_eligibility == "ELIGIBLE",
                PurchaseInvoiceLineTax.is_deleted.is_(False),
                PurchaseInvoiceLineTax.recoverable.is_(True),
                PurchaseInvoiceLineTax.included_in_price.is_(False),
                PurchaseInvoiceLineTax.reverse_charge.is_(False),
            )
        ).tuples():
            share = _bucket(code, Decimal(str(amount)))
            heads = credit.setdefault(bill_id, dict.fromkeys(HEADS, ZERO))
            for head in HEADS:
                heads[head] += getattr(share, head)
        return {
            bill_id: heads
            for bill_id, heads in credit.items()
            if sum(heads.values(), ZERO) > ZERO
        }

    def _standing(self, firm_id: UUID) -> dict[UUID, dict[str, Decimal]]:
        """Return what stands reversed on each bill: reversals less reclaims."""
        sign = case((ItcReversal.movement == ItcMovement.REVERSAL.value, 1), else_=-1)
        standing: dict[UUID, dict[str, Decimal]] = {}
        for bill_id, igst, cgst, sgst, cess in self._session.execute(
            select(
                ItcReversal.purchase_invoice_id,
                func.sum(ItcReversal.igst * sign),
                func.sum(ItcReversal.cgst * sign),
                func.sum(ItcReversal.sgst * sign),
                func.sum(ItcReversal.cess * sign),
            )
            .where(
                ItcReversal.firm_id == firm_id,
                ItcReversal.is_deleted.is_(False),
            )
            .group_by(ItcReversal.purchase_invoice_id)
        ).tuples():
            heads = {
                "igst": Decimal(str(igst or 0)),
                "cgst": Decimal(str(cgst or 0)),
                "sgst": Decimal(str(sgst or 0)),
                "cess": Decimal(str(cess or 0)),
            }
            if sum(heads.values(), ZERO) > ZERO:
                standing[bill_id] = heads
        return standing

    def _reference(self, firm_id: UUID, invoice_number: str) -> str:
        """Return a journal reference no journal has used: R37-<bill>-<n>."""
        journals = JournalEntryEngine(self._session)
        number = 1
        while True:
            reference = f"R37-{invoice_number}-{number}"[:80]
            if not journals.reference_taken(reference, firm_id=firm_id):
                return reference
            number += 1
