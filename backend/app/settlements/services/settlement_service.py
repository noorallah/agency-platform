"""Record money arriving and money going out, and put it in the ledger.

The gap this closes: `POST /customers/{id}/receivables/transactions` could
already record a receipt, and it moved the customer's outstanding balance
without writing a journal. Using it made the subsidiary ledger and the general
ledger disagree by the amount collected, silently and permanently. Nothing on
the vendor side existed at all.

So a settlement is not a balance adjustment that also posts. It is a document
that posts, and the posting is what makes it real: if the journal cannot be
written -- no control account, no open period -- the settlement is refused
rather than recorded half-way.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.common.audit.services import record_audit
from app.common.report_names import customers_matching, vendors_matching
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.database.batch import children_by_parent
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.chunks import over_chunks, whole_past_a_chunk
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import (
    Customer,
    CustomerOpeningBill,
    CustomerReceivableTransaction,
)
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.customers.services.opening_bill_service import (
    opening_bill_label as customer_opening_bill_label,
)
from app.customers.services.opening_bill_service import (
    opening_bill_receipts,
)
from app.customers.services.opening_bill_service import (
    standing_opening_bills as standing_customer_opening_bills,
)
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.models import LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.messaging.services import MessagingDocument, stage_document_event
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrder
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementMethod,
    SettlementStatus,
)
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementCreate,
)
from app.settlements.services.supplier_credits import credit_applied_against
from app.tcs.services import TcsService
from app.vendors.models import Vendor, VendorOpeningBill
from app.vendors.services.opening_bill_service import (
    opening_bill_label,
    opening_bill_payments,
    standing_opening_bills,
)

#: Which control account the money moved through, by method.
METHOD_PURPOSE = {
    SettlementMethod.CASH: ControlAccountPurpose.CASH,
    SettlementMethod.BANK: ControlAccountPurpose.BANK,
}

#: Invoice states that owe anything. A draft invoice is not a debt, and
#: cancelled invoices are not owed by anybody.
SETTLEABLE_INVOICE_STATES = (
    "APPROVED",
    "COMPLETED",
    "CLOSED",
    "PARTIALLY_PAID",
    "PAID",
)


def _among(
    column: InstrumentedAttribute[Any], ids: Sequence[UUID] | None
) -> tuple[Any, ...]:
    """Narrow to ``ids``, or to nothing more than the firm when ids is None."""
    return () if ids is None else (column.in_(ids),)


@whole_past_a_chunk("invoice_ids")
def credited_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
) -> dict[UUID, Decimal]:
    """Sum what returns and credit notes have taken off each sales invoice.

    A completed sales return and an approved credit note both post Cr
    receivable, so the ledger already says the customer owes less. Only a
    return raised from the bill's own lines names the bill; one raised from a
    delivery note stays a credit on the customer's account, exactly as a
    purchase return raised from a goods receipt does on the supplier's
    (D-BUY-6). A credit note is always raised against one invoice.

    One derivation, used by Record Receipt's list and by the loyalty cap, so
    the two cannot answer "what does this bill still owe" differently.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about; None asks about every
            invoice of the firm in one grouped read, which is what a
            firm-wide report wants rather than its ids sent in chunks.
        as_of: Count only what was dated on or before this day; None counts
            everything.

    Returns:
        The credited amount per invoice, for those with any.

    """
    if invoice_ids is not None and not invoice_ids:
        return {}
    # Imported here: both modules import settlement-adjacent models.
    from app.credit_note.models import CreditNote, CreditNoteStatus
    from app.sales_return.models import SalesReturn, SalesReturnLine

    credited: dict[UUID, Decimal] = {}
    returned = session.execute(
        select(
            SalesReturnLine.source_document_id,
            func.coalesce(func.sum(SalesReturnLine.net_amount), 0),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(
            SalesReturnLine.firm_id == firm_id,
            SalesReturnLine.source_document_type == "SALES_INVOICE",
            *_among(SalesReturnLine.source_document_id, invoice_ids),
            SalesReturnLine.is_deleted.is_(False),
            # Completing is what posts Cr receivable; a draft or approved
            # return has not moved anything yet, a cancelled one is gone.
            SalesReturn.status.in_(("COMPLETED", "CLOSED")),
            SalesReturn.is_deleted.is_(False),
            *(() if as_of is None else (SalesReturn.return_date <= as_of,)),
        )
        .group_by(SalesReturnLine.source_document_id)
    ).all()
    notes = session.execute(
        select(
            CreditNote.sales_invoice_id,
            func.coalesce(func.sum(CreditNote.total_amount), 0),
        )
        .where(
            CreditNote.firm_id == firm_id,
            *_among(CreditNote.sales_invoice_id, invoice_ids),
            # Approval is what posts; a draft has not, a cancelled one is gone.
            CreditNote.status == CreditNoteStatus.APPROVED.value,
            CreditNote.is_deleted.is_(False),
            *(() if as_of is None else (CreditNote.credit_note_date <= as_of,)),
        )
        .group_by(CreditNote.sales_invoice_id)
    ).all()
    for invoice_id, total in (*returned, *notes):
        credited[invoice_id] = credited.get(invoice_id, ZERO) + quantize_ledger(
            Decimal(str(total))
        )
    return credited


@whole_past_a_chunk("invoice_ids")
def settled_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
) -> dict[UUID, Decimal]:
    """Sum everything that has come off each sales invoice.

    Money allocated from a posted receipt, points spent on the bill, and the
    returns and credit notes raised against it (``credited_against``). Each
    part is rounded to the ledger's two decimals before they are added, which
    is how Record Receipt has always shown them. This is the one answer to
    "what does this bill still owe": Record Receipt's list and the ageing both
    read it, so the two cannot disagree again (D-FIN-10, where the ageing left
    out points spent and aged 3,698.95 while Record Receipt offered 3,598.95).

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about; None asks about every
            invoice of the firm, as ``credited_against`` does.
        as_of: Count only what had happened by the end of this day -- a
            receipt dated after it had not arrived yet, and one reversed after
            it still stood. None counts what stands now.

    Returns:
        The settled amount per invoice, for those with any.

    """
    if invoice_ids is not None and not invoice_ids:
        return {}
    if as_of is None:
        standing = Settlement.status == SettlementStatus.POSTED.value
        dated: tuple[Any, ...] = ()
    else:
        standing = or_(
            Settlement.status == SettlementStatus.POSTED.value,
            and_(
                Settlement.status == SettlementStatus.REVERSED.value,
                Settlement.reversed_at >= _start_of_day_after(as_of),
            ),
        )
        dated = (Settlement.settlement_date <= as_of,)
    allocated = session.execute(
        select(
            SettlementAllocation.sales_invoice_id,
            func.coalesce(func.sum(SettlementAllocation.amount), 0),
        )
        .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
        .where(
            SettlementAllocation.firm_id == firm_id,
            *_among(SettlementAllocation.sales_invoice_id, invoice_ids),
            SettlementAllocation.is_deleted.is_(False),
            Settlement.is_deleted.is_(False),
            standing,
            *dated,
        )
        .group_by(SettlementAllocation.sales_invoice_id)
    ).all()
    spent = session.execute(
        select(
            LoyaltyEntry.sales_invoice_id,
            func.coalesce(func.sum(LoyaltyEntry.amount), 0),
        )
        .where(
            LoyaltyEntry.firm_id == firm_id,
            *_among(LoyaltyEntry.sales_invoice_id, invoice_ids),
            LoyaltyEntry.kind == LoyaltyEntryKind.REDEEMED.value,
            LoyaltyEntry.is_deleted.is_(False),
            *(() if as_of is None else (LoyaltyEntry.earned_on <= as_of,)),
        )
        .group_by(LoyaltyEntry.sales_invoice_id)
    ).all()
    settled: dict[UUID, Decimal] = {}
    for invoice_id, total in (*allocated, *spent):
        if invoice_id is None:
            continue
        settled[invoice_id] = settled.get(invoice_id, ZERO) + quantize_ledger(
            Decimal(str(total))
        )
    for invoice_id, amount in credited_against(
        session, firm_id=firm_id, invoice_ids=invoice_ids, as_of=as_of
    ).items():
        settled[invoice_id] = settled.get(invoice_id, ZERO) + amount
    return settled


def _start_of_day_after(day: date) -> datetime:
    """Return midnight UTC at the end of ``day`` -- the first instant after it."""
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC)


class SettlementService(TransactionalDocumentService):
    """Record a settlement, allocate it to invoices, and post it."""

    DIRECTION: SettlementDirection

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)
        self._controls = ControlAccountService(session)
        self._customers = CustomerService(session)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def outstanding_invoices(
        self, *, firm_id: UUID, party_id: UUID | None
    ) -> list[OutstandingInvoiceRecord]:
        """Return the party's invoices that still owe something.

        Outstanding is the invoice total less everything allocated against it,
        computed here rather than stored. A paid-to-date column on the invoice
        would be a second copy of the allocations, and the copy is wrong the
        first time anything writes one without going through this service.

        ``party_id`` of None answers for every party in the firm. The vendor
        outstanding and overdue purchase-invoice reports summed ``grand_total``
        of every non-cancelled bill and never read an allocation, so a bill
        paid in full was owed and overdue for ever (D-RPT-2); they read this
        now, so Record Payment and the reports cannot disagree.

        Totals are rounded to the two decimals money moves in. A document is
        consistent at its own four -- the seeded invoices carry totals like
        `8429.6250` -- and a customer settling one in full pays `8429.63`,
        which an unrounded comparison refuses as more than the invoice owes.
        """
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        invoice: type[SalesInvoice] | type[PurchaseInvoice]
        if is_receipt:
            invoice = SalesInvoice
            party_column = SalesInvoice.customer_id
            allocation_column = SettlementAllocation.sales_invoice_id
        else:
            invoice = PurchaseInvoice
            party_column = PurchaseInvoice.vendor_id
            allocation_column = SettlementAllocation.purchase_invoice_id
        # Joined to the settlement so a reversed one stops clearing anything.
        # The allocation rows stay: the reversed settlement still shows what it
        # had been applied to, which is what somebody asks first when a
        # correction is queried.
        allocated = (
            select(
                allocation_column.label("invoice_id"),
                func.coalesce(func.sum(SettlementAllocation.amount), 0).label("total"),
            )
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .where(
                SettlementAllocation.firm_id == firm_id,
                SettlementAllocation.is_deleted.is_(False),
                Settlement.status == SettlementStatus.POSTED.value,
                allocation_column.is_not(None),
            )
            .group_by(allocation_column)
            .subquery()
        )
        # The columns the list shows, never the whole document: a firm-wide
        # read of full rows was a third of Customer Outstanding's 16 s on a
        # firm with 109,566 invoices (backlog 56 C, step 4).
        rows = self._session.execute(
            select(
                invoice.id,
                invoice.invoice_number,
                invoice.invoice_date,
                invoice.grand_total,
                invoice.due_date,
                party_column.label("party_id"),
                func.coalesce(allocated.c.total, 0),
            )
            .outerjoin(allocated, allocated.c.invoice_id == invoice.id)
            .where(
                invoice.firm_id == firm_id,
                *(() if party_id is None else (party_column == party_id,)),
                invoice.is_deleted.is_(False),
                invoice.status.in_(SETTLEABLE_INVOICE_STATES),
            )
            .order_by(invoice.invoice_date.asc(), invoice.invoice_number.asc())
        ).all()
        # A customer's bill: money allocated, points spent (plan item 10.9)
        # and returns and credit notes against it (D-SELL-10) -- through the
        # one derivation the ageing reads as well (D-FIN-10).
        settled: dict[UUID, Decimal] = {}
        if is_receipt and rows:
            # Firm-wide, one grouped read per source beats the ids in chunks.
            settled = settled_against(
                self._session,
                firm_id=firm_id,
                invoice_ids=None if party_id is None else [row.id for row in rows],
            )
        # Goods sent back against a bill's own lines come off that bill (D-BUY-6,
        # decided by the owner on 2026-09-18). A completed return posts Dr
        # payable, so the ledger already owed less while this list still showed
        # the whole bill and a payment could settle it again. Only a return
        # raised from the bill's lines names the bill; one raised from a goods
        # receipt or an order stays a credit on the supplier, as a sales
        # return does on the customer.
        returned: dict[UUID, Decimal] = {}
        credited: dict[UUID, Decimal] = {}
        if not is_receipt and rows:
            returned = self._returned_against(
                firm_id=firm_id, invoice_ids=[row.id for row in rows]
            )
            # And supplier credit from a return raised off the goods receipt,
            # once somebody has set it against this bill (D-FIN-19).
            credited = credit_applied_against(
                self._session,
                firm_id=firm_id,
                invoice_ids=[row.id for row in rows],
            )
        records: list[OutstandingInvoiceRecord] = []
        for row in rows:
            allocated_amount = row[-1]
            already = (
                settled.get(row.id, ZERO)
                if is_receipt
                else quantize_ledger(Decimal(allocated_amount))
                + quantize_ledger(returned.get(row.id, ZERO))
                + credited.get(row.id, ZERO)
            )
            total = quantize_ledger(row.grand_total)
            outstanding = total - already
            if outstanding <= ZERO:
                continue
            records.append(
                OutstandingInvoiceRecord(
                    invoice_id=row.id,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_date,
                    invoice_total=total,
                    allocated_amount=already,
                    outstanding_amount=outstanding,
                    party_id=row.party_id,
                    due_date=row.due_date,
                )
            )
        records.extend(
            self._owing_customer_opening_bills(firm_id=firm_id, party_id=party_id)
            if is_receipt
            else self._owing_opening_bills(firm_id=firm_id, party_id=party_id)
        )
        records.sort(key=lambda record: (record.invoice_date, record.invoice_number))
        return records

    def _owing_customer_opening_bills(
        self, *, firm_id: UUID, party_id: UUID | None
    ) -> list[OutstandingInvoiceRecord]:
        """Offer what customers owed at cutover as bills to be received against.

        The receivable twin of `_owing_opening_bills`: beside the sales
        invoices, in the one derivation Record Receipt, the outstanding and
        overdue reports and the customer delete guard all read.
        """
        bills = standing_customer_opening_bills(
            self._session, firm_id=firm_id, customer_id=party_id
        )
        received = opening_bill_receipts(
            self._session, firm_id=firm_id, bill_ids=[row.id for row in bills]
        )
        records: list[OutstandingInvoiceRecord] = []
        for row in bills:
            total = quantize_ledger(row.amount)
            already = received.get(row.id, ZERO)
            if total - already <= ZERO:
                continue
            records.append(
                OutstandingInvoiceRecord(
                    invoice_id=row.id,
                    invoice_number=customer_opening_bill_label(row),
                    invoice_date=row.bill_date,
                    invoice_total=total,
                    allocated_amount=already,
                    outstanding_amount=total - already,
                    party_id=row.customer_id,
                    due_date=row.due_date,
                    is_opening_bill=True,
                )
            )
        return records

    def _owing_opening_bills(
        self, *, firm_id: UUID, party_id: UUID | None
    ) -> list[OutstandingInvoiceRecord]:
        """Offer what suppliers were owed at cutover as bills to be paid.

        Beside the purchase bills, in the one derivation every payable reader
        uses -- Record Payment, the outstanding and overdue reports and the
        vendor delete guard -- so a supplier's opening debt cannot be owed on
        one screen and missing from another.
        """
        bills = standing_opening_bills(
            self._session, firm_id=firm_id, vendor_id=party_id
        )
        paid = opening_bill_payments(
            self._session, firm_id=firm_id, bill_ids=[row.id for row in bills]
        )
        records: list[OutstandingInvoiceRecord] = []
        for row in bills:
            total = quantize_ledger(row.amount)
            already = paid.get(row.id, ZERO)
            if total - already <= ZERO:
                continue
            records.append(
                OutstandingInvoiceRecord(
                    invoice_id=row.id,
                    invoice_number=opening_bill_label(row),
                    invoice_date=row.bill_date,
                    invoice_total=total,
                    allocated_amount=already,
                    outstanding_amount=total - already,
                    party_id=row.vendor_id,
                    due_date=row.due_date,
                    is_opening_bill=True,
                )
            )
        return records

    def _opening_bill_ids(self, ids: Sequence[UUID]) -> set[UUID]:
        """Say which of the ids a settlement names are opening bills.

        A customer's for a receipt, a supplier's for a payment.
        """
        if not ids:
            return set()
        model: type[CustomerOpeningBill] | type[VendorOpeningBill] = (
            CustomerOpeningBill
            if self.DIRECTION == SettlementDirection.RECEIPT
            else VendorOpeningBill
        )
        return set(
            self._session.scalars(select(model.id).where(model.id.in_(list(ids)))).all()
        )

    @over_chunks("invoice_ids")
    def _returned_against(
        self, *, firm_id: UUID, invoice_ids: list[UUID]
    ) -> dict[UUID, Decimal]:
        """Sum what returns and debit notes took off each bill.

        Completed purchase returns sent back off the bill's lines, and
        approved debit notes claimed against it (backlog 65 row 6). Both post
        Dr payable, so both are what the bill no longer owes. A debit note is
        counted as its journal debited the payable -- each part rounded to the
        ledger, then summed -- so the bill and the books agree to the paisa.
        """
        # Imported here: the return module imports settlement-adjacent models.
        from app.debit_note.models import DebitNote, DebitNoteStatus

        taken: dict[UUID, Decimal] = {}
        for invoice_id, taxable, tax in self._session.execute(
            select(
                DebitNote.purchase_invoice_id,
                DebitNote.taxable_amount,
                DebitNote.tax_amount,
            ).where(
                DebitNote.firm_id == firm_id,
                DebitNote.purchase_invoice_id.in_(invoice_ids),
                # Approval is what posts; a draft has not, a cancelled one is
                # gone.
                DebitNote.status == DebitNoteStatus.APPROVED.value,
                DebitNote.is_deleted.is_(False),
            )
        ).all():
            taken[invoice_id] = (
                taken.get(invoice_id, ZERO)
                + quantize_ledger(Decimal(str(taxable)))
                + quantize_ledger(Decimal(str(tax)))
            )
        for invoice_id, total in self._returned_by_goods(
            firm_id=firm_id, invoice_ids=invoice_ids
        ).items():
            taken[invoice_id] = taken.get(invoice_id, ZERO) + total
        return taken

    def _returned_by_goods(
        self, *, firm_id: UUID, invoice_ids: list[UUID]
    ) -> dict[UUID, Decimal]:
        """Sum what completed purchase returns sent back off each bill's lines."""
        from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

        return {
            invoice_id: Decimal(str(total))
            for invoice_id, total in self._session.execute(
                select(
                    PurchaseReturnLine.source_document_id,
                    func.coalesce(func.sum(PurchaseReturnLine.net_amount), 0),
                )
                .join(
                    PurchaseReturn,
                    PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
                )
                .where(
                    PurchaseReturnLine.firm_id == firm_id,
                    PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
                    PurchaseReturnLine.source_document_id.in_(invoice_ids),
                    PurchaseReturnLine.is_deleted.is_(False),
                    # Completing is what posts Dr payable; a draft or approved
                    # return has not moved anything yet, a cancelled one is gone.
                    PurchaseReturn.status.in_(("COMPLETED", "CLOSED")),
                    PurchaseReturn.is_deleted.is_(False),
                )
                .group_by(PurchaseReturnLine.source_document_id)
            ).all()
        }

    def list_settlements(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str = "",
        party_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[Settlement], int]:
        """Return one page of settlements, newest first.

        The search also matches the customer or supplier, and ``date_from`` /
        ``date_to`` bound the settlement date inclusively -- the Period filter
        every phase 2 list carries (owner, 2026-09-27).
        """
        statement = self._scoped(select(Settlement), firm_id)
        if party_id is not None:
            # A refund is a customer's as much as a receipt is; this compared
            # it with the vendor column, so a refund list never filtered.
            statement = statement.where(
                Settlement.vendor_id == party_id
                if self.DIRECTION == SettlementDirection.PAYMENT
                else Settlement.customer_id == party_id
            )
        if date_from is not None:
            statement = statement.where(Settlement.settlement_date >= date_from)
        if date_to is not None:
            statement = statement.where(Settlement.settlement_date <= date_to)
        if search.strip():
            pattern = f"%{search.strip()}%"
            party = (
                Settlement.vendor_id.in_(vendors_matching(pattern))
                if self.DIRECTION == SettlementDirection.PAYMENT
                else Settlement.customer_id.in_(customers_matching(pattern))
            )
            statement = statement.where(
                Settlement.settlement_number.ilike(pattern)
                | Settlement.instrument_reference.ilike(pattern)
                | party
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                Settlement.settlement_date.desc(),
                Settlement.settlement_number.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, settlement_id: UUID, *, firm_id: UUID) -> Settlement:
        """Return one settlement or raise when it is unavailable."""
        row = self._session.scalar(
            self._scoped(select(Settlement), firm_id).where(
                Settlement.id == settlement_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Settlement not found.")
        return row

    def allocations_for(self, settlement_id: UUID) -> Sequence[SettlementAllocation]:
        """Return the allocations of one settlement, oldest invoice first."""
        return self._session.scalars(
            select(SettlementAllocation)
            .where(
                SettlementAllocation.settlement_id == settlement_id,
                SettlementAllocation.is_deleted.is_(False),
            )
            .order_by(SettlementAllocation.created_at.asc())
        ).all()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(
        self, data: SettlementCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Settlement:
        """Record one settlement, allocate it, and post it to the ledger."""
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        is_refund = self.DIRECTION == SettlementDirection.REFUND
        tds_amount = quantize_ledger(data.tds_amount or ZERO)
        if is_refund and tds_amount > ZERO:
            # A refund hands back the customer's own money; nobody deducts
            # tax at source from returning it.
            raise ValidationError("A refund carries no tax deducted at source.")
        if is_refund and data.allocations:
            # A refund hands back what was never applied to a
            # document. Allocating it to one would claim it settled
            # something, when it did the opposite.
            raise ValidationError(
                "A refund returns money held on account, so it is not "
                "applied to an invoice."
            )
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        party = self._require_party(firm_id=firm_id, party_id=data.party_id)
        order = self._advance_order(data, firm_id=firm_id)
        amount = quantize_ledger(data.amount)
        allocated = self._validate_allocations(
            data, firm_id=firm_id, party_id=data.party_id, amount=amount
        )
        money_account_id = self._money_account(
            firm_id=firm_id, method=SettlementMethod(data.method.value)
        )
        # A taken number is stepped over rather than re-issued (D-FIN-9), and
        # a typed one is accepted only where the series allows it (D-CFG-2).
        number = self._issue_number(
            numbering_rule,
            typed=(
                data.settlement_number.strip().upper()
                if data.settlement_number
                else None
            ),
            number_column=Settlement.settlement_number,
            firm_id=firm_id,
            document_date=data.settlement_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )

        # Both directions of the link are set before either row is written:
        # the journal names the settlement as its source, and the settlement
        # names the journal it wrote. Inserting the settlement first with a
        # placeholder would leave a row referencing nothing if the posting
        # failed, which is the state this module exists to make impossible.
        settlement_id = uuid4()
        entry = (
            self._posting.post_customer_refund(
                firm_id=firm_id,
                settlement_id=settlement_id,
                settlement_number=number,
                settlement_date=data.settlement_date,
                amount=amount,
                money_account_id=money_account_id,
                actor_id=actor_id,
            )
            if is_refund
            else self._posting.post_settlement(
                firm_id=firm_id,
                settlement_id=settlement_id,
                settlement_number=number,
                settlement_date=data.settlement_date,
                amount=amount,
                is_receipt=is_receipt,
                money_account_id=money_account_id,
                actor_id=actor_id,
                tds_amount=tds_amount,
            )
        )
        row = Settlement(
            id=settlement_id,
            firm_id=firm_id,
            direction=self.DIRECTION.value,
            customer_id=data.party_id if is_receipt or is_refund else None,
            vendor_id=None if is_receipt or is_refund else data.party_id,
            settlement_number=number,
            settlement_date=data.settlement_date,
            amount=amount,
            tds_amount=tds_amount,
            tds_section=data.tds_section if tds_amount > ZERO else None,
            allocated_amount=allocated,
            unallocated_amount=amount - allocated,
            sales_order_id=None if order is None else order.id,
            method=data.method.value,
            ledger_account_id=money_account_id,
            instrument_reference=(
                data.instrument_reference.strip() if data.instrument_reference else None
            ),
            narration=data.narration,
            status=SettlementStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()

        opening_bills = self._opening_bill_ids(
            [item.invoice_id for item in data.allocations]
        )
        for allocation in data.allocations:
            opening = allocation.invoice_id in opening_bills
            self._session.add(
                SettlementAllocation(
                    firm_id=firm_id,
                    settlement_id=row.id,
                    **self._allocation_target(
                        allocation.invoice_id, is_receipt=is_receipt, opening=opening
                    ),
                    amount=quantize_ledger(allocation.amount),
                    # Applied with the money, so it met the bill the day the
                    # money arrived.
                    allocated_on=data.settlement_date,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

        if is_refund:
            # The receivable service holds the rule that a refund cannot
            # exceed the advance the customer is actually holding, and
            # refuses it by name.
            self._customers.post_receivable_transaction(
                data.party_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=(CustomerReceivableTransactionType.REFUND),
                    amount=amount,
                    transaction_date=data.settlement_date,
                    reference_type="settlement",
                    reference_id=row.id,
                    reference_number=number,
                    remarks=data.narration,
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
        if is_receipt:
            # Keep the customer's outstanding and advance balances in step, so
            # credit control keeps answering with the money already collected.
            # The receivable service decides for itself how much of a receipt
            # clears the balance and how much becomes an advance, which is the
            # one place that rule should live.
            self._customers.post_receivable_transaction(
                data.party_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.RECEIPT,
                    amount=amount,
                    transaction_date=data.settlement_date,
                    reference_type="settlement",
                    reference_id=row.id,
                    reference_number=number,
                    remarks=data.narration,
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
            # Tax collected at source is charged **here**, on the money, not
            # when the invoice was raised: section 206C(1H) says "at the time
            # of receipt of such amount". Staged rather than committed, so a
            # receipt that posts and a collection that does not cannot both
            # happen -- that would leave the buyer under-charged with nothing
            # on the record to say why. Nothing is charged unless the firm has
            # switched the section on and this buyer is past the threshold.
            TcsService(self._session).stage_collection(
                row, firm_id=firm_id, actor_id=actor_id
            )

        record_audit(
            self._session,
            action=f"settlement.{self.DIRECTION.value.lower()}.recorded",
            entity_type="settlement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "settlement_number": number,
                "amount": str(amount),
                "tds_amount": str(tds_amount),
                "tds_section": data.tds_section if tds_amount > ZERO else None,
                "allocated_amount": str(allocated),
                "party": party.code,
            },
        )
        self._session.flush()
        if is_receipt:
            stage_document_event(
                self._session,
                "RECEIPT_POSTED",
                MessagingDocument(
                    document_type="RECEIPT",
                    document_id=row.id,
                    document_number=row.settlement_number,
                    document_date=row.settlement_date,
                    customer_id=row.customer_id,
                    amount=row.amount,
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
        return row

    def order_number_of(self, row: Settlement) -> str | None:
        """Return the order a receipt came in against, by number."""
        if row.sales_order_id is None:
            return None
        order = self._session.get(SalesOrder, row.sales_order_id)
        return None if order is None else order.order_number

    def _advance_order(
        self, data: SettlementCreate, *, firm_id: UUID
    ) -> SalesOrder | None:
        """Return the order this money came in against, if one was named.

        Refused where it is not this firm's, or not this customer's: an advance
        filed against somebody else's order answers "what has this customer
        paid us for order X" with another customer's money.

        A payment to a vendor has no sales order behind it, so naming one is
        refused rather than quietly ignored -- a field that is accepted and
        discarded is worse than one that is not accepted at all.

        Args:
            data: The settlement being recorded.
            firm_id: The owning firm.

        Returns:
            The order, or None where none was named.

        Raises:
            ValidationError: If the order is not the customer's, or this is not
                a receipt.
            ResourceNotFoundError: If the order is not this firm's.

        """
        if data.sales_order_id is None:
            return None
        if self.DIRECTION != SettlementDirection.RECEIPT:
            raise ValidationError(
                "Only a receipt can be recorded against a sales order."
            )
        order = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == data.sales_order_id,
                SalesOrder.firm_id == firm_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Sales order not found.")
        if order.customer_id != data.party_id:
            raise ValidationError("That sales order belongs to a different customer.")
        return order

    def _advance_part_of(self, row: Settlement, *, allocating: Decimal) -> Decimal:
        """Return how much of this allocation comes out of the advance.

        A receipt splits when it is recorded: `min(amount, outstanding)` comes
        straight off what the customer owes, and only the excess becomes an
        advance. The receivable row it wrote remembers the split, and it is
        the only thing that does.

        So allocating to an invoice has two halves. The part covered by what
        already came off the balance needs **no** receivable transaction --
        the balance moved when the money arrived, and moving it again would
        take the same rupees off twice. Only the part drawn from the advance
        posts `ADVANCE_APPLY`, which is what that type is for.

        In the ordinary case -- a deposit taken while the customer already
        owed something -- the answer is zero, and the allocation is purely a
        statement about which invoice the money cleared.

        Args:
            row: The receipt being allocated.
            allocating: How much of it is being set against an invoice now.

        Returns:
            The part that must come out of the advance, never negative.

        """
        original = self._recording_row(row)
        if original is None:
            # Nothing recorded the split, so nothing can be claimed about it.
            # Treating it as advance would risk the double count this method
            # exists to avoid.
            return ZERO
        off_the_balance = quantize_ledger(-Decimal(str(original.outstanding_delta)))
        if off_the_balance <= ZERO:
            # The whole receipt became an advance.
            return quantize_ledger(allocating)
        already = quantize_ledger(row.allocated_amount)
        remaining = off_the_balance - already
        if remaining >= allocating:
            return ZERO
        return quantize_ledger(allocating - max(remaining, ZERO))

    def allocate(
        self,
        settlement_id: UUID,
        *,
        invoice_id: UUID,
        amount: Decimal,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Settlement:
        """Set money already moved against an invoice raised since.

        The missing half of an advance. `ADVANCE_APPLY` has been a declared
        receivable transaction type since the module shipped and **nothing
        could reach it**: a deposit taken before the bill existed sat on the
        customer's account with no way to say which bill it settled.

        **Both directions.** A supplier advance is the same fact the other way
        round -- money paid before the bill arrived -- and it had the same
        hole: a payment recorded with no allocation could never be set against
        one afterwards, so the supplier's account showed a bill owed in full
        beside cash they had already been sent (D-BUY-8). A refund is still
        refused: handing money back is the opposite of settling a document.

        **Nothing is posted to the general ledger, and that is correct.** The
        receipt already debited cash and credited receivables; the invoice
        already debited receivables and credited revenue and tax. Applying the
        advance changes no account -- it decides which invoice the receivable
        credit belongs to, which is the subsidiary ledger's business. A journal
        here would count the money twice. The payment side is the mirror of
        that, and there is no vendor balance to move either: the firm keeps no
        running payable per vendor, so what a bill still owes is derived from
        its allocations exactly as it is for a customer.

        Args:
            settlement_id: The settlement holding the money.
            invoice_id: The invoice to set it against.
            amount: How much of it.
            firm_id: The owning firm.
            actor_id: The user applying it.

        Returns:
            The settlement, with its allocated and unallocated figures moved.

        Raises:
            ValidationError: If the settlement is reversed or a refund, holds
                less than was asked for, or the invoice is not this party's or
                owes less.

        """
        row = self.get(settlement_id, firm_id=firm_id)
        if row.status == SettlementStatus.REVERSED.value:
            raise ValidationError(
                f"{row.settlement_number} has been reversed and holds nothing."
            )
        is_receipt = row.direction == SettlementDirection.RECEIPT.value
        if row.direction == SettlementDirection.REFUND.value:
            raise ValidationError(
                "A refund returns money held on account, so it is not "
                "applied to an invoice."
            )
        asked = quantize_ledger(amount)
        if asked <= ZERO:
            raise ValidationError("An allocation must be for more than nothing.")
        if asked > quantize_ledger(row.unallocated_amount):
            raise ValidationError(
                f"{row.settlement_number} has only "
                f"{quantize_ledger(row.unallocated_amount)} left unapplied."
            )
        party_id = row.customer_id if is_receipt else row.vendor_id
        if party_id is None:  # pragma: no cover - direction guarantees it
            raise ValidationError("This settlement names no party to apply it for.")
        outstanding = {
            record.invoice_id: record
            for record in self.outstanding_invoices(firm_id=firm_id, party_id=party_id)
        }
        record = outstanding.get(invoice_id)
        if record is None:
            raise ValidationError(
                f"That invoice does not belong to this "
                f"{'customer' if is_receipt else 'supplier'}, is not "
                "approved, or is already settled in full."
            )
        if asked > record.outstanding_amount:
            raise ValidationError(
                f"{record.invoice_number} owes only {record.outstanding_amount}."
            )
        opening = record.is_opening_bill
        invoice_column = (
            (
                SettlementAllocation.customer_opening_bill_id
                if opening
                else SettlementAllocation.sales_invoice_id
            )
            if is_receipt
            else (
                SettlementAllocation.vendor_opening_bill_id
                if opening
                else SettlementAllocation.purchase_invoice_id
            )
        )
        existing = self._session.scalar(
            select(SettlementAllocation).where(
                SettlementAllocation.settlement_id == row.id,
                invoice_column == invoice_id,
                SettlementAllocation.is_deleted.is_(False),
            )
        )
        if existing is not None:
            # The unique key refuses it anyway; saying so in the language of
            # the request beats a constraint violation.
            raise ValidationError(
                f"{row.settlement_number} is already applied to "
                f"{record.invoice_number}."
            )
        self._session.add(
            SettlementAllocation(
                firm_id=firm_id,
                settlement_id=row.id,
                **self._allocation_target(
                    invoice_id, is_receipt=is_receipt, opening=opening
                ),
                amount=asked,
                # The day the money met the bill: the bill's own date, or the
                # receipt's where the receipt came later. Not today, which
                # would put the collection in whichever month the clerk got
                # round to applying it -- and it is the date the ADVANCE_APPLY
                # row below already carries, so the customer's ledger and the
                # commission report read the same day (D-TER-6).
                allocated_on=max(row.settlement_date, record.invoice_date),
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        # Only a receipt has a party balance behind it. The firm keeps a
        # running receivable per customer and nothing of the sort per vendor,
        # so a payment's allocation is purely the statement about which bill
        # the money cleared.
        from_advance = (
            self._advance_part_of(row, allocating=asked) if is_receipt else ZERO
        )
        row.allocated_amount = quantize_ledger(row.allocated_amount + asked)
        row.unallocated_amount = quantize_ledger(row.unallocated_amount - asked)
        row.updated_by = actor_id
        if from_advance > ZERO and row.customer_id is not None:
            # Only the part that actually became an advance. The rest of the
            # receipt already reduced what the customer owes -- posting
            # ADVANCE_APPLY for it would take the same money off the balance
            # twice. Found by driving it: a deposit taken while the customer
            # owed money creates no advance at all, and the whole allocation
            # was refused with "exceeds unapplied advance".
            self._customers.post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.ADVANCE_APPLY,
                    amount=from_advance,
                    transaction_date=record.invoice_date,
                    reference_type="settlement",
                    reference_id=row.id,
                    reference_number=row.settlement_number,
                    remarks=f"Applied to {record.invoice_number}.",
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
        record_audit(
            self._session,
            action=f"settlement.{row.direction.lower()}.allocated",
            entity_type="settlement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "settlement_number": row.settlement_number,
                "invoice_number": record.invoice_number,
                "amount": str(asked),
                "unallocated_amount": str(row.unallocated_amount),
            },
        )
        self._session.commit()
        return row

    def reverse(
        self,
        settlement_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> Settlement:
        """Take a settlement back, in the ledger and on the party's account.

        Nothing is edited or deleted. A mirror journal cancels the original,
        the allocations stop clearing their invoices, and where the settlement
        moved the customer's outstanding and advance balances they are put back
        by the exact amounts it moved them -- read from the transaction row it
        wrote, not recomputed. A receipt of 500 against an outstanding 300
        became 300 off the balance and 200 of advance, and only that row
        remembers the split.

        **A refund moves that balance too** and is undone the same way. It was
        excluded until 2026-08-22, which was invisible only because no endpoint
        exposed it: `create` posts a receivable transaction for a refund as
        well as for a receipt -- a refund hands back an advance, so the advance
        has to come back when the refund is taken back. Reversing the journal
        alone would have left the ledger right and the customer's advance short
        by the refunded amount. A payment faces a vendor and writes no
        receivable transaction, so there is nothing to put back.

        Args:
            settlement_id: The settlement to take back.
            firm_id: The owning firm.
            actor_id: The user reversing it.
            reason: Why, kept on the record.

        Returns:
            The reversed settlement.

        Raises:
            ValidationError: If it is already reversed, or the customer has
                traded since in a way that makes the undo impossible.

        """
        row = self.get(settlement_id, firm_id=firm_id)
        if row.status == SettlementStatus.REVERSED.value:
            raise ValidationError(f"{row.settlement_number} has already been reversed.")
        mirror = self._journals.reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.settlement_number}-REV",
            actor_id=actor_id,
        )
        if self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        ):
            # Every row the settlement wrote, newest first: the receipt's own
            # and one `ADVANCE_APPLY` per later application of its advance
            # (D-SELL-8). Taking "the" row with `scalar()` picked one of them
            # at random -- undoing the receipt alone put back an advance the
            # application had already spent, and was refused as overtaken, so
            # a bounced cheque that had been applied could never be taken
            # back; undoing the application alone left the balance out of
            # step with 1100 by the whole receipt. The applications are undone
            # first because they are later, and undoing them returns the
            # advance the receipt's own reversal then takes away.
            for written in self._rows_written_by(row):
                self._customers.reverse_receivable_transaction(
                    written.id,
                    firm_scope=firm_id,
                    actor_id=actor_id,
                    reference_number=f"{row.settlement_number}-REV",
                    remarks=reason,
                    commit=False,
                    on=mirror.journal_date,
                )
        if self.DIRECTION == SettlementDirection.RECEIPT:
            # The money is going back, so the tax collected on it goes back
            # too. Mirrored rather than deleted: a quarterly return may
            # already have reported it.
            TcsService(self._session).stage_reversal(
                row, firm_id=firm_id, actor_id=actor_id
            )
        row.status = SettlementStatus.REVERSED.value
        row.reversal_journal_entry_id = mirror.id
        row.reversed_at = utc_now()
        row.reversed_by = actor_id
        row.reversal_reason = reason
        row.updated_by = actor_id
        record_audit(
            self._session,
            action=f"settlement.{self.DIRECTION.value.lower()}.reversed",
            entity_type="settlement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": SettlementStatus.POSTED.value},
            after_data={
                "status": SettlementStatus.REVERSED.value,
                "reversal_journal_entry_id": str(mirror.id),
                "reason": reason,
            },
        )
        self._session.flush()
        return row

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _allocation_target(
        invoice_id: UUID, *, is_receipt: bool, opening: bool
    ) -> dict[str, UUID | None]:
        """Say which of the four bill columns an allocation fills.

        A sales invoice or a customer's opening bill for a receipt, a purchase
        invoice or a supplier's opening bill for a payment -- exactly one.
        """
        return {
            "sales_invoice_id": invoice_id if is_receipt and not opening else None,
            "customer_opening_bill_id": invoice_id if is_receipt and opening else None,
            "purchase_invoice_id": (
                invoice_id if not is_receipt and not opening else None
            ),
            "vendor_opening_bill_id": (
                invoice_id if not is_receipt and opening else None
            ),
        }

    def _rows_written_by(self, row: Settlement) -> list[CustomerReceivableTransaction]:
        """Return the receivable rows a settlement wrote, to be undone in order.

        The row written when it was recorded comes last; every `ADVANCE_APPLY`
        an allocation added since comes before it, newest first.
        """
        written = self._session.scalars(
            select(CustomerReceivableTransaction)
            .where(
                CustomerReceivableTransaction.reference_type == "settlement",
                CustomerReceivableTransaction.reference_id == row.id,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
            .order_by(
                CustomerReceivableTransaction.created_at.desc(),
                CustomerReceivableTransaction.id.desc(),
            )
        ).all()
        applied = CustomerReceivableTransactionType.ADVANCE_APPLY.value
        return sorted(written, key=lambda item: item.transaction_type != applied)

    def _recording_row(self, row: Settlement) -> CustomerReceivableTransaction | None:
        """Return the receivable row written when the settlement was recorded.

        Not an `ADVANCE_APPLY` a later allocation added beside it: only the
        recording row remembers how the money split between balance and
        advance.
        """
        written = self._rows_written_by(row)
        if not written:
            return None
        last = written[-1]
        applied = CustomerReceivableTransactionType.ADVANCE_APPLY.value
        return None if last.transaction_type == applied else last

    def _scoped(
        self, statement: Select[tuple[Settlement]], firm_id: UUID
    ) -> Select[tuple[Settlement]]:
        """Restrict a query to this firm, this direction and live rows."""
        return statement.where(
            Settlement.firm_id == firm_id,
            Settlement.direction == self.DIRECTION.value,
            Settlement.is_deleted.is_(False),
        )

    def _require_party(self, *, firm_id: UUID, party_id: UUID) -> Customer | Vendor:
        """Return the customer or vendor this settlement is with."""
        if self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        ):
            customer = self._session.scalar(
                select(Customer).where(
                    Customer.id == party_id,
                    Customer.firm_id == firm_id,
                    Customer.is_deleted.is_(False),
                )
            )
            if customer is None:
                raise ResourceNotFoundError("Customer not found.")
            return customer
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == party_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ResourceNotFoundError("Vendor not found.")
        return vendor

    def parties(
        self,
        *,
        firm_id: UUID,
        search: str = "",
        page: int = 1,
        page_size: int = MAX_PAGE_SIZE,
    ) -> list[tuple[UUID, str, str]]:
        """List the parties this direction can settle with, by code.

        Id, code and name -- nothing else. See `SettlementPartyRecord` for why
        this exists rather than the money screens reading the customer or
        vendor master: a cashier holds the receipt permissions and not
        `CUSTOMER_VIEW`, so reading the master made the wrong code the gate on
        taking money.

        Ordered by code because that is what the picker shows, and read a
        page at a time. It used to stop at the first 200 by code, so a firm
        with more could not take money from the rest from the desktop at all
        (D-SELL-18); the client now reads every page.

        Args:
            firm_id: The firm whose parties to list.
            search: Match against code or name, case-insensitively.
            page: Which page, from 1.
            page_size: How many to a page.

        Returns:
            One page of parties as (id, code, name), in code order.

        """
        is_customer = self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        )
        model: type[Customer] | type[Vendor] = Customer if is_customer else Vendor
        statement = select(model.id, model.code, model.name).where(
            model.firm_id == firm_id,
            model.is_deleted.is_(False),
        )
        if search.strip():
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(model.code.ilike(pattern), model.name.ilike(pattern))
            )
        rows = self._session.execute(
            statement.order_by(model.code.asc(), model.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [(row[0], row[1], row[2]) for row in rows]

    def _money_account(self, *, firm_id: UUID, method: SettlementMethod) -> UUID:
        """Return the cash or bank account this method moves money through.

        `resolve` refuses with a message naming the purpose when the firm has
        not mapped one, which is the right failure: money cannot be recorded
        as arriving somewhere the firm has not said exists.
        """
        return self._controls.resolve(firm_id, METHOD_PURPOSE[method])

    def _validate_allocations(
        self,
        data: SettlementCreate,
        *,
        firm_id: UUID,
        party_id: UUID,
        amount: Decimal,
    ) -> Decimal:
        """Check every allocation and return the total allocated.

        Three things can be wrong, and each of them writes a lie into the
        books if it is let through: allocating more than arrived, allocating to
        somebody else's invoice, and allocating more to an invoice than is left
        owing on it.
        """
        if not data.allocations:
            return ZERO
        outstanding = {
            record.invoice_id: record
            for record in self.outstanding_invoices(firm_id=firm_id, party_id=party_id)
        }
        total = ZERO
        for allocation in data.allocations:
            record = outstanding.get(allocation.invoice_id)
            if record is None:
                raise ValidationError(
                    "An allocated invoice does not belong to this party, is "
                    "not approved, or is already settled in full."
                )
            allocated = quantize_ledger(allocation.amount)
            if allocated > record.outstanding_amount:
                raise ValidationError(
                    f"Invoice {record.invoice_number} has "
                    f"{record.outstanding_amount} outstanding, so "
                    f"{allocated} cannot be allocated to it."
                )
            total += allocated
        if total > amount:
            raise ValidationError(
                f"Allocations total {total}, which is more than the "
                f"{amount} that moved."
            )
        return total

    def ledger_account_name(self, account_id: UUID) -> str:
        """Return the name of the account money moved through."""
        name = self._session.scalar(
            select(LedgerAccount.name).where(LedgerAccount.id == account_id)
        )
        return name or ""

    def party_of(self, row: Settlement) -> Customer | Vendor:
        """Return the party of one settlement, for the response."""
        party_id = (
            row.customer_id
            if self.DIRECTION
            in (SettlementDirection.RECEIPT, SettlementDirection.REFUND)
            else row.vendor_id
        )
        if party_id is None:  # pragma: no cover - the check constraint forbids it
            raise ValidationError("Settlement has no party.")
        return self._require_party(firm_id=row.firm_id, party_id=party_id)

    def parties_of(
        self, rows: Sequence[Settlement]
    ) -> dict[UUID, tuple[UUID, str, str]]:
        """Answer `party_of` for a page of settlements in one read.

        Keyed by settlement id: the party's id, code and name. A party that
        `party_of` would refuse -- another firm's, or deleted since -- is
        refused the same way, so a page and a single row cannot disagree.
        """
        is_customer = self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        )
        model: type[Customer] | type[Vendor] = Customer if is_customer else Vendor
        wanted = {
            row.id: (row.firm_id, row.customer_id if is_customer else row.vendor_id)
            for row in rows
        }
        found = {
            (firm_id, party_id): (party_id, code, name)
            for party_id, firm_id, code, name in self._session.execute(
                select(model.id, model.firm_id, model.code, model.name).where(
                    model.id.in_(
                        {party for _, party in wanted.values() if party is not None}
                    ),
                    model.is_deleted.is_(False),
                )
            )
        }
        answer: dict[UUID, tuple[UUID, str, str]] = {}
        for settlement_id, key in wanted.items():
            if key[1] is None:  # pragma: no cover - the check constraint forbids it
                raise ValidationError("Settlement has no party.")
            party = found.get(key)
            if party is None:
                raise ResourceNotFoundError(
                    "Customer not found." if is_customer else "Vendor not found."
                )
            answer[settlement_id] = party
        return answer

    def allocations_for_many(
        self, settlement_ids: Sequence[UUID]
    ) -> dict[UUID, list[SettlementAllocation]]:
        """Answer `allocations_for` for a page of settlements in one read."""
        return children_by_parent(
            self._session,
            SettlementAllocation,
            SettlementAllocation.settlement_id,
            settlement_ids,
            SettlementAllocation.created_at.asc(),
        )

    def order_numbers_of(self, rows: Sequence[Settlement]) -> dict[UUID, str]:
        """Answer `order_number_of` for a page, keyed by order id."""
        wanted = {row.sales_order_id for row in rows if row.sales_order_id}
        if not wanted:
            return {}
        return {
            found[0]: found[1]
            for found in self._session.execute(
                select(SalesOrder.id, SalesOrder.order_number).where(
                    SalesOrder.id.in_(wanted)
                )
            )
        }

    def ledger_account_names(self, account_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Answer `ledger_account_name` for a page, keyed by account id."""
        if not account_ids:
            return {}
        return {
            found[0]: found[1] or ""
            for found in self._session.execute(
                select(LedgerAccount.id, LedgerAccount.name).where(
                    LedgerAccount.id.in_(set(account_ids))
                )
            )
        }

    def invoice_summaries(
        self, allocations: Sequence[SettlementAllocation]
    ) -> dict[UUID, tuple[str, object, Decimal]]:
        """Return number, date and total for every allocated invoice."""
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        invoice = SalesInvoice if is_receipt else PurchaseInvoice
        ids = [
            (
                allocation.sales_invoice_id
                if is_receipt
                else allocation.purchase_invoice_id
            )
            for allocation in allocations
        ]
        wanted = [value for value in ids if value is not None]
        summaries: dict[UUID, tuple[str, object, Decimal]] = {}
        if wanted:
            rows = self._session.execute(
                select(
                    invoice.id,
                    invoice.invoice_number,
                    invoice.invoice_date,
                    invoice.grand_total,
                ).where(invoice.id.in_(wanted))
            ).all()
            summaries = {
                row[0]: (row[1], row[2], quantize_ledger(row[3])) for row in rows
            }
        opening_ids = [
            allocation.vendor_opening_bill_id
            for allocation in allocations
            if allocation.vendor_opening_bill_id is not None
        ]
        if opening_ids:
            for bill in self._session.scalars(
                select(VendorOpeningBill).where(VendorOpeningBill.id.in_(opening_ids))
            ).all():
                summaries[bill.id] = (
                    opening_bill_label(bill),
                    bill.bill_date,
                    quantize_ledger(bill.amount),
                )
        customer_ids = [
            allocation.customer_opening_bill_id
            for allocation in allocations
            if allocation.customer_opening_bill_id is not None
        ]
        if customer_ids:
            for customer_bill in self._session.scalars(
                select(CustomerOpeningBill).where(
                    CustomerOpeningBill.id.in_(customer_ids)
                )
            ).all():
                summaries[customer_bill.id] = (
                    customer_opening_bill_label(customer_bill),
                    customer_bill.bill_date,
                    quantize_ledger(customer_bill.amount),
                )
        return summaries


class RefundService(SettlementService):
    """Money handed back to a customer.

    Money out, like a payment, and about a customer, like a receipt -- which is
    why it is neither. It returns what a customer paid in advance rather than
    settling anything owed to a supplier, so it touches receivables and not
    payables, and it is not applied to an invoice.
    """

    DIRECTION = SettlementDirection.REFUND
    DOCUMENT = DocumentTypeSpec(
        code="CUSTOMER_REFUND",
        name="Customer Refund",
        description="Money returned to a customer",
        category="FINANCE",
        module="settlements",
        prefix="RF",
        states=(DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),),
    )


class ReceiptService(SettlementService):
    """Money arriving from a customer."""

    DIRECTION = SettlementDirection.RECEIPT
    DOCUMENT = DocumentTypeSpec(
        code="RECEIPT",
        name="Receipt",
        description="Money received from a customer",
        category="FINANCE",
        module="settlements",
        prefix="RC",
        states=(DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),),
    )


class PaymentService(SettlementService):
    """Money going out to a vendor."""

    DIRECTION = SettlementDirection.PAYMENT
    DOCUMENT = DocumentTypeSpec(
        code="PAYMENT",
        name="Payment",
        description="Money paid to a vendor",
        category="FINANCE",
        module="settlements",
        prefix="PY",
        states=(DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),),
    )
