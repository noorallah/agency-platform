"""Import a month's GSTR-2B and match it to the firm's bills (backlog 78 row 3).

Decision A36, after TallyPrime, Zoho Books and ERPNext: the firm downloads the
2B JSON from the portal and imports it here; no portal connection is needed.
Each supplier invoice in it is matched to the firm's own bill by the supplier's
GSTIN and the supplier's bill number, read loosely -- case, spaces and
punctuation ignored, leading zeros dropped, because ``INV/001`` and ``inv-1``
are how the same number is typed by two people. A supplier's credit note
matches the debit note that recorded it (decision A31).

A document that finds its bill is MATCHED when the date and every head of tax
agree within the firm's tolerance (₹1 by default), DIFFERENT otherwise, with
what differs in words; one that finds none is NOT_IN_BOOKS. A person can match
a row by hand (MANUAL) where the numbers were typed beyond recognition, and
undo it. The month's reconciliation adds the other side: bills dated in the
month from a registered supplier, carrying credit, that no 2B row matched.

Importing a month again replaces it, so the reconciliation always reads one
statement; a hand match does not survive a re-import, because the statement it
was made against is gone.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_money
from app.finance.currency import rupee_rate, rupee_rate_sql
from app.gst_returns.models import Gstr2bDocument, Gstr2bImport

#: The sections of a 2B file this reads; anything else present is reported.
READ_SECTIONS = ("b2b", "cdnr")
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_HEADS = ("igst", "cgst", "sgst", "cess")


def normalise_number(number: str | None) -> str:
    """Reduce a document number to what identifies it, for matching.

    Upper case, letters and digits only, and each run of digits without its
    leading zeros: ``INV/0001``, ``inv-1`` and ``INV 1`` are one number.
    """
    token = re.sub(r"[^A-Z0-9]", "", (number or "").upper())
    return re.sub(r"\d+", lambda m: str(int(m.group())), token)


def _paise(value: Decimal) -> Decimal:
    """Round to the two places a return is filed in."""
    return value.quantize(Decimal("0.01"))


def _money(value: object) -> Decimal:
    """Read an amount from the file; anything unreadable is nothing."""
    try:
        return _paise(Decimal(str(value if value is not None else 0)))
    except (InvalidOperation, ValueError):
        return ZERO


def _date(value: object) -> date:
    """Read the portal's ``dd-mm-yyyy`` date."""
    try:
        return datetime.strptime(str(value), "%d-%m-%Y").date()
    except ValueError as exc:
        raise ValidationError(
            f"GSTR-2B date {value!r} is not dd-mm-yyyy, as the portal writes it."
        ) from exc


@dataclass
class ParsedDocument:
    """One supplier document read from the file."""

    supplier_gstin: str
    supplier_name: str | None
    document_type: str
    document_number: str
    document_date: date
    document_value: Decimal
    taxable_value: Decimal
    heads: dict[str, Decimal]
    itc_available: bool
    reverse_charge: bool


@dataclass
class ParsedFile:
    """What a 2B file holds that this reads, and what it skipped."""

    gstin: str | None
    return_period: str | None
    documents: list[ParsedDocument] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def parse_gstr2b(content: str) -> ParsedFile:
    """Read the portal's GSTR-2B JSON.

    Accepts the file as downloaded (``{"data": {...}}``) or its ``data`` alone.
    Reads ``docdata.b2b`` (invoices) and ``docdata.cdnr`` (credit and debit
    notes); any other section present is named in ``skipped``.

    Raises:
        ValidationError: When the text is not JSON or not a GSTR-2B.

    """
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "The file is not JSON. Download GSTR-2B from the portal as JSON."
        ) from exc
    data = payload.get("data", payload) if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("docdata"), dict):
        raise ValidationError(
            "This is not a GSTR-2B file: it has no 'docdata' section."
        )
    period = str(data.get("rtnprd") or "")
    parsed = ParsedFile(
        gstin=str(data.get("gstin") or "") or None,
        return_period=(
            f"{period[2:]}-{period[:2]}" if re.fullmatch(r"\d{6}", period) else None
        ),
    )
    docdata: dict[str, object] = data["docdata"]
    for name, section in docdata.items():
        if name not in READ_SECTIONS and section:
            parsed.skipped.append(name)
    for supplier in docdata.get("b2b") or []:  # type: ignore[attr-defined]
        for invoice in supplier.get("inv") or []:
            parsed.documents.append(
                _document(supplier, invoice, "INVOICE", number_key="inum")
            )
    for supplier in docdata.get("cdnr") or []:  # type: ignore[attr-defined]
        for note in supplier.get("nt") or []:
            kind = (
                "DEBIT_NOTE"
                if str(note.get("typ", "C")).upper() == "D"
                else ("CREDIT_NOTE")
            )
            parsed.documents.append(_document(supplier, note, kind, number_key="ntnum"))
    return parsed


def _document(
    supplier: dict[str, object],
    row: dict[str, object],
    kind: str,
    *,
    number_key: str,
) -> ParsedDocument:
    """Read one invoice or note under its supplier."""
    gstin = str(supplier.get("ctin") or "").strip().upper()
    number = str(row.get(number_key) or "").strip()
    if not gstin or not number:
        raise ValidationError(
            "A GSTR-2B document has no supplier GSTIN or no number; the file "
            "looks damaged. Download it again from the portal."
        )
    return ParsedDocument(
        supplier_gstin=gstin,
        supplier_name=str(supplier.get("trdnm") or "") or None,
        document_type=kind,
        document_number=number[:40],
        document_date=_date(row.get("dt")),
        document_value=_money(row.get("val")),
        taxable_value=_money(row.get("txval")),
        heads={head: _money(row.get(head)) for head in _HEADS},
        itc_available=str(row.get("itcavl", "Y")).upper() != "N",
        reverse_charge=str(row.get("rev", "N")).upper() == "Y",
    )


@dataclass(frozen=True)
class _BookDocument:
    """A bill or debit note of the firm's, in the terms 2B states."""

    id: UUID
    number: str
    document_date: date
    taxable_value: Decimal
    heads: dict[str, Decimal]


class Gstr2bService:
    """Import GSTR-2B, match it, and report the month's reconciliation."""

    def __init__(self, session: Session) -> None:
        """Hold the firm's session."""
        self._session = session

    # -- Import ---------------------------------------------------------------

    def import_file(
        self,
        *,
        firm_id: UUID,
        return_period: str,
        content: str,
        source_name: str | None,
        actor_id: UUID,
    ) -> Gstr2bImport:
        """Import one month's GSTR-2B, replacing any earlier import of it.

        Raises:
            ValidationError: When the period is malformed, the file is not a
                GSTR-2B, or it says it is for another month.

        """
        if not _PERIOD.match(return_period):
            raise ValidationError("Give the 2B month as YYYY-MM.")
        parsed = parse_gstr2b(content)
        if parsed.return_period and parsed.return_period != return_period:
            raise ValidationError(
                f"This GSTR-2B is for {parsed.return_period}, not {return_period}."
            )
        now = utc_now()
        for earlier in self._session.scalars(
            select(Gstr2bImport).where(
                Gstr2bImport.firm_id == firm_id,
                Gstr2bImport.return_period == return_period,
                Gstr2bImport.is_deleted.is_(False),
            )
        ).all():
            earlier.is_deleted = True
            earlier.deleted_at = now
            earlier.deleted_by = actor_id
            for row in self._documents(earlier.id):
                row.is_deleted = True
                row.deleted_at = now
                row.deleted_by = actor_id
        self._session.flush()
        imported = Gstr2bImport(
            firm_id=firm_id,
            return_period=return_period,
            gstin=parsed.gstin,
            source_name=(source_name or "").strip()[:260] or None,
            document_count=len(parsed.documents),
            skipped_sections=", ".join(parsed.skipped) or None,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(imported)
        self._session.flush()
        for item in parsed.documents:
            self._session.add(
                Gstr2bDocument(
                    gstr2b_import_id=imported.id,
                    firm_id=firm_id,
                    supplier_gstin=item.supplier_gstin,
                    supplier_name=item.supplier_name,
                    document_type=item.document_type,
                    document_number=item.document_number,
                    document_date=item.document_date,
                    document_value=item.document_value,
                    taxable_value=item.taxable_value,
                    itc_available=item.itc_available,
                    reverse_charge=item.reverse_charge,
                    created_by=actor_id,
                    updated_by=actor_id,
                    **item.heads,
                )
            )
        self._session.flush()
        self.match(imported, firm_id=firm_id)
        record_audit(
            self._session,
            action="gstr2b.imported",
            entity_type="gstr2b_import",
            entity_id=imported.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "return_period": return_period,
                "documents": len(parsed.documents),
                "skipped_sections": parsed.skipped,
            },
        )
        return imported

    def _documents(self, import_id: UUID) -> list[Gstr2bDocument]:
        """Return an import's live rows."""
        return list(
            self._session.scalars(
                select(Gstr2bDocument).where(
                    Gstr2bDocument.gstr2b_import_id == import_id,
                    Gstr2bDocument.is_deleted.is_(False),
                )
            ).all()
        )

    def current_import(self, firm_id: UUID, return_period: str) -> Gstr2bImport | None:
        """Return the month's live import, if it has one."""
        return self._session.scalar(
            select(Gstr2bImport).where(
                Gstr2bImport.firm_id == firm_id,
                Gstr2bImport.return_period == return_period,
                Gstr2bImport.is_deleted.is_(False),
            )
        )

    # -- Matching -------------------------------------------------------------

    def _tolerance(self, firm_id: UUID) -> Decimal:
        """Return how far tax may differ and still match."""
        from app.tax.services.gst_compliance import GstComplianceService

        return (
            GstComplianceService(self._session)
            .settings_response(firm_id)
            .gstr2b_tolerance
        )

    def _bills(self, firm_id: UUID, gstins: set[str]) -> dict[str, list[_BookDocument]]:
        """Return the live bills of suppliers with these GSTINs, by GSTIN."""
        from app.gst_returns.services.gstr_service import _bucket
        from app.purchase_invoice.models import (
            PurchaseInvoice,
            PurchaseInvoiceLine,
            PurchaseInvoiceLineTax,
        )
        from app.vendors.models import Vendor

        if not gstins:
            return {}
        rows = self._session.execute(
            select(
                PurchaseInvoice.id,
                PurchaseInvoice.supplier_invoice_number,
                PurchaseInvoice.supplier_invoice_date,
                PurchaseInvoice.grand_total,
                PurchaseInvoice.tax_total,
                func.upper(Vendor.gstin),
                # 2B is in rupees; a bill in another currency is compared at
                # its own rate, as its journal posted it (D-CMP-23).
                rupee_rate_sql(
                    PurchaseInvoice.currency_code, PurchaseInvoice.exchange_rate
                ),
            )
            .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                func.upper(Vendor.gstin).in_(sorted(gstins)),
            )
        ).all()
        ids = [row[0] for row in rows]
        rupees = {row[0]: Decimal(str(row[6])) for row in rows}
        heads: dict[UUID, dict[str, Decimal]] = {
            bill_id: dict.fromkeys(_HEADS, ZERO) for bill_id in ids
        }
        if ids:
            for bill_id, code, amount in self._session.execute(
                select(
                    PurchaseInvoiceLine.purchase_invoice_id,
                    PurchaseInvoiceLineTax.component_code,
                    PurchaseInvoiceLineTax.amount,
                )
                .join(
                    PurchaseInvoiceLine,
                    PurchaseInvoiceLine.id
                    == PurchaseInvoiceLineTax.purchase_invoice_line_id,
                )
                .where(
                    PurchaseInvoiceLine.purchase_invoice_id.in_(ids),
                    PurchaseInvoiceLine.is_deleted.is_(False),
                    PurchaseInvoiceLineTax.is_deleted.is_(False),
                    PurchaseInvoiceLineTax.included_in_price.is_(False),
                )
            ).all():
                bucket = _bucket(code, Decimal(str(amount)) * rupees[bill_id])
                for head in _HEADS:
                    heads[bill_id][head] += getattr(bucket, head)
        found: dict[str, list[_BookDocument]] = {}
        for bill_id, number, on, total, tax, gstin, rate in rows:
            found.setdefault(str(gstin), []).append(
                _BookDocument(
                    id=bill_id,
                    number=normalise_number(number),
                    document_date=on,
                    taxable_value=_paise(
                        (Decimal(str(total)) - Decimal(str(tax))) * Decimal(str(rate))
                    ),
                    heads={h: _paise(v) for h, v in heads[bill_id].items()},
                )
            )
        return found

    def _notes(self, firm_id: UUID, gstins: set[str]) -> dict[str, list[_BookDocument]]:
        """Return debit notes recording a supplier's credit note, by GSTIN."""
        from app.debit_note.models import DebitNote, DebitNoteStatus
        from app.purchase_invoice.models import PurchaseInvoice
        from app.vendors.models import Vendor

        if not gstins:
            return {}
        found: dict[str, list[_BookDocument]] = {}
        # A note is in its bill's currency: in rupees at the bill's rate.
        for note, currency, rate in self._session.execute(
            select(
                DebitNote, PurchaseInvoice.currency_code, PurchaseInvoice.exchange_rate
            )
            .join(Vendor, Vendor.id == DebitNote.vendor_id)
            .join(PurchaseInvoice, PurchaseInvoice.id == DebitNote.purchase_invoice_id)
            .where(
                DebitNote.firm_id == firm_id,
                DebitNote.is_deleted.is_(False),
                DebitNote.status == DebitNoteStatus.APPROVED.value,
                DebitNote.supplier_credit_note_number.is_not(None),
                func.upper(Vendor.gstin).in_(sorted(gstins)),
            )
        ).tuples():
            vendor = self._session.get(Vendor, note.vendor_id)
            gstin = (vendor.gstin or "").upper() if vendor else ""
            found.setdefault(gstin, []).append(
                _BookDocument(
                    id=note.id,
                    number=normalise_number(note.supplier_credit_note_number),
                    document_date=note.supplier_credit_note_date
                    or note.debit_note_date,
                    taxable_value=_paise(
                        Decimal(str(note.taxable_amount)) * rupee_rate(currency, rate)
                    ),
                    heads={},
                )
            )
        return found

    def match(self, imported: Gstr2bImport, *, firm_id: UUID) -> None:
        """Match every row of an import that a person has not matched by hand."""
        rows = [
            row for row in self._documents(imported.id) if row.match_status != "MANUAL"
        ]
        gstins = {row.supplier_gstin for row in rows}
        bills = self._bills(firm_id, gstins)
        notes = self._notes(firm_id, gstins)
        tolerance = self._tolerance(firm_id)
        for row in rows:
            row.purchase_invoice_id = None
            row.debit_note_id = None
            pool = (
                notes.get(row.supplier_gstin, [])
                if row.document_type == "CREDIT_NOTE"
                else (
                    bills.get(row.supplier_gstin, [])
                    if row.document_type == "INVOICE"
                    else []
                )
            )
            wanted = normalise_number(row.document_number)
            book = next((doc for doc in pool if doc.number == wanted), None)
            if book is None:
                row.match_status = "NOT_IN_BOOKS"
                row.match_note = None
                continue
            if row.document_type == "INVOICE":
                row.purchase_invoice_id = book.id
            else:
                row.debit_note_id = book.id
            differences = self._differences(row, book, tolerance)
            row.match_status = "DIFFERENT" if differences else "MATCHED"
            row.match_note = "; ".join(differences) or None
        self._session.flush()

    @staticmethod
    def _differences(
        row: Gstr2bDocument, book: _BookDocument, tolerance: Decimal
    ) -> list[str]:
        """Say what differs between a 2B row and the firm's document."""
        found: list[str] = []
        if row.document_date != book.document_date:
            found.append(
                f"date {row.document_date.isoformat()} in 2B, "
                f"{book.document_date.isoformat()} in the books"
            )
        if abs(Decimal(str(row.taxable_value)) - book.taxable_value) > tolerance:
            found.append(
                f"taxable {row.taxable_value} in 2B, {book.taxable_value} in the books"
            )
        for head, booked in book.heads.items():
            filed = Decimal(str(getattr(row, head)))
            if abs(filed - booked) > tolerance:
                found.append(f"{head.upper()} {filed} in 2B, {booked} in the books")
        return found

    def match_by_hand(
        self,
        document_id: UUID,
        *,
        firm_id: UUID,
        purchase_invoice_id: UUID | None,
        actor_id: UUID,
    ) -> Gstr2bDocument:
        """Match a 2B row to a bill by hand, or undo a hand match with None.

        Raises:
            ResourceNotFoundError: When the row or the bill is not the firm's.
            ValidationError: When the bill is not the supplier's, or the row is
                not an invoice.

        """
        from app.purchase_invoice.models import PurchaseInvoice
        from app.vendors.models import Vendor

        row = self._session.get(Gstr2bDocument, document_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("GSTR-2B document not found.")
        before: dict[str, object] = {
            "status": row.match_status,
            "bill": str(row.purchase_invoice_id),
        }
        if purchase_invoice_id is None:
            row.match_status = "NOT_IN_BOOKS"
            imported = self._session.get(Gstr2bImport, row.gstr2b_import_id)
            if imported is not None:
                self.match(imported, firm_id=firm_id)
        else:
            if row.document_type != "INVOICE":
                raise ValidationError("Only a supplier invoice is matched to a bill.")
            bill = self._session.get(PurchaseInvoice, purchase_invoice_id)
            if bill is None or bill.firm_id != firm_id or bill.is_deleted:
                raise ResourceNotFoundError("Purchase bill not found.")
            vendor = self._session.get(Vendor, bill.vendor_id)
            if vendor is None or (vendor.gstin or "").upper() != row.supplier_gstin:
                raise ValidationError(
                    f"{bill.invoice_number} is not from GSTIN {row.supplier_gstin}."
                )
            row.purchase_invoice_id = bill.id
            row.match_status = "MANUAL"
            row.match_note = None
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="gstr2b.matched_by_hand",
            entity_type="gstr2b_document",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "status": row.match_status,
                "bill": str(row.purchase_invoice_id),
            },
        )
        return row

    # -- Reconciliation ---------------------------------------------------------

    def reconciliation(self, firm_id: UUID, return_period: str) -> dict[str, object]:
        """Return the month: each 2B row with its status, and bills 2B lacks.

        The books' side is bills dated (by the supplier) in the month, from a
        supplier with a GSTIN, carrying tax, that no live 2B row of any month
        matched: the credit at risk if 3B claims it.
        """
        from app.purchase_invoice.models import PurchaseInvoice
        from app.vendors.models import Vendor

        if not _PERIOD.match(return_period):
            raise ValidationError("Give the 2B month as YYYY-MM.")
        imported = self.current_import(firm_id, return_period)
        rows = self._documents(imported.id) if imported is not None else []
        year, month = (int(part) for part in return_period.split("-"))
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        matched_bills = set(
            self._session.scalars(
                select(Gstr2bDocument.purchase_invoice_id).where(
                    Gstr2bDocument.firm_id == firm_id,
                    Gstr2bDocument.is_deleted.is_(False),
                    Gstr2bDocument.purchase_invoice_id.is_not(None),
                )
            ).all()
        )
        missing = [
            {
                "purchase_invoice_id": str(bill_id),
                "invoice_number": number,
                "supplier_invoice_number": supplier_number,
                "supplier_invoice_date": on.isoformat(),
                "supplier_name": name,
                "supplier_gstin": gstin,
                "tax_total": float(quantize_money(Decimal(str(tax)))),
            }
            for bill_id, number, supplier_number, on, name, gstin, tax in (
                self._session.execute(
                    select(
                        PurchaseInvoice.id,
                        PurchaseInvoice.invoice_number,
                        PurchaseInvoice.supplier_invoice_number,
                        PurchaseInvoice.supplier_invoice_date,
                        Vendor.display_name,
                        Vendor.gstin,
                        func.coalesce(
                            PurchaseInvoice.base_tax_total, PurchaseInvoice.tax_total
                        ),
                    )
                    .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
                    .where(
                        PurchaseInvoice.firm_id == firm_id,
                        PurchaseInvoice.is_deleted.is_(False),
                        PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                        PurchaseInvoice.supplier_invoice_date >= start,
                        PurchaseInvoice.supplier_invoice_date < end,
                        PurchaseInvoice.tax_total > 0,
                        Vendor.gstin.is_not(None),
                        Vendor.gstin != "",
                    )
                    .order_by(PurchaseInvoice.supplier_invoice_date.asc())
                ).all()
            )
            if bill_id not in matched_bills
        ]
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.match_status] = counts.get(row.match_status, 0) + 1
        return {
            "return_period": return_period,
            "imported": imported is not None,
            "import_id": str(imported.id) if imported else None,
            "imported_at": imported.created_at.isoformat() if imported else None,
            "source_name": imported.source_name if imported else None,
            "skipped_sections": (imported.skipped_sections or "") if imported else "",
            "counts": {**counts, "IN_BOOKS_ONLY": len(missing)},
            "documents": [
                {
                    "id": str(row.id),
                    "supplier_gstin": row.supplier_gstin,
                    "supplier_name": row.supplier_name,
                    "document_type": row.document_type,
                    "document_number": row.document_number,
                    "document_date": row.document_date.isoformat(),
                    "taxable_value": float(row.taxable_value),
                    "igst": float(row.igst),
                    "cgst": float(row.cgst),
                    "sgst": float(row.sgst),
                    "cess": float(row.cess),
                    "itc_available": row.itc_available,
                    "reverse_charge": row.reverse_charge,
                    "match_status": row.match_status,
                    "match_note": row.match_note,
                    "purchase_invoice_id": (
                        str(row.purchase_invoice_id)
                        if row.purchase_invoice_id
                        else None
                    ),
                    "debit_note_id": (
                        str(row.debit_note_id) if row.debit_note_id else None
                    ),
                }
                for row in sorted(
                    rows,
                    key=lambda r: (
                        r.supplier_gstin,
                        r.document_date,
                        normalise_number(r.document_number),
                    ),
                )
            ],
            "in_books_only": missing,
        }

    def matched_bill_ids(self, firm_id: UUID) -> set[UUID]:
        """Return every bill a live 2B row matched, for a matched-only 3B."""
        return {
            bill_id
            for bill_id in self._session.scalars(
                select(Gstr2bDocument.purchase_invoice_id).where(
                    Gstr2bDocument.firm_id == firm_id,
                    Gstr2bDocument.is_deleted.is_(False),
                    Gstr2bDocument.match_status.in_(("MATCHED", "MANUAL")),
                    Gstr2bDocument.purchase_invoice_id.is_not(None),
                )
            ).all()
            if bill_id is not None
        }
