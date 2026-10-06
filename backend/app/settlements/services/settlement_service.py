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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy import null as sa_null
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_day_after
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
from app.finance.currency import (
    check_currency,
    is_foreign,
    normalize_currency,
    rupee_rate,
    rupee_rate_sql,
    to_base,
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
from app.settlements.services.customer_credits import (
    absorb_credit_no_longer_given,
    credit_applied_to_bills,
    draw_refund_on_credits,
    drawn_back_onto_bills,
    release_refund_draws,
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
def debited_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
) -> dict[UUID, Decimal]:
    """Sum what approved debit notes have added to each sales invoice.

    A customer debit note is owed **on the invoice it names** (backlog 77
    row 5, OWNER_DECISIONS A40), as TallyPrime's against-reference debit note
    is: a receipt allocated to the invoice settles it and the ageing ages it
    from the invoice's due date. Each note is rounded to the ledger's two
    decimals the way its journal and receivable row were -- the taxable value
    and the tax each, then summed.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about; None asks about every
            invoice of the firm in one grouped read.
        as_of: Count only notes dated on or before this day; None counts
            everything.

    Returns:
        The debited amount per invoice, for those with any.

    """
    if invoice_ids is not None and not invoice_ids:
        return {}
    # Imported here, as the credit note is in `credited_against`.
    from app.customer_debit_note.models import (
        CustomerDebitNote,
        CustomerDebitNoteStatus,
    )

    debited: dict[UUID, Decimal] = {}
    for invoice_id, taxable, tax in session.execute(
        select(
            CustomerDebitNote.sales_invoice_id,
            CustomerDebitNote.taxable_amount,
            CustomerDebitNote.tax_amount,
        ).where(
            CustomerDebitNote.firm_id == firm_id,
            *_among(CustomerDebitNote.sales_invoice_id, invoice_ids),
            # Approval is what posts; a draft has not, a cancelled one is gone.
            CustomerDebitNote.status == CustomerDebitNoteStatus.APPROVED.value,
            CustomerDebitNote.is_deleted.is_(False),
            *(() if as_of is None else (CustomerDebitNote.debit_note_date <= as_of,)),
        )
    ).all():
        debited[invoice_id] = (
            debited.get(invoice_id, ZERO)
            + quantize_ledger(Decimal(str(taxable)))
            + quantize_ledger(Decimal(str(tax)))
        )
    return debited


def _returns_off_bills(
    firm_id: UUID, invoice_ids: Sequence[UUID] | None, as_of: date | None
) -> tuple[Any, ...]:
    """Return the test for a return line that has taken something off a bill.

    The one statement of which returns count against a sales invoice, read by
    ``credited_against`` for the money and by ``returned_units_against`` for
    the units, so a commission paid on value and one paid per unit cannot
    disagree about whether the same goods came back (D-PRC-59).

    This is the half that names its bill: a return raised from the bill's own
    lines. The other half -- a return raised off the delivery note after the
    bill exists -- names no bill and is set against the bills that charged
    its units by ``returns_off_notes_against`` (D-PRC-66); both readers add
    the two. Completing is what posts Cr receivable; a draft or approved
    return has not moved anything yet, and a cancelled one is gone.
    """
    # Imported here: both modules import settlement-adjacent models.
    from app.sales_return.models import SalesReturn, SalesReturnLine

    return (
        SalesReturnLine.firm_id == firm_id,
        SalesReturnLine.source_document_type == "SALES_INVOICE",
        *_among(SalesReturnLine.source_document_id, invoice_ids),
        SalesReturnLine.is_deleted.is_(False),
        SalesReturn.status.in_(("COMPLETED", "CLOSED")),
        SalesReturn.is_deleted.is_(False),
        *(() if as_of is None else (SalesReturn.return_date <= as_of,)),
    )


@dataclass(frozen=True)
class ReturnedUnits:
    """The charged units one return line took off a bill line."""

    #: In the bill line's own unit, at four places.
    quantity: Decimal
    #: What was typed, where that was another unit; else None.
    entered: Decimal | None
    #: How many of the bill line's unit one typed unit is.
    factor: Decimal

    def in_units_of(self, per_line_unit: Decimal) -> Decimal:
        """Restate the return in a unit the bill line's unit holds so many of.

        Worked from what was typed where there is one, at the factor's full
        ten places, so seven pieces of a box of twelve are seven and not
        6.9996.

        Args:
            per_line_unit: How many of the wanted unit one of the bill
                line's unit is -- twelve pieces to the box.

        Returns:
            The units, at the four places a quantity is kept to.

        """
        if self.entered is not None and self.factor > ZERO:
            units = self.entered * self.factor * per_line_unit
        else:
            units = self.quantity * per_line_unit
        return units.quantize(Decimal("0.0001"))


@over_chunks("invoice_ids")
def returned_units_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
) -> dict[UUID, list[ReturnedUnits]]:
    """List the charged units returns have taken off each sales invoice line.

    The units behind the money ``credited_against`` sums, by the same test
    (``_returns_off_bills``): what a per-unit commission stops paying on.
    Free goods beside them were never charged and are not counted, and a
    credit note is not here at all -- it credits value and moves no goods,
    and the quantity it states is a description, not what it is worked from.

    Each entry is in the **bill line's own unit** with, where the return was
    typed in another unit, what was typed and the factor that restates it:
    seven pieces of a line sold by the box are stored as 0.5833 of a box,
    and 0.5833 of twelve is not seven. ``ReturnedUnits.in_units_of`` is the
    one place that is worked out.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about; None asks about every
            invoice of the firm.
        as_of: Count only returns dated on or before this day.

    Returns:
        The returns per invoice **line** id, for the lines with any.

    """
    if invoice_ids is not None and not invoice_ids:
        return {}
    from app.sales_return.models import SalesReturn, SalesReturnLine

    answer: dict[UUID, list[ReturnedUnits]] = {}
    for line_id, quantity, entered, factor in session.execute(
        select(
            SalesReturnLine.source_document_line_id,
            SalesReturnLine.current_return_quantity,
            SalesReturnLine.entered_quantity,
            SalesReturnLine.conversion_factor,
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(*_returns_off_bills(firm_id, invoice_ids, as_of))
    ).all():
        answer.setdefault(line_id, []).append(
            ReturnedUnits(
                quantity=Decimal(str(quantity or 0)),
                entered=None if entered is None else Decimal(str(entered)),
                factor=Decimal(str(factor or 0)),
            )
        )
    # And the units that came back off the delivery note, on the bill lines
    # that charged them (D-PRC-66): 7 of 24 back off the note took nothing
    # off a 2.50-a-unit commission where the same return off the bill took
    # 17.50.
    from app.sales_return.billing import returns_off_notes_against

    for share in returns_off_notes_against(
        session, firm_id=firm_id, invoice_ids=invoice_ids, as_of=as_of
    ):
        answer.setdefault(share.bill_line_id, []).append(
            ReturnedUnits(
                quantity=share.quantity.quantize(Decimal("0.0001")),
                entered=share.entered,
                factor=share.factor,
            )
        )
    return answer


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
    receivable, so the ledger already says the customer owes less. A return
    raised from the bill's own lines names the bill; one raised from a
    delivery note is set against the bills that charged its units
    (``returns_off_notes_against``, D-PRC-66), and one off a note nobody has
    billed credits nothing and counts against nothing. A credit note is
    always raised against one invoice. A return's header figures -- its
    ``additional_charges`` and ``round_off``, which credit the customer and
    are in no line -- come off the bills its goods were charged on too
    (``header_credits_against``, D-PRC-74).

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
        .where(*_returns_off_bills(firm_id, invoice_ids, as_of))
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
    # What came back off a delivery note, on the bills that charged those
    # units (D-PRC-66): such a return credits the customer and reverses the
    # bill's tax, and the bill went on reading wholly outstanding.
    from app.sales_return.billing import (
        header_credits_against,
        returns_off_notes_against,
    )

    off_notes: dict[UUID, Decimal] = {}
    shares = returns_off_notes_against(
        session, firm_id=firm_id, invoice_ids=invoice_ids, as_of=as_of
    )
    for share in shares:
        off_notes[share.invoice_id] = off_notes.get(share.invoice_id, ZERO) + share.net
    # And what those returns gave back on their header: additional charges
    # and round-off credit the customer and are in no line, so a bill
    # returned in full with its 100.00 of charges went on reading 100.00
    # outstanding and took a receipt nobody owed (D-PRC-74).
    headers = header_credits_against(
        session,
        firm_id=firm_id,
        invoice_ids=invoice_ids,
        as_of=as_of,
        worked_out=[share for share in shares if not share.placed],
    )
    for invoice_id, total in (
        *returned,
        *notes,
        *off_notes.items(),
        *headers.items(),
    ):
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
    drawn_back: bool = True,
) -> dict[UUID, Decimal]:
    """Sum everything that has come off each sales invoice.

    Money allocated from a posted receipt, points spent on the bill, the
    returns and credit notes raised against it (``credited_against``) and the
    credit of another bill's return or credit note set against it
    (``credit_applied_to_bills``, D-PRC-75), less what approved debit notes
    added to it (``debited_against``). Each
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
        drawn_back: False leaves out what goes back on a bill whose own
            return's credit was used elsewhere (``drawn_back_onto_bills``),
            which is itself worked out from this reading.

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
                Settlement.reversed_at >= firm_day_after(session, firm_id, as_of),
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
    # And the credit a return or credit note left on a bill already paid,
    # set against this one (D-PRC-75): it posts nothing and settles the bill
    # exactly as money allocated to it does.
    for invoice_id, amount in credit_applied_to_bills(
        session, firm_id=firm_id, bill_ids=invoice_ids, as_of=as_of
    ).items():
        settled[invoice_id] = settled.get(invoice_id, ZERO) + amount
    # Less what goes back on a bill whose own return's credit was used
    # elsewhere and which has since come to owe more again -- its receipt
    # reversed -- so the same credit is not counted on two bills.
    if drawn_back:
        for invoice_id, amount in drawn_back_onto_bills(
            session, firm_id=firm_id, invoice_ids=invoice_ids
        ).items():
            settled[invoice_id] = settled.get(invoice_id, ZERO) - amount
    # And what an approved party adjustment -- a write-off or a set-off --
    # took off the bill (backlog 74 row 2). Imported here: that module reads
    # these services.
    from app.party_adjustments.services.allocations import adjusted_against

    for invoice_id, amount in adjusted_against(
        session,
        firm_id=firm_id,
        column="sales_invoice_id",
        bill_ids=invoice_ids,
        as_of=as_of,
    ).items():
        settled[invoice_id] = settled.get(invoice_id, ZERO) + amount
    # A debit note runs the other way: it added to the bill, so it counts
    # against what has come off it. Netted here rather than added to every
    # caller's bill total, so the one derivation stays the one answer -- a
    # bill with a debit note and nothing paid reads as settled below zero, and
    # a caller showing "allocated" asks `debited_against` to split the two.
    for invoice_id, amount in debited_against(
        session, firm_id=firm_id, invoice_ids=invoice_ids, as_of=as_of
    ).items():
        settled[invoice_id] = settled.get(invoice_id, ZERO) - amount
    return settled


@dataclass(frozen=True, slots=True)
class _ForeignPart:
    """One bill's share of a payment in its currency (PG-12)."""

    #: What the share cleared in the bill's currency.
    currency_amount: Decimal
    #: The rupees paid for it at the payment's rate.
    paid: Decimal
    #: What it took off the bill's rupee value, at the bill's rate.
    base: Decimal


@dataclass(frozen=True, slots=True)
class _ForeignPayment:
    """A payment in a supplier's currency, worked out in rupees (PG-12)."""

    #: What left the bank: the amount at the payment's rate.
    rupees: Decimal
    #: Rupees paid less the bills' rupee value cleared: a loss above zero.
    difference: Decimal
    parts: dict[UUID, _ForeignPart]


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
        # A supplier's bill in another currency comes off at its own rupee
        # value, not at the rupees paid (PG-12): ``base_amount``, where the
        # allocation has one. Its own currency comes off by what was
        # allocated in it.
        allocated = (
            select(
                allocation_column.label("invoice_id"),
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            SettlementAllocation.base_amount,
                            SettlementAllocation.amount,
                        )
                    ),
                    0,
                ).label("total"),
                func.coalesce(func.sum(SettlementAllocation.currency_amount), 0).label(
                    "currency_total"
                ),
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
        # A bill its allocations alone already cover owes nothing, whatever
        # else is known of it: points, returns, credit notes, write-offs and
        # a supplier return only ever take more off. Only a debit note to a
        # customer adds to a bill, so a bill one names is always read. Left
        # in SQL, two years of paid bills never reach Python -- they were
        # nine in ten of Customer Outstanding's rows (PLT-4).
        # What the bill is worth to the party: a supplier's bill carries the
        # TCS it charged on top (PG-6), which the payable was credited with.
        # A bill in another currency is owed in rupees at its own rate (PG-12).
        owed: Any = (
            invoice.grand_total
            if is_receipt
            else func.coalesce(
                PurchaseInvoice.base_grand_total, PurchaseInvoice.grand_total
            )
            + PurchaseInvoice.tcs_amount
        )
        open_bills: list[Any] = [
            allocated.c.total.is_(None),
            allocated.c.total < owed,
        ]
        if is_receipt:
            # Imported here, as in `debited_against`.
            from app.customer_debit_note.models import CustomerDebitNote

            open_bills.append(
                invoice.id.in_(
                    select(CustomerDebitNote.sales_invoice_id).where(
                        CustomerDebitNote.firm_id == firm_id,
                        CustomerDebitNote.sales_invoice_id.is_not(None),
                    )
                )
            )
        # The columns the list shows, never the whole document: a firm-wide
        # read of full rows was a third of Customer Outstanding's 16 s on a
        # firm with 109,566 invoices (backlog 56 C, step 4).
        rows = self._session.execute(
            select(
                invoice.id,
                invoice.invoice_number,
                invoice.invoice_date,
                owed.label("grand_total"),
                invoice.due_date,
                party_column.label("party_id"),
                # The bill's own currency (PG-12); a customer's bill has none.
                (sa_null() if is_receipt else PurchaseInvoice.currency_code).label(
                    "currency_code"
                ),
                (sa_null() if is_receipt else PurchaseInvoice.exchange_rate).label(
                    "exchange_rate"
                ),
                invoice.grand_total.label("document_total"),
                func.coalesce(allocated.c.currency_total, 0).label("currency_paid"),
                func.coalesce(allocated.c.total, 0),
            )
            .outerjoin(allocated, allocated.c.invoice_id == invoice.id)
            .where(
                invoice.firm_id == firm_id,
                *(() if party_id is None else (party_column == party_id,)),
                invoice.is_deleted.is_(False),
                invoice.status.in_(SETTLEABLE_INVOICE_STATES),
                or_(*open_bills),
            )
            .order_by(invoice.invoice_date.asc(), invoice.invoice_number.asc())
        ).all()
        # A customer's bill: money allocated, points spent (plan item 10.9)
        # and returns and credit notes against it (D-SELL-10) -- through the
        # one derivation the ageing reads as well (D-FIN-10).
        settled: dict[UUID, Decimal] = {}
        debited: dict[UUID, Decimal] = {}
        if is_receipt and rows:
            # The bills still read: past one chunk of them the reads go
            # firm-wide in one grouped statement each (`whole_past_a_chunk`).
            asked = [row.id for row in rows]
            settled = settled_against(self._session, firm_id=firm_id, invoice_ids=asked)
            # Shown as part of the bill rather than as money taken off it
            # below zero (backlog 77 row 5).
            debited = debited_against(self._session, firm_id=firm_id, invoice_ids=asked)
        # Goods sent back against a bill's own lines come off that bill (D-BUY-6,
        # decided by the owner on 2026-09-18). A completed return posts Dr
        # payable, so the ledger already owed less while this list still showed
        # the whole bill and a payment could settle it again. Only a return
        # raised from the bill's lines names the bill; one raised from a goods
        # receipt or an order stays a credit on the supplier, as a sales
        # return does on the customer.
        taken: dict[UUID, Decimal] = {}
        if not is_receipt and rows:
            taken = self._purchase_bill_taken(
                firm_id=firm_id,
                invoice_ids=[row.id for row in rows],
                firm_wide=party_id is None,
            )
        # What returns and debit notes took off a bill in another currency,
        # in that currency: it owes that much less of it too (D-BUY-41).
        foreign_ids = [row.id for row in rows if is_foreign(row.currency_code)]
        currency_taken = (
            self._returned_against(
                firm_id=firm_id, invoice_ids=foreign_ids, in_currency=True
            )
            if foreign_ids
            else {}
        )
        records: list[OutstandingInvoiceRecord] = []
        for row in rows:
            allocated_amount = row[-1]
            already = (
                settled.get(row.id, ZERO)
                if is_receipt
                else quantize_ledger(Decimal(allocated_amount))
                + taken.get(row.id, ZERO)
            )
            extra = debited.get(row.id, ZERO)
            total = quantize_ledger(row.grand_total) + extra
            already += extra
            outstanding = total - already
            if outstanding <= ZERO:
                continue
            foreign = is_foreign(row.currency_code)
            currency_total = quantize_ledger(Decimal(row.document_total))
            records.append(
                OutstandingInvoiceRecord(
                    invoice_id=row.id,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_date,
                    invoice_total=total,
                    allocated_amount=already,
                    outstanding_amount=outstanding,
                    party_id=row.party_id,
                    # A bill with no credit days is due the day it is raised:
                    # the ageing has always read it so, and the collection
                    # sheet and the overdue report must agree (D-SELL-87).
                    due_date=row.due_date or row.invoice_date,
                    currency_code=row.currency_code if foreign else None,
                    exchange_rate=row.exchange_rate if foreign else None,
                    currency_total=currency_total if foreign else None,
                    currency_outstanding=(
                        max(
                            currency_total
                            - quantize_ledger(Decimal(row.currency_paid))
                            - currency_taken.get(row.id, ZERO),
                            ZERO,
                        )
                        if foreign
                        else None
                    ),
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
                    due_date=row.due_date or row.bill_date,
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
                    due_date=row.due_date or row.bill_date,
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
    def _purchase_bill_taken(
        self,
        *,
        firm_id: UUID,
        invoice_ids: list[UUID],
        firm_wide: bool = False,
        draw_back: bool = True,
    ) -> dict[UUID, Decimal]:
        """Sum what came off each bill other than the money paid against it.

        Goods sent back against a bill's own lines come off that bill (D-BUY-6,
        decided by the owner on 2026-09-18), as do approved debit notes. Only a
        return raised from the bill's lines names the bill; one raised from a
        goods receipt stays a credit on the supplier until somebody sets it
        against a bill (D-FIN-19). A supplier write-back or a set-off takes its
        share too (backlog 74 row 2). And where the part of a return the bill
        could not absorb was used as credit elsewhere and the bill now owes
        more again, that part goes back on the bill (D-BUY-20).

        ``firm_wide`` reads the write-backs for the whole firm in one grouped
        statement rather than by the ids. ``draw_back`` False leaves out what
        goes back on the bill, which is what a supplier credit asks to work
        that out.
        """
        from app.party_adjustments.services.allocations import adjusted_against
        from app.settlements.services.supplier_credits import drawn_back_onto_bills

        taken: dict[UUID, Decimal] = {}
        for invoice_id, amount in self._returned_against(
            firm_id=firm_id, invoice_ids=invoice_ids
        ).items():
            taken[invoice_id] = taken.get(invoice_id, ZERO) + quantize_ledger(amount)
        # TDS deducted on the bill itself (PG-5): the journal credited it to
        # TDS Payable rather than the supplier, so the bill owes that less.
        for invoice_id, deducted in self._session.execute(
            select(PurchaseInvoice.id, PurchaseInvoice.tds_amount).where(
                PurchaseInvoice.id.in_(invoice_ids),
                PurchaseInvoice.tds_amount > 0,
            )
        ).all():
            taken[invoice_id] = taken.get(invoice_id, ZERO) + quantize_ledger(deducted)
        for source in (
            credit_applied_against(
                self._session, firm_id=firm_id, invoice_ids=invoice_ids
            ),
            adjusted_against(
                self._session,
                firm_id=firm_id,
                column="purchase_invoice_id",
                bill_ids=None if firm_wide else invoice_ids,
            ),
        ):
            for invoice_id, amount in source.items():
                taken[invoice_id] = taken.get(invoice_id, ZERO) + amount
        if not draw_back:
            return taken
        for invoice_id, amount in drawn_back_onto_bills(
            self._session, firm_id=firm_id, invoice_ids=invoice_ids
        ).items():
            taken[invoice_id] = taken.get(invoice_id, ZERO) - amount
        return taken

    def purchase_bill_positions(
        self, *, firm_id: UUID, invoice_ids: list[UUID]
    ) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return each live bill's total and what came off it, money included.

        The same figures `outstanding_invoices` subtracts, for the few bills a
        supplier credit asks about (D-BUY-20) -- before anything is drawn back
        onto them, which is the question that credit answers.
        """
        if not invoice_ids:
            return {}
        rows = self._session.execute(
            select(
                PurchaseInvoice.id,
                # The TCS the supplier charged is owed with the bill (PG-6); a
                # bill in another currency in rupees at its rate (PG-12).
                (
                    func.coalesce(
                        PurchaseInvoice.base_grand_total, PurchaseInvoice.grand_total
                    )
                    + PurchaseInvoice.tcs_amount
                ).label("grand_total"),
            ).where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.id.in_(invoice_ids),
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(SETTLEABLE_INVOICE_STATES),
            )
        ).all()
        ids = [row.id for row in rows]
        if not ids:
            return {}
        paid = {
            invoice_id: quantize_ledger(Decimal(str(total)))
            for invoice_id, total in self._session.execute(
                select(
                    SettlementAllocation.purchase_invoice_id,
                    func.coalesce(
                        func.sum(
                            func.coalesce(
                                SettlementAllocation.base_amount,
                                SettlementAllocation.amount,
                            )
                        ),
                        0,
                    ),
                )
                .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
                .where(
                    SettlementAllocation.firm_id == firm_id,
                    SettlementAllocation.is_deleted.is_(False),
                    Settlement.status == SettlementStatus.POSTED.value,
                    SettlementAllocation.purchase_invoice_id.in_(ids),
                )
                .group_by(SettlementAllocation.purchase_invoice_id)
            ).all()
        }
        taken = self._purchase_bill_taken(
            firm_id=firm_id, invoice_ids=ids, draw_back=False
        )
        return {
            row.id: (
                quantize_ledger(row.grand_total),
                paid.get(row.id, ZERO) + taken.get(row.id, ZERO),
            )
            for row in rows
        }

    def _returned_against(
        self, *, firm_id: UUID, invoice_ids: list[UUID], in_currency: bool = False
    ) -> dict[UUID, Decimal]:
        """Sum what returns and debit notes took off each bill.

        Completed purchase returns sent back off the bill's lines, and
        approved debit notes claimed against it (backlog 65 row 6). Both post
        Dr payable, so both are what the bill no longer owes. A debit note is
        counted as its journal debited the payable -- each part rounded to the
        ledger, then summed -- so the bill and the books agree to the paisa.

        In rupees: both documents are typed in their bill's currency and come
        off at the bill's own rate, as their journals posted (D-BUY-41).
        ``in_currency`` True answers in the bill's currency instead, which is
        what a bill in another currency still owes in it.
        """
        # Imported here: the return module imports settlement-adjacent models.
        from app.debit_note.models import DebitNote, DebitNoteStatus

        taken: dict[UUID, Decimal] = {}
        for invoice_id, taxable, tax, currency, rate in self._session.execute(
            select(
                DebitNote.purchase_invoice_id,
                DebitNote.taxable_amount,
                DebitNote.tax_amount,
                PurchaseInvoice.currency_code,
                PurchaseInvoice.exchange_rate,
            )
            .join(PurchaseInvoice, PurchaseInvoice.id == DebitNote.purchase_invoice_id)
            .where(
                DebitNote.firm_id == firm_id,
                DebitNote.purchase_invoice_id.in_(invoice_ids),
                # Approval is what posts; a draft has not, a cancelled one is
                # gone.
                DebitNote.status == DebitNoteStatus.APPROVED.value,
                DebitNote.is_deleted.is_(False),
            )
        ).all():
            rupees = Decimal("1") if in_currency else rupee_rate(currency, rate)
            taken[invoice_id] = (
                taken.get(invoice_id, ZERO)
                + quantize_ledger(Decimal(str(taxable)) * rupees)
                + quantize_ledger(Decimal(str(tax)) * rupees)
            )
        for invoice_id, total in self._returned_by_goods(
            firm_id=firm_id, invoice_ids=invoice_ids, in_currency=in_currency
        ).items():
            taken[invoice_id] = taken.get(invoice_id, ZERO) + total
        return taken

    def _returned_by_goods(
        self, *, firm_id: UUID, invoice_ids: list[UUID], in_currency: bool = False
    ) -> dict[UUID, Decimal]:
        """Sum what completed purchase returns sent back off each bill's lines.

        With the lines, the header figures a return claimed back from the
        bill -- its ``additional_charges`` and ``round_off`` -- which are in
        the payables debit its journal posted and in no line
        (``return_header_parts``, D-PRC-83). In rupees at the bill's own
        rate, or in the bill's currency.
        """
        from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
        from app.settlements.services.supplier_credits import return_header_parts

        rupees: Any = (
            literal(1)
            if in_currency
            else rupee_rate_sql(
                PurchaseInvoice.currency_code, PurchaseInvoice.exchange_rate
            )
        )
        taken = {
            invoice_id: Decimal(str(total))
            for invoice_id, total in self._session.execute(
                select(
                    PurchaseReturnLine.source_document_id,
                    func.coalesce(func.sum(PurchaseReturnLine.net_amount * rupees), 0),
                )
                .join(
                    PurchaseReturn,
                    PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
                )
                .join(
                    PurchaseInvoice,
                    PurchaseInvoice.id == PurchaseReturnLine.source_document_id,
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
        for header in return_header_parts(
            self._session,
            firm_id=firm_id,
            invoice_ids=invoice_ids,
            in_currency=in_currency,
        ):
            taken[header.purchase_invoice_id] = (
                taken.get(header.purchase_invoice_id, ZERO) + header.amount
            )
        return taken

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
        if data.credit_source_id is not None and not is_refund:
            # Accepted and discarded would be worse than refused: a credit
            # is set against a bill by its own route, not by a receipt.
            raise ValidationError(
                "Only a refund names the return or credit note it pays back."
            )
        order = self._advance_order(data, firm_id=firm_id)
        currency = normalize_currency(data.currency_code)
        # A payment in a supplier's currency (PG-12): the request's amounts
        # are in that currency, and what is stored and posted is rupees.
        fx = (
            self._foreign_allocations(
                data, firm_id=firm_id, party_id=data.party_id, currency=currency
            )
            if is_foreign(currency)
            else None
        )
        deductions: dict[ControlAccountPurpose, Decimal]
        if fx is not None:
            amount = fx.rupees
            allocated = amount
            deductions = {}
        else:
            amount = quantize_ledger(data.amount)
            allocated = self._validate_allocations(
                data, firm_id=firm_id, party_id=data.party_id, amount=amount
            )
            deductions = self._deductions(data, firm_id=firm_id, allocated=allocated)
        # 194C and 194J are deducted at the earlier of credit and payment
        # (PG-5): what this payment should deduct is worked out before it is
        # written, so it is not its own past, and kept beside what it did.
        # Not on a payment abroad, which neither section reaches (PG-12).
        tds_proposed: Decimal | None = None
        if (
            self.DIRECTION == SettlementDirection.PAYMENT
            and isinstance(party, Vendor)
            and fx is None
        ):
            # Imported here: the finance services read this module's models.
            from app.finance.services.tds_sections import TdsSectionService

            proposal = TdsSectionService(self._session).propose(
                party,
                firm_id=firm_id,
                on=data.settlement_date,
                advance_amount=amount - allocated,
                allocating=allocated,
            )
            if proposal.section is not None:
                tds_proposed = proposal.proposed
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
                deductions=deductions,
                exchange_difference=ZERO if fx is None else fx.difference,
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
            tds_proposed_amount=tds_proposed,
            rounding_amount=deductions.get(ControlAccountPurpose.ROUNDING, ZERO),
            bank_charges_amount=deductions.get(
                ControlAccountPurpose.BANK_CHARGES, ZERO
            ),
            discount_amount=deductions.get(
                ControlAccountPurpose.DISCOUNT_ALLOWED,
                deductions.get(ControlAccountPurpose.DISCOUNT_RECEIVED, ZERO),
            ),
            allocated_amount=allocated,
            unallocated_amount=amount - allocated,
            currency_code=None if fx is None else currency,
            exchange_rate=None if fx is None else data.exchange_rate,
            currency_amount=None if fx is None else quantize_ledger(data.amount),
            sales_order_id=None if order is None else order.id,
            method=data.method.value,
            payment_mode=(
                None if data.payment_mode is None else data.payment_mode.value
            ),
            ledger_account_id=money_account_id,
            instrument_reference=(
                data.instrument_reference.strip() if data.instrument_reference else None
            ),
            instrument_date=data.instrument_date,
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
            part = None if fx is None else fx.parts[allocation.invoice_id]
            self._session.add(
                SettlementAllocation(
                    firm_id=firm_id,
                    settlement_id=row.id,
                    **self._allocation_target(
                        allocation.invoice_id, is_receipt=is_receipt, opening=opening
                    ),
                    # The rupees paid for this bill; in another currency, what
                    # it cleared in that currency and at the bill's rate too.
                    amount=(
                        quantize_ledger(allocation.amount)
                        if part is None
                        else part.paid
                    ),
                    currency_amount=None if part is None else part.currency_amount,
                    base_amount=None if part is None else part.base,
                    # Applied with the money, so it met the bill the day the
                    # money arrived.
                    allocated_on=data.settlement_date,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

        if is_refund:
            # What a return or credit note left on the account is that
            # document's credit, and money handed back out of it is the
            # credit gone (D-PRC-75): the refund names its source or takes
            # the oldest credit held first, before the advance moves, so a
            # credit paid back cannot be set against a bill as well.
            draw_refund_on_credits(
                self._session,
                firm_id=firm_id,
                customer_id=data.party_id,
                refund_id=row.id,
                refund_number=number,
                amount=amount,
                refunded_on=data.settlement_date,
                actor_id=actor_id,
                source_id=data.credit_source_id,
            )
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
                "tds_proposed_amount": (
                    None if tds_proposed is None else str(tds_proposed)
                ),
                "tds_overridden": (
                    tds_proposed is not None and tds_amount != tds_proposed
                ),
                "deductions": {
                    purpose.value: str(value) for purpose, value in deductions.items()
                },
                "allocated_amount": str(allocated),
                "party": party.code,
                # A payment in another currency (PG-12).
                **(
                    {}
                    if fx is None
                    else {
                        "currency_code": currency,
                        "exchange_rate": str(data.exchange_rate),
                        "currency_amount": str(quantize_ledger(data.amount)),
                        "exchange_difference": str(fx.difference),
                    }
                ),
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
        self._refuse_rupees_for_foreign_bill(record)
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
        on: date | None = None,
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
            on: The day the reversal is dated; blank is today. A bounced
                cheque (ACC-2) is reversed on the day the bank returned it.

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
            journal_date=on,
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
        if self.DIRECTION == SettlementDirection.REFUND:
            # The money came back, so the credits it paid back are free
            # again (D-PRC-75).
            release_refund_draws(
                self._session,
                firm_id=firm_id,
                refund_id=row.id,
                actor_id=actor_id,
                reason=reason or f"{row.settlement_number} reversed.",
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
        if row.customer_id is not None and self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        ):
            # A bill this receipt paid owes again, so what a return had left
            # on the account because the bill was paid is no longer held for
            # the customer: it comes off that bill, as the bill already
            # reads. A refund reversed puts back an advance the same may be
            # true of. Left alone, the customer owed that much on no bill
            # and held it from no source (D-PRC-88).
            absorb_credit_no_longer_given(
                self._session,
                firm_id=firm_id,
                customer_id=row.customer_id,
                actor_id=actor_id,
                on=mirror.journal_date,
            )
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

    def _deductions(
        self, data: SettlementCreate, *, firm_id: UUID, allocated: Decimal
    ) -> dict[ControlAccountPurpose, Decimal]:
        """Check what settled the bills without money, by the account it posts to.

        Rules, each decided by convention on 2026-10-01 (backlog 74 row 2):

        * A refund takes none: it hands money back, it settles no bill.
        * Bank charges are a receipt's only. On a payment the firm's own bank
          fee is the firm's expense and settles nothing the supplier is owed;
          it is recorded on the Expenses screen.
        * Rounding is capped by the firm's rounding limit (10.00 unless set in
          the party adjustment settings): more than that is a decision to give
          a discount or write the balance off, and should be named as one.
        * Together they cannot exceed what the allocations clear. A deduction
          closes a bill; one on money held on account would close nothing and
          turn an advance into a cost.

        Returns:
            Each non-zero deduction by its control purpose.

        Raises:
            ValidationError: If any rule above is broken.

        """
        rounding = quantize_ledger(data.rounding_amount or ZERO)
        charges = quantize_ledger(data.bank_charges_amount or ZERO)
        discount = quantize_ledger(data.discount_amount or ZERO)
        total = rounding + charges + discount
        if total == ZERO:
            return {}
        if self.DIRECTION == SettlementDirection.REFUND:
            raise ValidationError(
                "A refund hands money back and settles no bill, so it takes "
                "no deductions."
            )
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        if charges > ZERO and not is_receipt:
            raise ValidationError(
                "Bank charges are deducted on a receipt, where the customer's "
                "bank took them. The firm's own bank fee on a payment is an "
                "expense: record it on the Expenses screen."
            )
        # Imported here: the party adjustment module reads the settlement
        # services.
        from app.party_adjustments.services.settings import adjustment_limits

        limit = adjustment_limits(self._session, firm_id).rounding_limit
        if rounding > limit:
            raise ValidationError(
                f"Rounding of {rounding} is more than this firm's limit of "
                f"{quantize_ledger(limit)}. Record the difference as a discount, "
                "or write the balance off with a party adjustment."
            )
        if total > allocated:
            raise ValidationError(
                f"Deductions total {total}, but only {allocated} is allocated "
                "to bills. A deduction closes a bill, so allocate at least the "
                "money and the deductions together."
            )
        found = {
            ControlAccountPurpose.ROUNDING: rounding,
            ControlAccountPurpose.BANK_CHARGES: charges,
            (
                ControlAccountPurpose.DISCOUNT_ALLOWED
                if is_receipt
                else ControlAccountPurpose.DISCOUNT_RECEIVED
            ): discount,
        }
        return {purpose: value for purpose, value in found.items() if value > ZERO}

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
            self._refuse_rupees_for_foreign_bill(record)
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

    @staticmethod
    def _refuse_rupees_for_foreign_bill(record: OutstandingInvoiceRecord) -> None:
        """Refuse rupees set against a bill in another currency (PG-12).

        Such a bill is owed in its currency; how many rupees clear it depends
        on the day's rate, which only a payment in that currency states.
        """
        if record.currency_code is not None:
            raise ValidationError(
                f"Bill {record.invoice_number} is in {record.currency_code}. "
                f"Pay it with a payment in {record.currency_code} at the "
                "day's rate."
            )

    def _foreign_allocations(
        self,
        data: SettlementCreate,
        *,
        firm_id: UUID,
        party_id: UUID,
        currency: str | None,
    ) -> _ForeignPayment:
        """Check a payment in a supplier's currency and work out its rupees.

        Rules, decided on 2026-10-05 by the Tally and ERPNext convention
        (PG-12):

        * Only a payment to a supplier, applied to its bills in that currency,
          and the whole amount: money abroad held on account would need a
          rate of its own to apply later, so an advance is not carried.
        * No TDS and no deductions -- neither 194C/194J nor 194Q reaches a
          supplier abroad, and a rounding or discount is a rupee figure.
        * The rupees paid are the amount at the payment's rate, each bill's
          share rounded on its own and the last taking the residual, so the
          shares sum to what left the bank. What comes off each bill is its
          share at the bill's own rate -- or, where the payment clears the
          bill, whatever rupees it still owed -- so a part payment settles in
          proportion and the last one leaves nothing behind.

        Raises:
            ValidationError: If any rule above is broken.

        """
        if self.DIRECTION != SettlementDirection.PAYMENT:
            raise ValidationError(
                "Only a payment to a supplier is recorded in another currency."
            )
        check_currency(currency, data.exchange_rate, document="payment")
        rate = data.exchange_rate
        if rate is None:  # pragma: no cover - check_currency refused it
            raise ValidationError("A payment in another currency needs its rate.")
        taken = (
            (data.tds_amount or ZERO)
            + (data.rounding_amount or ZERO)
            + (data.bank_charges_amount or ZERO)
            + (data.discount_amount or ZERO)
        )
        if taken > ZERO:
            raise ValidationError(
                f"A payment in {currency} takes no TDS, rounding, bank charges "
                "or discount; record it for the amount that was sent."
            )
        total = quantize_ledger(data.amount)
        if not data.allocations or (
            sum((quantize_ledger(item.amount) for item in data.allocations), ZERO)
            != total
        ):
            raise ValidationError(
                f"A payment in {currency} is applied in full to the supplier's "
                f"bills in {currency}; an advance in another currency is not "
                "carried."
            )
        outstanding = {
            record.invoice_id: record
            for record in self.outstanding_invoices(firm_id=firm_id, party_id=party_id)
        }
        rupees = to_base(total, rate)
        parts: dict[UUID, _ForeignPart] = {}
        paid_so_far = ZERO
        for index, allocation in enumerate(data.allocations):
            record = outstanding.get(allocation.invoice_id)
            if record is None or record.currency_code != currency:
                raise ValidationError(
                    f"A payment in {currency} is applied only to this "
                    f"supplier's open bills in {currency}."
                )
            share = quantize_ledger(allocation.amount)
            left = record.currency_outstanding or ZERO
            if share > left:
                raise ValidationError(
                    f"Bill {record.invoice_number} has {left} {currency} "
                    f"outstanding, so {share} cannot be allocated to it."
                )
            last = index == len(data.allocations) - 1
            paid = rupees - paid_so_far if last else to_base(share, rate)
            paid_so_far += paid
            base = (
                record.outstanding_amount
                if share == left
                else to_base(share, record.exchange_rate or rate)
            )
            parts[allocation.invoice_id] = _ForeignPart(
                currency_amount=share, paid=paid, base=base
            )
        cleared = sum((part.base for part in parts.values()), ZERO)
        return _ForeignPayment(rupees=rupees, difference=rupees - cleared, parts=parts)

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
