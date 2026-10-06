"""Raising, approving and cancelling a debit note.

The purchasing mirror of `CreditNoteService`, and it turns on the same rule:
**input tax comes off at the rate the bill charged**, split across the GST
heads the way that bill's credit was claimed. Only the bill line knows either,
which is why a debit note always names a bill and the lines within it.

What the bill still owes is never written onto the bill. It is derived in
`PaymentService.outstanding_invoices`, which reads approved debit notes beside
the purchase returns raised off the bill's lines -- so approving a note takes
it off the bill and cancelling one puts it back, with nothing stored to drift.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.report_names import product_names, vendor_names, vendors_matching
from app.core.concurrency import assert_version
from app.core.database.batch import children_by_parent
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.debit_note.models import DebitNote, DebitNoteLine, DebitNoteStatus
from app.debit_note.schemas import (
    DebitNoteClaimableLine,
    DebitNoteCreate,
    DebitNoteLineResponse,
    DebitNoteLineWrite,
    DebitNoteReasonEnum,
    DebitNoteRegisterRecord,
    DebitNoteResponse,
    DebitNoteStatusEnum,
    DebitNoteUpdate,
)
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.currency import rupee_rate
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.purchase_invoice.services.reverse_charge import (
    ReverseChargeShare,
    reverse_charge_share,
)
from app.purchase_invoice.services.rupees import bill_line_rupee_rates

HUNDRED = Decimal("100")

#: Only a bill that raised a payable can be claimed against: a draft is not a
#: debt, and a cancelled one has been undone. CLOSED means nothing more to pay,
#: not never bought -- the purchase return's rule.
_CLAIMABLE_INVOICE_STATES = frozenset({"APPROVED", "CLOSED"})


class DebitNoteService(TransactionalDocumentService):
    """Claim value back from a supplier, without goods going back."""

    DOCUMENT = DocumentTypeSpec(
        code="DEBIT_NOTE",
        name="Debit Note",
        description="Supplier debit without a goods movement",
        category="PURCHASE",
        module="debit_note",
        # `DN` is the delivery note's.
        prefix="DBN",
        include_branch_code=True,
        include_company_code=True,
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 2),
            DocumentStateSpec("CANCELLED", "Cancelled", 3, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)

    # ---- reads ---------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[DebitNote]], firm_id: UUID
    ) -> Select[tuple[DebitNote]]:
        """Restrict a query to one firm's live notes."""
        return statement.where(
            DebitNote.firm_id == firm_id, DebitNote.is_deleted.is_(False)
        )

    def list_notes(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        vendor_id: UUID | None = None,
        purchase_invoice_id: UUID | None = None,
        status: DebitNoteStatusEnum | None = None,
        search: str | None = None,
        debit_note_from: date | None = None,
        debit_note_to: date | None = None,
        supplier_credit_note: bool | None = None,
    ) -> tuple[Sequence[DebitNote], int]:
        """Return one page of debit notes, newest first.

        Args:
            firm_scope: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            vendor_id: Restrict to one supplier.
            purchase_invoice_id: Restrict to one bill.
            status: Restrict to one state.
            search: Match the note's number or reference, or the supplier.
            debit_note_from: The first note date to include.
            debit_note_to: The last note date to include.
            supplier_credit_note: True for the notes recording a supplier's
                own credit note, False for the firm's own claims only.

        Returns:
            The page of notes and the total matching count.

        """
        statement = self._scoped(select(DebitNote), firm_scope)
        if vendor_id is not None:
            statement = statement.where(DebitNote.vendor_id == vendor_id)
        if purchase_invoice_id is not None:
            statement = statement.where(
                DebitNote.purchase_invoice_id == purchase_invoice_id
            )
        if status is not None:
            statement = statement.where(DebitNote.status == status.value)
        if search and search.strip():
            token = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    DebitNote.debit_note_number.ilike(token),
                    DebitNote.reference_number.ilike(token),
                    DebitNote.supplier_credit_note_number.ilike(token),
                    DebitNote.vendor_id.in_(vendors_matching(token)),
                )
            )
        if debit_note_from is not None:
            statement = statement.where(DebitNote.debit_note_date >= debit_note_from)
        if debit_note_to is not None:
            statement = statement.where(DebitNote.debit_note_date <= debit_note_to)
        if supplier_credit_note is not None:
            column = DebitNote.supplier_credit_note_number
            statement = statement.where(
                column.is_not(None) if supplier_credit_note else column.is_(None)
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                DebitNote.debit_note_date.desc(),
                DebitNote.created_at.desc(),
                DebitNote.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get_note(self, note_id: UUID, *, firm_scope: UUID) -> DebitNote:
        """Return one debit note.

        Raises:
            ResourceNotFoundError: If the firm has no such live note.

        """
        row = self._session.scalar(
            self._scoped(select(DebitNote), firm_scope).where(DebitNote.id == note_id)
        )
        if row is None:
            raise ResourceNotFoundError("Debit note not found.")
        return row

    def lines_of(self, note: DebitNote) -> list[DebitNoteLine]:
        """Return one note's live lines, in order."""
        return list(
            self._session.scalars(
                select(DebitNoteLine)
                .where(
                    DebitNoteLine.debit_note_id == note.id,
                    DebitNoteLine.is_deleted.is_(False),
                )
                .order_by(DebitNoteLine.line_number.asc())
            ).all()
        )

    def claimable_lines(
        self,
        invoice_id: UUID,
        *,
        firm_id: UUID,
        excluding_note_id: UUID | None = None,
    ) -> list[DebitNoteClaimableLine]:
        """Return a bill's lines and how much of each may still be claimed.

        Args:
            invoice_id: The supplier bill.
            firm_id: The owning firm.
            excluding_note_id: A draft being edited, whose own claim is not
                counted against it.

        Returns:
            One row per live bill line, in line order.

        """
        invoice = self._claimable_invoice(invoice_id, firm_id=firm_id)
        lines = list(
            self._session.scalars(
                select(PurchaseInvoiceLine)
                .where(
                    PurchaseInvoiceLine.purchase_invoice_id == invoice.id,
                    PurchaseInvoiceLine.is_deleted.is_(False),
                )
                .order_by(PurchaseInvoiceLine.line_number.asc())
            ).all()
        )
        ids = [line.id for line in lines]
        claimed = self._claimed_by_line(
            firm_id=firm_id, line_ids=ids, excluding_note_id=excluding_note_id
        )
        returned = self._returned_by_line(firm_id=firm_id, line_ids=ids)
        names = product_names(self._session, (line.product_id for line in lines))
        rows: list[DebitNoteClaimableLine] = []
        for line in lines:
            billed = self._billed_taxable(line)
            already = claimed.get(line.id, ZERO)
            back = returned.get(line.id, ZERO)
            rows.append(
                DebitNoteClaimableLine(
                    purchase_invoice_line_id=line.id,
                    line_number=line.line_number,
                    product_id=line.product_id,
                    product_name=names.get(line.product_id, ("", ""))[1],
                    quantity=line.current_invoice_quantity,
                    unit_price=line.unit_price,
                    billed_taxable=billed,
                    already_claimed=already,
                    already_returned=back,
                    claimable=max(billed - already - back, ZERO),
                    tax_rate_percent=self._tax_rate(line, billed),
                )
            )
        return rows

    # ---- writes --------------------------------------------------------

    def create_note(
        self, data: DebitNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> DebitNote:
        """Stage one debit note against an approved supplier bill.

        Flushes and leaves the commit to the caller, so a preview can roll
        it back and the router commits once.

        Raises:
            ValidationError: If the bill cannot be claimed against, or a line
                claims more than is left of it.

        """
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        invoice = self._claimable_invoice(data.purchase_invoice_id, firm_id=firm_id)
        number = self._issue_number(
            numbering_rule,
            typed=(
                data.debit_note_number.strip().upper()
                if data.debit_note_number
                else None
            ),
            number_column=DebitNote.debit_note_number,
            firm_id=firm_id,
            document_date=data.debit_note_date,
            actor_id=actor_id,
            branch_code=self._scope_code(invoice.branch_id),
            company_code=self._company_code(firm_id),
        )
        row = DebitNote(
            firm_id=firm_id,
            vendor_id=invoice.vendor_id,
            branch_id=invoice.branch_id,
            purchase_invoice_id=invoice.id,
            debit_note_number=number,
            debit_note_date=data.debit_note_date,
            reason=data.reason.value,
            status=DebitNoteStatus.DRAFT.value,
            reference_number=data.reference_number,
            supplier_credit_note_number=_clean(data.supplier_credit_note_number),
            supplier_credit_note_date=data.supplier_credit_note_date,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._check_supplier_credit_note(row, invoice)
        self._session.add(row)
        self._flush_or_conflict("Debit note number already exists in this firm.")
        self._replace_lines(row, data.lines, invoice=invoice, actor_id=actor_id)
        self._record_event(row, action="CREATED", from_state=None, actor_id=actor_id)
        record_audit(
            self._session,
            action="debit_note.created",
            entity_type="debit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def preview_note(
        self, data: DebitNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> DebitNoteResponse:
        """Price a debit note exactly as raising it would, then save nothing."""
        try:
            row = self.create_note(data, firm_id=firm_id, actor_id=actor_id)
            return self.note_response(row)
        finally:
            self._session.rollback()

    def update_note(
        self,
        note_id: UUID,
        data: DebitNoteUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> DebitNote:
        """Change a debit note nobody has approved.

        The status is not in the write model at all: it belongs to approve
        and cancel.

        Raises:
            ValidationError: If the note has left DRAFT.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != DebitNoteStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft debit note can be changed. Cancel this one and "
                "raise another."
            )
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        if values.get("debit_note_date") is not None:
            row.debit_note_date = values["debit_note_date"]
        if values.get("reason") is not None:
            row.reason = DebitNoteReasonEnum(values["reason"]).value
        if "reference_number" in values:
            row.reference_number = values["reference_number"]
        if "remarks" in values:
            row.remarks = values["remarks"]
        if "supplier_credit_note_number" in values:
            row.supplier_credit_note_number = _clean(
                values["supplier_credit_note_number"]
            )
        if "supplier_credit_note_date" in values:
            row.supplier_credit_note_date = values["supplier_credit_note_date"]
        invoice = self._claimable_invoice(row.purchase_invoice_id, firm_id=firm_scope)
        self._check_supplier_credit_note(row, invoice)
        if data.lines is not None:
            self._replace_lines(row, data.lines, invoice=invoice, actor_id=actor_id)
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row, action="EDITED", from_state=row.status, actor_id=actor_id
        )
        record_audit(
            self._session,
            action="debit_note.updated",
            entity_type="debit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def approve_note(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> DebitNote:
        """Recognise the claim: post the journal, and the bill owes less.

        The bill owing less is not a write -- `outstanding_invoices` reads
        approved notes -- so the journal and the payable list cannot disagree.
        A claim larger than the bill still owes -- it is already paid, say --
        leaves the excess as a supplier credit (decision A4), to set against
        another bill or be paid back.

        Raises:
            ValidationError: If it is not a draft, claims nothing, or claims
                more than the bill was ever worth.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != DebitNoteStatus.DRAFT.value:
            raise ValidationError("Only a draft debit note can be approved.")
        if row.total_amount <= ZERO:
            raise ValidationError("A debit note for nothing cannot be approved.")
        invoice = self._claimable_invoice(row.purchase_invoice_id, firm_id=firm_scope)
        self._assert_lines_still_have_room(row)
        self._refuse_more_than_billed(row, invoice)
        before = self._snapshot(row)
        # A note against a bill in another currency is typed in it and posts
        # rupees at the bill's own rate, each leg converted on its own -- what
        # the bill's journal credited the supplier with (D-BUY-41).
        rate = rupee_rate(invoice.currency_code, invoice.exchange_rate)
        entry = self._posting.post_debit_note_document(
            firm_id=firm_scope,
            debit_note_id=row.id,
            debit_note_number=row.debit_note_number,
            note_date=row.debit_note_date,
            taxable_amount=Decimal(str(row.taxable_amount)) * rate,
            tax_amount=Decimal(str(row.tax_amount)) * rate,
            tax_by_component=debit_note_tax_by_component(self._session, row.id),
            blocked_tax_amount=sum(
                debit_note_tax_by_component(
                    self._session, row.id, claimable=False
                ).values(),
                ZERO,
            ),
            reverse_charge_by_component=debit_note_reverse_charge(
                self._session, row.id
            ).owed,
            actor_id=actor_id,
        )
        row.journal_entry_id = None if entry is None else entry.id
        row.status = DebitNoteStatus.APPROVED.value
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="APPROVED",
            from_state=DebitNoteStatus.DRAFT.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="debit_note.approved",
            entity_type="debit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def cancel_note(
        self,
        note_id: UUID,
        *,
        reason: str,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> DebitNote:
        """Withdraw a debit note, undoing whatever it did.

        An approved note's journal is reversed, not deleted, dated the day it
        is cancelled. The bill owes the claimed part again because the
        derivation stops counting a cancelled note -- nothing to restore by
        hand.

        Raises:
            ValidationError: If it is already cancelled, or no reason is given.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status == DebitNoteStatus.CANCELLED.value:
            raise ValidationError("This debit note is already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the debit note is being cancelled.")
        # Imported here: settlements imports this module's models.
        from app.settlements.services.supplier_credits import (
            withdraw_credit_applications,
        )

        self._refuse_while_refunded(row)
        before = self._snapshot(row)
        # The credit it left, if any, goes with it, and a bill it was set
        # against owes that part again (A4).
        withdraw_credit_applications(
            self._session,
            firm_id=firm_scope,
            actor_id=actor_id,
            debit_note_id=row.id,
        )
        if row.journal_entry_id is not None:
            # A mirror is right: every leg is a document amount, worth exactly
            # what it was when it posted -- unlike a stock reversal.
            self._journals.reverse_entry(
                row.journal_entry_id,
                firm_id=firm_scope,
                reference_number=f"{row.debit_note_number}-REV",
                actor_id=actor_id,
            )
        was = row.status
        row.status = DebitNoteStatus.CANCELLED.value
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="CANCELLED",
            from_state=was,
            actor_id=actor_id,
            remarks=row.cancel_reason,
        )
        record_audit(
            self._session,
            action="debit_note.cancelled",
            entity_type="debit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def _refuse_while_refunded(self, row: DebitNote) -> None:
        """Refuse to cancel while the supplier's money against its credit stands.

        The refund posted cash against the payable this note debited; taking
        the note away would leave that cash with nothing behind it. Reverse
        the refund first, as a return asks (A4).
        """
        from app.settlements.services.supplier_credits import live_refunds

        standing = [
            refund
            for refund in live_refunds(
                self._session, firm_id=row.firm_id, source_id=row.id
            )
            if refund.status == "POSTED"
        ]
        if standing:
            raise ValidationError(
                f"The supplier paid back {standing[0].amount} against "
                f"{row.debit_note_number}'s credit. Reverse that refund before "
                "cancelling the debit note."
            )

    def _record_event(
        self,
        row: DebitNote,
        *,
        action: str,
        from_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> None:
        """Append one step to the note's timeline."""
        self._record_lifecycle_event(
            firm_id=row.firm_id,
            document_type=self._document_type(row.firm_id),
            document_id=row.id,
            document_number=row.debit_note_number,
            action=action,
            from_state=from_state,
            to_state=row.status,
            actor_id=actor_id,
            remarks=remarks,
            details={
                "debit_note_number": row.debit_note_number,
                "purchase_invoice_id": str(row.purchase_invoice_id),
                "total_amount": str(row.total_amount),
            },
            snapshot={"status": row.status},
        )

    # ---- lines ---------------------------------------------------------

    def _claimable_invoice(self, invoice_id: UUID, *, firm_id: UUID) -> PurchaseInvoice:
        """Return the bill being claimed against, if it can be at all."""
        invoice = self._session.scalar(
            select(PurchaseInvoice).where(
                PurchaseInvoice.id == invoice_id,
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Purchase invoice not found.")
        if invoice.status not in _CLAIMABLE_INVOICE_STATES:
            raise ValidationError(
                f"{invoice.invoice_number} is {invoice.status.lower()}, so no "
                "debit note can be raised against it: only an approved supplier "
                "bill raised a payable to claim against."
            )
        return invoice

    def _check_supplier_credit_note(
        self, row: DebitNote, invoice: PurchaseInvoice
    ) -> None:
        """Refuse a supplier's credit note recorded by halves, early or twice.

        Its number and date are both stated or neither; it cannot be dated
        before the supplier's own bill it credits; and one supplier's credit
        note is recorded once -- a second live note naming it would take the
        same money off the payable and the input credit twice.
        """
        number = row.supplier_credit_note_number
        when = row.supplier_credit_note_date
        if (number is None) != (when is None):
            raise ValidationError(
                "Record the supplier's credit note with both its number and "
                "its date, or neither."
            )
        if number is None or when is None:
            return
        if when < invoice.supplier_invoice_date:
            raise ValidationError(
                f"The supplier's credit note is dated {when.isoformat()}, before "
                f"the bill it credits ({invoice.supplier_invoice_date.isoformat()})."
            )
        statement = select(DebitNote.debit_note_number).where(
            DebitNote.firm_id == row.firm_id,
            DebitNote.vendor_id == row.vendor_id,
            DebitNote.is_deleted.is_(False),
            DebitNote.status != DebitNoteStatus.CANCELLED.value,
            func.upper(DebitNote.supplier_credit_note_number) == number.upper(),
        )
        if row.id is not None:
            statement = statement.where(DebitNote.id != row.id)
        clash = self._session.scalar(statement.limit(1))
        if clash is not None:
            raise ValidationError(
                f"The supplier's credit note {number} is already recorded on "
                f"debit note {clash}."
            )

    def _refuse_more_than_billed(
        self, row: DebitNote, invoice: PurchaseInvoice
    ) -> None:
        """Refuse a claim larger than what is left of the bill to claim against.

        Since decision A4 a claim past what the bill still **owes** is fine:
        what the bill cannot absorb -- because it is paid -- is a supplier
        credit, derived like a return's (``app/settlements/services/
        supplier_credits.py``). What no supplier owes back is more than the
        bill was worth: its total, less what returns and other approved debit
        notes already took off it. The bill row is locked so two approvals
        cannot both see the same room.
        """
        # Imported here: settlements imports this module's models.
        from app.settlements.services.settlement_service import PaymentService

        self._session.execute(
            select(PurchaseInvoice.id)
            .where(PurchaseInvoice.id == invoice.id)
            .with_for_update()
        )
        taken = (
            PaymentService(self._session)
            ._returned_against(
                firm_id=row.firm_id, invoice_ids=[invoice.id], in_currency=True
            )
            .get(invoice.id, ZERO)
        )
        room = max(quantize_ledger(invoice.grand_total) - quantize_ledger(taken), ZERO)
        claim = quantize_ledger(row.taxable_amount) + quantize_ledger(row.tax_amount)
        if claim > room:
            raise ValidationError(
                f"{invoice.invoice_number} has only {room} left to claim against "
                f"after its returns and debit notes, and this debit note claims "
                f"{claim}."
            )

    def _replace_lines(
        self,
        note: DebitNote,
        lines: Sequence[DebitNoteLineWrite],
        *,
        invoice: PurchaseInvoice,
        actor_id: UUID,
    ) -> None:
        """Write the note's lines, replacing whatever it had.

        Raises:
            ValidationError: If a line names something outside the bill, or
                claims more than is left of it.

        """
        for existing in self.lines_of(note):
            existing.is_deleted = True
            existing.deleted_at = utc_now()
            existing.deleted_by = actor_id
            existing.updated_by = actor_id
        self._session.flush()

        sources = {
            row.id: row
            for row in self._session.scalars(
                select(PurchaseInvoiceLine).where(
                    PurchaseInvoiceLine.purchase_invoice_id == invoice.id,
                    PurchaseInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        }
        taxable_total = ZERO
        tax_total = ZERO
        for item in sorted(lines, key=lambda line: line.line_number):
            source = sources.get(item.purchase_invoice_line_id)
            if source is None:
                raise ValidationError(
                    "A debit note line must name a line of the bill it claims "
                    "against."
                )
            asked = quantize_money(item.taxable_amount)
            billed = self._assert_line_has_room(note, source, asked)
            rate = self._tax_rate(source, billed)
            tax = quantize_money(asked * rate / HUNDRED)
            self._session.add(
                DebitNoteLine(
                    debit_note_id=note.id,
                    firm_id=note.firm_id,
                    line_number=item.line_number,
                    purchase_invoice_line_id=source.id,
                    product_id=source.product_id,
                    description=item.description or source.description,
                    quantity=item.quantity,
                    taxable_amount=asked,
                    tax_amount=tax,
                    total_amount=quantize_money(asked + tax),
                    tax_profile_id=source.tax_profile_id,
                    tax_rate_percent=rate,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            taxable_total += asked
            tax_total += tax
        note.taxable_amount = quantize_money(taxable_total)
        note.tax_amount = quantize_money(tax_total)
        note.total_amount = quantize_money(taxable_total + tax_total)
        self._session.flush()

    def _assert_line_has_room(
        self, note: DebitNote, source: PurchaseInvoiceLine, asked: Decimal
    ) -> Decimal:
        """Refuse a claim for more than is left of what a bill line billed.

        What is left is what the line billed, less what other live debit
        notes claim **and less what went back**: goods returned have already
        been claimed from the supplier, and a debit note for their value as
        well claims it twice. That counts a return raised off the bill line
        and one raised off the goods receipt it billed (D-PRC-67) -- the
        second names no bill line and was not counted, so a further debit
        note was approved after everything on the bill had gone back.

        The bill line is held before the cap is read: the cap is a sum over
        other documents' lines, which no row version protects, and a return
        completing takes the same lock.

        Returns:
            What the line billed, before tax.

        Raises:
            ValidationError: If the line has less room than is asked.

        """
        self._session.execute(
            select(PurchaseInvoiceLine.id)
            .where(PurchaseInvoiceLine.id == source.id)
            .with_for_update()
        )
        billed = self._billed_taxable(source)
        claimed = self._claimed_by_line(
            firm_id=note.firm_id,
            line_ids=[source.id],
            excluding_note_id=note.id,
        ).get(source.id, ZERO)
        returned = self._returned_by_line(
            firm_id=note.firm_id, line_ids=[source.id]
        ).get(source.id, ZERO)
        if asked > billed - claimed - returned:
            # Money, said as money: "1440.0000 billed, 400.0000 already
            # claimed" counted rupees to four places (D-PRC-70), where the
            # credit note's twin says them to the paisa.
            raise ValidationError(
                "A debit note cannot claim more than is left of the bill "
                f"line: {billed:.2f} billed, {claimed:.2f} already claimed, "
                f"{returned:.2f} already returned."
            )
        return billed

    def _assert_lines_still_have_room(self, note: DebitNote) -> None:
        """Ask the cap again at approval, where the claim becomes real.

        The cap is read when the note is saved. Goods that went back between
        then and approval have been claimed from the supplier since, so a
        note saved with room may have none left; the one that reaches the
        supplier second is refused by name.
        """
        for line in self.lines_of(note):
            source = self._session.get(
                PurchaseInvoiceLine, line.purchase_invoice_line_id
            )
            if source is None:
                continue
            self._assert_line_has_room(
                note, source, quantize_money(line.taxable_amount)
            )

    @staticmethod
    def _billed_taxable(source: PurchaseInvoiceLine) -> Decimal:
        """Return what a bill line was taxed on.

        Exactly the base the bill handed the tax engine: gross, less both
        discounts, plus the line's charges -- which is the line's net less
        its tax. Reading `net_amount` would include the tax and let a note
        claim it twice.
        """
        return quantize_money(
            Decimal(str(source.gross_amount))
            - Decimal(str(source.discount_amount))
            - Decimal(str(source.bill_discount_amount))
            + Decimal(str(source.charges_amount))
        )

    @staticmethod
    def _tax_rate(source: PurchaseInvoiceLine, billed: Decimal) -> Decimal:
        """Return the effective rate the bill line was taxed at.

        Derived from what was actually charged rather than read from a tax
        profile that may since have been edited.
        """
        tax = Decimal(str(source.tax_amount))
        if billed <= ZERO or tax <= ZERO:
            return ZERO
        return quantize_money(tax * HUNDRED / billed)

    def _claimed_by_line(
        self,
        *,
        firm_id: UUID,
        line_ids: Sequence[UUID],
        excluding_note_id: UUID | None,
    ) -> dict[UUID, Decimal]:
        """Sum what other live debit notes have claimed on each bill line."""
        if not line_ids:
            return {}
        conditions = [
            DebitNoteLine.firm_id == firm_id,
            DebitNoteLine.purchase_invoice_line_id.in_(list(line_ids)),
            DebitNoteLine.is_deleted.is_(False),
            DebitNote.is_deleted.is_(False),
            DebitNote.status != DebitNoteStatus.CANCELLED.value,
        ]
        if excluding_note_id is not None:
            conditions.append(DebitNote.id != excluding_note_id)
        return {
            line_id: quantize_money(Decimal(str(total)))
            for line_id, total in self._session.execute(
                select(
                    DebitNoteLine.purchase_invoice_line_id,
                    func.coalesce(func.sum(DebitNoteLine.taxable_amount), 0),
                )
                .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
                .where(*conditions)
                .group_by(DebitNoteLine.purchase_invoice_line_id)
            ).all()
        }

    def _returned_by_line(
        self, *, firm_id: UUID, line_ids: Sequence[UUID]
    ) -> dict[UUID, Decimal]:
        """Sum the taxable value purchase returns sent back off each bill line.

        By either route (`bill_line_claims`). A return raised **off the bill
        line** counts while it is not cancelled -- a draft is still a claim
        on the same value, and counting it late would let both be raised in
        full. A return raised **off the goods receipt** the line billed
        counts once it has completed: until then how much of it reverses a
        bill, and how much went back before billing, is not decided. It is
        placed on the receipt line's bills earliest first.
        """
        # Imported here: the return module imports settlement-adjacent models.
        from app.purchase_return.billing import COMPLETED, LIVE, bill_line_claims

        if not line_ids:
            return {}
        sources = self._session.scalars(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.firm_id == firm_id,
                PurchaseInvoiceLine.id.in_(list(line_ids)),
            )
        ).all()
        return {
            line_id: quantize_money(claims.returned_taxable)
            for line_id, claims in bill_line_claims(
                self._session,
                sources,
                bill_returns=LIVE,
                receipt_returns=COMPLETED,
            ).items()
            if claims.returned_taxable > ZERO
        }

    # ---- responses -----------------------------------------------------

    def note_response(self, row: DebitNote) -> DebitNoteResponse:
        """Build the response for one debit note."""
        return self.note_responses([row])[0]

    def note_responses(self, rows: Sequence[DebitNote]) -> list[DebitNoteResponse]:
        """Build the responses for a page of debit notes, one read per table."""
        if not rows:
            return []
        lines = children_by_parent(
            self._session,
            DebitNoteLine,
            DebitNoteLine.debit_note_id,
            [row.id for row in rows],
            DebitNoteLine.line_number.asc(),
        )
        names = {
            product_id: name
            for product_id, (_code, name) in product_names(
                self._session,
                (line.product_id for group in lines.values() for line in group),
            ).items()
        }
        invoices = self._invoice_numbers({row.purchase_invoice_id for row in rows})
        suppliers = vendor_names(self._session, (row.vendor_id for row in rows))
        return [
            self._note_response(
                row,
                lines=lines[row.id],
                names=names,
                invoice=invoices.get(row.purchase_invoice_id, ("", "")),
                vendor_name=suppliers.get(row.vendor_id) or "",
            )
            for row in rows
        ]

    def _note_response(
        self,
        row: DebitNote,
        *,
        lines: list[DebitNoteLine],
        names: dict[UUID, str],
        invoice: tuple[str, str],
        vendor_name: str,
    ) -> DebitNoteResponse:
        """Build one note's response from what the page already read."""
        return DebitNoteResponse(
            id=row.id,
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            vendor_name=vendor_name,
            branch_id=row.branch_id,
            purchase_invoice_id=row.purchase_invoice_id,
            purchase_invoice_number=invoice[0],
            supplier_invoice_number=invoice[1],
            debit_note_number=row.debit_note_number,
            debit_note_date=row.debit_note_date,
            reason=DebitNoteReasonEnum(row.reason),
            status=DebitNoteStatusEnum(row.status),
            taxable_amount=row.taxable_amount,
            tax_amount=row.tax_amount,
            total_amount=row.total_amount,
            reference_number=row.reference_number,
            supplier_credit_note_number=row.supplier_credit_note_number,
            supplier_credit_note_date=row.supplier_credit_note_date,
            remarks=row.remarks,
            cancel_reason=row.cancel_reason,
            journal_entry_id=row.journal_entry_id,
            version=row.version,
            lines=[
                DebitNoteLineResponse(
                    id=line.id,
                    line_number=line.line_number,
                    purchase_invoice_line_id=line.purchase_invoice_line_id,
                    product_id=line.product_id,
                    product_name=names.get(line.product_id, ""),
                    description=line.description,
                    quantity=line.quantity,
                    taxable_amount=line.taxable_amount,
                    tax_amount=line.tax_amount,
                    total_amount=line.total_amount,
                    tax_rate_percent=line.tax_rate_percent,
                )
                for line in lines
            ],
        )

    def _invoice_numbers(self, ids: set[UUID]) -> dict[UUID, tuple[str, str]]:
        """Read each bill's own number and the supplier's, in one query."""
        if not ids:
            return {}
        return {
            found[0]: (found[1], found[2] or "")
            for found in self._session.execute(
                select(
                    PurchaseInvoice.id,
                    PurchaseInvoice.invoice_number,
                    PurchaseInvoice.supplier_invoice_number,
                ).where(PurchaseInvoice.id.in_(list(ids)))
            )
        }

    def _snapshot(self, row: DebitNote) -> dict[str, object]:
        """Describe a debit note for the audit trail."""
        return {
            "debit_note_number": row.debit_note_number,
            "debit_note_date": row.debit_note_date.isoformat(),
            "purchase_invoice_id": str(row.purchase_invoice_id),
            "reason": row.reason,
            "supplier_credit_note_number": row.supplier_credit_note_number,
            "supplier_credit_note_date": (
                row.supplier_credit_note_date.isoformat()
                if row.supplier_credit_note_date
                else None
            ),
            "status": row.status,
            "taxable_amount": str(row.taxable_amount),
            "tax_amount": str(row.tax_amount),
            "total_amount": str(row.total_amount),
            "cancel_reason": row.cancel_reason,
            "journal_entry_id": (
                str(row.journal_entry_id) if row.journal_entry_id else None
            ),
        }

    # ---- reports -------------------------------------------------------

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[DebitNoteRegisterRecord]:
        """Every debit note raised in the window, newest first; paged in SQL."""
        rows = window.fetch(
            self._session,
            select(DebitNote)
            .where(
                DebitNote.firm_id == firm_scope,
                DebitNote.is_deleted.is_(False),
                *window.dated(DebitNote.debit_note_date),
            )
            .order_by(
                DebitNote.debit_note_date.desc(),
                DebitNote.created_at.desc(),
                DebitNote.id.desc(),
            ),
        )
        suppliers = vendor_names(self._session, (row.vendor_id for row in rows))
        invoices = self._invoice_numbers({row.purchase_invoice_id for row in rows})
        records = [
            DebitNoteRegisterRecord(
                debit_note_id=row.id,
                debit_note_number=row.debit_note_number,
                debit_note_date=row.debit_note_date,
                vendor_id=row.vendor_id,
                vendor_name=suppliers.get(row.vendor_id) or str(row.vendor_id),
                purchase_invoice_id=row.purchase_invoice_id,
                purchase_invoice_number=invoices.get(row.purchase_invoice_id, ("", ""))[
                    0
                ],
                reason=DebitNoteReasonEnum(row.reason),
                supplier_credit_note_number=row.supplier_credit_note_number,
                taxable_amount=row.taxable_amount,
                tax_amount=row.tax_amount,
                total_amount=row.total_amount,
                status=DebitNoteStatusEnum(row.status),
            )
            for row in rows
        ]
        return mapped_like(rows, records)


def _clean(value: str | None) -> str | None:
    """Return a typed reference trimmed, or None for a blank one."""
    if value is None:
        return None
    text = value.strip()
    return text or None


def debit_note_tax_by_component(
    session: Session, note_id: UUID, *, claimable: bool = True
) -> dict[str, Decimal]:
    """Split a debit note's tax by GST head, as its bill charged it.

    Each note line's tax is split in the proportions of its bill line's
    `purchase_invoice_line_taxes` rows -- the twin of
    `return_tax_by_component`. The ledger posting and GSTR-3B's ITC reversal
    both read this, so the books and the return reverse the same heads. A
    bill written before the rows existed gives nothing, and the posting then
    reverses `INPUT_TAX` as a whole.

    ``claimable`` False returns the other part instead: the share of tax the
    bill could not claim (backlog 78 row 1), which goes back to the cost
    account rather than coming off input tax.
    """
    lines = session.scalars(
        select(DebitNoteLine).where(
            DebitNoteLine.debit_note_id == note_id,
            DebitNoteLine.is_deleted.is_(False),
        )
    ).all()
    if not lines:
        return {}
    # The note is in its bill's currency; each head goes back in rupees at
    # the bill's own rate, as the bill's journal claimed it (D-BUY-41).
    rupees = bill_line_rupee_rates(
        session, [line.purchase_invoice_line_id for line in lines]
    )
    shares: dict[UUID, list[tuple[str, Decimal, bool]]] = {}
    for line_id, code, amount, recoverable in session.execute(
        select(
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            PurchaseInvoiceLineTax.component_code,
            PurchaseInvoiceLineTax.amount,
            PurchaseInvoiceLineTax.recoverable,
        ).where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(
                [line.purchase_invoice_line_id for line in lines]
            ),
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
            # Reverse charge never sat in the bill's payable or its credit.
            PurchaseInvoiceLineTax.reverse_charge.is_(False),
        )
    ).all():
        shares.setdefault(line_id, []).append(
            (code, Decimal(str(amount)), bool(recoverable))
        )
    totals: dict[str, Decimal] = {}
    for line in lines:
        parts = shares.get(line.purchase_invoice_line_id, [])
        # Shared out over everything the bill line charged; only the part
        # asked for -- claimed, or blocked (backlog 78 row 1) -- is returned.
        charged = sum((amount for _, amount, _ in parts), ZERO)
        if charged <= ZERO:
            continue
        for code, amount, recoverable in parts:
            if recoverable is not claimable:
                continue
            totals[code] = totals.get(code, ZERO) + quantize_money(
                Decimal(str(line.tax_amount))
                * rupees.get(line.purchase_invoice_line_id, Decimal("1"))
                * amount
                / charged
            )
    return totals


def debit_note_reverse_charge(session: Session, note_id: UUID) -> ReverseChargeShare:
    """Return the reverse charge a debit note takes off its bill.

    Backlog 68 row 8, the twin of ``return_reverse_charge``: each line takes
    the share of its bill line's reverse charge that its taxable value is of
    the bill line's. The posting and GSTR-3B both read this.
    """
    lines = session.scalars(
        select(DebitNoteLine).where(
            DebitNoteLine.debit_note_id == note_id,
            DebitNoteLine.is_deleted.is_(False),
        )
    ).all()
    return reverse_charge_share(
        session,
        (
            (line.purchase_invoice_line_id, Decimal(str(line.taxable_amount)))
            for line in lines
        ),
    )


__all__ = [
    "DebitNoteService",
    "debit_note_reverse_charge",
    "debit_note_tax_by_component",
]
