"""The GST sales register and the HSN summary of sales (backlog §87 #1).

The sales invoice register lists bills by number and total; a GST filer and
the firm's CA need the same bills by **tax head** -- the buyer's GSTIN, the
taxable value, IGST, CGST, SGST and cess -- with the credit notes, customer
debit notes and sales returns of the period beside them, and the outward
supplies folded by HSN. Tally, Busy and Marg print both, outside the return.

Nothing here prices a document a second time. Every figure is read through
`GstReturnService`'s own readers -- `_priced` for a bill, the `*_as_credits`
shapers for a note or a return -- so a head is settled at paise to what the
journal credited (`settle_to_ledger`, D-SELL-48) and the register cannot
disagree with GSTR-1 or the ledger about a paisa.

What counts is what GSTR-1 counts. Approved and closed bills, on the invoice
date. A credit note, a completed sales return and a customer debit note are
rows of their own on their own date -- the first two in minus, the debit note
in plus. A bill cancelled before its month's return was due is left out, as
the return leaves it out; one cancelled **after** stays in its month and its
cancellation is a row in minus on the day it happened (D-CMP-11).

The register reads a constant number of statements whatever the window holds
(`docs/PERFORMANCE_AT_VOLUME.md`): the late cancellations, the page of
documents, then each kind's rows, lines, taxes and customers once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session, lazyload, load_only

from app.core.pagination.reports import (
    WHOLE_HISTORY,
    ReportRows,
    ReportWindow,
    mapped_like,
)
from app.core.utils.money import ZERO, quantize_ledger
from app.credit_note.models import CreditNote, CreditNoteStatus
from app.customer_debit_note.models import (
    CustomerDebitNote,
    CustomerDebitNoteStatus,
)
from app.customers.models import Customer, CustomerReceivableTransaction
from app.gst_returns.services.gstr_service import (
    _CREDITED_RETURN_STATUSES,
    _INVOICE_COLUMNS,
    _LIVE_INVOICE_STATUSES,
    GstReturnService,
    _Credit,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_return.models import SalesReturn
from app.tax.services.gst_buckets import GstBuckets

#: What a register row is.
INVOICE = "INVOICE"
CREDIT_NOTE = "CREDIT_NOTE"
DEBIT_NOTE = "DEBIT_NOTE"
SALES_RETURN = "SALES_RETURN"
CANCELLED_INVOICE = "CANCELLED_INVOICE"

#: One document on a page: its id and its kind. A bill cancelled late is two
#: rows -- the bill and its cancellation -- so the id alone is not a key.
_Key = tuple[UUID, str]


@dataclass
class GstSalesRegisterRow:
    """One bill, credit note, debit note, sales return or late cancellation.

    A credit note's, a return's and a cancellation's figures are negative.
    """

    document_id: UUID
    document_date: date
    document_number: str
    document_type: str
    customer_id: UUID
    customer_name: str
    customer_gstin: str | None
    #: The two-digit state code the supply was made in, where one is known.
    place_of_supply: str
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    total_tax: Decimal
    document_total: Decimal
    #: The bill a note, a return or a cancellation corrects; empty on a bill.
    against_invoice_number: str = ""


@dataclass
class HsnSalesRow:
    """The outward supplies of one HSN code at one rate, net of credits."""

    hsn_code: str
    description: str
    rate: Decimal
    quantity: Decimal
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    total_tax: Decimal


def _gstin(customer: Customer | None) -> str:
    """Return a customer's GSTIN as a return states it, or blank."""
    return (getattr(customer, "gst_number", None) or "").strip().upper()


def _row(
    kind: str,
    *,
    document_id: UUID,
    on: date,
    number: str,
    customer_id: UUID,
    customer: Customer | None,
    place: str,
    taxable: Decimal,
    buckets: GstBuckets,
    total: Decimal,
    against: str = "",
) -> GstSalesRegisterRow:
    """Build one register row at the scale a return is filed in."""
    gstin = _gstin(customer)
    heads = [quantize_ledger(getattr(buckets, head)) for head in _HEADS]
    return GstSalesRegisterRow(
        document_id=document_id,
        document_date=on,
        document_number=number,
        document_type=kind,
        customer_id=customer_id,
        customer_name=getattr(customer, "name", None) or str(customer_id),
        customer_gstin=gstin or None,
        place_of_supply=place or gstin[:2],
        taxable_value=quantize_ledger(taxable),
        igst=heads[0],
        cgst=heads[1],
        sgst=heads[2],
        cess=heads[3],
        total_tax=sum(heads, ZERO),
        document_total=quantize_ledger(total),
        against_invoice_number=against,
    )


#: The heads a return files tax under, in the order a row states them.
_HEADS = ("igst", "cgst", "sgst", "cess")


class GstSalesRegisterService:
    """Read a period's outward supplies by tax head, and by HSN."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a firm store's session."""
        self._session = session
        self._returns = GstReturnService(session)

    def register(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[GstSalesRegisterRow]:
        """Return the window's declared documents by tax head, newest first."""
        standing, reversed_on = self._late_cancellations(firm_id, window)
        documents = self._documents(firm_id, window, standing, reversed_on)

        def of(kind: str) -> list[UUID]:
            return [key for key, found in documents if found == kind]

        rows: dict[_Key, GstSalesRegisterRow] = {}
        rows.update(self._invoice_rows(of(INVOICE), of(CANCELLED_INVOICE), reversed_on))
        rows.update(
            self._credit_rows(of(CREDIT_NOTE), of(DEBIT_NOTE), of(SALES_RETURN))
        )
        return mapped_like(documents, [rows[key] for key in documents if key in rows])

    def _late_cancellations(
        self, firm_id: UUID, window: ReportWindow
    ) -> tuple[list[UUID], dict[UUID, date]]:
        """Return the bills cancelled only after their month's return was due.

        Two answers: the cancelled bills dated in the window that still stand
        in it, and, by bill, the day of each such cancellation that fell in
        the window. Which is which turns on the firm's filing calendar, so it
        is settled here rather than in SQL; a firm cancels few bills that
        late, so the ids are few.
        """
        billed = window.dated(SalesInvoice.invoice_date)
        undone = window.dated(CustomerReceivableTransaction.transaction_date)
        statement = (
            select(
                SalesInvoice.id,
                SalesInvoice.invoice_date,
                func.max(CustomerReceivableTransaction.transaction_date),
            )
            .join(
                CustomerReceivableTransaction,
                CustomerReceivableTransaction.reference_id == SalesInvoice.id,
            )
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status == "CANCELLED",
                CustomerReceivableTransaction.reference_type == "SALES_INVOICE",
                CustomerReceivableTransaction.transaction_type == "CREDIT_NOTE",
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
            .group_by(SalesInvoice.id, SalesInvoice.invoice_date)
        )
        if billed:
            statement = statement.where(or_(and_(*billed), and_(*undone)))
        standing: list[UUID] = []
        reversed_on: dict[UUID, date] = {}
        for invoice_id, invoice_date, cancelled_on in self._session.execute(
            statement
        ).all():
            if cancelled_on <= self._returns._gstr1_due(firm_id, invoice_date):
                continue
            if _inside(window, invoice_date):
                standing.append(invoice_id)
            if _inside(window, cancelled_on):
                reversed_on[invoice_id] = cancelled_on
        return standing, reversed_on

    def _documents(
        self,
        firm_id: UUID,
        window: ReportWindow,
        standing: list[UUID],
        reversed_on: dict[UUID, date],
    ) -> list[_Key]:
        """Return the id and kind of each document in the window, newest first.

        Every kind is paged together, on each document's own date, so a page
        is a page of the register rather than of one table.
        """
        declared: ColumnElement[bool] = SalesInvoice.status.in_(_LIVE_INVOICE_STATUSES)
        if standing:
            declared = or_(declared, SalesInvoice.id.in_(standing))
        parts: list[Select[Any]] = [
            select(
                SalesInvoice.id.label("id"),
                literal(INVOICE).label("kind"),
                SalesInvoice.invoice_date.label("dated"),
                SalesInvoice.created_at.label("made"),
            ).where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                declared,
                *window.dated(SalesInvoice.invoice_date),
            ),
            select(
                CreditNote.id,
                literal(CREDIT_NOTE),
                CreditNote.credit_note_date,
                CreditNote.created_at,
            ).where(
                CreditNote.firm_id == firm_id,
                CreditNote.is_deleted.is_(False),
                CreditNote.status == CreditNoteStatus.APPROVED.value,
                *window.dated(CreditNote.credit_note_date),
            ),
            select(
                CustomerDebitNote.id,
                literal(DEBIT_NOTE),
                CustomerDebitNote.debit_note_date,
                CustomerDebitNote.created_at,
            ).where(
                CustomerDebitNote.firm_id == firm_id,
                CustomerDebitNote.is_deleted.is_(False),
                CustomerDebitNote.status == CustomerDebitNoteStatus.APPROVED.value,
                *window.dated(CustomerDebitNote.debit_note_date),
            ),
            select(
                SalesReturn.id,
                literal(SALES_RETURN),
                SalesReturn.return_date,
                SalesReturn.created_at,
            ).where(
                SalesReturn.firm_id == firm_id,
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.in_(_CREDITED_RETURN_STATUSES),
                *window.dated(SalesReturn.return_date),
            ),
        ]
        if reversed_on:
            parts.append(
                select(
                    CustomerReceivableTransaction.reference_id,
                    literal(CANCELLED_INVOICE),
                    func.max(CustomerReceivableTransaction.transaction_date),
                    func.max(CustomerReceivableTransaction.created_at),
                )
                .where(
                    CustomerReceivableTransaction.reference_type == "SALES_INVOICE",
                    CustomerReceivableTransaction.transaction_type == "CREDIT_NOTE",
                    CustomerReceivableTransaction.is_deleted.is_(False),
                    CustomerReceivableTransaction.reference_id.in_(list(reversed_on)),
                )
                .group_by(CustomerReceivableTransaction.reference_id)
            )
        keys = union_all(*parts).subquery()
        statement = select(keys.c.id, keys.c.kind).order_by(
            keys.c.dated.desc(), keys.c.made.desc(), keys.c.id.desc()
        )
        if window.page is None:
            return [(key, kind) for key, kind in self._session.execute(statement).all()]
        total = self._session.scalar(select(func.count()).select_from(keys))
        page = self._session.execute(
            statement.offset((window.page - 1) * window.page_size).limit(
                window.page_size
            )
        ).all()
        return ReportRows(
            [(key, kind) for key, kind in page], total_records=int(total or 0)
        )

    def _invoice_rows(
        self,
        billed: list[UUID],
        cancelled: list[UUID],
        reversed_on: dict[UUID, date],
    ) -> dict[_Key, GstSalesRegisterRow]:
        """Return a row per bill, and a row in minus per late cancellation."""
        ids = list({*billed, *cancelled})
        if not ids:
            return {}
        invoices = list(
            self._session.scalars(
                select(SalesInvoice)
                .where(SalesInvoice.id.in_(ids))
                .options(load_only(*_INVOICE_COLUMNS), lazyload("*"))
            ).all()
        )
        standing, undone = set(billed), set(cancelled)
        rows: dict[_Key, GstSalesRegisterRow] = {}
        for invoice, customer, lines in self._returns._priced(
            invoices, with_products=False
        ):
            taxable = sum((line[0] for line in lines), ZERO)
            buckets = GstBuckets()
            for line in lines:
                buckets = buckets.plus(line[1])
            total = Decimal(str(invoice.grand_total))
            place = (invoice.place_of_supply or "").strip()
            if invoice.id in standing:
                rows[(invoice.id, INVOICE)] = _row(
                    INVOICE,
                    document_id=invoice.id,
                    on=invoice.invoice_date,
                    number=invoice.invoice_number,
                    customer_id=invoice.customer_id,
                    customer=customer,
                    place=place,
                    taxable=taxable,
                    buckets=buckets,
                    total=total,
                )
            if invoice.id in undone:
                rows[(invoice.id, CANCELLED_INVOICE)] = _row(
                    CANCELLED_INVOICE,
                    document_id=invoice.id,
                    on=reversed_on[invoice.id],
                    number=invoice.invoice_number,
                    customer_id=invoice.customer_id,
                    customer=customer,
                    place=place,
                    taxable=-taxable,
                    buckets=buckets.negated(),
                    total=-total,
                    against=invoice.invoice_number,
                )
        return rows

    def _credit_rows(
        self,
        credit_notes: list[UUID],
        debit_notes: list[UUID],
        returns: list[UUID],
    ) -> dict[_Key, GstSalesRegisterRow]:
        """Return a row per note and per return, as GSTR-1 reads each one.

        A credit is stated in minus. A debit note reaches here as a negative
        credit, which is how the return carries it, so the same negation
        states it in plus.
        """
        reader = self._returns
        found: list[tuple[_Key, _Credit]] = []
        if credit_notes:
            notes = self._named(CreditNote, credit_notes)
            found += zip(
                [(note.id, CREDIT_NOTE) for note in notes],
                reader._credit_notes_as_credits(notes),
                strict=True,
            )
        if debit_notes:
            debits = self._named(CustomerDebitNote, debit_notes)
            found += zip(
                [(note.id, DEBIT_NOTE) for note in debits],
                reader._debit_notes_as_credits(debits),
                strict=True,
            )
        if returns:
            taken = self._named(SalesReturn, returns)
            found += zip(
                [(row.id, SALES_RETURN) for row in taken],
                reader._returns_as_credits(taken),
                strict=True,
            )
        if not found:
            return {}
        customers = reader._customers(list({credit.customer_id for _, credit in found}))
        rows = {}
        for key, credit in found:
            buckets = credit.buckets.negated()
            taxable = -credit.taxable
            tax = sum((getattr(buckets, head) for head in _HEADS), ZERO)
            rows[key] = _row(
                key[1],
                document_id=key[0],
                on=credit.issued_on,
                number=credit.number,
                customer_id=credit.customer_id,
                customer=customers.get(credit.customer_id),
                place="",
                taxable=taxable,
                buckets=buckets,
                total=taxable + tax,
                against=credit.against_invoice_number,
            )
        return rows

    def _named[
        DocumentT: (CreditNote, CustomerDebitNote, SalesReturn)
    ](self, model: type[DocumentT], ids: Sequence[UUID]) -> list[DocumentT]:
        """Return the documents of one kind named, in one read."""
        return list(self._session.scalars(select(model).where(model.id.in_(ids))).all())

    def hsn_summary(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[HsnSalesRow]:
        """Return the window's outward supplies by HSN code and rate.

        GSTR-1's Table 12 for the same days, folded by the same code: every
        billed line, taxed or not, less each credit note, sales return and
        late cancellation dated in the window, plus each customer debit note.
        A line with no HSN is grouped under an empty code, so the gap shows.
        """
        reader = self._returns
        first = window.from_date or date.min
        last = window.to_date or date.max
        hsn: dict[tuple[str, str], dict[str, object]] = {}
        for _, _, lines in reader._invoices(
            firm_scope=firm_id, from_date=first, to_date=last
        ):
            for taxable, buckets, product, quantity, _ in lines:
                reader._fold_hsn(hsn, product, quantity, taxable, buckets)
        credits = reader._credit_notes(
            firm_scope=firm_id, from_date=first, to_date=last
        )
        for invoice, customer, lines, cancelled_on in reader._late_cancellations(
            firm_scope=firm_id, from_date=first, to_date=last
        ):
            reader._fold_cancellation(
                credits, invoice, customer, lines, cancelled_on, ""
            )
        for product, quantity, taxable, buckets in credits.hsn:
            reader._fold_hsn(hsn, product, -quantity, -taxable, buckets.negated())
        rows = []
        for folded in sorted(
            hsn.values(), key=lambda item: (str(item["hsn"]), float(str(item["rate"])))
        ):
            filed = reader._filed_row(folded)
            heads = [
                Decimal(str(filed[key]))
                for key in ("integrated_tax", "central_tax", "state_tax", "cess")
            ]
            rows.append(
                HsnSalesRow(
                    hsn_code=str(filed["hsn"]),
                    description=str(filed["description"] or ""),
                    rate=Decimal(str(filed["rate"])),
                    quantity=Decimal(str(filed["quantity"])),
                    taxable_value=Decimal(str(filed["taxable_value"])),
                    igst=heads[0],
                    cgst=heads[1],
                    sgst=heads[2],
                    cess=heads[3],
                    total_tax=sum(heads, ZERO),
                )
            )
        return rows


def _inside(window: ReportWindow, on: date) -> bool:
    """Say whether a date falls in the window, both ends inclusive."""
    return (window.from_date is None or on >= window.from_date) and (
        window.to_date is None or on <= window.to_date
    )


__all__ = [
    "GstSalesRegisterRow",
    "GstSalesRegisterService",
    "HsnSalesRow",
]
