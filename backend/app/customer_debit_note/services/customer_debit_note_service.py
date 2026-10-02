"""Raising, approving and cancelling a debit note to a customer.

The credit note's rule turned the other way: **tax is charged at the rate the
invoice charged**. Only the line being charged more knows that rate, which is
why a debit note always names an invoice and the lines within it -- an edit to
a tax profile in September must not change what a March supply is taxed at.

There is no cap. A credit note cannot take off more than was charged, but a
price can rise by whatever the parties agree; what stops a mistaken figure is
the approval, which is a separate authority from drafting.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.report_names import customer_names, customers_matching, product_names
from app.core.concurrency import assert_version
from app.core.database.batch import children_by_parent
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.customer_debit_note.models import (
    CustomerDebitNote,
    CustomerDebitNoteLine,
    CustomerDebitNoteStatus,
)
from app.customer_debit_note.schemas import (
    CustomerDebitNoteCreate,
    CustomerDebitNoteLineResponse,
    CustomerDebitNoteLineWrite,
    CustomerDebitNoteReasonEnum,
    CustomerDebitNoteRegisterRecord,
    CustomerDebitNoteResponse,
    CustomerDebitNoteStatusEnum,
    CustomerDebitNoteUpdate,
)
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CustomerService
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.services.output_tax import credited_tax_by_component

HUNDRED = Decimal("100")


class CustomerDebitNoteService(TransactionalDocumentService):
    """Charge a customer more on an invoice, with the tax that goes with it."""

    DOCUMENT = DocumentTypeSpec(
        code="CUSTOMER_DEBIT_NOTE",
        name="Customer Debit Note",
        description="More charged to a customer on an invoice already raised",
        category="SALES",
        module="customer_debit_note",
        # DN is the delivery note's and DBN the supplier debit note's.
        prefix="SDN",
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
        self._customers = CustomerService(session)

    # ---- reads ---------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[CustomerDebitNote]], firm_id: UUID
    ) -> Select[tuple[CustomerDebitNote]]:
        """Restrict a query to one firm's live notes."""
        return statement.where(
            CustomerDebitNote.firm_id == firm_id,
            CustomerDebitNote.is_deleted.is_(False),
        )

    def list_notes(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        customer_id: UUID | None = None,
        sales_invoice_id: UUID | None = None,
        status: CustomerDebitNoteStatusEnum | None = None,
        search: str | None = None,
        debit_note_from: date | None = None,
        debit_note_to: date | None = None,
    ) -> tuple[Sequence[CustomerDebitNote], int]:
        """Return one page of debit notes, newest first.

        Args:
            firm_scope: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            customer_id: Restrict to one customer.
            sales_invoice_id: Restrict to the notes raised on one invoice.
            status: Restrict to one state.
            search: Match the note's number or reference, or the customer's
                name, code or phone.
            debit_note_from: The first note date to include.
            debit_note_to: The last note date to include.

        Returns:
            The page of notes and the total matching count.

        """
        statement = self._scoped(select(CustomerDebitNote), firm_scope)
        if customer_id is not None:
            statement = statement.where(CustomerDebitNote.customer_id == customer_id)
        if sales_invoice_id is not None:
            statement = statement.where(
                CustomerDebitNote.sales_invoice_id == sales_invoice_id
            )
        if status is not None:
            statement = statement.where(CustomerDebitNote.status == status.value)
        if search:
            token = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    CustomerDebitNote.debit_note_number.ilike(token),
                    CustomerDebitNote.reference_number.ilike(token),
                    CustomerDebitNote.customer_id.in_(customers_matching(token)),
                )
            )
        if debit_note_from is not None:
            statement = statement.where(
                CustomerDebitNote.debit_note_date >= debit_note_from
            )
        if debit_note_to is not None:
            statement = statement.where(
                CustomerDebitNote.debit_note_date <= debit_note_to
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                CustomerDebitNote.debit_note_date.desc(),
                CustomerDebitNote.created_at.desc(),
                CustomerDebitNote.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get_note(self, note_id: UUID, *, firm_scope: UUID) -> CustomerDebitNote:
        """Return one debit note.

        Args:
            note_id: The note to read.
            firm_scope: The owning firm.

        Returns:
            The debit note.

        Raises:
            ResourceNotFoundError: If the firm has no such live note.

        """
        row = self._session.scalar(
            self._scoped(select(CustomerDebitNote), firm_scope).where(
                CustomerDebitNote.id == note_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Debit note not found.")
        return row

    def lines_of(self, note: CustomerDebitNote) -> list[CustomerDebitNoteLine]:
        """Return one note's lines, in order."""
        return list(
            self._session.scalars(
                select(CustomerDebitNoteLine)
                .where(
                    CustomerDebitNoteLine.debit_note_id == note.id,
                    CustomerDebitNoteLine.is_deleted.is_(False),
                )
                .order_by(CustomerDebitNoteLine.line_number.asc())
            ).all()
        )

    # ---- writes --------------------------------------------------------

    def create_note(
        self, data: CustomerDebitNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CustomerDebitNote:
        """Raise one debit note against an approved invoice.

        Args:
            data: The invoice, the lines and how much more each is charged.
            firm_id: The owning firm.
            actor_id: The user raising it.

        Returns:
            The stored note, still a draft.

        Raises:
            ValidationError: If the invoice cannot take a debit note, or a line
                names something outside it.

        """
        _document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        invoice = self._chargeable_invoice(data.sales_invoice_id, firm_id=firm_id)
        self._not_before_invoice(data.debit_note_date, invoice)
        number = self._issue_number(
            numbering_rule,
            typed=(
                data.debit_note_number.strip().upper()
                if data.debit_note_number
                else None
            ),
            number_column=CustomerDebitNote.debit_note_number,
            firm_id=firm_id,
            document_date=data.debit_note_date,
            actor_id=actor_id,
            branch_code=self._scope_code(invoice.branch_id),
            company_code=self._company_code(firm_id),
        )
        row = CustomerDebitNote(
            firm_id=firm_id,
            customer_id=invoice.customer_id,
            branch_id=invoice.branch_id,
            sales_invoice_id=invoice.id,
            debit_note_number=number,
            debit_note_date=data.debit_note_date,
            reason=data.reason.value,
            status=CustomerDebitNoteStatus.DRAFT.value,
            salesman_id=invoice.salesman_id,
            territory_id=invoice.territory_id,
            reference_number=data.reference_number,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Debit note number already exists in this firm.")
        self._replace_lines(row, data.lines, invoice=invoice, actor_id=actor_id)
        self._record_event(row, action="CREATED", from_state=None, actor_id=actor_id)
        record_audit(
            self._session,
            action="customer_debit_note.created",
            entity_type="customer_debit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def preview_note(
        self, data: CustomerDebitNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CustomerDebitNoteResponse:
        """Price a debit note exactly as raising it would, then save nothing.

        Staged through the create and rolled back: no note, no number used
        up, no audit row.
        """
        try:
            row = self.create_note(data, firm_id=firm_id, actor_id=actor_id)
            return self.note_response(row)
        finally:
            self._session.rollback()

    def update_note(
        self,
        note_id: UUID,
        data: CustomerDebitNoteUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CustomerDebitNote:
        """Change a debit note nobody has approved.

        Args:
            note_id: The note to change.
            data: The fields to change.
            firm_scope: The owning firm.
            actor_id: The user making the change.
            expected_version: The version the caller last read, if any.

        Returns:
            The changed note.

        Raises:
            ValidationError: If the note has left DRAFT.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != CustomerDebitNoteStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft debit note can be changed. Cancel this one and "
                "raise another."
            )
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        invoice = self._chargeable_invoice(row.sales_invoice_id, firm_id=firm_scope)
        if values.get("debit_note_date") is not None:
            self._not_before_invoice(values["debit_note_date"], invoice)
            row.debit_note_date = values["debit_note_date"]
        if values.get("reason") is not None:
            row.reason = CustomerDebitNoteReasonEnum(values["reason"]).value
        if "reference_number" in values:
            row.reference_number = values["reference_number"]
        if "remarks" in values:
            row.remarks = values["remarks"]
        if data.lines is not None:
            self._replace_lines(row, data.lines, invoice=invoice, actor_id=actor_id)
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row, action="EDITED", from_state=row.status, actor_id=actor_id
        )
        record_audit(
            self._session,
            action="customer_debit_note.updated",
            entity_type="customer_debit_note",
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
    ) -> CustomerDebitNote:
        """Recognise the charge: post the journal and raise the balance.

        Both, or neither -- a balance raised with no journal behind it drives
        the customer's ledger and the general one apart by its value.

        Args:
            note_id: The note to approve.
            firm_scope: The owning firm.
            actor_id: The user approving it.
            expected_version: The version the caller last read, if any.

        Returns:
            The approved note.

        Raises:
            ValidationError: If it is not a draft, charges nothing, or its
                invoice has since been cancelled.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != CustomerDebitNoteStatus.DRAFT.value:
            raise ValidationError("Only a draft debit note can be approved.")
        if row.total_amount <= ZERO:
            raise ValidationError("A debit note for nothing cannot be approved.")
        self._chargeable_invoice(row.sales_invoice_id, firm_id=firm_scope)
        before = self._snapshot(row)
        entry = self._posting.post_customer_debit_note_document(
            firm_id=firm_scope,
            debit_note_id=row.id,
            debit_note_number=row.debit_note_number,
            note_date=row.debit_note_date,
            taxable_amount=Decimal(str(row.taxable_amount)),
            tax_amount=Decimal(str(row.tax_amount)),
            actor_id=actor_id,
            # Charged per GST head the way the invoice was taxed (63.3); the
            # split reads only the invoice, so it serves a debit as well.
            tax_by_component=credited_tax_by_component(
                self._session, row.sales_invoice_id, Decimal(str(row.tax_amount))
            ),
        )
        row.journal_entry_id = None if entry is None else entry.id
        transaction = self._customers.post_receivable_transaction(
            row.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.DEBIT_NOTE,
                transaction_date=row.debit_note_date,
                # Rounded the way the journal rounded it -- each part, then
                # summed -- so the two books record one figure.
                amount=quantize_ledger(row.taxable_amount)
                + quantize_ledger(row.tax_amount),
                reference_type="CUSTOMER_DEBIT_NOTE",
                reference_id=row.id,
                reference_number=row.debit_note_number,
                remarks=row.remarks,
            ),
            firm_scope=firm_scope,
            actor_id=actor_id,
            commit=False,
        )
        row.receivable_transaction_id = transaction.id
        row.status = CustomerDebitNoteStatus.APPROVED.value
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="APPROVED",
            from_state=CustomerDebitNoteStatus.DRAFT.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="customer_debit_note.approved",
            entity_type="customer_debit_note",
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
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CustomerDebitNote:
        """Withdraw a debit note, undoing whatever it did.

        An approved one is reversed rather than deleted, and the balance is
        put back by the deltas the original transaction stored. Refused while
        money received on the invoice depends on the extra: undoing the
        charge would leave that money settling more than the bill now owes.

        Args:
            note_id: The note to withdraw.
            firm_scope: The owning firm.
            actor_id: The user withdrawing it.
            expected_version: The version the caller last read, if any.

        Returns:
            The cancelled note.

        Raises:
            ValidationError: If it is already cancelled, or what was received
                on the invoice would exceed the bill without it.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status == CustomerDebitNoteStatus.CANCELLED.value:
            raise ValidationError("This debit note is already cancelled.")
        before = self._snapshot(row)
        if row.status == CustomerDebitNoteStatus.APPROVED.value:
            self._refuse_if_paid_into(row, firm_scope=firm_scope)
        reversed_on = None
        if row.journal_entry_id is not None:
            reversed_on = self._journals.reverse_entry(
                row.journal_entry_id,
                firm_id=firm_scope,
                reference_number=f"{row.debit_note_number}-REV",
                actor_id=actor_id,
            ).journal_date
        if row.receivable_transaction_id is not None:
            self._customers.reverse_receivable_transaction(
                row.receivable_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reference_number=f"{row.debit_note_number}-REV",
                remarks=f"Cancelled debit note {row.debit_note_number}.",
                commit=False,
                on=reversed_on,
            )
        was = row.status
        row.status = CustomerDebitNoteStatus.CANCELLED.value
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(row, action="CANCELLED", from_state=was, actor_id=actor_id)
        record_audit(
            self._session,
            action="customer_debit_note.cancelled",
            entity_type="customer_debit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def _refuse_if_paid_into(self, row: CustomerDebitNote, *, firm_scope: UUID) -> None:
        """Refuse to cancel a charge that money received has already met.

        The invoice owes its own total plus its debit notes, less what came
        off it. Without this note it would owe that much less, and if what
        came off is more than the bill without the note, a receipt is
        settling a charge that no longer exists -- reverse it first.
        """
        # Imported here: the settlement module imports the customer services.
        from app.settlements.services.settlement_service import settled_against

        invoice = self._session.get(SalesInvoice, row.sales_invoice_id)
        if invoice is None:  # pragma: no cover - RESTRICT keeps it
            return
        settled = settled_against(
            self._session, firm_id=firm_scope, invoice_ids=[invoice.id]
        ).get(invoice.id, ZERO)
        mine = quantize_ledger(row.taxable_amount) + quantize_ledger(row.tax_amount)
        owing_without = quantize_ledger(invoice.grand_total) - settled - mine
        if owing_without < ZERO:
            raise ValidationError(
                f"Money received on invoice {invoice.invoice_number} has already "
                f"met {-owing_without} of this debit note. Reverse that receipt "
                "first, then cancel the note."
            )

    def _record_event(
        self,
        row: CustomerDebitNote,
        *,
        action: str,
        from_state: str | None,
        actor_id: UUID,
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
            details={
                "debit_note_number": row.debit_note_number,
                "sales_invoice_id": str(row.sales_invoice_id),
                "total_amount": str(row.total_amount),
            },
            snapshot={"status": row.status},
        )

    # ---- lines ---------------------------------------------------------

    def _chargeable_invoice(self, invoice_id: UUID, *, firm_id: UUID) -> SalesInvoice:
        """Return the invoice being charged more, if it can be at all."""
        invoice = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        if invoice.status not in {"APPROVED", "CLOSED"}:
            raise ValidationError(
                "A debit note can only be raised on an approved invoice. A "
                "draft is not a sale yet -- change it instead -- and a "
                "cancelled one has been undone."
            )
        return invoice

    @staticmethod
    def _not_before_invoice(on: date, invoice: SalesInvoice) -> None:
        """Refuse a debit note dated before the invoice it corrects."""
        if on < invoice.invoice_date:
            raise ValidationError(
                f"A debit note cannot be dated before invoice "
                f"{invoice.invoice_number} ({invoice.invoice_date.isoformat()})."
            )

    def _replace_lines(
        self,
        note: CustomerDebitNote,
        lines: Sequence[CustomerDebitNoteLineWrite],
        *,
        invoice: SalesInvoice,
        actor_id: UUID,
    ) -> None:
        """Write the note's lines, replacing whatever it had.

        Raises:
            ValidationError: If a line names something outside the invoice.

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
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.sales_invoice_id == invoice.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        }
        taxable_total = ZERO
        tax_total = ZERO
        for item in sorted(lines, key=lambda line: line.line_number):
            source = sources.get(item.sales_invoice_line_id)
            if source is None:
                raise ValidationError(
                    "A debit note line must name a line of the invoice it charges."
                )
            asked = quantize_money(item.taxable_amount)
            rate = self._tax_rate(source)
            tax = quantize_money(asked * rate / HUNDRED)
            self._session.add(
                CustomerDebitNoteLine(
                    debit_note_id=note.id,
                    firm_id=note.firm_id,
                    line_number=item.line_number,
                    sales_invoice_line_id=source.id,
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

    @staticmethod
    def _tax_rate(source: SalesInvoiceLine) -> Decimal:
        """Return the effective rate the invoice line was taxed at.

        What was actually charged over the base the tax engine was handed --
        gross less both discounts plus the line's charges and freight, the
        credit note's `_charged_taxable` -- rather than a tax profile that
        may since have been edited. A line taxed at nothing charges nothing,
        which is right for an exempt supply.
        """
        base = quantize_money(
            Decimal(str(source.gross_amount))
            - Decimal(str(source.discount_amount))
            - Decimal(str(source.bill_discount_amount))
            + Decimal(str(source.charges_amount))
            + Decimal(str(source.freight_amount))
        )
        tax = Decimal(str(source.tax_amount))
        if base <= ZERO or tax <= ZERO:
            return ZERO
        return quantize_money(tax * HUNDRED / base)

    # ---- responses -----------------------------------------------------

    def note_response(self, row: CustomerDebitNote) -> CustomerDebitNoteResponse:
        """Build the response for one debit note.

        Args:
            row: The stored note.

        Returns:
            The response model.

        """
        return self.note_responses([row])[0]

    def note_responses(
        self, rows: Sequence[CustomerDebitNote]
    ) -> list[CustomerDebitNoteResponse]:
        """Build the responses for a page of debit notes, one read per table."""
        if not rows:
            return []
        lines = children_by_parent(
            self._session,
            CustomerDebitNoteLine,
            CustomerDebitNoteLine.debit_note_id,
            [row.id for row in rows],
            CustomerDebitNoteLine.line_number.asc(),
        )
        names = {
            product_id: name
            for product_id, (_code, name) in product_names(
                self._session,
                (line.product_id for group in lines.values() for line in group),
            ).items()
        }
        invoices = self._invoice_numbers({row.sales_invoice_id for row in rows})
        customers = customer_names(self._session, (row.customer_id for row in rows))
        return [
            CustomerDebitNoteResponse(
                id=row.id,
                firm_id=row.firm_id,
                customer_id=row.customer_id,
                customer_name=customers.get(row.customer_id) or "",
                branch_id=row.branch_id,
                sales_invoice_id=row.sales_invoice_id,
                sales_invoice_number=invoices.get(row.sales_invoice_id) or "",
                debit_note_number=row.debit_note_number,
                debit_note_date=row.debit_note_date,
                reason=CustomerDebitNoteReasonEnum(row.reason),
                status=CustomerDebitNoteStatusEnum(row.status),
                taxable_amount=row.taxable_amount,
                tax_amount=row.tax_amount,
                total_amount=row.total_amount,
                reference_number=row.reference_number,
                remarks=row.remarks,
                journal_entry_id=row.journal_entry_id,
                version=row.version,
                lines=[
                    CustomerDebitNoteLineResponse(
                        id=line.id,
                        line_number=line.line_number,
                        sales_invoice_line_id=line.sales_invoice_line_id,
                        product_id=line.product_id,
                        product_name=names.get(line.product_id, ""),
                        description=line.description,
                        quantity=line.quantity,
                        taxable_amount=line.taxable_amount,
                        tax_amount=line.tax_amount,
                        total_amount=line.total_amount,
                        tax_rate_percent=line.tax_rate_percent,
                    )
                    for line in lines[row.id]
                ],
            )
            for row in rows
        ]

    def _snapshot(self, row: CustomerDebitNote) -> dict[str, object]:
        """Describe a debit note for the audit trail."""
        return {
            "debit_note_number": row.debit_note_number,
            "debit_note_date": row.debit_note_date.isoformat(),
            "sales_invoice_id": str(row.sales_invoice_id),
            "reason": row.reason,
            "status": row.status,
            "taxable_amount": str(row.taxable_amount),
            "tax_amount": str(row.tax_amount),
            "total_amount": str(row.total_amount),
            "journal_entry_id": (
                str(row.journal_entry_id) if row.journal_entry_id else None
            ),
        }

    # ---- reports -------------------------------------------------------

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[CustomerDebitNoteRegisterRecord]:
        """Every debit note raised in the window, newest first; paged in SQL."""
        rows = window.fetch(
            self._session,
            select(CustomerDebitNote)
            .where(
                CustomerDebitNote.firm_id == firm_scope,
                CustomerDebitNote.is_deleted.is_(False),
                *window.dated(CustomerDebitNote.debit_note_date),
            )
            .order_by(
                CustomerDebitNote.debit_note_date.desc(),
                CustomerDebitNote.created_at.desc(),
                CustomerDebitNote.id.desc(),
            ),
        )
        names = customer_names(self._session, (row.customer_id for row in rows))
        invoices = self._invoice_numbers({row.sales_invoice_id for row in rows})
        records = [
            CustomerDebitNoteRegisterRecord(
                debit_note_id=row.id,
                debit_note_number=row.debit_note_number,
                debit_note_date=row.debit_note_date,
                customer_id=row.customer_id,
                customer_name=names.get(row.customer_id) or str(row.customer_id),
                sales_invoice_id=row.sales_invoice_id,
                sales_invoice_number=invoices.get(row.sales_invoice_id, ""),
                reason=CustomerDebitNoteReasonEnum(row.reason),
                taxable_amount=row.taxable_amount,
                tax_amount=row.tax_amount,
                total_amount=row.total_amount,
                status=CustomerDebitNoteStatusEnum(row.status),
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def _invoice_numbers(self, ids: set[UUID]) -> dict[UUID, str]:
        """Read the invoice numbers in one query."""
        if not ids:
            return {}
        return {
            invoice_id: number
            for invoice_id, number in self._session.execute(
                select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                    SalesInvoice.id.in_(list(ids))
                )
            ).all()
        }


__all__ = ["CustomerDebitNoteService"]
