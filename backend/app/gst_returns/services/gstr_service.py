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
  A completed **sales return** is a credit note here (CGST Act s.34).
- **CDNUR** -- credits to an unregistered buyer against a B2CL invoice, which
  was declared invoice by invoice and so is credited note by note.
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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, Row, Select, func, select, true
from sqlalchemy.orm import Session, lazyload

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.chunks import chunks, over_chunks
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.credit_note.models import CreditNote, CreditNoteLine, CreditNoteStatus
from app.customers.gst_registration import (
    GSTR1_INVOICE_TYPES,
    ZERO_RATED_TYPES,
    effective_type,
)
from app.customers.models import Customer, CustomerReceivableTransaction
from app.debit_note.models import DebitNote, DebitNoteStatus
from app.products.models import Product
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.sales_return.models import SalesReturn, SalesReturnLine, SalesReturnLineTax
from app.tax.services.gst_buckets import (
    CESS,
    CGST,
    IGST,
    SGST,
    GstBuckets,
    TaxComponent,
    settle_to_ledger,
    split_components,
)

#: The place of supply a return gives a supply outside India.
FOREIGN_PLACE = "96"


def _bucket(component_code: str, amount: Decimal) -> GstBuckets:
    """Place one component's amount under the head a return files it in."""
    code = (component_code or "").strip().upper()
    amount = quantize_money(amount)
    if CGST in code:
        return GstBuckets(cgst=amount)
    if SGST in code:
        return GstBuckets(sgst=amount)
    if IGST in code:
        return GstBuckets(igst=amount)
    if CESS in code:
        return GstBuckets(cess=amount)
    return GstBuckets()


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
#: invoice by invoice rather than summarised: Rs 2,50,000 for invoices dated
#: before 1 August 2024, Rs 1,00,000 from that day (Notification 12/2024-CT,
#: amending rule 59). Date-effective, because a return for an older period is
#: still filed under the rule of its day (D-CMP-10).
B2CL_THRESHOLD = Decimal("100000")
B2CL_THRESHOLD_BEFORE_AUGUST_2024 = Decimal("250000")
B2CL_THRESHOLD_CHANGED_ON = date(2024, 8, 1)


def b2cl_threshold(invoice_date: date) -> Decimal:
    """Return the B2CL invoice-value limit in force on an invoice's date.

    Args:
        invoice_date: The invoice's own date.

    Returns:
        The value an inter-state bill to an unregistered buyer must exceed to
        be declared invoice by invoice.

    """
    if invoice_date < B2CL_THRESHOLD_CHANGED_ON:
        return B2CL_THRESHOLD_BEFORE_AUGUST_2024
    return B2CL_THRESHOLD


#: What a line that charged no GST was, for Table 8 and 3.1(c)/(e): a
#: component at 0% is nil-rated, no component at all is exempt, and a line
#: with no tax profile at all is outside GST.
NIL_RATED = "NIL_RATED"
EXEMPTED = "EXEMPTED"
NON_GST = "NON_GST"
TAXABLE = "TAXABLE"

#: What the invoice statuses mean for a return. A draft is not a supply and a
#: cancelled one has been undone, so neither is declared.
_LIVE_INVOICE_STATUSES = ("APPROVED", "CLOSED")

#: A sales return has given tax back once it is completed -- the customer is
#: credited and the output tax reversed -- and closing it changes neither.
_CREDITED_RETURN_STATUSES = ("COMPLETED", "CLOSED")


def gstr1_due_date(invoice_date: date) -> date:
    """Return when an invoice's GSTR-1 was due: the 11th of the next month.

    Nothing in this system records that a return was filed, so the due date
    stands in for it: once it has passed, the month is taken as filed, and a
    later cancellation cannot rewrite it (D-CMP-11).

    Args:
        invoice_date: The invoice's own date.

    Returns:
        The 11th of the month after the invoice's month.

    """
    if invoice_date.month == 12:
        return date(invoice_date.year + 1, 1, 11)
    return date(invoice_date.year, invoice_date.month + 1, 11)


#: The longest period one return may be asked for, in calendar months. GSTR-1
#: and 3B are filed monthly, or quarterly under QRMP; a year is GSTR-9, a
#: different return. A year of GSTR-1 on the volume firm read 280,000 lines
#: and took 64 s (backlog 56 C, step 4).
MAX_RETURN_MONTHS = 3


def _check_period(from_date: date, to_date: date) -> None:
    """Refuse a period that runs backwards or spans more than a quarter."""
    if to_date < from_date:
        raise ValidationError("to_date cannot be before from_date.")
    months = (to_date.year - from_date.year) * 12 + to_date.month - from_date.month
    if months >= MAX_RETURN_MONTHS:
        raise ValidationError(
            f"A return covers at most {MAX_RETURN_MONTHS} calendar months -- a "
            "month, or a quarter under QRMP. Ask for each period separately."
        )


class _PricedLine(Protocol):
    """The fields of an invoice line the return prices it from."""

    @property
    def tax_profile_id(self) -> UUID | None:
        """The tax profile the line named, if any."""

    @property
    def gross_amount(self) -> Decimal:
        """Quantity times price."""

    @property
    def discount_amount(self) -> Decimal:
        """The line's own discount."""

    @property
    def bill_discount_amount(self) -> Decimal:
        """Its share of the bill's discount."""

    @property
    def charges_amount(self) -> Decimal:
        """The line's own charges."""

    @property
    def freight_amount(self) -> Decimal:
        """Its share of the freight."""


class _PricedTax(Protocol):
    """The fields of a line's tax component the return reads."""

    @property
    def component_code(self) -> str:
        """CGST, SGST, IGST or CESS."""

    @property
    def percentage(self) -> Decimal:
        """The rate charged."""

    @property
    def amount(self) -> Decimal:
        """The tax charged."""


#: What `_priced` reads of each line: the columns, never the whole row, since
#: a year of lines as ORM objects was a large part of the 64 s GSTR-1 took on
#: the volume firm (backlog 56 C, step 4).
_LINE_COLUMNS = (
    SalesInvoiceLine.id,
    SalesInvoiceLine.sales_invoice_id,
    SalesInvoiceLine.line_number,
    SalesInvoiceLine.product_id,
    SalesInvoiceLine.hsn_sac,
    SalesInvoiceLine.current_invoice_quantity,
    SalesInvoiceLine.tax_profile_id,
    SalesInvoiceLine.gross_amount,
    SalesInvoiceLine.discount_amount,
    SalesInvoiceLine.bill_discount_amount,
    SalesInvoiceLine.charges_amount,
    SalesInvoiceLine.freight_amount,
)


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


@dataclass(frozen=True)
class _Billed:
    """What the HSN summary needs of one line: its code as billed, and a name.

    The code is the one the invoice line was billed under (D-CMP-22), read off
    the line, and the product's own only for a line written before lines kept
    one -- so correcting a product does not rewrite a month already filed.
    """

    hsn_sac: str | None
    name: str


@dataclass(slots=True)
class _CreditNotes:
    """The period's credit notes, split by whether the buyer is registered.

    ``unregistered_large`` is Table 9B's CDNUR: a credit to an unregistered
    buyer against an invoice that was itself declared invoice by invoice in
    B2CL, so it is declared note by note too rather than netted off B2CS.
    """

    registered: list[dict[str, object]] = field(default_factory=list)
    unregistered: list[_RateRow] = field(default_factory=list)
    unregistered_large: list[dict[str, object]] = field(default_factory=list)
    #: Every credited line, to take off the HSN summary: Table 12 is declared
    #: net of credit notes (GSTN FAQ on GSTR-1 Table 12; D-CMP-17).
    hsn: list[tuple[_Billed | None, Decimal, Decimal, GstBuckets]] = field(
        default_factory=list
    )
    #: Nil-rated, exempt and non-GST value a late cancellation gave back, as
    #: (kind, taxable, interstate, registered) -- netted off Table 8 and 3B
    #: 3.1(c)/(e) in the month of the cancellation (D-CMP-18).
    untaxed: list[tuple[str, Decimal, bool, bool]] = field(default_factory=list)


@dataclass(slots=True)
class _Credit:
    """One document that gives tax back: a credit note or a sales return.

    A completed sales return is a credit note in GST terms (CGST Act s.34): it
    reduces the taxable value and the tax of a supply already declared, and
    the ledger has already reversed its output tax. Both are brought to this
    one shape so the return cannot treat them differently.
    """

    number: str
    issued_on: date
    customer_id: UUID
    reason: str | None
    against_invoice_ids: list[UUID]
    against_invoice_number: str
    rates: dict[Decimal, _RateRow]
    document_type: str
    #: Each line as the HSN summary nets it: product, the invoice line it
    #: credits (whose billed code it nets under, D-CMP-22), quantity, taxable
    #: value and tax (D-CMP-17).
    items: list[tuple[UUID | None, UUID | None, Decimal, Decimal, GstBuckets]] = field(
        default_factory=list
    )

    @property
    def taxable(self) -> Decimal:
        """Return the credit's whole taxable value."""
        return sum((row.taxable for row in self.rates.values()), ZERO)

    @property
    def buckets(self) -> GstBuckets:
        """Return the credit's whole tax, by bucket."""
        total = GstBuckets()
        for row in self.rates.values():
            total = total.plus(row.buckets)
        return total


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
            ValidationError: If the period runs backwards or spans more than a
                quarter (``_check_period``), or the firm has no
                GSTIN -- a return is filed *by* a GSTIN, so there is nothing to
                file without one.

        """
        _check_period(from_date, to_date)
        firm = self._firms.get(firm_scope)
        seller_gstin = (firm.gst_number or "").strip().upper()
        if not seller_gstin:
            raise ValidationError(
                "This firm has no GST number, so it has no return to file."
            )
        seller_state = seller_gstin[:2]

        b2b: dict[str, dict[str, object]] = {}
        b2cl: list[dict[str, object]] = []
        exports: list[dict[str, object]] = []
        b2cs: dict[tuple[str, str], _RateRow] = {}
        hsn: dict[tuple[str, str], dict[str, object]] = {}
        unplaced: list[str] = []
        nil: dict[str, dict[str, Decimal]] = {}

        for invoice, customer, lines in self._invoices(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ):
            buyer_gstin = (getattr(customer, "gst_number", None) or "").strip().upper()
            rates: dict[Decimal, _RateRow] = {}
            charged = GstBuckets()
            untaxed: list[tuple[str, Decimal]] = []
            for taxable, buckets, product, quantity, kind in lines:
                # Every supply is in the HSN summary, taxed or not.
                self._fold_hsn(hsn, product, quantity, taxable, buckets)
                if kind != TAXABLE:
                    # Nil-rated, exempt and non-GST supplies are Table 8, not
                    # a 0% row in B2B or B2CS (D-CMP-10).
                    untaxed.append((kind, taxable))
                    continue
                row = rates.setdefault(buckets.rate, _RateRow(rate=buckets.rate))
                row.add(taxable, buckets)
                charged = charged.plus(buckets)
            if untaxed:
                crossed = (
                    buyer_gstin[:2] != seller_state
                    if buyer_gstin
                    else charged.igst > ZERO
                )
                self._fold_nil(
                    nil, untaxed, interstate=crossed, registered=bool(buyer_gstin)
                )
            if not rates:
                continue
            place = (
                buyer_gstin[:2]
                if buyer_gstin
                else self._place_of_supply(charged, seller_state)
            )
            if not place:
                unplaced.append(invoice.invoice_number)

            gst_type = getattr(
                invoice, "buyer_gst_registration_type", None
            ) or effective_type(
                getattr(customer, "gst_registration_type", None), buyer_gstin
            )
            if place == FOREIGN_PLACE or gst_type == "OVERSEAS":
                # An export is Table 6A, by whether IGST was paid on it or it
                # went under a bond or LUT -- never B2CL or B2CS (backlog 75).
                exports.append(
                    {
                        "export_type": "WPAY" if charged.igst > ZERO else "WOPAY",
                        **self._document(invoice, FOREIGN_PLACE, rates),
                    }
                )
                continue
            if buyer_gstin:
                # Registered buyer: declared invoice by invoice, whatever the
                # value, because the buyer claims credit against it. SEZ and
                # deemed-export supplies are B2B too, marked by invoice type.
                b2b.setdefault(
                    buyer_gstin,
                    {"gstin": buyer_gstin, "name": customer.name, "invoices": []},
                )
                invoices = b2b[buyer_gstin]["invoices"]
                assert isinstance(invoices, list)
                invoices.append(
                    {
                        **self._document(invoice, place, rates),
                        "invoice_type": GSTR1_INVOICE_TYPES.get(gst_type, "R"),
                    }
                )
                continue
            interstate = place != seller_state
            if interstate and Decimal(str(invoice.grand_total)) > b2cl_threshold(
                invoice.invoice_date
            ):
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
        for invoice, customer, lines, cancelled_on in self._late_cancellations(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ):
            # A bill cancelled after its month's return was due stays in that
            # month, and its cancellation is declared here, in the month it
            # happened, the way a credit note is (D-CMP-11).
            self._fold_cancellation(
                credits, invoice, customer, lines, cancelled_on, seller_state
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
        for product, quantity, taxable, buckets in credits.hsn:
            # Table 12 is net of credit notes and returns (D-CMP-17).
            self._fold_hsn(hsn, product, -quantity, -taxable, buckets.negated())
        for kind, taxable, crossed, registered in credits.untaxed:
            self._fold_nil(
                nil, [(kind, -taxable)], interstate=crossed, registered=registered
            )

        return {
            "gstin": seller_gstin,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "b2b": list(b2b.values()),
            "b2cl": b2cl,
            "exp": exports,
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
            "cdnur": credits.unregistered_large,
            "hsn": [
                self._filed_row(row)
                for row in sorted(hsn.values(), key=lambda item: str(item["hsn"]))
            ],
            "nil_exempt": [
                {
                    "supply_type": supply_type,
                    "nil_rated": _filed(amounts[NIL_RATED]),
                    "exempted": _filed(amounts[EXEMPTED]),
                    "non_gst": _filed(amounts[NON_GST]),
                }
                for supply_type, amounts in sorted(nil.items())
            ],
            "docs": self._document_series(
                firm_scope=firm_scope, from_date=from_date, to_date=to_date
            ),
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

        And, since D-CMP-20, the credit half: table 4A(5) is summed from the
        components each approved bill's lines recorded, per head, and 4B(2)
        from the completed returns raised off those bills, split in the same
        proportions. A return raised off a receipt or an order names no bill,
        so its tax cannot be placed under a head and is reported as such rather
        than guessed at.

        Credit notes are **subtracted** rather than listed: 3B is a summary of
        what is payable, and a credit note reduces it.

        Args:
            firm_scope: The owning firm.
            from_date: First day of the period.
            to_date: Last day.

        Returns:
            Section 3.1(a), and what was taken off it.

        Raises:
            ValidationError: If the period runs backwards or spans more than a
                quarter (``_check_period``), or the firm has no
                GSTIN to file under.

        """
        _check_period(from_date, to_date)
        firm = self._firms.get(firm_scope)
        seller_gstin = (firm.gst_number or "").strip().upper()
        if not seller_gstin:
            raise ValidationError(
                "This firm has no GST number, so it has no return to file."
            )

        taxable = ZERO
        buckets = GstBuckets()
        zero_rated = ZERO
        zero_rated_buckets = GstBuckets()
        nil_or_exempt = non_gst = ZERO
        for invoice, customer, lines in self._invoices(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ):
            # Exports and supplies to an SEZ are zero-rated, 3.1(b), whether
            # IGST was paid on them or they went under an LUT (backlog 75).
            to_zero = self._is_zero_rated(invoice, customer)
            for line_taxable, line_buckets, _product, _quantity, kind in lines:
                # 3.1(a) is taxable supplies; nil-rated and exempt ones are
                # 3.1(c) and non-GST ones 3.1(e) (D-CMP-10).
                if kind == NON_GST:
                    non_gst += line_taxable
                elif to_zero:
                    zero_rated += line_taxable
                    zero_rated_buckets = zero_rated_buckets.plus(line_buckets)
                elif kind != TAXABLE:
                    nil_or_exempt += line_taxable
                else:
                    taxable += line_taxable
                    buckets = buckets.plus(line_buckets)

        credited = ZERO
        credit_igst = credit_cgst = credit_sgst = credit_cess = ZERO
        credits = self._credit_notes(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        )
        seller_state = seller_gstin[:2]
        for invoice, customer, lines, cancelled_on in self._late_cancellations(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ):
            self._fold_cancellation(
                credits, invoice, customer, lines, cancelled_on, seller_state
            )
        for kind, untaxed_value, _crossed, _registered in credits.untaxed:
            # A late cancellation gives back its untaxed lines too, in the
            # month it happened (D-CMP-18).
            if kind == NON_GST:
                non_gst -= untaxed_value
            else:
                nil_or_exempt -= untaxed_value
        # Both halves: 3B is a summary of what is payable, and an unregistered
        # buyer's credit reduces it exactly as a registered one does. Reading
        # only CDNR here is what left the two returns disagreeing.
        for note in (*credits.registered, *credits.unregistered_large):
            credited += Decimal(str(note["taxable_value"]))
            credit_igst += Decimal(str(note["integrated_tax"]))
            credit_cgst += Decimal(str(note["central_tax"]))
            credit_sgst += Decimal(str(note["state_tax"]))
            credit_cess += Decimal(str(note["cess"]))
        for row in credits.unregistered:
            credited += row.taxable
            credit_igst += row.buckets.igst
            credit_cgst += row.buckets.cgst
            credit_sgst += row.buckets.sgst
            credit_cess += row.buckets.cess

        return {
            "gstin": seller_gstin,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "outward_taxable_supplies": {
                "taxable_value": _filed(taxable - credited),
                "integrated_tax": _filed(buckets.igst - credit_igst),
                "central_tax": _filed(buckets.cgst - credit_cgst),
                "state_tax": _filed(buckets.sgst - credit_sgst),
                "cess": _filed(buckets.cess - credit_cess),
            },
            "zero_rated_supplies": {
                "taxable_value": _filed(zero_rated),
                "integrated_tax": _filed(zero_rated_buckets.igst),
                "cess": _filed(zero_rated_buckets.cess),
            },
            "nil_rated_and_exempt_supplies": {
                "taxable_value": _filed(nil_or_exempt),
            },
            "non_gst_supplies": {"taxable_value": _filed(non_gst)},
            # Credit notes and completed sales returns alike (D-CMP-2).
            "credit_notes_deducted": {
                "taxable_value": _filed(credited),
                "tax": _filed(credit_igst + credit_cgst + credit_sgst + credit_cess),
            },
            **self._input_tax_credit(
                firm_scope=firm_scope, from_date=from_date, to_date=to_date
            ),
        }

    @staticmethod
    def _is_zero_rated(invoice: object, customer: object) -> bool:
        """Return whether a bill is an export or a supply to an SEZ."""
        gst_type = getattr(invoice, "buyer_gst_registration_type", None) or (
            effective_type(
                getattr(customer, "gst_registration_type", None),
                getattr(customer, "gst_number", None),
            )
        )
        if gst_type in ZERO_RATED_TYPES:
            return True
        place = str(getattr(invoice, "place_of_supply", None) or "")
        return place.endswith(f"({FOREIGN_PLACE})") or place == FOREIGN_PLACE

    def _input_tax_credit(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> dict[str, object]:
        """Return table 4 of GSTR-3B: the credit claimed, reversed, and net.

        4A(5), "all other ITC", is the recoverable tax the period's approved
        and closed bills recorded component by component
        (`purchase_invoice_line_taxes`, D-CMP-20 part 1), bucketed by head the
        way the outward side is. 4B(2), "other reversals", is the tax on the
        period's completed purchase returns, split by head in the proportions
        of the bill each return line came off -- and the tax on the period's
        approved debit notes, split the same way; a return raised off a receipt or
        an order names no bill, and its tax is counted under
        ``unplaced_reversals`` rather than put under a head it may not belong
        to. Bills written before the rows existed contribute nothing here and
        are counted under ``bills_without_components``: said, not silently
        zero.
        """
        from app.debit_note.services.debit_note_service import (
            debit_note_tax_by_component,
        )
        from app.purchase_invoice.models import (
            PurchaseInvoice,
            PurchaseInvoiceLine,
            PurchaseInvoiceLineTax,
        )
        from app.purchase_return.models import PurchaseReturn
        from app.purchase_return.services.purchase_return_service import (
            return_tax_by_component,
        )

        claimed = GstBuckets()
        billed_ids: set[UUID] = set()
        for invoice_id, code, amount in self._session.execute(
            select(
                PurchaseInvoice.id,
                PurchaseInvoiceLineTax.component_code,
                PurchaseInvoiceLineTax.amount,
            )
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                PurchaseInvoice.invoice_date >= from_date,
                PurchaseInvoice.invoice_date <= to_date,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLineTax.is_deleted.is_(False),
                PurchaseInvoiceLineTax.recoverable.is_(True),
                PurchaseInvoiceLineTax.included_in_price.is_(False),
                # Reverse charge is claimed in 4(A)(3), never in 4(A)(5).
                PurchaseInvoiceLineTax.reverse_charge.is_(False),
            )
        ).all():
            billed_ids.add(invoice_id)
            claimed = claimed.plus(_bucket(code, Decimal(str(amount))))
        inward_rcm, rcm_credit = self._reverse_charge_inward(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        )
        without_rows = self._session.scalar(
            select(func.count())
            .select_from(PurchaseInvoice)
            .where(
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                PurchaseInvoice.invoice_date >= from_date,
                PurchaseInvoice.invoice_date <= to_date,
                PurchaseInvoice.tax_total > ZERO,
                (PurchaseInvoice.id.not_in(list(billed_ids)) if billed_ids else true()),
            )
        )

        reversed_ = GstBuckets()
        unplaced = ZERO
        unplaced_count = 0
        for purchase_return in self._session.scalars(
            select(PurchaseReturn).where(
                PurchaseReturn.firm_id == firm_scope,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(("COMPLETED", "CLOSED")),
                PurchaseReturn.return_date >= from_date,
                PurchaseReturn.return_date <= to_date,
            )
        ).all():
            split = return_tax_by_component(self._session, purchase_return.id)
            placed = ZERO
            for code, amount in split.items():
                reversed_ = reversed_.plus(_bucket(code, amount))
                placed += amount
            rest = quantize_money(Decimal(str(purchase_return.tax_total)) - placed)
            if rest > ZERO:
                unplaced += rest
                unplaced_count += 1
        # A debit note to a supplier reverses the credit its bill claimed
        # exactly as a return off the bill does, head by head, in the period
        # it was approved for (backlog 65 row 6). Counted with the returns
        # rather than in a table of its own: 3B has one reversal row.
        for note in self._session.scalars(
            select(DebitNote).where(
                DebitNote.firm_id == firm_scope,
                DebitNote.is_deleted.is_(False),
                DebitNote.status == DebitNoteStatus.APPROVED.value,
                DebitNote.debit_note_date >= from_date,
                DebitNote.debit_note_date <= to_date,
            )
        ).all():
            split = debit_note_tax_by_component(self._session, note.id)
            placed = ZERO
            for code, amount in split.items():
                reversed_ = reversed_.plus(_bucket(code, amount))
                placed += amount
            rest = quantize_money(Decimal(str(note.tax_amount)) - placed)
            if rest > ZERO:
                unplaced += rest
                unplaced_count += 1

        return {
            # 3.1(d): inward supplies on which the firm pays the tax itself.
            "inward_reverse_charge": {
                "taxable_value": _filed(inward_rcm[0]),
                "integrated_tax": _filed(inward_rcm[1].igst),
                "central_tax": _filed(inward_rcm[1].cgst),
                "state_tax": _filed(inward_rcm[1].sgst),
                "cess": _filed(inward_rcm[1].cess),
            },
            # 4(A)(3): the credit of that same tax.
            "itc_reverse_charge": {
                "integrated_tax": _filed(rcm_credit.igst),
                "central_tax": _filed(rcm_credit.cgst),
                "state_tax": _filed(rcm_credit.sgst),
                "cess": _filed(rcm_credit.cess),
            },
            "eligible_itc": {
                "integrated_tax": _filed(claimed.igst),
                "central_tax": _filed(claimed.cgst),
                "state_tax": _filed(claimed.sgst),
                "cess": _filed(claimed.cess),
                "bill_count": len(billed_ids),
                "bills_without_components": int(without_rows or 0),
            },
            "itc_reversed": {
                "integrated_tax": _filed(reversed_.igst),
                "central_tax": _filed(reversed_.cgst),
                "state_tax": _filed(reversed_.sgst),
                "cess": _filed(reversed_.cess),
                "unplaced_reversals": _filed(unplaced),
                "unplaced_return_count": unplaced_count,
            },
            # Table 4(C): 4(A)(3) plus 4(A)(5), less 4(B).
            "net_itc": {
                "integrated_tax": _filed(
                    claimed.igst + rcm_credit.igst - reversed_.igst
                ),
                "central_tax": _filed(claimed.cgst + rcm_credit.cgst - reversed_.cgst),
                "state_tax": _filed(claimed.sgst + rcm_credit.sgst - reversed_.sgst),
                "cess": _filed(claimed.cess + rcm_credit.cess - reversed_.cess),
            },
        }

    def _reverse_charge_inward(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> tuple[tuple[Decimal, GstBuckets], GstBuckets]:
        """Return 3.1(d) and 4(A)(3): reverse charge on the period's bills.

        Read off the components each approved or closed bill recorded as
        reverse charge (backlog 68 row 8), the same rows the posting credits
        to reverse-charge payable. The taxable value is each such line's own,
        counted once however many components it carries; the credit is the
        recoverable part of the tax.

        Less what the period's purchase returns and debit notes took off such
        bills, in the period each was completed or approved -- the same share
        their postings debit back out of reverse-charge payable. A supply the
        firm no longer received owes no tax, and no credit stands for it.

        Returns:
            ((taxable value, tax per head), credit per head).

        """
        from app.debit_note.services.debit_note_service import (
            debit_note_reverse_charge,
        )
        from app.purchase_invoice.models import (
            PurchaseInvoice,
            PurchaseInvoiceLine,
            PurchaseInvoiceLineTax,
        )
        from app.purchase_invoice.services.reverse_charge import ReverseChargeShare
        from app.purchase_return.models import PurchaseReturn
        from app.purchase_return.services.purchase_return_service import (
            return_reverse_charge,
        )

        taxable = ZERO
        owed = GstBuckets()
        credit = GstBuckets()
        lines_counted: set[UUID] = set()
        for (
            line_id,
            line_net,
            line_tax,
            code,
            amount,
            recoverable,
        ) in self._session.execute(
            select(
                PurchaseInvoiceLine.id,
                PurchaseInvoiceLine.net_amount,
                PurchaseInvoiceLine.tax_amount,
                PurchaseInvoiceLineTax.component_code,
                PurchaseInvoiceLineTax.amount,
                PurchaseInvoiceLineTax.recoverable,
            )
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(("APPROVED", "CLOSED")),
                PurchaseInvoice.invoice_date >= from_date,
                PurchaseInvoice.invoice_date <= to_date,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLineTax.is_deleted.is_(False),
                PurchaseInvoiceLineTax.reverse_charge.is_(True),
                PurchaseInvoiceLineTax.included_in_price.is_(False),
            )
        ).all():
            if line_id not in lines_counted:
                lines_counted.add(line_id)
                # The supplier charged no tax, so the line's net is its value.
                taxable += Decimal(str(line_net)) - Decimal(str(line_tax))
            bucket = _bucket(code, Decimal(str(amount)))
            owed = owed.plus(bucket)
            if recoverable:
                credit = credit.plus(bucket)

        taken_off: list[ReverseChargeShare] = [
            return_reverse_charge(self._session, return_id)
            for return_id in self._session.scalars(
                select(PurchaseReturn.id).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status.in_(("COMPLETED", "CLOSED")),
                    PurchaseReturn.return_date >= from_date,
                    PurchaseReturn.return_date <= to_date,
                )
            ).all()
        ]
        taken_off += [
            debit_note_reverse_charge(self._session, note_id)
            for note_id in self._session.scalars(
                select(DebitNote.id).where(
                    DebitNote.firm_id == firm_scope,
                    DebitNote.is_deleted.is_(False),
                    DebitNote.status == DebitNoteStatus.APPROVED.value,
                    DebitNote.debit_note_date >= from_date,
                    DebitNote.debit_note_date <= to_date,
                )
            ).all()
        ]
        for share in taken_off:
            taxable -= share.taxable
            for code, amount in share.owed.items():
                owed = owed.plus(_bucket(code, amount).negated())
            for code, amount in share.credit.items():
                credit = credit.plus(_bucket(code, amount).negated())
        return (taxable, owed), credit

    # ---- reading -------------------------------------------------------

    def _invoices(self, *, firm_scope: UUID, from_date: date, to_date: date) -> list[
        tuple[
            SalesInvoice,
            Customer,
            list[tuple[Decimal, GstBuckets, _Billed | None, Decimal, str]],
        ]
    ]:
        """Return each invoice the period declares, with its priced lines.

        The live ones, and one cancelled only **after** the period's return
        was due: that month was filed with the bill in it, and the
        cancellation belongs to the month it happened in (D-CMP-11). One
        cancelled before the due date is dropped, as it always was.
        """
        declared = (
            SalesInvoice.firm_id == firm_scope,
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_((*_LIVE_INVOICE_STATUSES, "CANCELLED")),
            SalesInvoice.invoice_date >= from_date,
            SalesInvoice.invoice_date <= to_date,
        )
        in_period = list(
            self._session.scalars(
                select(SalesInvoice)
                .where(*declared)
                .order_by(SalesInvoice.invoice_date.asc())
            ).all()
        )
        cancelled_on = self._cancellation_dates(
            [row.id for row in in_period if row.status == "CANCELLED"]
        )
        return self._priced(
            [
                row
                for row in in_period
                if row.status != "CANCELLED"
                or self._cancelled_after_filing(row, cancelled_on.get(row.id))
            ],
            among=select(SalesInvoice.id).where(*declared),
        )

    @staticmethod
    def _cancelled_after_filing(invoice: SalesInvoice, on: date | None) -> bool:
        """Say whether a bill was cancelled after its month's return was due."""
        return on is not None and on > gstr1_due_date(invoice.invoice_date)

    @over_chunks("invoice_ids")
    def _cancellation_dates(self, invoice_ids: list[UUID]) -> dict[UUID, date]:
        """Return the day each cancelled invoice was cancelled.

        Read off the receivable movement the cancellation posted -- dated the
        day its journal was reversed -- because the invoice itself carries no
        cancellation date. A bill cancelled while still a draft posted none,
        and was never declared anyway.
        """
        if not invoice_ids:
            return {}
        answer: dict[UUID, date] = {}
        for reference_id, on in self._session.execute(
            select(
                CustomerReceivableTransaction.reference_id,
                CustomerReceivableTransaction.transaction_date,
            ).where(
                CustomerReceivableTransaction.reference_type == "SALES_INVOICE",
                CustomerReceivableTransaction.reference_id.in_(invoice_ids),
                CustomerReceivableTransaction.transaction_type == "CREDIT_NOTE",
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
        ).all():
            if reference_id is not None and (
                reference_id not in answer or on > answer[reference_id]
            ):
                answer[reference_id] = on
        return answer

    def _late_cancellations(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> list[
        tuple[
            SalesInvoice,
            Customer,
            list[tuple[Decimal, GstBuckets, _Billed | None, Decimal, str]],
            date,
        ]
    ]:
        """Return the bills cancelled in the period after their month was filed."""
        cancelled_in_period = {
            reference_id: on
            for reference_id, on in self._session.execute(
                select(
                    CustomerReceivableTransaction.reference_id,
                    CustomerReceivableTransaction.transaction_date,
                ).where(
                    CustomerReceivableTransaction.firm_id == firm_scope,
                    CustomerReceivableTransaction.reference_type == "SALES_INVOICE",
                    CustomerReceivableTransaction.transaction_type == "CREDIT_NOTE",
                    CustomerReceivableTransaction.is_deleted.is_(False),
                    CustomerReceivableTransaction.transaction_date >= from_date,
                    CustomerReceivableTransaction.transaction_date <= to_date,
                )
            ).all()
            if reference_id is not None
        }
        if not cancelled_in_period:
            return []
        invoices = [
            row
            for row in self._session.scalars(
                select(SalesInvoice)
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status == "CANCELLED",
                    SalesInvoice.id.in_(list(cancelled_in_period)),
                )
                .order_by(SalesInvoice.invoice_date.asc())
            ).all()
            if self._cancelled_after_filing(row, cancelled_in_period[row.id])
        ]
        return [
            (invoice, customer, lines, cancelled_in_period[invoice.id])
            for invoice, customer, lines in self._priced(invoices)
        ]

    def _fold_cancellation(
        self,
        credits: _CreditNotes,
        invoice: SalesInvoice,
        customer: Customer,
        lines: list[tuple[Decimal, GstBuckets, _Billed | None, Decimal, str]],
        cancelled_on: date,
        seller_state: str,
    ) -> None:
        """Declare a late cancellation the way a credit note for the whole bill is.

        A registered buyer's goes in CDNR against the bill it cancels; an
        unregistered buyer's comes off B2CS, rate by rate. Its nil-rated,
        exempt and non-GST lines come off Table 8 and 3B 3.1(c)/(e) the same
        month, as the bill put them there (D-CMP-18), and every line comes
        off the HSN summary (D-CMP-17).
        """
        gstin = (getattr(customer, "gst_number", None) or "").strip().upper()
        rates: dict[Decimal, _RateRow] = {}
        charged = GstBuckets()
        untaxed: list[tuple[str, Decimal]] = []
        for taxable, buckets, product, quantity, kind in lines:
            credits.hsn.append((product, quantity, taxable, buckets))
            # A nil-rated or exempt line was never in B2B / B2CS, so there is
            # nothing there to reverse (D-CMP-10); it is Table 8's instead.
            if kind != TAXABLE:
                untaxed.append((kind, taxable))
                continue
            charged = charged.plus(buckets)
            rates.setdefault(buckets.rate, _RateRow(rate=buckets.rate)).add(
                taxable, buckets
            )
        if untaxed:
            # Placed exactly as the bill placed them in Table 8.
            crossed = gstin[:2] != seller_state if gstin else charged.igst > ZERO
            credits.untaxed.extend(
                (kind, taxable, crossed, bool(gstin)) for kind, taxable in untaxed
            )
        if not rates:
            return
        if not gstin:
            credits.unregistered.extend(rates.values())
            return
        total = GstBuckets()
        for row in rates.values():
            total = total.plus(row.buckets)
        credits.registered.append(
            {
                "gstin": gstin,
                "name": getattr(customer, "name", ""),
                "note_number": invoice.invoice_number,
                "note_date": cancelled_on.isoformat(),
                "document_type": "CANCELLED_INVOICE",
                "against_invoice": invoice.invoice_number,
                "reason": invoice.cancel_reason,
                "rate": float(max(rates, default=ZERO)),
                "taxable_value": _filed(
                    sum((row.taxable for row in rates.values()), ZERO)
                ),
                **self._bucket_fields(total),
            }
        )

    def _priced(
        self,
        invoices: list[SalesInvoice],
        *,
        among: Select[tuple[UUID]] | None = None,
    ) -> list[
        tuple[
            SalesInvoice,
            Customer,
            list[tuple[Decimal, GstBuckets, _Billed | None, Decimal, str]],
        ]
    ]:
        """Return each invoice with its lines, priced into GST buckets.

        ``among`` is the query that chose ``invoices``, when one did: the
        lines and their taxes are then read through it rather than by sending
        every id back in chunks, which was most of a year's 64 s on a firm
        with 110,000 invoices (backlog 56 C, step 4). It may name more
        invoices than ``invoices`` holds; their lines are read and ignored.
        """
        if not invoices:
            return []
        live_lines = SalesInvoiceLine.is_deleted.is_(False)
        if among is not None:
            lines = list(
                self._session.execute(
                    select(*_LINE_COLUMNS).where(
                        SalesInvoiceLine.sales_invoice_id.in_(among), live_lines
                    )
                ).all()
            )
            tax_parts: list[ColumnElement[bool]] = [
                SalesInvoiceLineTax.sales_invoice_line_id.in_(
                    select(SalesInvoiceLine.id).where(
                        SalesInvoiceLine.sales_invoice_id.in_(among), live_lines
                    )
                )
            ]
        else:
            # Read in chunks: a quarter's lines are about as many as one
            # statement may name (backlog 56 C).
            lines = [
                line
                for part in chunks([invoice.id for invoice in invoices])
                for line in self._session.execute(
                    select(*_LINE_COLUMNS).where(
                        SalesInvoiceLine.sales_invoice_id.in_(part), live_lines
                    )
                ).all()
            ]
            tax_parts = [
                SalesInvoiceLineTax.sales_invoice_line_id.in_(part)
                for part in chunks([line.id for line in lines])
            ]
        taxes: dict[UUID, list[_PricedTax]] = defaultdict(list)
        for part in tax_parts:
            for component in self._session.execute(
                select(
                    SalesInvoiceLineTax.sales_invoice_line_id,
                    SalesInvoiceLineTax.component_code,
                    SalesInvoiceLineTax.percentage,
                    SalesInvoiceLineTax.amount,
                ).where(part, SalesInvoiceLineTax.is_deleted.is_(False))
            ).all():
                taxes[component.sales_invoice_line_id].append(component)
        products = self._products(list({line.product_id for line in lines}))
        customers = self._customers(list({invoice.customer_id for invoice in invoices}))
        by_invoice: dict[UUID, list[Row[Any]]] = defaultdict(list)
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
                    self._billed(line.hsn_sac, products.get(line.product_id)),
                    Decimal(str(line.current_invoice_quantity)),
                    self._kind(line, taxes.get(line.id, [])),
                )
                for line in sorted(
                    by_invoice.get(invoice.id, []), key=lambda row: row.line_number
                )
            ]
            # Declared at paise, adding up to what the journal credited for
            # this invoice -- rounded once, as a sum, not bucket by bucket
            # (D-CMP-4). Every section below folds these, so B2B, B2CS, HSN
            # and 3B all carry the same paise the ledger does.
            settled = settle_to_ledger([buckets for _, buckets, _, _, _ in priced])
            priced = [
                (taxable, filed, product, quantity, kind)
                for (taxable, _, product, quantity, kind), filed in zip(
                    priced, settled, strict=True
                )
            ]
            answer.append((invoice, customer, priced))
        return answer

    def _credit_notes(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> _CreditNotes:
        """Return the credits issued in the period, split by buyer.

        Two documents give tax back: an approved **credit note** and a
        completed **sales return**. A return is a credit note in GST terms
        (CGST Act s.34) -- it credits the customer and its journal reverses
        the output tax (Dr 2200) -- so it is declared exactly as one. Until
        D-CMP-2 only credit notes were read, and a firm declared and paid tax
        it had already given back on every return.

        Declared in the period they were **issued**, not the period of the
        invoice they credit: that is what the return asks for, and it is why a
        note against an old invoice still belongs in this month's filing.

        A registered buyer's credit is declared in CDNR, note by note, because
        the buyer reverses its own credit against it. An unregistered buyer's
        is declared note by note in CDNUR when the invoice it credits was
        itself declared invoice by invoice in B2CL (Table 9B), and otherwise
        netted off the B2CS row for its place and rate -- there is nobody to
        reverse a claim, and that section has no room for a number nobody
        reads.

        Args:
            firm_scope: The owning firm.
            from_date: First day of the period.
            to_date: Last day.

        Returns:
            The CDNR and CDNUR rows, and the summary rows to take off B2CS.

        """
        credits = self._issued_credit_notes(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        ) + self._completed_sales_returns(
            firm_scope=firm_scope, from_date=from_date, to_date=to_date
        )
        if not credits:
            return _CreditNotes()
        customers = self._customers([credit.customer_id for credit in credits])
        large = self._b2cl_invoices(
            [
                invoice_id
                for credit in credits
                for invoice_id in credit.against_invoice_ids
            ]
        )

        answer = _CreditNotes()
        products = self._products(
            [
                product_id
                for credit in credits
                for product_id, _, _, _, _ in credit.items
                if product_id is not None
            ]
        )
        billed_codes = self._billed_codes(
            [
                line_id
                for credit in credits
                for _, line_id, _, _, _ in credit.items
                if line_id is not None
            ]
        )
        for credit in credits:
            answer.hsn.extend(
                (
                    (
                        self._billed(
                            billed_codes.get(line_id) if line_id else None,
                            products.get(product_id),
                        )
                        if product_id is not None
                        else None
                    ),
                    quantity,
                    taxable,
                    buckets,
                )
                for product_id, line_id, quantity, taxable, buckets in credit.items
            )
            customer = customers.get(credit.customer_id)
            gstin = (getattr(customer, "gst_number", None) or "").strip().upper()
            buckets = credit.buckets
            row: dict[str, object] = {
                "note_number": credit.number,
                "note_date": credit.issued_on.isoformat(),
                "document_type": credit.document_type,
                "against_invoice": credit.against_invoice_number,
                "reason": credit.reason,
                "rate": float(max(credit.rates, default=ZERO)),
                "taxable_value": _filed(credit.taxable),
                **self._bucket_fields(buckets),
            }
            if gstin:
                answer.registered.append(
                    {"gstin": gstin, "name": getattr(customer, "name", ""), **row}
                )
                continue
            if buckets.igst > ZERO and any(
                invoice_id in large for invoice_id in credit.against_invoice_ids
            ):
                answer.unregistered_large.append(
                    {"name": getattr(customer, "name", ""), **row}
                )
                continue
            # A credit note to an unregistered buyer is netted off the B2CS
            # row it belongs to, which is what the return asks for and what
            # keeps GSTR-1 reconciling against 3B. Filed in CDNR it would be a
            # claim about a buyer who cannot claim credit; dropped -- which it
            # was, on the belief that this system could not produce one -- it
            # left 3B deducting a credit that GSTR-1 never declared.
            answer.unregistered.extend(credit.rates.values())
        return answer

    def _issued_credit_notes(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> list[_Credit]:
        """Return the approved credit notes issued in the period."""
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
            return []
        crossed_a_border = self._interstate_invoices(
            [note.sales_invoice_id for note in notes]
        )
        invoice_numbers = self._invoice_numbers(
            [note.sales_invoice_id for note in notes]
        )
        lines_by_note: dict[UUID, list[CreditNoteLine]] = defaultdict(list)
        for line in self._session.scalars(
            select(CreditNoteLine)
            .where(
                CreditNoteLine.credit_note_id.in_([note.id for note in notes]),
                CreditNoteLine.is_deleted.is_(False),
            )
            .order_by(CreditNoteLine.line_number.asc())
        ).all():
            lines_by_note[line.credit_note_id].append(line)

        answer: list[_Credit] = []
        for note in notes:
            # The note stores one tax figure per line, not a split. Re-split
            # it the way the supply it credits was taxed, read off that
            # invoice rather than off an address -- the same rule the place of
            # supply uses, and the only one an unregistered buyer can be
            # judged by at all.
            interstate = note.sales_invoice_id in crossed_a_border
            lines = lines_by_note.get(note.id, [])
            # Each line at its own rate (D-CMP-13): a note crediting a 5% and
            # an 18% line was declared wholly at whichever came first.
            parts: list[
                tuple[UUID | None, UUID | None, Decimal, Decimal, Decimal, Decimal]
            ] = [
                (
                    line.product_id,
                    line.sales_invoice_line_id,
                    Decimal(str(line.quantity)),
                    Decimal(str(line.taxable_amount)),
                    Decimal(str(line.tax_rate_percent)),
                    Decimal(str(line.tax_amount)),
                )
                for line in lines
            ] or [
                (
                    None,
                    None,
                    ZERO,
                    Decimal(str(note.taxable_amount)),
                    ZERO,
                    Decimal(str(note.tax_amount)),
                )
            ]
            # Settled at paise to what the note's journal credited, as an
            # invoice's lines are (D-CMP-4).
            settled = settle_to_ledger(
                [
                    GstBuckets(
                        igst=tax if interstate else ZERO,
                        cgst=ZERO if interstate else tax / 2,
                        sgst=ZERO if interstate else tax / 2,
                        rate=rate,
                    )
                    for _, _, _, _, rate, tax in parts
                ]
            )
            rates: dict[Decimal, _RateRow] = {}
            items: list[
                tuple[UUID | None, UUID | None, Decimal, Decimal, GstBuckets]
            ] = []
            for (product_id, credited, quantity, taxable, rate, _), buckets in zip(
                parts, settled, strict=True
            ):
                rates.setdefault(rate, _RateRow(rate=rate)).add(taxable, buckets)
                items.append((product_id, credited, quantity, taxable, buckets))
            answer.append(
                _Credit(
                    number=note.credit_note_number,
                    issued_on=note.credit_note_date,
                    customer_id=note.customer_id,
                    reason=note.reason,
                    against_invoice_ids=[note.sales_invoice_id],
                    against_invoice_number=invoice_numbers.get(
                        note.sales_invoice_id, ""
                    ),
                    rates=rates,
                    document_type="CREDIT_NOTE",
                    items=[item for item in items if item[0] is not None],
                )
            )
        return answer

    def _completed_sales_returns(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> list[_Credit]:
        """Return the sales returns completed with a return date in the period.

        COMPLETED and CLOSED: completion is what credits the customer and
        posts the reversal of output tax, and closing a completed return
        changes neither. A draft or approved return has given nothing back
        yet, and a cancelled one has been undone.

        Split exactly as the invoice was -- read off the components each line
        stored (``sales_return_line_taxes``), through the same
        ``split_components`` -- never re-derived from an address.
        """
        returns = list(
            self._session.scalars(
                select(SalesReturn)
                .where(
                    SalesReturn.firm_id == firm_scope,
                    SalesReturn.is_deleted.is_(False),
                    SalesReturn.status.in_(_CREDITED_RETURN_STATUSES),
                    SalesReturn.return_date >= from_date,
                    SalesReturn.return_date <= to_date,
                )
                .order_by(SalesReturn.return_date.asc())
            ).all()
        )
        if not returns:
            return []
        lines = list(
            self._session.scalars(
                select(SalesReturnLine).where(
                    SalesReturnLine.sales_return_id.in_([row.id for row in returns]),
                    SalesReturnLine.is_deleted.is_(False),
                )
            ).all()
        )
        taxes: dict[UUID, list[SalesReturnLineTax]] = defaultdict(list)
        if lines:
            for component in self._session.scalars(
                select(SalesReturnLineTax).where(
                    SalesReturnLineTax.sales_return_line_id.in_(
                        [line.id for line in lines]
                    ),
                    SalesReturnLineTax.is_deleted.is_(False),
                )
            ).all():
                taxes[component.sales_return_line_id].append(component)
        by_return: dict[UUID, list[SalesReturnLine]] = defaultdict(list)
        for line in lines:
            by_return[line.sales_return_id].append(line)
        billed = self._invoice_numbers(
            [
                line.source_document_id
                for line in lines
                if line.source_document_type == "SALES_INVOICE"
            ]
        )

        answer: list[_Credit] = []
        for sales_return in returns:
            rates: dict[Decimal, _RateRow] = {}
            against: list[UUID] = []
            ordered = sorted(
                by_return.get(sales_return.id, []), key=lambda row: row.line_number
            )
            # Settled at paise to what the return's journal reversed, as an
            # invoice's lines are (D-CMP-4): rounding each bucket on its own
            # declares a paisa the ledger never moved.
            settled = settle_to_ledger(
                [
                    split_components(
                        [
                            TaxComponent(
                                code=component.component_code,
                                percentage=Decimal(str(component.percentage)),
                                amount=Decimal(str(component.amount)),
                            )
                            for component in taxes.get(line.id, [])
                            if not component.included_in_price
                        ]
                    )
                    for line in ordered
                ]
            )
            items: list[
                tuple[UUID | None, UUID | None, Decimal, Decimal, GstBuckets]
            ] = []
            for line, buckets in zip(ordered, settled, strict=True):
                # What the line credited before tax: `net_amount` carries the
                # tax, exactly as an invoice line's does.
                taxable = Decimal(str(line.net_amount)) - Decimal(str(line.tax_amount))
                rates.setdefault(buckets.rate, _RateRow(rate=buckets.rate)).add(
                    taxable, buckets
                )
                items.append(
                    (
                        line.product_id,
                        # The invoice line it returns, when it returns a bill.
                        (
                            line.source_document_line_id
                            if line.source_document_id in billed
                            else None
                        ),
                        Decimal(str(line.current_return_quantity)),
                        taxable,
                        buckets,
                    )
                )
                if (
                    line.source_document_id in billed
                    and line.source_document_id not in against
                ):
                    against.append(line.source_document_id)
            answer.append(
                _Credit(
                    number=sales_return.return_number,
                    issued_on=sales_return.return_date,
                    customer_id=sales_return.customer_id,
                    reason=sales_return.return_reason,
                    against_invoice_ids=against,
                    against_invoice_number=(
                        ", ".join(billed[invoice_id] for invoice_id in against)
                        or (sales_return.reference_invoice_number or "")
                    ),
                    rates=rates,
                    document_type="SALES_RETURN",
                    items=items,
                )
            )
        return answer

    @over_chunks("invoice_ids")
    def _invoice_numbers(self, invoice_ids: list[UUID]) -> dict[UUID, str]:
        """Return the numbers of these invoices."""
        if not invoice_ids:
            return {}
        return {
            invoice_id: number
            for invoice_id, number in self._session.execute(
                select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                    SalesInvoice.id.in_(set(invoice_ids))
                )
            ).all()
        }

    @over_chunks("invoice_ids")
    def _b2cl_invoices(self, invoice_ids: list[UUID]) -> set[UUID]:
        """Return which of these invoices were declared in B2CL.

        Inter-state (they charged IGST), to a buyer with no GSTIN, and above
        the invoice-wise threshold -- the same test ``gstr1`` applies.
        """
        if not invoice_ids:
            return set()
        interstate = self._interstate_invoices(list(set(invoice_ids)))
        if not interstate:
            return set()
        rows = self._session.execute(
            select(SalesInvoice.id, SalesInvoice.grand_total, Customer.gst_number)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(SalesInvoice.id.in_(interstate))
        ).all()
        return {
            invoice_id
            for invoice_id, grand_total, gstin in rows
            if not (gstin or "").strip() and Decimal(str(grand_total)) > B2CL_THRESHOLD
        }

    @staticmethod
    def _kind(line: _PricedLine, components: Sequence[_PricedTax]) -> str:
        """Say whether a line was a taxable supply, and if not, which kind.

        A component charging a rate is taxable. Components that are all at 0%
        are a **nil-rated** supply (GST applies, at nil). No component at all
        is **exempt** -- the profile or a rule charged nothing -- unless the
        line names no tax profile whatever, which is a supply **outside GST**.
        """
        if any(
            Decimal(str(component.percentage)) != ZERO
            or Decimal(str(component.amount)) != ZERO
            for component in components
        ):
            return TAXABLE
        if components:
            return NIL_RATED
        return EXEMPTED if line.tax_profile_id is not None else NON_GST

    @staticmethod
    def _fold_nil(
        nil: dict[str, dict[str, Decimal]],
        untaxed: list[tuple[str, Decimal]],
        *,
        interstate: bool,
        registered: bool,
    ) -> None:
        """Add an invoice's untaxed lines to Table 8, by supply type.

        The four rows the table has: inter- or intra-state, to a registered
        or an unregistered person. Where the invoice charged no tax at all
        there is no tax to place it by, so an unregistered buyer's untaxed
        invoice is taken as intra-state unless some line on it charged IGST.
        """
        supply_type = (
            f"{'INTER' if interstate else 'INTRA'}-STATE TO "
            f"{'REGISTERED' if registered else 'UNREGISTERED'}"
        )
        row = nil.setdefault(
            supply_type, {NIL_RATED: ZERO, EXEMPTED: ZERO, NON_GST: ZERO}
        )
        for kind, taxable in untaxed:
            row[kind] += taxable

    def _document_series(
        self, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> list[dict[str, object]]:
        """Return the invoice series issued in the period, with what was cancelled.

        Table 13 declares every number issued -- first, last, how many, how
        many were cancelled and how many stand -- so a range with a gap in it
        explains the gap. Counting only live bills left a cancelled number as
        a gap nothing explained (D-CMP-10). A draft has not been issued.

        A bill cancelled only **after** its month's return was due counts as
        issued, not cancelled: that month was filed with it standing, and the
        cancellation is declared in the month it happened (D-CMP-11).
        """
        series: dict[str, dict[str, object]] = {}
        rows = self._session.execute(
            select(
                SalesInvoice.id,
                SalesInvoice.invoice_number,
                SalesInvoice.status,
                SalesInvoice.invoice_date,
            ).where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status.in_((*_LIVE_INVOICE_STATUSES, "CANCELLED")),
                SalesInvoice.invoice_date >= from_date,
                SalesInvoice.invoice_date <= to_date,
            )
        ).all()
        cancelled_on = self._cancellation_dates(
            [row[0] for row in rows if row[2] == "CANCELLED"]
        )
        for invoice_id, number, status, invoice_date in rows:
            text = number or ""
            prefix = text.rsplit("-", 1)[0] if "-" in text else text
            row = series.setdefault(
                prefix,
                {
                    "prefix": prefix,
                    "from": text,
                    "to": text,
                    "total_number": 0,
                    "cancelled": 0,
                },
            )
            row["total_number"] = int(str(row["total_number"])) + 1
            on = cancelled_on.get(invoice_id)
            if status == "CANCELLED" and not (
                on is not None and on > gstr1_due_date(invoice_date)
            ):
                row["cancelled"] = int(str(row["cancelled"])) + 1
            if text < str(row["from"]):
                row["from"] = text
            if text > str(row["to"]):
                row["to"] = text
        for row in series.values():
            issued = int(str(row["total_number"])) - int(str(row["cancelled"]))
            row["net_issued"] = issued
            # Kept under its old name for readers that sum it.
            row["count"] = issued
        return sorted(series.values(), key=lambda item: str(item["prefix"]))

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

    @staticmethod
    def _billed(code: str | None, product: Product | None) -> _Billed | None:
        """Return one line's code as billed, falling back to the product's."""
        if product is None and not code:
            return None
        return _Billed(
            hsn_sac=code or (product.hsn_sac if product is not None else None),
            name=product.name if product is not None else "",
        )

    def _billed_codes(self, line_ids: list[UUID]) -> dict[UUID, str]:
        """Return the code each invoice line was billed under, where it kept one."""
        if not line_ids:
            return {}
        return {
            line_id: code
            for line_id, code in self._session.execute(
                select(SalesInvoiceLine.id, SalesInvoiceLine.hsn_sac).where(
                    SalesInvoiceLine.id.in_(set(line_ids)),
                    SalesInvoiceLine.hsn_sac.is_not(None),
                )
            ).all()
            if code
        }

    def _fold_hsn(
        self,
        hsn: dict[tuple[str, str], dict[str, object]],
        product: _Billed | None,
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

    # ---- helpers -------------------------------------------------------

    @staticmethod
    def _taxable(line: _PricedLine) -> Decimal:
        """Return what a line was charged before tax.

        Gross less both discounts **plus its share of the freight**, which is
        the figure the tax was computed on. `net_amount` includes the tax, and
        declaring that as the taxable value would over-state every supply by
        its own tax.

        Freight and the line's own charges belong in here because both are
        ancillary to the supply of the goods and are taxed with them --
        exactly the base `SalesInvoiceService._line_net_amount` hands the tax
        engine. Leaving either out declares less than the invoice charged tax
        on, which is the one way a return can be wrong that nobody notices
        until an assessment.

        `charges_amount` was missing until the 2026-09-03 review: freight was
        added here when #191 moved it inside the taxable value and the line
        charges were never added at all. `credit_note` carried the same
        staleness (#207).
        """
        return quantize_money(
            Decimal(str(line.gross_amount))
            - Decimal(str(line.discount_amount))
            - Decimal(str(line.bill_discount_amount))
            + Decimal(str(line.charges_amount))
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

    @over_chunks("invoice_ids")
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

    @over_chunks("ids")
    def _products(self, ids: list[UUID]) -> dict[UUID, Product]:
        """Return the products named by a set of lines."""
        if not ids:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(Product.id.in_(ids))
                # Its eager collections are never read here, and loading them
                # cost as much again as the rows (backlog 56 C, step 4).
                .options(lazyload("*"))
            ).all()
        }

    @over_chunks("ids")
    def _customers(self, ids: list[UUID]) -> dict[UUID, Customer]:
        """Return the customers named by a set of documents."""
        if not ids:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Customer).where(Customer.id.in_(ids))
                # Its eager collections are never read here, and loading them
                # cost as much again as the rows (backlog 56 C, step 4).
                .options(lazyload("*"))
            ).all()
        }


__all__ = [
    "B2CL_THRESHOLD",
    "MAX_RETURN_MONTHS",
    "GstReturnService",
    "b2cl_threshold",
]
