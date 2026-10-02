"""Registering credit notes and customer debit notes with the portal (77 row 4).

A firm that e-invoices registers its credit and debit notes too: the portal
takes them as documents of type CRN and DBN, each referring to the invoice it
corrects. The rules are the invoice's -- registered once, withdrawn within 24
hours and never reused, a refusal recorded on the row -- and the route is the
firm's (A42): through the sandbox now, or exported for the portal's bulk
upload with the invoices.
"""

from dataclasses import dataclass
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
from app.sales_invoice.models import SalesInvoice

CREDIT_NOTE = "CREDIT_NOTE"
DEBIT_NOTE = "DEBIT_NOTE"

#: The portal's document type for each kind of note.
_PORTAL_TYPE = {CREDIT_NOTE: "CRN", DEBIT_NOTE: "DBN"}

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
    lines: list[CreditNoteLine] | list[CustomerDebitNoteLine]


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
        status=status,
        invoice=invoice,
        lines=lines,
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
    )


def note_column(kind: str) -> str:
    """Return the registration column that names this kind of note."""
    return "credit_note_id" if kind == CREDIT_NOTE else "customer_debit_note_id"


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
