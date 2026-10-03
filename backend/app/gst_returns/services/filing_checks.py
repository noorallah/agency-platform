"""What a period's documents would trip on, listed before filing (GST-5, A82).

A return the portal rejects is a return filed late, and the fix is always in a
document: a buyer's GSTIN mistyped, a line with no HSN, a bill with no place of
supply. Tally's "GST exceptions" and ERPNext India Compliance's GSTR-1 checks
list them per document before anything is uploaded; this does the same, for
the same window GSTR-1 takes, and each row names the document to open.

The checks read the invoices GSTR-1 declares (``declared_invoices``), so a
period that passes here cannot fail there for one of these reasons:

- **GSTIN_INVALID** -- the firm's own, a buyer's or a supplier's GSTIN has the
  wrong shape, no state's code, or a wrong check character (GSTN's mod-36
  scheme). A buyer's sends their credit nowhere; a supplier's puts the firm's
  own credit at risk.
- **HSN_MISSING / HSN_SHORT** -- GSTR-1 table 12 wants six digits once the
  firm's turnover passes 5 crore and four below it (notification 78/2020-CT).
  The firm tells the platform it is past 5 crore by setting the date it
  e-invoices from, which is the same threshold, so that setting decides.
- **PLACE_OF_SUPPLY_MISSING** -- IGST charged to a buyer with no GSTIN and no
  state to read: GSTR-1 lists it in ``unplaced_invoices`` and cannot file it.
- **IRN_MISSING** -- a document the firm had to e-invoice with no live IRN
  (rule 48(4)), which is not a tax invoice at all.
- **CREDIT_NOTE_LATE** -- a credit note dated after 30 November following the
  end of the year of the supply it credits: section 34(2) lets no tax be
  reduced on it.
- **CREDIT_NOTE_ON_CANCELLED_INVOICE** -- a live credit note against a bill
  since cancelled, which credits a supply the return no longer declares.

Nothing is stored: like the returns, the list is derived on every read.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.validation.common import gstin_problem
from app.credit_note.models import CreditNote, CreditNoteStatus
from app.customer_debit_note.models import (
    CustomerDebitNote,
    CustomerDebitNoteStatus,
)
from app.customers.models import Customer
from app.einvoice.services.issue_gate import missing_irn
from app.gst_returns.services.gstr_service import GstReturnService
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.tax.services.gst_compliance import GstComplianceService
from app.vendors.models import Vendor

ERROR = "ERROR"
WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class FilingCheckRow:
    """One thing to put right, on one document."""

    check: str
    severity: str
    document_type: str
    document_id: UUID | None
    document_number: str
    document_date: date | None
    party_name: str
    message: str


def credit_note_deadline(supply_date: date) -> date:
    """Return the last day a credit note may reduce tax on a supply (s.34(2)).

    30 November following the end of the financial year the supply was made in.
    """
    year_end = supply_date.year + 1 if supply_date.month >= 4 else supply_date.year
    return date(year_end, 11, 30)


def hsn_digits(code: str | None) -> int:
    """Return how many digits an HSN or SAC code carries."""
    return sum(character.isdigit() for character in code or "")


class GstFilingChecks:
    """List what a period's documents would trip on before filing."""

    def __init__(self, session: Session) -> None:
        """Bind the checks to the firm's store."""
        self._session = session
        self._returns = GstReturnService(session)

    def required_hsn_digits(self, firm_id: UUID, *, on: date) -> int:
        """Return six once the firm e-invoices (past 5 crore), else four."""
        since = (
            GstComplianceService(self._session).settings_response(firm_id)
        ).einvoice_applicable_from
        return 6 if since is not None and since <= on else 4

    def rows(
        self, firm_id: UUID, *, from_date: date, to_date: date
    ) -> list[FilingCheckRow]:
        """Return every problem in the window, firm first, then by date."""
        rows = self._firm_gstin(firm_id)
        rows += self._invoices(firm_id, from_date=from_date, to_date=to_date)
        rows += self._credit_notes(firm_id, from_date=from_date, to_date=to_date)
        rows += self._debit_notes(firm_id, from_date=from_date, to_date=to_date)
        rows += self._purchase_invoices(firm_id, from_date=from_date, to_date=to_date)
        return sorted(
            rows,
            key=lambda row: (
                row.document_date is not None,
                row.document_date or date.min,
                row.document_number,
                row.check,
            ),
        )

    # ---- the firm --------------------------------------------------------

    def _firm_gstin(self, firm_id: UUID) -> list[FilingCheckRow]:
        """Check the GSTIN the return is filed under."""
        firm = FirmMetadataReader(self._session).get(firm_id)
        problem = gstin_problem(firm.gst_number)
        if problem is None:
            return []
        return [
            FilingCheckRow(
                check="GSTIN_INVALID",
                severity=ERROR,
                document_type="FIRM",
                document_id=None,
                document_number="",
                document_date=None,
                party_name=firm.name or "",
                message=f"The firm's own {problem}",
            )
        ]

    # ---- sales invoices --------------------------------------------------

    def _invoices(
        self, firm_id: UUID, *, from_date: date, to_date: date
    ) -> list[FilingCheckRow]:
        """Check each invoice GSTR-1 declares: GSTIN, HSN, place, IRN."""
        declared = self._returns.declared_invoices(
            firm_scope=firm_id, from_date=from_date, to_date=to_date
        )
        unplaced = self._returns.unplaced_invoice_ids(
            firm_scope=firm_id, from_date=from_date, to_date=to_date
        )
        rows: list[FilingCheckRow] = []
        for invoice, customer, lines in declared:

            def row(
                check: str,
                message: str,
                invoice: SalesInvoice = invoice,
                customer: Customer = customer,
            ) -> FilingCheckRow:
                """Return a row on this invoice."""
                return FilingCheckRow(
                    check=check,
                    severity=ERROR,
                    document_type="SALES_INVOICE",
                    document_id=invoice.id,
                    document_number=invoice.invoice_number,
                    document_date=invoice.invoice_date,
                    party_name=customer.name,
                    message=message,
                )

            problem = gstin_problem(customer.gst_number)
            if problem is not None:
                rows.append(row("GSTIN_INVALID", f"The buyer's {problem}"))
            rows += self._hsn_rows(firm_id, invoice, lines, row)
            if invoice.id in unplaced:
                rows.append(
                    row(
                        "PLACE_OF_SUPPLY_MISSING",
                        "IGST was charged to a buyer with no GSTIN and no state "
                        "on the bill; give the buyer's address a state.",
                    )
                )
            reason = missing_irn(
                self._session,
                firm_scope=firm_id,
                number=invoice.invoice_number,
                on=invoice.invoice_date,
                customer_id=invoice.customer_id,
                status=invoice.status,
                sales_invoice_id=invoice.id,
            )
            if reason is not None:
                rows.append(row("IRN_MISSING", reason))
        return rows

    def _hsn_rows(
        self,
        firm_id: UUID,
        invoice: SalesInvoice,
        lines: list[tuple[str | None, str]],
        row: Callable[[str, str], FilingCheckRow],
    ) -> list[FilingCheckRow]:
        """Return the invoice's HSN problems: one row for missing, one for short."""
        required = self.required_hsn_digits(firm_id, on=invoice.invoice_date)
        missing = [n for n, (code, _kind) in enumerate(lines, 1) if not code]
        short = [
            n
            for n, (code, _kind) in enumerate(lines, 1)
            if code and hsn_digits(code) < required
        ]
        rows = []
        if missing:
            rows.append(
                row(
                    "HSN_MISSING",
                    f"{_lines(missing)}: no HSN or SAC code.",
                )
            )
        if short:
            rows.append(
                row(
                    "HSN_SHORT",
                    f"{_lines(short)}: fewer than {required} digits of HSN, which "
                    "GSTR-1 table 12 needs at this firm's turnover.",
                )
            )
        return rows

    # ---- notes -----------------------------------------------------------

    def _credit_notes(
        self, firm_id: UUID, *, from_date: date, to_date: date
    ) -> list[FilingCheckRow]:
        """Check approved credit notes: GSTIN, time limit, cancelled bill, IRN."""
        found = self._session.execute(
            select(CreditNote, SalesInvoice, Customer)
            .join(SalesInvoice, SalesInvoice.id == CreditNote.sales_invoice_id)
            .join(Customer, Customer.id == CreditNote.customer_id)
            .where(
                CreditNote.firm_id == firm_id,
                CreditNote.is_deleted.is_(False),
                CreditNote.status == CreditNoteStatus.APPROVED.value,
                CreditNote.credit_note_date >= from_date,
                CreditNote.credit_note_date <= to_date,
            )
        ).all()
        rows: list[FilingCheckRow] = []
        for note, invoice, customer in found:

            def row(
                check: str,
                message: str,
                note: CreditNote = note,
                customer: Customer = customer,
            ) -> FilingCheckRow:
                """Return a row on this credit note."""
                return FilingCheckRow(
                    check=check,
                    severity=ERROR,
                    document_type="CREDIT_NOTE",
                    document_id=note.id,
                    document_number=note.credit_note_number,
                    document_date=note.credit_note_date,
                    party_name=customer.name,
                    message=message,
                )

            problem = gstin_problem(customer.gst_number)
            if problem is not None:
                rows.append(row("GSTIN_INVALID", f"The buyer's {problem}"))
            deadline = credit_note_deadline(invoice.invoice_date)
            if note.credit_note_date > deadline:
                rows.append(
                    row(
                        "CREDIT_NOTE_LATE",
                        f"Bill {invoice.invoice_number} is dated "
                        f"{invoice.invoice_date:%d-%m-%Y}; section 34(2) allowed a "
                        f"credit note against it until {deadline:%d-%m-%Y}, so it "
                        "reduces no tax.",
                    )
                )
            if invoice.status == "CANCELLED":
                rows.append(
                    row(
                        "CREDIT_NOTE_ON_CANCELLED_INVOICE",
                        f"Bill {invoice.invoice_number} has been cancelled; "
                        "cancel this credit note too, or it credits a supply the "
                        "return no longer declares.",
                    )
                )
            reason = missing_irn(
                self._session,
                firm_scope=firm_id,
                number=note.credit_note_number,
                on=note.credit_note_date,
                customer_id=note.customer_id,
                status=note.status,
                credit_note_id=note.id,
            )
            if reason is not None:
                rows.append(row("IRN_MISSING", reason))
        return rows

    def _debit_notes(
        self, firm_id: UUID, *, from_date: date, to_date: date
    ) -> list[FilingCheckRow]:
        """Check approved customer debit notes: GSTIN and IRN."""
        found = self._session.execute(
            select(CustomerDebitNote, Customer)
            .join(Customer, Customer.id == CustomerDebitNote.customer_id)
            .where(
                CustomerDebitNote.firm_id == firm_id,
                CustomerDebitNote.is_deleted.is_(False),
                CustomerDebitNote.status == CustomerDebitNoteStatus.APPROVED.value,
                CustomerDebitNote.debit_note_date >= from_date,
                CustomerDebitNote.debit_note_date <= to_date,
            )
        ).all()
        rows: list[FilingCheckRow] = []
        for note, customer in found:
            messages: list[tuple[str, str]] = []
            problem = gstin_problem(customer.gst_number)
            if problem is not None:
                messages.append(("GSTIN_INVALID", f"The buyer's {problem}"))
            reason = missing_irn(
                self._session,
                firm_scope=firm_id,
                number=note.debit_note_number,
                on=note.debit_note_date,
                customer_id=note.customer_id,
                status=note.status,
                customer_debit_note_id=note.id,
            )
            if reason is not None:
                messages.append(("IRN_MISSING", reason))
            rows += [
                FilingCheckRow(
                    check=check,
                    severity=ERROR,
                    document_type="CUSTOMER_DEBIT_NOTE",
                    document_id=note.id,
                    document_number=note.debit_note_number,
                    document_date=note.debit_note_date,
                    party_name=customer.name,
                    message=message,
                )
                for check, message in messages
            ]
        return rows

    # ---- purchases -------------------------------------------------------

    def _purchase_invoices(
        self, firm_id: UUID, *, from_date: date, to_date: date
    ) -> list[FilingCheckRow]:
        """Warn on supplier bills whose GSTIN would not carry the credit."""
        found = self._session.execute(
            select(PurchaseInvoice, Vendor)
            .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                PurchaseInvoice.invoice_date >= from_date,
                PurchaseInvoice.invoice_date <= to_date,
                Vendor.gstin.is_not(None),
            )
        ).all()
        rows: list[FilingCheckRow] = []
        for bill, vendor in found:
            problem = gstin_problem(vendor.gstin)
            if problem is None:
                continue
            rows.append(
                FilingCheckRow(
                    check="GSTIN_INVALID",
                    severity=WARNING,
                    document_type="PURCHASE_INVOICE",
                    document_id=bill.id,
                    document_number=bill.invoice_number,
                    document_date=bill.invoice_date,
                    party_name=vendor.name,
                    message=(
                        f"The supplier's {problem} The credit on this bill "
                        "will not match GSTR-2B."
                    ),
                )
            )
        return rows


def _lines(numbers: list[int]) -> str:
    """Name line numbers: ``Line 1``, ``Lines 1 and 3``, ``Lines 1, 2 and 4``."""
    text = [str(n) for n in numbers]
    if len(text) == 1:
        return f"Line {text[0]}"
    return f"Lines {', '.join(text[:-1])} and {text[-1]}"


__all__ = [
    "ERROR",
    "WARNING",
    "FilingCheckRow",
    "GstFilingChecks",
    "credit_note_deadline",
    "hsn_digits",
]
