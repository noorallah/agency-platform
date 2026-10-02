"""Registering e-invoices by hand on the portal (decision A42, the OFFLINE route).

Free, with no provider contract, which is why every Indian accounting product
offers it beside its own integration:

1. **Export** -- the chosen approved invoices as one JSON file in the
   portal's schema (the same payload the sandbox and the APIs send), for the
   bulk upload on the e-invoice portal. Each gets a registration row in
   PENDING, mode LIVE, so the screen shows what is waiting for its IRN.
2. **Import** -- the result the portal gives back, as JSON or a spreadsheet.
   Each entry is matched to its invoice by document number; an IRN makes the
   row REGISTERED with its acknowledgement and signed QR, an error makes it
   FAILED with the portal's words. An entry naming no exported invoice is
   reported, never guessed at.
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.file_import import FileFormat, normalise_heading, read_grid
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.einvoice.models import (
    EInvoiceProvider,
    EInvoiceRegistration,
    RegistrationMode,
    RegistrationStatus,
)
from app.einvoice.services.note_registration import (
    CREDIT_NOTE,
    DEBIT_NOTE,
    SALES_RETURN,
    note_column,
    note_payload,
    read_note,
)
from app.einvoice.services.payload import EInvoicePayloadBuilder
from app.einvoice.services.reporting_window import refuse_if_late
from app.sales_invoice.models import SalesInvoice

#: The keys a portal result names each value under, normalised: the JSON's own
#: and the bulk-upload tool's spreadsheet headings.
_KEYS: dict[str, tuple[str, ...]] = {
    "number": ("docno", "documentno", "documentnumber", "invoiceno", "no"),
    "irn": ("irn",),
    "ack_no": ("ackno", "acknowledgementno", "acknowledgementnumber"),
    "ack_date": ("ackdt", "ackdate", "acknowledgementdate"),
    "qr": ("signedqrcode", "qrcode", "signedqr"),
    "signed": ("signedinvoice",),
    "error": ("error", "errordetails", "errormessage", "errors", "remarks"),
    "type": ("typ", "doctype", "documenttype", "doctyp"),
}

#: The portal's document type to the kind of record it names (77 row 4).
_TYPES = {"INV": "SALES_INVOICE", "CRN": "CREDIT_NOTE", "DBN": "DEBIT_NOTE"}
#: The records a portal type may name: a CRN is a credit note or a sales
#: return's credit note (D-TAX-2).
_SAME_TYPE = {"CREDIT_NOTE": {"CREDIT_NOTE", "SALES_RETURN"}}


@dataclass
class OfflineImportReport:
    """What importing a portal result did."""

    registered: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)


def _pick(entry: dict[str, Any], kind: str) -> str:
    """Return one value of a result entry by any of its names, as text."""
    names = _KEYS[kind]
    for key, value in entry.items():
        if normalise_heading(key) in names and value not in (None, ""):
            if isinstance(value, list | dict):
                return json.dumps(value)
            return str(value).strip()
    return ""


def _flatten(entry: dict[str, Any]) -> dict[str, Any]:
    """Lift the values a result nests (``data``, ``DocDtls``) to the top."""
    flat = dict(entry)
    for nested in ("data", "Data", "result", "Result"):
        inner = entry.get(nested)
        if isinstance(inner, dict):
            flat.update(inner)
    document = flat.get("DocDtls")
    if isinstance(document, dict) and "No" in document:
        flat.setdefault("DocNo", document["No"])
    if isinstance(document, dict) and "Typ" in document:
        flat.setdefault("DocTyp", document["Typ"])
    return flat


def _number_from_signed(signed: str) -> str:
    """Read the document number out of a signed invoice JWT, if it carries one."""
    parts = signed.split(".")
    if len(parts) < 2:
        return ""
    body = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(body))
        data = claims.get("data", claims)
        if isinstance(data, str):
            data = json.loads(data)
        document = data.get("DocDtls", {}) if isinstance(data, dict) else {}
        return str(document.get("No", "")).strip()
    except (ValueError, TypeError, AttributeError):
        return ""


def _entries(content: bytes, file_format: str) -> list[dict[str, Any]]:
    """Read a portal result file into one dictionary per document."""
    if file_format == "json":
        try:
            value = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("The result file is not valid JSON.") from exc
        if isinstance(value, dict):
            value = value.get("data") or value.get("Data") or [value]
        if not isinstance(value, list):
            raise ValidationError("The result file holds no list of documents.")
        return [_flatten(item) for item in value if isinstance(item, dict)]
    fmt: FileFormat = "csv" if file_format == "csv" else "xlsx"
    headings, rows = read_grid(content, fmt)
    return [dict(zip(headings, row, strict=False)) for row in rows]


def _ack_time(raw: str) -> datetime | None:
    """Read the portal's acknowledgement date, as it writes it."""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    return None


class OfflineEInvoiceService:
    """Export invoices for the portal's bulk upload, and import its answer."""

    def __init__(self, session: Session) -> None:
        """Hold the firm's session."""
        self._session = session
        self._payloads = EInvoicePayloadBuilder(session)

    def export(
        self,
        invoice_ids: list[UUID],
        *,
        firm_scope: UUID,
        actor_id: UUID,
        credit_note_ids: list[UUID] | None = None,
        debit_note_ids: list[UUID] | None = None,
        sales_return_ids: list[UUID] | None = None,
    ) -> list[dict[str, object]]:
        """Return the bulk-upload JSON for these invoices, marking them PENDING.

        Raises:
            ValidationError: When an invoice is not approved, is registered
                already, or was cancelled on the portal.

        """
        if not (invoice_ids or credit_note_ids or debit_note_ids or sales_return_ids):
            raise ValidationError("Choose at least one document to export.")
        invoices = list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.id.in_(invoice_ids),
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                )
            )
        )
        if len(invoices) != len(set(invoice_ids)):
            raise ValidationError("An invoice to export was not found.")
        payloads: list[dict[str, object]] = []
        for invoice in sorted(invoices, key=lambda row: row.invoice_number):
            if invoice.status != "APPROVED":
                raise ValidationError(
                    f"{invoice.invoice_number} is {invoice.status.lower()}; only "
                    "an approved invoice is registered."
                )
            row = self._registration(invoice.id, firm_scope)
            if row is not None and row.status in (
                RegistrationStatus.REGISTERED.value,
                RegistrationStatus.CANCELLED.value,
            ):
                raise ValidationError(
                    f"{invoice.invoice_number} is {row.status.lower()} already "
                    f"({row.irn}); it is not exported again."
                )
            refuse_if_late(
                self._session,
                firm_scope=firm_scope,
                number=invoice.invoice_number,
                on=invoice.invoice_date,
            )
            payload = self._payloads.build(invoice, firm_id=firm_scope)
            if row is None:
                row = EInvoiceRegistration(
                    firm_id=firm_scope,
                    sales_invoice_id=invoice.id,
                    created_by=actor_id,
                )
                self._session.add(row)
            row.mode = RegistrationMode.LIVE.value
            row.provider = EInvoiceProvider.OFFLINE.value
            row.status = RegistrationStatus.PENDING.value
            row.request_payload = payload
            row.attempts = int(row.attempts or 0) + 1
            row.error_code = None
            row.error_message = None
            row.updated_by = actor_id
            payloads.append(payload)
        exported = [row.invoice_number for row in invoices]
        for kind, ids in (
            (CREDIT_NOTE, credit_note_ids or []),
            (DEBIT_NOTE, debit_note_ids or []),
            (SALES_RETURN, sales_return_ids or []),
        ):
            for note_id in ids:
                payloads.append(
                    self._export_note(
                        kind, note_id, firm_scope=firm_scope, actor_id=actor_id
                    )
                )
                exported.append(str(payloads[-1]["DocDtls"]["No"]))  # type: ignore[index]
        self._session.flush()
        record_audit(
            self._session,
            action="einvoice.exported",
            entity_type="einvoice_registration",
            # The first document of the upload names the event.
            entity_id=(
                invoices[0].id
                if invoices
                else [
                    *(credit_note_ids or []),
                    *(debit_note_ids or []),
                    *(sales_return_ids or []),
                ][0]
            ),
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"documents": exported},
        )
        self._session.commit()
        return payloads

    def import_result(
        self,
        content: bytes,
        file_format: str,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> OfflineImportReport:
        """Match a portal result to the exported invoices, and record it.

        Raises:
            ValidationError: When the file cannot be read or holds nothing.

        """
        entries = _entries(content, file_format)
        if not entries:
            raise ValidationError("The result file holds no documents.")
        report = OfflineImportReport()
        for entry in entries:
            signed = _pick(entry, "signed")
            number = _pick(entry, "number") or _number_from_signed(signed)
            if not number:
                continue
            row = self._registration_by_number(
                number,
                _TYPES.get(_pick(entry, "type").upper()),
                firm_scope=firm_scope,
            )
            if row is None:
                report.unmatched.append(number)
                continue
            if row.status == RegistrationStatus.REGISTERED.value:
                report.already.append(number)
                continue
            irn = _pick(entry, "irn")
            if irn:
                row.status = RegistrationStatus.REGISTERED.value
                row.irn = irn
                row.acknowledgement_number = _pick(entry, "ack_no") or None
                row.acknowledged_at = _ack_time(_pick(entry, "ack_date")) or utc_now()
                row.signed_qr_code = _pick(entry, "qr") or None
                row.signed_invoice = signed or None
                row.error_code = None
                row.error_message = None
                report.registered.append(number)
            else:
                row.status = RegistrationStatus.FAILED.value
                row.error_code = "PORTAL"
                row.error_message = (
                    _pick(entry, "error") or "The portal returned no IRN."
                )
                report.failed.append(number)
            row.mode = RegistrationMode.LIVE.value
            row.provider = EInvoiceProvider.OFFLINE.value
            row.updated_by = actor_id
            self._session.flush()
            record_audit(
                self._session,
                action="einvoice.imported",
                entity_type="einvoice_registration",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_scope,
                after_data={"invoice": number, "status": row.status, "irn": row.irn},
            )
        self._session.commit()
        return report

    def _export_note(
        self, kind: str, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> dict[str, object]:
        """Build one note's payload and mark it PENDING, as an invoice is."""
        note = read_note(self._session, kind, note_id, firm_scope=firm_scope)
        if note.status != "APPROVED":
            raise ValidationError(
                f"{note.number} is {note.status.lower()}; only an approved note "
                "is registered."
            )
        refuse_if_late(
            self._session, firm_scope=firm_scope, number=note.number, on=note.dated
        )
        column = note_column(kind)
        row = self._session.scalar(
            select(EInvoiceRegistration).where(
                EInvoiceRegistration.firm_id == firm_scope,
                getattr(EInvoiceRegistration, column) == note_id,
                EInvoiceRegistration.is_deleted.is_(False),
            )
        )
        if row is not None and row.status in (
            RegistrationStatus.REGISTERED.value,
            RegistrationStatus.CANCELLED.value,
        ):
            raise ValidationError(
                f"{note.number} is {row.status.lower()} already ({row.irn}); it "
                "is not exported again."
            )
        payload = note_payload(self._session, note, firm_id=firm_scope)
        if row is None:
            row = EInvoiceRegistration(
                firm_id=firm_scope, created_by=actor_id, **{column: note_id}
            )
            self._session.add(row)
        row.mode = RegistrationMode.LIVE.value
        row.provider = EInvoiceProvider.OFFLINE.value
        row.status = RegistrationStatus.PENDING.value
        row.request_payload = payload
        row.attempts = int(row.attempts or 0) + 1
        row.error_code = None
        row.error_message = None
        row.updated_by = actor_id
        return payload

    def _registration_by_number(
        self, number: str, kind: str | None, *, firm_scope: UUID
    ) -> EInvoiceRegistration | None:
        """Find the registration of the document a portal result names.

        By the portal's document type where the result gives it; otherwise an
        invoice first, then a credit note, then a debit note.
        """
        from app.credit_note.models import CreditNote
        from app.customer_debit_note.models import CustomerDebitNote
        from app.sales_return.models import SalesReturn

        lookups = (
            (
                "SALES_INVOICE",
                SalesInvoice,
                SalesInvoice.invoice_number,
                "sales_invoice_id",
            ),
            (
                "CREDIT_NOTE",
                CreditNote,
                CreditNote.credit_note_number,
                "credit_note_id",
            ),
            (
                "DEBIT_NOTE",
                CustomerDebitNote,
                CustomerDebitNote.debit_note_number,
                "customer_debit_note_id",
            ),
            # A CRN may be a sales return's credit note too (D-TAX-2).
            (
                "SALES_RETURN",
                SalesReturn,
                SalesReturn.return_number,
                "sales_return_id",
            ),
        )
        for name, model, column, key in lookups:
            if kind is not None and name not in _SAME_TYPE.get(kind, {kind}):
                continue
            document_id = self._session.scalar(
                select(model.id).where(
                    model.firm_id == firm_scope,
                    column == number,
                    model.is_deleted.is_(False),
                )
            )
            if document_id is None:
                continue
            row = self._session.scalar(
                select(EInvoiceRegistration).where(
                    EInvoiceRegistration.firm_id == firm_scope,
                    getattr(EInvoiceRegistration, key) == document_id,
                    EInvoiceRegistration.is_deleted.is_(False),
                )
            )
            if row is not None:
                return row
        return None

    def _registration(
        self, invoice_id: UUID, firm_scope: UUID
    ) -> EInvoiceRegistration | None:
        """Return the invoice's registration row, if it has one."""
        return self._session.scalar(
            select(EInvoiceRegistration).where(
                EInvoiceRegistration.firm_id == firm_scope,
                EInvoiceRegistration.sales_invoice_id == invoice_id,
                EInvoiceRegistration.is_deleted.is_(False),
            )
        )
