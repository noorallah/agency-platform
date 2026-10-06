"""Registering credit notes and customer debit notes with the portal (77 row 4).

A firm that e-invoices registers its credit and debit notes too: the portal
takes them as documents of type CRN and DBN, each referring to the invoice it
corrects. The rules are the invoice's -- registered once, withdrawn within 24
hours and never reused, a refusal recorded on the row -- and the route is the
firm's (A42): through the sandbox now, or exported for the portal's bulk
upload with the invoices.

A completed sales return is a credit note too (CGST s.34; GSTR-1 reports it
as one, D-CMP-2), so since D-TAX-2 it registers as a CRN like any other --
provided it returns goods an invoice billed. A return of goods only ever
delivered credits no tax invoice, and there is nothing for the portal to tie
it to.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import as_utc, utc_now
from app.credit_note.models import CreditNote, CreditNoteLine
from app.customer_debit_note.models import CustomerDebitNote, CustomerDebitNoteLine
from app.einvoice.models import EInvoiceRegistration, RegistrationStatus
from app.einvoice.services.einvoice_service import EInvoiceService
from app.einvoice.services.payload import EInvoicePayloadBuilder
from app.einvoice.services.portal import portal_for
from app.einvoice.services.reporting_window import refuse_if_late
from app.sales_invoice.models import SalesInvoice
from app.uom.services import stated_line

CREDIT_NOTE = "CREDIT_NOTE"
DEBIT_NOTE = "DEBIT_NOTE"
#: A sales return's credit note (D-TAX-2).
SALES_RETURN = "SALES_RETURN"

#: The portal's document type for each kind of note.
_PORTAL_TYPE = {CREDIT_NOTE: "CRN", DEBIT_NOTE: "DBN", SALES_RETURN: "CRN"}

#: The registration column that names each kind.
NOTE_COLUMNS = {
    CREDIT_NOTE: "credit_note_id",
    DEBIT_NOTE: "customer_debit_note_id",
    SALES_RETURN: "sales_return_id",
}

#: A return's statuses once it has credited the customer: its credit note is
#: issued, as an approved note's is (GSTR-1 reads the same two).
_ISSUED_RETURN = ("COMPLETED", "CLOSED")


@dataclass(frozen=True)
class ReturnLine:
    """A sales return line, in the shape the note payload reads."""

    sales_invoice_line_id: UUID | None
    product_id: UUID
    description: str | None
    quantity: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal


_CANCELLATION_WINDOW_HOURS = 24


@dataclass(frozen=True)
class NoteDocument:
    """One note, read for registering: what the portal needs to know."""

    kind: str
    id: UUID
    number: str
    on: str
    status: str
    invoice: SalesInvoice
    lines: list[CreditNoteLine] | list[CustomerDebitNoteLine] | list[ReturnLine]
    #: The note's own date, which the 30-day limit counts from (77 row 7).
    dated: date
    #: Every invoice the note credits; a return may cover several.
    invoices: tuple[SalesInvoice, ...] = ()


def read_note(
    session: Session, kind: str, note_id: UUID, *, firm_scope: UUID
) -> NoteDocument:
    """Return a credit or debit note with its lines and its invoice.

    Raises:
        ResourceNotFoundError: When the firm has no such note.

    """
    if kind == CREDIT_NOTE:
        credit = session.get(CreditNote, note_id)
        if credit is None or credit.firm_id != firm_scope or credit.is_deleted:
            raise ResourceNotFoundError("Credit note not found.")
        lines: list[CreditNoteLine] | list[CustomerDebitNoteLine] = list(
            session.scalars(
                select(CreditNoteLine)
                .where(
                    CreditNoteLine.credit_note_id == credit.id,
                    CreditNoteLine.is_deleted.is_(False),
                )
                .order_by(CreditNoteLine.line_number.asc())
            )
        )
        invoice_id, number, on, status = (
            credit.sales_invoice_id,
            credit.credit_note_number,
            credit.credit_note_date,
            credit.status,
        )
    elif kind == DEBIT_NOTE:
        debit = session.get(CustomerDebitNote, note_id)
        if debit is None or debit.firm_id != firm_scope or debit.is_deleted:
            raise ResourceNotFoundError("Debit note not found.")
        lines = list(
            session.scalars(
                select(CustomerDebitNoteLine)
                .where(
                    CustomerDebitNoteLine.debit_note_id == debit.id,
                    CustomerDebitNoteLine.is_deleted.is_(False),
                )
                .order_by(CustomerDebitNoteLine.line_number.asc())
            )
        )
        invoice_id, number, on, status = (
            debit.sales_invoice_id,
            debit.debit_note_number,
            debit.debit_note_date,
            debit.status,
        )
    elif kind == SALES_RETURN:
        return _read_return(session, note_id, firm_scope=firm_scope)
    else:
        raise ResourceNotFoundError(f"There is no {kind} to register.")
    invoice = session.get(SalesInvoice, invoice_id)
    if invoice is None:
        raise ResourceNotFoundError("The note's invoice was not found.")
    return NoteDocument(
        kind=kind,
        id=note_id,
        number=number,
        on=on.strftime("%d/%m/%Y"),
        dated=on,
        status=status,
        invoice=invoice,
        lines=lines,
    )


def _read_return(
    session: Session, return_id: UUID, *, firm_scope: UUID
) -> NoteDocument:
    """Read a sales return as the credit note it issues (D-TAX-2).

    Its parties come from the first invoice it returns goods from, and it
    refers to every one. Only the lines returning billed goods are credited
    against an invoice; the rest credit no tax invoice and are left out.

    Which invoices those are is what the return's print and GSTR-1 say
    (``bills_credited``): the bill a line names, and for a line raised off a
    delivery note every bill its units were set against when the return
    completed. Asked only of lines raised on a bill, a return off the note
    that credited a bill was refused here as crediting none (D-PRC-89).

    Raises:
        ResourceNotFoundError: When the firm has no such return.
        ValidationError: When it returns nothing an invoice billed.

    """
    from app.sales_return.billing import billed_share, bills_credited
    from app.sales_return.models import SalesReturn, SalesReturnLine

    found = session.get(SalesReturn, return_id)
    if found is None or found.firm_id != firm_scope or found.is_deleted:
        raise ResourceNotFoundError("Sales return not found.")
    completed = found.status in _ISSUED_RETURN
    rows = list(
        session.scalars(
            select(SalesReturnLine)
            .where(
                SalesReturnLine.sales_return_id == found.id,
                SalesReturnLine.is_deleted.is_(False),
            )
            .order_by(SalesReturnLine.line_number.asc())
        )
    )
    credited = bills_credited(session, rows, completed=completed)
    invoice_ids = list(
        dict.fromkeys(
            bill.invoice_id for row in rows for bill in credited.get(row.id, [])
        )
    )
    invoices = {
        row.id: row
        for row in session.scalars(
            select(SalesInvoice).where(
                SalesInvoice.id.in_(invoice_ids or [None]),
                SalesInvoice.firm_id == firm_scope,
            )
        )
    }
    ordered = tuple(invoices[key] for key in invoice_ids if key in invoices)
    if not ordered and not completed and found.status != "CANCELLED":
        # A return off a delivery note is set against its bills only when it
        # completes, so until then it cannot say whether it credits one.
        raise ValidationError(
            f"{found.return_number} is not completed; only a completed return "
            "is registered."
        )
    if not ordered:
        raise ValidationError(
            f"{found.return_number} returns goods no invoice billed, so it "
            "credits no tax invoice and is not registered."
        )
    lines: list[ReturnLine] = []
    for row in rows:
        bills = [
            bill for bill in credited.get(row.id, []) if bill.invoice_id in invoices
        ]
        if not bills:
            continue
        # What came back before any bill charged it credited nothing, and
        # is no part of the credit note.
        share = billed_share(row)
        # As the printed credit note states the line -- 7 for seven pieces
        # off a line sold by the box, not the 0.5833 of a box the row
        # stores -- through the function the print reads; the unit price is
        # then the taxable value over it, 100.000 (D-PRC-50).
        stated = stated_line(
            quantity=row.current_return_quantity,
            free_quantity=row.free_quantity,
            unit_price=row.unit_price,
            source_uom_id=row.sales_uom_id,
            typed_uom_id=row.return_uom_id,
            entered_quantity=row.entered_quantity,
            conversion_factor=row.conversion_factor,
        ).quantity
        tax = Decimal(str(row.tax_amount)) * share
        lines.append(
            ReturnLine(
                # The bill line whose tax heads the line's tax is split by,
                # and whose HSN code it carries: the one it names, or the
                # earliest it was set against. The bills of one delivery
                # note line charged the same goods under the same heads.
                sales_invoice_line_id=bills[0].invoice_line_id,
                product_id=row.product_id,
                description=row.description,
                quantity=stated if share == 1 else stated * share,
                # What the line credited before tax, as GSTR-1 reads it.
                taxable_amount=Decimal(str(row.net_amount)) * share - tax,
                tax_amount=tax,
            )
        )
    return NoteDocument(
        kind=SALES_RETURN,
        id=found.id,
        number=found.return_number,
        on=found.return_date.strftime("%d/%m/%Y"),
        # A completed return has issued its credit note, which is what an
        # approved note is to the checks that read this. A return approved
        # but not yet completed has credited nobody, and must not read as one.
        status=(
            "APPROVED"
            if found.status in _ISSUED_RETURN
            else (
                found.status
                if found.status in ("DRAFT", "CANCELLED")
                else "NOT COMPLETED"
            )
        ),
        invoice=ordered[0],
        lines=lines,
        dated=found.return_date,
        invoices=ordered,
    )


def note_payload(
    session: Session, note: NoteDocument, *, firm_id: UUID
) -> dict[str, object]:
    """Return the portal payload for a note."""
    return EInvoicePayloadBuilder(session).build_note(
        kind=_PORTAL_TYPE[note.kind],
        number=note.number,
        on=note.on,
        invoice=note.invoice,
        lines=list(note.lines),
        firm_id=firm_id,
        references=note.invoices or (note.invoice,),
    )


def note_column(kind: str) -> str:
    """Return the registration column that names this kind of note."""
    return NOTE_COLUMNS[kind]


class NoteRegistrationService:
    """Register and withdraw credit and debit notes on the firm's route."""

    def __init__(self, session: Session, *, base: EInvoiceService) -> None:
        """Ride on the invoice service's route (``EInvoiceService.for_firm``)."""
        self._session = session
        self._base = base

    def registration_for(
        self, kind: str, note_id: UUID, *, firm_scope: UUID
    ) -> EInvoiceRegistration | None:
        """Return a note's registration, or None."""
        column = getattr(EInvoiceRegistration, note_column(kind))
        return self._session.scalar(
            select(EInvoiceRegistration).where(
                EInvoiceRegistration.firm_id == firm_scope,
                column == note_id,
                EInvoiceRegistration.is_deleted.is_(False),
            )
        )

    def register(
        self, kind: str, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> EInvoiceRegistration:
        """Register one approved note; a refusal comes back FAILED.

        Raises:
            ValidationError: When the note is not approved, or its payload
                cannot be built.
            ConflictError: When it is registered, or was and was withdrawn.

        """
        note = read_note(self._session, kind, note_id, firm_scope=firm_scope)
        if note.status != "APPROVED":
            raise ValidationError(
                f"{note.number} is {note.status.lower()}; only an approved note "
                "is registered."
            )
        existing = self.registration_for(kind, note_id, firm_scope=firm_scope)
        if existing is not None and existing.status in (
            RegistrationStatus.REGISTERED.value,
            RegistrationStatus.CANCELLED.value,
        ):
            raise ConflictError(
                f"{note.number} is {existing.status.lower()} already "
                f"({existing.irn}); a cancelled IRN is not reused."
            )
        refuse_if_late(
            self._session,
            firm_scope=firm_scope,
            number=note.number,
            on=note.dated,
        )
        payload = note_payload(self._session, note, firm_id=firm_scope)
        row = existing or EInvoiceRegistration(
            firm_id=firm_scope, created_by=actor_id, **{note_column(kind): note_id}
        )
        row.mode = self._base.mode
        row.provider = self._base.provider
        row.request_payload = payload
        row.attempts = int(row.attempts or 0) + 1
        row.updated_by = actor_id
        result = portal_for(self._base.provider).register_invoice(payload)
        EInvoiceService._apply(row, result)
        if existing is None:
            self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="einvoice.registered" if result.ok else "einvoice.refused",
            entity_type="einvoice_registration",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"document": note.number, "status": row.status, "irn": row.irn},
        )
        return row

    def cancel(
        self,
        kind: str,
        note_id: UUID,
        *,
        reason: str,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> EInvoiceRegistration:
        """Withdraw a note's registration within the authority's 24 hours.

        Raises:
            ValidationError: When it is not registered, no reason is given,
                the window has closed, or the portal refuses.

        """
        row = self.registration_for(kind, note_id, firm_scope=firm_scope)
        if row is None or row.status != RegistrationStatus.REGISTERED.value:
            raise ValidationError("This note has no live registration.")
        if not reason.strip():
            raise ValidationError("Say why the registration is being withdrawn.")
        if row.acknowledged_at is not None:
            hours = (utc_now() - as_utc(row.acknowledged_at)).total_seconds() / 3600
            if hours > _CANCELLATION_WINDOW_HOURS:
                raise ValidationError(
                    "A registration can only be withdrawn within "
                    f"{_CANCELLATION_WINDOW_HOURS} hours."
                )
        result = portal_for(row.provider or row.mode).cancel_invoice(
            row.irn or "", reason=reason
        )
        if not result.ok:
            raise ValidationError(
                result.error_message or "The portal refused the cancellation."
            )
        row.status = RegistrationStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancellation_reason = reason.strip()[:200]
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="einvoice.cancelled",
            entity_type="einvoice_registration",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"status": row.status, "reason": row.cancellation_reason},
        )
        return row
