"""What a firm has to declare for a period, read off what it actually sold.

Nothing here stores anything. A return is a **view of the documents**, and the
moment it were stored it could disagree with them -- a cancelled invoice, a
credit note raised late, an amended rate. So it is derived on every read, from
the invoices and credit notes as they stand.

The sections are the ones this system's data can honestly fill:

- **B2B** -- supplies to a customer carrying a GSTIN, invoice by invoice.
- **B2CL** -- inter-state supplies to an unregistered customer above the
  invoice-wise threshold.
- **B2CS** -- everything else unregistered, summarised by place of supply and
  rate, because that is all the return asks for, net of any credit notes
  issued to those buyers in the period.
- **CDNR** -- credit notes against registered customers. One to an
  unregistered customer is netted off its B2CS row instead: there is nobody
  to reverse a claim, and the section has no room for a number nobody reads.
- **HSN** -- what was sold, by HSN code and rate.
- **DOCS** -- the document series issued.

`app/einvoice` and this module split a line's tax through the **same**
`split_components`, so what is filed and what was registered can never
disagree about which bucket a component belongs in.

Two rules run through the whole module. **A supply is placed by the tax it
was charged**, never by an address: CGST with SGST is only chargeable within
one state and IGST only between two, so the document settles the question --
and for an unregistered buyer it is the only thing that can, there being no
GSTIN to read a state code from. Where the tax says a border was crossed and
the buyer is unregistered, the invoice is reported in `unplaced_invoices`
rather than filed with a blank cell the portal would reject. And **every
figure that leaves here is in rupees and paise**: documents are priced to
four decimals, no portal accepts that, and the rounding happens once, on the
way out, so the running totals behind it keep the scale they were priced at.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.credit_note.models import CreditNote, CreditNoteLine, CreditNoteStatus
from app.customers.models import Customer
from app.products.models import Product
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.tax.services.gst_buckets import GstBuckets, TaxComponent, split_components


def _filed(value: Decimal) -> float:
    """Round a figure to the scale a return is filed in: rupees and paise.

    Documents here are priced to four decimals and no GST portal accepts
    that, so every figure crossing out of this module is rounded -- once, at
    the point of declaring, so the running totals behind it keep the scale
    the documents were priced at. Rounding as they accumulate would let the
    HSN summary and the invoice detail drift apart a paisa at a time.

    Args:
        value: The amount to declare.

    Returns:
        The amount at two decimals.

    """
    return float(quantize_ledger(value))


#: Above this, an inter-state supply to an unregistered buyer is declared
#: invoice by invoice rather than summarised. The published figure; held here
#: rather than inline so the one place it is read is the one place to change.
B2CL_THRESHOLD = Decimal("250000")

#: What the invoice statuses mean for a return. A draft is not a supply and a
#: cancelled one has been undone, so neither is declared.
_LIVE_INVOICE_STATUSES = ("APPROVED", "CLOSED")


@dataclass(slots=True)
class _RateRow:
    """One rate's worth of a document or a summary."""

    rate: Decimal
    taxable: Decimal = ZERO
    buckets: GstBuckets = field(default_factory=GstBuckets)

    def add(self, taxable: Decimal, buckets: GstBuckets) -> None:
        """Fold one more line into this rate."""
        self.taxable += taxable
        self.buckets = self.buckets.plus(buckets)

    def subtract(self, taxable: Decimal, buckets: GstBuckets) -> None:
        """Take a credit note off this rate."""
        self.taxable -= taxable
        self.buckets = self.buckets.plus(buckets.negated())


@dataclass(slots=True)
class _CreditNotes:
    """The period's credit notes, split by whether the buyer is registered."""

    registered: list[dict[str, object]] = field(default_factory=list)
    unregistered: list[_RateRow] = field(default_factory=list)


class GstReturnService:
    """Derive GSTR-1 and the outward half of GSTR-3B for one period."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._firms = FirmMetadataReader(session)

    def gstr1(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> dict[str, object]:
        """Return the outward supplies for a period, section by section.

        Args:
            firm_scope: The owning firm.
            from_date: First day of the period, inclusive.
            to_date: Last day, inclusive.

        Returns:
            The sections, each already summed the way the return wants them.

        Raises:
            ValidationError: If the period runs backwards, or the firm has no
                GSTIN -- a return is filed *by* a GSTIN, so there is nothing to
                file without one.

        """
        if to_date < from_date:
            raise ValidationError("to_date cannot be before from_date.")
        firm = self._firms.get(firm_scope)
        seller_gstin = (firm.gst_number or "").strip().upper()
        if not seller_gstin:
            raise ValidationError(
                "This firm has no GST number, so it has no return to file."
            )
        seller_state = seller_gstin[:2]

        b2b: dict[str, dict[str, object]] = {}
        b2cl: list[dict[str, object]] = []
        b2cs: dict[tuple[str, str], _RateRow] = {}
        hsn: dict[tuple[str, str], dict[str, object]] = {}
        series: dict[str, dict[str, object]] = {}
        unplaced: list[str] = []

        for invoice, customer, lines in self._invoices(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ):
            buyer_gstin = (getattr(customer, "gst_number", None) or "").strip().upper()
            rates: dict[Decimal, _RateRow] = {}
            charged = GstBuckets()
            for taxable, buckets, product, quantity in lines:
                row = rates.setdefault(buckets.rate, _RateRow(rate=buckets.rate))
                row.add(taxable, buckets)
                charged = charged.plus(buckets)
                self._fold_hsn(hsn, product, quantity, taxable, buckets)
            self._fold_series(series, invoice)
            place = (
                buyer_gstin[:2]
                if buyer_gstin
                else self._place_of_supply(charged, seller_state)
            )
            if not place:
                unplaced.append(invoice.invoice_number)

            if buyer_gstin:
                # Registered buyer: declared invoice by invoice, whatever the
                # value, because the buyer claims credit against it.
                b2b.setdefault(
                    buyer_gstin,
                    {"gstin": buyer_gstin, "name": customer.name, "invoices": []},
                )
                invoices = b2b[buyer_gstin]["invoices"]
                assert isinstance(invoices, list)
                invoices.append(self._document(invoice, place, rates))
                continue
            interstate = place != seller_state
            if interstate and Decimal(str(invoice.grand_total)) > B2CL_THRESHOLD:
                b2cl.append(self._document(invoice, place, rates))
                continue
            # Everything else the return only wants summarised: an
            # unregistered buyer claims no credit, so the invoice number is of
            # no use to anybody reading it.
            for rate_row in rates.values():
                key = (place, str(rate_row.rate))
                summary = b2cs.setdefault(key, _RateRow(rate=rate_row.rate))
                summary.add(rate_row.taxable, rate_row.buckets)

        credits = self._credit_notes(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        )
        for credited in credits.unregistered:
            # Subtracted from the row it belongs to, and creating that row if
            # the period holds a credit and no supply at the same rate -- a
            # negative B2CS row is what a month of nothing but credits looks
            # like, and hiding it would leave the value undeclared.
            key = (
                self._place_of_supply(credited.buckets, seller_state),
                str(credited.rate),
            )
            row = b2cs.setdefault(key, _RateRow(rate=credited.rate))
            row.subtract(credited.taxable, credited.buckets)

        return {
            "gstin": seller_gstin,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "b2b": list(b2b.values()),
            "b2cl": b2cl,
            "b2cs": [
                {
                    "place_of_supply": place,
                    "rate": float(row.rate),
                    "taxable_value": _filed(row.taxable),
                    **self._bucket_fields(row.buckets),
                }
                for (place, _), row in sorted(b2cs.items())
            ],
            "cdnr": credits.registered,
            "hsn": [
                self._filed_row(row)
                for row in sorted(hsn.values(), key=lambda item: str(item["hsn"]))
            ],
            "docs": sorted(series.values(), key=lambda item: str(item["prefix"])),
            # Named rather than left as a blank cell. The portal rejects a row
            # with no place of supply, so a return that quietly carried one
            # would be refused at upload with nothing here to say which
            # invoice caused it.
            "unplaced_invoices": unplaced,
        }

    def gstr3b(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> dict[str, object]:
        """Return the outward half of the summary return.

        Aggregated from the same documents GSTR-1 reads, **not** from GSTR-1's
        own answer: parsing a report back out of its own JSON is how a summary
        drifts from the detail it is supposed to summarise.

        Only the outward half. Inward supplies and input tax credit are the
        purchase side, and declaring a figure this module cannot derive would
        be worse than leaving the box for somebody who can.

        Credit notes are **subtracted** rather than listed: 3B is a summary of
        what is payable, and a credit note reduces it.

        Args:
            firm_scope: The owning firm.
            from_date: First day of the period.
            to_date: Last day.

        Returns:
            Section 3.1(a), and what was taken off it.

        Raises:
            ValidationError: If the period runs backwards, or the firm has no
                GSTIN to file under.

        """
        if to_date < from_date:
            raise ValidationError("to_date cannot be before from_date.")
        firm = self._firms.get(firm_scope)
        seller_gstin = (firm.gst_number or "").strip().upper()
        if not seller_gstin:
            raise ValidationError(
                "This firm has no GST number, so it has no return to file."
            )

        taxable = ZERO
        buckets = GstBuckets()
        for _invoice, _customer, lines in self._invoices(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ):
            for line_taxable, line_buckets, _product, _quantity in lines:
                taxable += line_taxable
                buckets = buckets.plus(line_buckets)

        credited = ZERO
        credit_igst = credit_cgst = credit_sgst = ZERO
        credits = self._credit_notes(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        )
        # Both halves: 3B is a summary of what is payable, and an unregistered
        # buyer's credit reduces it exactly as a registered one does. Reading
        # only CDNR here is what left the two returns disagreeing.
        for note in credits.registered:
            credited += Decimal(str(note["taxable_value"]))
            credit_igst += Decimal(str(note["integrated_tax"]))
            credit_cgst += Decimal(str(note["central_tax"]))
            credit_sgst += Decimal(str(note["state_tax"]))
        for row in credits.unregistered:
            credited += row.taxable
            credit_igst += row.buckets.igst
            credit_cgst += row.buckets.cgst
            credit_sgst += row.buckets.sgst

        return {
            "gstin": seller_gstin,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "outward_taxable_supplies": {
                "taxable_value": _filed(taxable - credited),
                "integrated_tax": _filed(buckets.igst - credit_igst),
                "central_tax": _filed(buckets.cgst - credit_cgst),
                "state_tax": _filed(buckets.sgst - credit_sgst),
                "cess": _filed(buckets.cess),
            },
            "credit_notes_deducted": {
                "taxable_value": _filed(credited),
                "tax": _filed(credit_igst + credit_cgst + credit_sgst),
            },
            # Said rather than left blank: a zero here would read as "no input
            # credit", which is a different claim from "this module does not
            # know".
            "inward_supplies": "Not derived: the purchase side files this.",
        }

    # ---- reading -------------------------------------------------------

    def _invoices(self, *, firm_scope: UUID, from_date: date, to_date: date) -> list[
        tuple[
            SalesInvoice,
            Customer,
            list[tuple[Decimal, GstBuckets, Product | None, Decimal]],
        ]
    ]:
        """Return each live invoice in the period with its priced lines."""
        invoices = list(
            self._session.scalars(
                select(SalesInvoice)
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status.in_(_LIVE_INVOICE_STATUSES),
                    SalesInvoice.invoice_date >= from_date,
                    SalesInvoice.invoice_date <= to_date,
                )
                .order_by(SalesInvoice.invoice_date.asc())
            ).all()
        )
        if not invoices:
            return []
        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.sales_invoice_id.in_(
                        [invoice.id for invoice in invoices]
                    ),
                    SalesInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        )
        taxes: dict[UUID, list[SalesInvoiceLineTax]] = defaultdict(list)
        if lines:
            for component in self._session.scalars(
                select(SalesInvoiceLineTax).where(
                    SalesInvoiceLineTax.sales_invoice_line_id.in_(
                        [line.id for line in lines]
                    ),
                    SalesInvoiceLineTax.is_deleted.is_(False),
                )
            ).all():
                taxes[component.sales_invoice_line_id].append(component)
        products = self._products([line.product_id for line in lines])
        customers = self._customers([invoice.customer_id for invoice in invoices])
        by_invoice: dict[UUID, list[SalesInvoiceLine]] = defaultdict(list)
        for line in lines:
            by_invoice[line.sales_invoice_id].append(line)

        answer = []
        for invoice in invoices:
            customer = customers.get(invoice.customer_id)
            if customer is None:
                continue
            priced = [
                (
                    self._taxable(line),
                    split_components(
                        [
                            TaxComponent(
                                code=component.component_code,
                                percentage=Decimal(str(component.percentage)),
                                amount=Decimal(str(component.amount)),
                            )
                            for component in taxes.get(line.id, [])
                        ]
                    ),
                    products.get(line.product_id),
                    Decimal(str(line.current_invoice_quantity)),
                )
                for line in sorted(
                    by_invoice.get(invoice.id, []), key=lambda row: row.line_number
                )
            ]
            answer.append((invoice, customer, priced))
        return answer

    def _credit_notes(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> _CreditNotes:
        """Return credit notes issued in the period, split by buyer.

        Declared in the period they were **issued**, not the period of the
        invoice they credit: that is what the return asks for, and it is why a
        note against an old invoice still belongs in this month's filing.

        A registered buyer's note is declared in CDNR, note by note, because
        the buyer reverses its own credit against it. An unregistered buyer's
        is netted off the B2CS row for its place and rate -- there is nobody
        to reverse a claim, and the section has no room for a number nobody
        reads.

        Args:
            firm_scope: The owning firm.
            from_date: First day of the period.
            to_date: Last day.

        Returns:
            The CDNR rows, and the summary rows to take off B2CS.

        """
        notes = list(
            self._session.scalars(
                select(CreditNote)
                .where(
                    CreditNote.firm_id == firm_scope,
                    CreditNote.is_deleted.is_(False),
                    CreditNote.status == CreditNoteStatus.APPROVED.value,
                    CreditNote.credit_note_date >= from_date,
                    CreditNote.credit_note_date <= to_date,
                )
                .order_by(CreditNote.credit_note_date.asc())
            ).all()
        )
        if not notes:
            return _CreditNotes()
        customers = self._customers([note.customer_id for note in notes])
        crossed_a_border = self._interstate_invoices(
            [note.sales_invoice_id for note in notes]
        )
        invoice_numbers = {
            invoice_id: number
            for invoice_id, number in self._session.execute(
                select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                    SalesInvoice.id.in_([note.sales_invoice_id for note in notes])
                )
            ).all()
        }
        rates: dict[UUID, Decimal] = {}
        for line in self._session.scalars(
            select(CreditNoteLine).where(
                CreditNoteLine.credit_note_id.in_([note.id for note in notes]),
                CreditNoteLine.is_deleted.is_(False),
            )
        ).all():
            rates.setdefault(line.credit_note_id, Decimal(str(line.tax_rate_percent)))

        answer: list[dict[str, object]] = []
        unregistered: list[_RateRow] = []
        for note in notes:
            customer = customers.get(note.customer_id)
            gstin = (getattr(customer, "gst_number", None) or "").strip().upper()
            rate = rates.get(note.id, ZERO)
            taxable = Decimal(str(note.taxable_amount))
            tax = Decimal(str(note.tax_amount))
            # The note stores one tax figure, not a split. Re-split it the way
            # the supply it credits was taxed, read off that invoice rather
            # than off an address -- the same rule the place of supply uses,
            # and the only one an unregistered buyer can be judged by at all.
            interstate = note.sales_invoice_id in crossed_a_border
            if not gstin:
                # A credit note to an unregistered buyer is netted off the
                # B2CS row it belongs to, which is what the return asks for
                # and what keeps GSTR-1 reconciling against 3B. Filed in CDNR
                # it would be a claim about a buyer who cannot claim credit;
                # dropped -- which it was, on the belief that this system
                # could not produce one -- it left 3B deducting a credit that
                # GSTR-1 never declared.
                unregistered.append(
                    _RateRow(
                        rate=rate,
                        taxable=taxable,
                        buckets=GstBuckets(
                            igst=tax if interstate else ZERO,
                            cgst=ZERO if interstate else tax / 2,
                            sgst=ZERO if interstate else tax / 2,
                            rate=rate,
                        ),
                    )
                )
                continue
            answer.append(
                {
                    "gstin": gstin,
                    "name": getattr(customer, "name", ""),
                    "note_number": note.credit_note_number,
                    "note_date": note.credit_note_date.isoformat(),
                    "against_invoice": invoice_numbers.get(note.sales_invoice_id, ""),
                    "reason": note.reason,
                    "rate": float(rate),
                    "taxable_value": _filed(taxable),
                    "integrated_tax": _filed(tax if interstate else ZERO),
                    "central_tax": _filed(ZERO if interstate else tax / 2),
                    "state_tax": _filed(ZERO if interstate else tax / 2),
                    "cess": 0.0,
                }
            )
        return _CreditNotes(registered=answer, unregistered=unregistered)

    # ---- folding -------------------------------------------------------

    def _document(
        self,
        invoice: SalesInvoice,
        place: str,
        rates: dict[Decimal, _RateRow],
    ) -> dict[str, object]:
        """Describe one invoice the way the return states it."""
        taxable = quantize_money(sum((row.taxable for row in rates.values()), ZERO))
        buckets = GstBuckets()
        for row in rates.values():
            buckets = buckets.plus(row.buckets)
        return {
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat(),
            "invoice_value": _filed(Decimal(str(invoice.grand_total))),
            "place_of_supply": place,
            "rate": float(max(rates, default=ZERO)),
            "taxable_value": _filed(taxable),
            **self._bucket_fields(buckets),
        }

    @staticmethod
    def _bucket_fields(buckets: GstBuckets) -> dict[str, float]:
        """Name the four buckets the way the return does."""
        return {
            "integrated_tax": _filed(buckets.igst),
            "central_tax": _filed(buckets.cgst),
            "state_tax": _filed(buckets.sgst),
            "cess": _filed(buckets.cess),
        }

    def _fold_hsn(
        self,
        hsn: dict[tuple[str, str], dict[str, object]],
        product: Product | None,
        quantity: Decimal,
        taxable: Decimal,
        buckets: GstBuckets,
    ) -> None:
        """Add one line to the HSN summary.

        A product with no HSN is folded under a blank code rather than
        dropped: the summary has to add up to the supplies above it, and a
        missing code is a master to fix, not a supply to hide.
        """
        code = (getattr(product, "hsn_sac", None) or "").strip()
        key = (code, str(buckets.rate))
        row = hsn.setdefault(
            key,
            {
                "hsn": code,
                "description": getattr(product, "name", ""),
                "rate": float(buckets.rate),
                "quantity": 0.0,
                "taxable_value": 0.0,
                "integrated_tax": 0.0,
                "central_tax": 0.0,
                "state_tax": 0.0,
                "cess": 0.0,
            },
        )
        row["quantity"] = float(Decimal(str(row["quantity"])) + quantity)
        row["taxable_value"] = float(
            quantize_money(Decimal(str(row["taxable_value"])) + taxable)
        )
        row["integrated_tax"] = float(
            quantize_money(Decimal(str(row["integrated_tax"])) + buckets.igst)
        )
        row["central_tax"] = float(
            quantize_money(Decimal(str(row["central_tax"])) + buckets.cgst)
        )
        row["state_tax"] = float(
            quantize_money(Decimal(str(row["state_tax"])) + buckets.sgst)
        )
        row["cess"] = float(quantize_money(Decimal(str(row["cess"])) + buckets.cess))

    @staticmethod
    def _filed_row(row: dict[str, object]) -> dict[str, object]:
        """Declare an accumulated HSN row at the filing scale."""
        money = (
            "taxable_value",
            "integrated_tax",
            "central_tax",
            "state_tax",
            "cess",
        )
        return {
            key: _filed(Decimal(str(value))) if key in money else value
            for key, value in row.items()
        }

    @staticmethod
    def _fold_series(
        series: dict[str, dict[str, object]], invoice: SalesInvoice
    ) -> None:
        """Record the document series an invoice belongs to.

        The return asks which numbers were issued, so a firm cannot quietly
        skip a range. Derived from the number itself, since that is where the
        series lives.
        """
        number = invoice.invoice_number or ""
        prefix = number.rsplit("-", 1)[0] if "-" in number else number
        row = series.setdefault(
            prefix, {"prefix": prefix, "from": number, "to": number, "count": 0}
        )
        row["count"] = int(row["count"]) + 1  # type: ignore[call-overload]
        if number < str(row["from"]):
            row["from"] = number
        if number > str(row["to"]):
            row["to"] = number

    # ---- helpers -------------------------------------------------------

    @staticmethod
    def _taxable(line: SalesInvoiceLine) -> Decimal:
        """Return what a line was charged before tax.

        Gross less both discounts **plus its share of the freight**, which is
        the figure the tax was computed on. `net_amount` includes the tax, and
        declaring that as the taxable value would over-state every supply by
        its own tax.

        Freight belongs in here because delivery charged by the seller is
        ancillary to the supply of the goods and is taxed with them. Leaving
        it out would declare less than the invoice charged tax on, which is
        the one way a return can be wrong that nobody notices until an
        assessment.
        """
        return quantize_money(
            Decimal(str(line.gross_amount))
            - Decimal(str(line.discount_amount))
            - Decimal(str(line.bill_discount_amount))
            + Decimal(str(line.freight_amount))
        )

    def _seller_state(self, firm_id: UUID) -> str:
        """Return the firm's own state code."""
        return ((self._firms.get(firm_id).gst_number or "").strip().upper())[:2]

    @staticmethod
    def _place_of_supply(charged: GstBuckets, seller_state: str) -> str:
        """Return where an unregistered buyer's supply was made.

        Read off **the tax the invoice actually charged**, not off the
        customer's address. CGST and SGST are only chargeable within one
        state, so an invoice carrying them was a supply in the seller's own --
        that is what the document says, and the document is what is being
        declared. The address is a second opinion that can disagree with it.

        An inter-state supply to a buyer with no GSTIN has nowhere left to
        read a state code from: the buyer is unregistered, so the number that
        would carry it does not exist. Blank, and the caller declares the
        invoice unplaced rather than filing a row the portal will reject.

        Args:
            charged: The tax the invoice's lines actually carried.
            seller_state: The first two digits of the firm's own GSTIN.

        Returns:
            A two-digit state code, or blank where none can be derived.

        """
        return "" if charged.igst > ZERO else seller_state

    def _interstate_invoices(self, invoice_ids: list[UUID]) -> set[UUID]:
        """Return which of these invoices crossed a state border.

        Read off **the tax they charged**, not off an address. IGST is only
        chargeable between states and CGST with SGST only within one, so the
        document itself settles the question -- and for an unregistered buyer
        it is the only thing that can, since there is no GSTIN to read a state
        code from.

        Args:
            invoice_ids: The invoices to judge.

        Returns:
            The subset that carried integrated tax.

        """
        if not invoice_ids:
            return set()
        crossed: set[UUID] = set()
        rows = self._session.execute(
            select(
                SalesInvoiceLine.sales_invoice_id, SalesInvoiceLineTax.component_code
            )
            .join(
                SalesInvoiceLineTax,
                SalesInvoiceLineTax.sales_invoice_line_id == SalesInvoiceLine.id,
            )
            .where(
                SalesInvoiceLine.sales_invoice_id.in_(invoice_ids),
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoiceLineTax.is_deleted.is_(False),
            )
        ).all()
        for invoice_id, code in rows:
            # Asked of the same splitter the figures go through, with a unit
            # amount, so which bucket a code belongs to has exactly one
            # answer in this codebase. Matching the string here instead would
            # be a second opinion that can drift from the first.
            probe = split_components(
                [TaxComponent(code=code, percentage=ZERO, amount=Decimal("1"))]
            )
            if probe.igst > ZERO:
                crossed.add(invoice_id)
        return crossed

    def _products(self, ids: list[UUID]) -> dict[UUID, Product]:
        """Return the products named by a set of lines."""
        if not ids:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(Product.id.in_(ids))
            ).all()
        }

    def _customers(self, ids: list[UUID]) -> dict[UUID, Customer]:
        """Return the customers named by a set of documents."""
        if not ids:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Customer).where(Customer.id.in_(ids))
            ).all()
        }


__all__ = ["B2CL_THRESHOLD", "GstReturnService"]
