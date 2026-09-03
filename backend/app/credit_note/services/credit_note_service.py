"""Raising, approving and cancelling a credit note.

The rule the module turns on: **tax comes off at the rate the invoice
charged**. Only the line being credited knows that rate, which is why a credit
note here always names an invoice and always names the lines within it. An
edit to a tax profile in September must not change what was charged in March
-- the same reasoning that stops an invoice re-reading a customer's discount.
"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.credit_note.models import CreditNote, CreditNoteLine, CreditNoteStatus
from app.credit_note.schemas import (
    CreditNoteCreate,
    CreditNoteLineResponse,
    CreditNoteLineWrite,
    CreditNoteReasonEnum,
    CreditNoteResponse,
    CreditNoteStatusEnum,
    CreditNoteUpdate,
)
from app.customers.models import Customer
from app.customers.schemas import CustomerReceivableTransactionCreate
from app.customers.services import CustomerService
from app.document_framework.schemas import DocumentLifecycleEventCreate
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

HUNDRED = Decimal("100")


class CreditNoteService(TransactionalDocumentService):
    """Credit a customer for value, without goods coming back."""

    DOCUMENT = DocumentTypeSpec(
        code="CREDIT_NOTE",
        name="Credit Note",
        description="Customer credit without a goods movement",
        category="SALES",
        module="credit_note",
        prefix="CN",
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
        self, statement: Select[tuple[CreditNote]], firm_id: UUID
    ) -> Select[tuple[CreditNote]]:
        """Restrict a query to one firm's live notes."""
        return statement.where(
            CreditNote.firm_id == firm_id, CreditNote.is_deleted.is_(False)
        )

    def list_notes(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        customer_id: UUID | None = None,
        status: CreditNoteStatusEnum | None = None,
    ) -> tuple[Sequence[CreditNote], int]:
        """Return one page of credit notes, newest first.

        Args:
            firm_scope: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            customer_id: Restrict to one customer.
            status: Restrict to one state.

        Returns:
            The page of notes and the total matching count.

        """
        statement = self._scoped(select(CreditNote), firm_scope)
        if customer_id is not None:
            statement = statement.where(CreditNote.customer_id == customer_id)
        if status is not None:
            statement = statement.where(CreditNote.status == status.value)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                CreditNote.credit_note_date.desc(),
                CreditNote.created_at.desc(),
                CreditNote.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get_note(self, note_id: UUID, *, firm_scope: UUID) -> CreditNote:
        """Return one credit note.

        Args:
            note_id: The note to read.
            firm_scope: The owning firm.

        Returns:
            The credit note.

        Raises:
            ResourceNotFoundError: If the firm has no such live note.

        """
        row = self._session.scalar(
            self._scoped(select(CreditNote), firm_scope).where(CreditNote.id == note_id)
        )
        if row is None:
            raise ResourceNotFoundError("Credit note not found.")
        return row

    def lines_of(self, note: CreditNote) -> list[CreditNoteLine]:
        """Return one note's lines, in order."""
        return list(
            self._session.scalars(
                select(CreditNoteLine)
                .where(
                    CreditNoteLine.credit_note_id == note.id,
                    CreditNoteLine.is_deleted.is_(False),
                )
                .order_by(CreditNoteLine.line_number.asc())
            ).all()
        )

    # ---- writes --------------------------------------------------------

    def create_note(
        self, data: CreditNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CreditNote:
        """Raise one credit note against an approved invoice.

        Args:
            data: The invoice, the lines and how much of each to credit.
            firm_id: The owning firm.
            actor_id: The user raising it.

        Returns:
            The stored note, still a draft.

        Raises:
            ValidationError: If the invoice cannot be credited, or a line
                credits more than it was charged.

        """
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        invoice = self._billable_invoice(data.sales_invoice_id, firm_id=firm_id)
        number = (
            data.credit_note_number.strip().upper()
            if data.credit_note_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.credit_note_date, firm_id
                ),
                branch_code=self._scope_code(invoice.branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.credit_note_date,
                actor_id=actor_id,
            )
        )
        row = CreditNote(
            firm_id=firm_id,
            customer_id=invoice.customer_id,
            branch_id=invoice.branch_id,
            sales_invoice_id=invoice.id,
            credit_note_number=number,
            credit_note_date=data.credit_note_date,
            reason=data.reason.value,
            status=CreditNoteStatus.DRAFT.value,
            salesman_id=invoice.salesman_id,
            territory_id=invoice.territory_id,
            reference_number=data.reference_number,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Credit note number already exists in this firm.")
        self._replace_lines(row, data.lines, invoice=invoice, actor_id=actor_id)
        self._documents.record_event(
            firm_id,
            DocumentLifecycleEventCreate(
                document_type_id=document_type.id,
                source_document_id=row.id,
                source_module_code="CREDIT_NOTE",
                document_number=row.credit_note_number,
                action="CREATED",
                from_state=None,
                to_state=row.status,
                details_json={
                    "credit_note_number": row.credit_note_number,
                    "sales_invoice_id": str(row.sales_invoice_id),
                },
                snapshot_json={"status": row.status},
            ),
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="credit_note.created",
            entity_type="credit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def update_note(
        self,
        note_id: UUID,
        data: CreditNoteUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CreditNote:
        """Change a credit note nobody has approved.

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
        if row.status != CreditNoteStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft credit note can be changed. Cancel this one and "
                "raise another."
            )
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        if values.get("credit_note_date") is not None:
            row.credit_note_date = values["credit_note_date"]
        if values.get("reason") is not None:
            row.reason = CreditNoteReasonEnum(values["reason"]).value
        if "reference_number" in values:
            row.reference_number = values["reference_number"]
        if "remarks" in values:
            row.remarks = values["remarks"]
        if data.lines is not None:
            invoice = self._billable_invoice(row.sales_invoice_id, firm_id=firm_scope)
            self._replace_lines(row, data.lines, invoice=invoice, actor_id=actor_id)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="credit_note.updated",
            entity_type="credit_note",
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
    ) -> CreditNote:
        """Recognise the credit: post the journal and move the balance.

        Both, or neither. A credit note that reduced the customer's balance
        and never reached the ledger would drive the subsidiary ledger and the
        general one apart by its value, which is the defect
        `CustomerService.post_receivable_transaction` is documented as still
        having on its own.

        Args:
            note_id: The note to approve.
            firm_scope: The owning firm.
            actor_id: The user approving it.
            expected_version: The version the caller last read, if any.

        Returns:
            The approved note.

        Raises:
            ValidationError: If it is not a draft, or credits nothing.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != CreditNoteStatus.DRAFT.value:
            raise ValidationError("Only a draft credit note can be approved.")
        if row.total_amount <= ZERO:
            raise ValidationError("A credit note for nothing cannot be approved.")
        before = self._snapshot(row)
        entry = self._posting.post_credit_note_document(
            firm_id=firm_scope,
            credit_note_id=row.id,
            credit_note_number=row.credit_note_number,
            note_date=row.credit_note_date,
            taxable_amount=Decimal(str(row.taxable_amount)),
            tax_amount=Decimal(str(row.tax_amount)),
            actor_id=actor_id,
        )
        row.journal_entry_id = None if entry is None else entry.id
        transaction = self._customers.post_receivable_transaction(
            row.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type="CREDIT_NOTE",
                transaction_date=row.credit_note_date,
                # The receivable ledger carries two decimals and a document
                # carries four. `sales_invoice` and `sales_return` each hit
                # this and each fixed it privately; this is the third copy,
                # and it was invisible until a seeded credit note reached it.
                #
                # Rounded the way the journal rounded it -- each part, then
                # summed -- rather than by rounding the document total. The
                # two books are recording one credit, and rounding a sum is
                # not always rounding the parts, so doing it differently
                # leaves the receivable and the ledger a paisa apart with
                # nothing to say which is right.
                amount=quantize_ledger(row.taxable_amount)
                + quantize_ledger(row.tax_amount),
                reference_number=row.credit_note_number,
                remarks=row.remarks,
            ),
            firm_scope=firm_scope,
            actor_id=actor_id,
            commit=False,
        )
        row.receivable_transaction_id = transaction.id
        row.status = CreditNoteStatus.APPROVED.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="credit_note.approved",
            entity_type="credit_note",
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
    ) -> CreditNote:
        """Withdraw a credit note, undoing whatever it did.

        An approved one is reversed rather than deleted: a posted entry is
        history, and the customer's balance is put back by the deltas the
        original transaction stored rather than recomputed -- the rule
        `CustomerService.reverse_receivable_transaction` exists to keep.

        Args:
            note_id: The note to withdraw.
            firm_scope: The owning firm.
            actor_id: The user withdrawing it.
            expected_version: The version the caller last read, if any.

        Returns:
            The cancelled note.

        Raises:
            ValidationError: If it is already cancelled.

        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status == CreditNoteStatus.CANCELLED.value:
            raise ValidationError("This credit note is already cancelled.")
        before = self._snapshot(row)
        if row.journal_entry_id is not None:
            # A mirror is right: what is being undone is worth exactly what it
            # was worth when it happened, unlike a stock reversal.
            self._journals.reverse_entry(
                row.journal_entry_id,
                firm_id=firm_scope,
                reference_number=f"{row.credit_note_number}-REV",
                journal_date=row.credit_note_date,
                actor_id=actor_id,
            )
        if row.receivable_transaction_id is not None:
            self._customers.reverse_receivable_transaction(
                row.receivable_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                commit=False,
            )
        row.status = CreditNoteStatus.CANCELLED.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="credit_note.cancelled",
            entity_type="credit_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    # ---- lines ---------------------------------------------------------

    def _billable_invoice(self, invoice_id: UUID, *, firm_id: UUID) -> SalesInvoice:
        """Return the invoice being credited, if it can be credited at all."""
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
                "Only an approved invoice can be credited. A draft is not a "
                "sale, and a cancelled one has already been undone."
            )
        return invoice

    def _replace_lines(
        self,
        note: CreditNote,
        lines: Sequence[CreditNoteLineWrite],
        *,
        invoice: SalesInvoice,
        actor_id: UUID,
    ) -> None:
        """Write the note's lines, replacing whatever it had.

        Replaced rather than merged: the lines *are* what is being credited,
        and reconciling them by position would let a line somebody removed
        stay in force.

        Raises:
            ValidationError: If a line names something outside the invoice, or
                credits more than the invoice charged for it.

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
                    "A credit note line must name a line of the invoice it credits."
                )
            charged = self._charged_taxable(source)
            already = self._already_credited(
                firm_id=note.firm_id,
                invoice_line_id=source.id,
                excluding_note_id=note.id,
            )
            asked = quantize_money(item.taxable_amount)
            if asked > charged - already:
                raise ValidationError(
                    "A credit note cannot credit more than the line was "
                    f"charged: {charged} charged, {already} already credited."
                )
            rate = self._tax_rate(source, charged)
            tax = quantize_money(asked * rate / HUNDRED)
            self._session.add(
                CreditNoteLine(
                    credit_note_id=note.id,
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
                )
            )
            taxable_total += asked
            tax_total += tax
        note.taxable_amount = quantize_money(taxable_total)
        note.tax_amount = quantize_money(tax_total)
        note.total_amount = quantize_money(taxable_total + tax_total)
        self._session.flush()

    @staticmethod
    def _charged_taxable(source: SalesInvoiceLine) -> Decimal:
        """Return what an invoice line was charged for, before tax.

        Exactly the base `SalesInvoiceService._line_net_amount` hands the tax
        engine: gross, less both discounts, **plus the line's charges and its
        share of the delivery charge**. Reading `net_amount` instead would
        include the tax and let a credit note credit it twice -- once inside
        the taxable value and once as the reversal beside it.

        The two charges were missing until the 2026-09-03 review. Freight
        moved inside the taxable value in #191 and this was not moved with it,
        which cost twice over: the cap stopped short of what the customer was
        actually charged, so a full credit was refused; and `_tax_rate`
        divided the line's tax by a base that excluded them, inflating the
        rate and reversing more output tax than had been collected on the
        part being credited.
        """
        return quantize_money(
            Decimal(str(source.gross_amount))
            - Decimal(str(source.discount_amount))
            - Decimal(str(source.bill_discount_amount))
            + Decimal(str(source.charges_amount))
            + Decimal(str(source.freight_amount))
        )

    @staticmethod
    def _tax_rate(source: SalesInvoiceLine, charged: Decimal) -> Decimal:
        """Return the effective rate the invoice line was taxed at.

        Derived from what was actually charged rather than read from the tax
        profile: the profile can be edited, and a rate that has changed since
        March must not decide what comes off a March supply. A line taxed at
        nothing reverses nothing, which is right for an exempt supply.
        """
        tax = Decimal(str(source.tax_amount))
        if charged <= ZERO or tax <= ZERO:
            return ZERO
        return quantize_money(tax * HUNDRED / charged)

    def _already_credited(
        self, *, firm_id: UUID, invoice_line_id: UUID, excluding_note_id: UUID
    ) -> Decimal:
        """Return what other live credit notes have already taken off a line.

        Counted across credit notes only. A sales return also credits the
        customer, and is deliberately **not** netted off here: a return may
        have sourced from a delivery note rather than from the invoice, so
        there is no reliable way to map it back to the invoice line, and a cap
        that silently under-counts is worse than one that says what it covers.
        A firm crediting the same value twice through two instruments is
        making a decision, not tripping over a missing guard.
        """
        total = self._session.scalar(
            select(func.coalesce(func.sum(CreditNoteLine.taxable_amount), ZERO))
            .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
            .where(
                CreditNoteLine.firm_id == firm_id,
                CreditNoteLine.sales_invoice_line_id == invoice_line_id,
                CreditNoteLine.is_deleted.is_(False),
                CreditNote.is_deleted.is_(False),
                CreditNote.id != excluding_note_id,
                CreditNote.status != CreditNoteStatus.CANCELLED.value,
            )
        )
        return quantize_money(Decimal(str(total or ZERO)))

    # ---- responses -----------------------------------------------------

    def note_response(self, row: CreditNote) -> CreditNoteResponse:
        """Build the response for one credit note.

        Args:
            row: The stored note.

        Returns:
            The response model.

        """
        lines = self.lines_of(row)
        names = {
            product_id: name
            for product_id, name in self._session.execute(
                select(Product.id, Product.name).where(
                    Product.id.in_([line.product_id for line in lines] or [None])
                )
            ).all()
        }
        invoice_number = (
            self._session.scalar(
                select(SalesInvoice.invoice_number).where(
                    SalesInvoice.id == row.sales_invoice_id
                )
            )
            or ""
        )
        customer_name = (
            self._session.scalar(
                select(Customer.display_name).where(Customer.id == row.customer_id)
            )
            or ""
        )
        return CreditNoteResponse(
            id=row.id,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            customer_name=customer_name,
            branch_id=row.branch_id,
            sales_invoice_id=row.sales_invoice_id,
            sales_invoice_number=invoice_number,
            credit_note_number=row.credit_note_number,
            credit_note_date=row.credit_note_date,
            reason=CreditNoteReasonEnum(row.reason),
            status=CreditNoteStatusEnum(row.status),
            taxable_amount=row.taxable_amount,
            tax_amount=row.tax_amount,
            total_amount=row.total_amount,
            reference_number=row.reference_number,
            remarks=row.remarks,
            journal_entry_id=row.journal_entry_id,
            version=row.version,
            lines=[
                CreditNoteLineResponse(
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
                for line in lines
            ],
        )

    def _snapshot(self, row: CreditNote) -> dict[str, object]:
        """Describe a credit note for the audit trail."""
        return {
            "credit_note_number": row.credit_note_number,
            "credit_note_date": row.credit_note_date.isoformat(),
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


__all__ = ["CreditNoteService"]
