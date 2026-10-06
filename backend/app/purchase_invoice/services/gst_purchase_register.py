"""The GST purchase register and the HSN summary of purchases (backlog §86 #17).

The purchase invoice register lists bills by number and total; a GST filer and
the firm's CA need the same bills by **tax head** -- the supplier's GSTIN, the
taxable value, IGST, CGST, SGST and cess, and how much of it may be claimed --
and the inward supplies folded by HSN. Tally, Busy and Marg print both.

Only approved and closed bills count: a draft has claimed nothing, and a
cancelled bill never did. A head is read off the components each line was
actually charged (`purchase_invoice_line_taxes`), as GSTR-3B and the GSTR-2B
reconciliation read them, through the same `_bucket`, so the three cannot
disagree on what a component is. A component included in the price is the
supplier's tax inside the rate, not a head charged on top, and is left out as
the 2B reconciliation leaves it out.

Approved supplier debit notes (the supplier's credit notes) are netted in, each
as a row of its own with every figure negative, on the note's own date: the
credit a note takes back comes off in the month the note is dated, not the
month of the bill it names. A `DebitNoteLine` keeps one `tax_amount`, so it is
split across the heads in the proportions its bill line was charged -- the
split `debit_note_tax_by_component` posts to the ledger and GSTR-3B reverses.
A note against a bill written before the component rows existed therefore
shows its taxable value and no heads.

Completed purchase returns are netted in the same way, on the return's own
date: the part of each line that went back **after** billing, split across the
heads of the bill line it was raised off or of the bill lines that billed its
receipt line -- `return_tax_by_component`'s reading, through the same
`_billed_lines`. What went back before any bill took no credit and is left
out, and a return made only of such lines is not listed.

Every figure is in **rupees** (D-BUY-35). A bill in another currency (PG-12)
is stored as typed, so its taxable value and total are its stored rupee
figures (`base_grand_total`, `base_tax_total`) and each head is the component
at the bill's own rate -- what its journal posted. A debit note or a return
against such a bill is in the bill's currency too, and is read at the bill's
rate: the credit goes back at the value it was taken at.

Both reports read a constant number of statements whatever the window holds
(`docs/PERFORMANCE_AT_VOLUME.md`): the page of documents, the bills, notes
and returns on it, their lines and taxes, then the supplier names.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, literal, select, union_all
from sqlalchemy.orm import Session

from app.core.pagination.reports import (
    WHOLE_HISTORY,
    ReportRows,
    ReportWindow,
    mapped_like,
)
from app.core.utils.money import quantize_money
from app.debit_note.models import DebitNote, DebitNoteLine, DebitNoteStatus
from app.finance.currency import rupee_rate
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

ZERO = Decimal("0")
ONE = Decimal("1")

#: A bill that has claimed its tax: approved, or approved and then closed.
CLAIMED_STATES = ("APPROVED", "CLOSED")

#: The heads a return files tax under.
HEADS = ("igst", "cgst", "sgst", "cess")

#: What a register row is: a supplier bill, a debit note against one, or
#: goods sent back after billing.
BILL = "BILL"
DEBIT_NOTE = "DEBIT_NOTE"
PURCHASE_RETURN = "PURCHASE_RETURN"

#: A return whose goods have gone: the states GSTR-3B reverses its credit in.
RETURNED_STATES = ("COMPLETED", "CLOSED")


@dataclass
class GstPurchaseRegisterRow:
    """One supplier bill, debit note or purchase return, by tax head.

    A debit note's or a return's row carries its own number and date in the
    invoice fields, the supplier's credit note in the supplier fields, and
    negative figures.
    """

    invoice_id: UUID
    invoice_date: date
    invoice_number: str
    supplier_invoice_number: str
    supplier_invoice_date: date
    vendor_id: UUID
    vendor_name: str
    vendor_gstin: str | None
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    total_tax: Decimal
    #: Tax the firm may not claim: s.17(5) blocked or otherwise ineligible.
    itc_not_claimable: Decimal
    #: Tax the firm itself pays under reverse charge, on top of the bill.
    reverse_charge_tax: Decimal
    invoice_total: Decimal
    #: Tax charged on capital-goods lines (PG-13): claimed in full with the
    #: rest, shown apart because GSTR-9 and an audit ask for it apart.
    capital_goods_tax: Decimal = ZERO
    document_type: str = BILL
    #: The bill a debit note or a return takes back from; empty on a bill.
    against_invoice_number: str = ""


@dataclass
class _TakenBack:
    """What one debit note or return line takes back, as its bill charged it."""

    heads: dict[str, Decimal]
    reverse_charge: Decimal = ZERO
    #: The part of the tax that sat on a blocked or ineligible bill line.
    not_claimable: Decimal = ZERO
    #: The part of the tax that sat on a capital-goods bill line.
    capital: Decimal = ZERO
    bills: set[str] = field(default_factory=set)
    #: Rupees per unit of the bill it takes back from; one for a rupee bill.
    rate: Decimal = ONE


@dataclass
class HsnPurchaseRow:
    """The inward supplies of one HSN code in one unit."""

    hsn_code: str
    description: str
    unit: str
    quantity: Decimal
    taxable_value: Decimal
    igst: Decimal = ZERO
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    cess: Decimal = ZERO
    total_tax: Decimal = ZERO
    bills: int = 0
    _bill_ids: set[UUID] = field(default_factory=set, repr=False)


def _heads_by_line(
    session: Session, line_ids: list[UUID]
) -> dict[UUID, dict[str, Decimal]]:
    """Return IGST, CGST, SGST and cess charged on each line, by line id.

    In rupees: a component on a bill in another currency is read at the
    bill's own rate, as its journal posted it.
    """
    from app.gst_returns.services.gstr_service import _bucket

    heads: dict[UUID, dict[str, Decimal]] = defaultdict(
        lambda: dict.fromkeys(HEADS, ZERO)
    )
    if not line_ids:
        return heads
    for line_id, code, amount, currency, rate in session.execute(
        select(
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            PurchaseInvoiceLineTax.component_code,
            PurchaseInvoiceLineTax.amount,
            PurchaseInvoice.currency_code,
            PurchaseInvoice.exchange_rate,
        )
        .join(
            PurchaseInvoiceLine,
            PurchaseInvoiceLine.id == PurchaseInvoiceLineTax.purchase_invoice_line_id,
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(line_ids),
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
        )
    ).all():
        bucket = _bucket(code, Decimal(str(amount)) * rupee_rate(currency, rate))
        for head in HEADS:
            heads[line_id][head] += getattr(bucket, head)
    return heads


#: One line that takes tax back: its id, the bill lines it reverses with each
#: one's weight, its taxable value and its tax.
_Taking = tuple[UUID, list[tuple[UUID, Decimal]], Decimal, Decimal]


def _taken_back(session: Session, lines: list[_Taking]) -> dict[UUID, _TakenBack]:
    """Split each line's tax across the heads of the bill lines it reverses.

    Args:
        session: The firm's store.
        lines: Each debit note or return line as (its id, the bill lines it
            reverses with each one's weight, its taxable value, its tax).

    Returns:
        By line id, positive figures in rupees -- each share at the rate of
        the bill it comes off, which is also kept as the line's ``rate`` for
        its own taxable value. The tax is shared over what the supplier
        charged on the bill lines, as `debit_note_tax_by_component` and
        `return_tax_by_component` share it; reverse charge is the share the
        line's taxable value is of the bill line's, as `reverse_charge_share`
        takes it, and sits in the heads as a bill's own reverse charge does.
        A line naming no bill line takes back no head.

    """
    from app.gst_returns.services.gstr_service import _bucket

    found = {
        line_id: _TakenBack(heads=dict.fromkeys(HEADS, ZERO))
        for line_id, _, _, _ in lines
    }
    bill_line_ids = list(
        {bill_line_id for _, named, _, _ in lines for bill_line_id, _ in named}
    )
    if not bill_line_ids:
        return found
    bill_lines = {
        line_id: (
            (eligibility or "ELIGIBLE") == "ELIGIBLE",
            bool(capital),
            Decimal(str(net)) - Decimal(str(tax)),
            number,
            rupee_rate(currency, rate),
        )
        for (
            line_id,
            eligibility,
            capital,
            net,
            tax,
            number,
            currency,
            rate,
        ) in session.execute(
            select(
                PurchaseInvoiceLine.id,
                PurchaseInvoiceLine.itc_eligibility,
                PurchaseInvoiceLine.is_capital_goods,
                PurchaseInvoiceLine.net_amount,
                PurchaseInvoiceLine.tax_amount,
                PurchaseInvoice.invoice_number,
                PurchaseInvoice.currency_code,
                PurchaseInvoice.exchange_rate,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(PurchaseInvoiceLine.id.in_(bill_line_ids))
        ).all()
    }
    charged: dict[UUID, list[tuple[str, Decimal, bool]]] = defaultdict(list)
    for line_id, code, amount, reverse in session.execute(
        select(
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            PurchaseInvoiceLineTax.component_code,
            PurchaseInvoiceLineTax.amount,
            PurchaseInvoiceLineTax.reverse_charge,
        ).where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(bill_line_ids),
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
        )
    ).all():
        charged[line_id].append((code, Decimal(str(amount)), bool(reverse)))
    for line_id, named, taxable, tax in lines:
        taken = found[line_id]
        supplier_tax = sum(
            (
                amount * weight
                for bill_line_id, weight in named
                for _, amount, reverse in charged.get(bill_line_id, [])
                if not reverse
            ),
            ZERO,
        )
        for bill_line_id, weight in named:
            if bill_line_id not in bill_lines:
                continue
            claimable, capital, bill_value, number, rate = bill_lines[bill_line_id]
            taken.bills.add(number)
            taken.rate = rate
            ratio = (
                min(taxable * weight / bill_value, Decimal("1"))
                if bill_value > ZERO
                else ZERO
            )
            for code, amount, reverse in charged.get(bill_line_id, []):
                if reverse:
                    share = amount * ratio * rate
                    taken.reverse_charge += share
                elif supplier_tax > ZERO:
                    share = tax * amount * weight / supplier_tax * rate
                else:
                    continue
                bucket = _bucket(code, share)
                for head in HEADS:
                    taken.heads[head] += getattr(bucket, head)
                if not claimable:
                    taken.not_claimable += share
                if capital:
                    taken.capital += share
    return found


def _vendors(session: Session, ids: set[UUID]) -> dict[UUID, tuple[str, str | None]]:
    """Return each supplier's name and GSTIN, in one read."""
    from app.vendors.models import Vendor

    if not ids:
        return {}
    return {
        vendor_id: (name, gstin)
        for vendor_id, name, gstin in session.execute(
            select(Vendor.id, Vendor.name, Vendor.gstin).where(Vendor.id.in_(list(ids)))
        ).all()
    }


def _return_part(
    line: PurchaseReturnLine, share: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """Return the billed part of a return line: quantity, taxable value, tax.

    The quantity is the one typed where the line kept it -- 7 for seven
    pieces of a line bought by the box, which the HSN summary files under
    the typed unit -- and not the 0.5833 of a box the row stores (D-PRC-50).
    """
    tax = Decimal(str(line.tax_amount))
    typed = line.entered_quantity
    return (
        Decimal(str(line.current_return_quantity if typed is None else typed)) * share,
        (Decimal(str(line.net_amount)) - tax) * share,
        tax * share,
    )


class GstPurchaseRegisterService:
    """Read supplier bills by tax head, and inward supplies by HSN."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a firm store's session."""
        self._session = session

    def register(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[GstPurchaseRegisterRow]:
        """Return the window's claimed bills and debit notes, newest first."""
        documents = self._documents(firm_id, window)
        bills = self._bills([key for key, kind in documents if kind == BILL])
        notes = self._notes([key for key, kind in documents if kind == DEBIT_NOTE])
        returns = self._returns(
            [key for key, kind in documents if kind == PURCHASE_RETURN]
        )
        vendors = _vendors(
            self._session,
            {bill.vendor_id for bill in bills}
            | {note.vendor_id for note in notes}
            | {row.vendor_id for row in returns},
        )
        rows = {
            **self._bill_rows(bills, vendors),
            **self._note_rows(notes, vendors),
            **self._return_rows(returns, vendors),
        }
        return mapped_like(documents, [rows[key] for key, _ in documents])

    def _documents(self, firm_id: UUID, window: ReportWindow) -> list[tuple[UUID, str]]:
        """Return the id and kind of each document in the window, newest first.

        Bills and notes are paged together, on each document's own date, so a
        page is a page of the register rather than of one table.
        """
        keys = union_all(
            select(
                PurchaseInvoice.id.label("id"),
                literal(BILL).label("kind"),
                PurchaseInvoice.invoice_date.label("dated"),
                PurchaseInvoice.created_at.label("made"),
            ).where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(CLAIMED_STATES),
                *window.dated(PurchaseInvoice.invoice_date),
            ),
            select(
                DebitNote.id,
                literal(DEBIT_NOTE),
                DebitNote.debit_note_date,
                DebitNote.created_at,
            ).where(
                DebitNote.firm_id == firm_id,
                DebitNote.is_deleted.is_(False),
                DebitNote.status == DebitNoteStatus.APPROVED.value,
                *window.dated(DebitNote.debit_note_date),
            ),
            select(
                PurchaseReturn.id,
                literal(PURCHASE_RETURN),
                PurchaseReturn.return_date,
                PurchaseReturn.created_at,
            ).where(
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(RETURNED_STATES),
                *window.dated(PurchaseReturn.return_date),
                # Goods that went back before any bill took no credit.
                exists().where(
                    PurchaseReturnLine.purchase_return_id == PurchaseReturn.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                    PurchaseReturnLine.current_return_quantity
                    > PurchaseReturnLine.unbilled_quantity,
                ),
            ),
        ).subquery()
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

    def _bills(self, ids: list[UUID]) -> list[PurchaseInvoice]:
        """Return the bills named, in one read."""
        if not ids:
            return []
        return list(
            self._session.scalars(
                select(PurchaseInvoice).where(PurchaseInvoice.id.in_(ids))
            ).all()
        )

    def _notes(self, ids: list[UUID]) -> list[DebitNote]:
        """Return the debit notes named, in one read."""
        if not ids:
            return []
        return list(
            self._session.scalars(select(DebitNote).where(DebitNote.id.in_(ids))).all()
        )

    def _bill_rows(
        self,
        bills: list[PurchaseInvoice],
        vendors: dict[UUID, tuple[str, str | None]],
    ) -> dict[UUID, GstPurchaseRegisterRow]:
        """Return a register row per bill, by bill id."""
        ids = [bill.id for bill in bills]
        lines = (
            self._session.execute(
                select(
                    PurchaseInvoiceLine.id,
                    PurchaseInvoiceLine.purchase_invoice_id,
                    PurchaseInvoiceLine.itc_eligibility,
                    PurchaseInvoiceLine.is_capital_goods,
                ).where(
                    PurchaseInvoiceLine.purchase_invoice_id.in_(ids),
                    PurchaseInvoiceLine.is_deleted.is_(False),
                )
            ).all()
            if ids
            else []
        )
        line_heads = _heads_by_line(self._session, [line[0] for line in lines])
        per_bill: dict[UUID, dict[str, Decimal]] = defaultdict(
            lambda: dict.fromkeys((*HEADS, "not_claimable", "capital"), ZERO)
        )
        for line_id, bill_id, eligibility, capital in lines:
            heads = line_heads[line_id]
            for head in HEADS:
                per_bill[bill_id][head] += heads[head]
            if (eligibility or "ELIGIBLE") != "ELIGIBLE":
                per_bill[bill_id]["not_claimable"] += sum(heads.values(), ZERO)
            if capital:
                per_bill[bill_id]["capital"] += sum(heads.values(), ZERO)
        rows = {}
        for bill in bills:
            heads = per_bill[bill.id]
            tax = sum((heads[head] for head in HEADS), ZERO)
            # A bill in another currency is listed at its stored rupee
            # figures, the ones its journal posted (D-BUY-35).
            rate = rupee_rate(bill.currency_code, bill.exchange_rate)
            if rate != ONE and bill.base_grand_total is not None:
                total = Decimal(str(bill.base_grand_total))
                charged = Decimal(str(bill.base_tax_total or ZERO))
            else:
                total = Decimal(str(bill.grand_total)) * rate
                charged = Decimal(str(bill.tax_total)) * rate
            name, gstin = vendors.get(bill.vendor_id, (str(bill.vendor_id), None))
            rows[bill.id] = GstPurchaseRegisterRow(
                invoice_id=bill.id,
                invoice_date=bill.invoice_date,
                invoice_number=bill.invoice_number,
                supplier_invoice_number=bill.supplier_invoice_number,
                supplier_invoice_date=bill.supplier_invoice_date,
                vendor_id=bill.vendor_id,
                vendor_name=name,
                vendor_gstin=gstin,
                # What the bill charged before tax, as the GSTR-2B
                # reconciliation reads it: the total less the tax on it.
                taxable_value=quantize_money(total - charged),
                igst=quantize_money(heads["igst"]),
                cgst=quantize_money(heads["cgst"]),
                sgst=quantize_money(heads["sgst"]),
                cess=quantize_money(heads["cess"]),
                total_tax=quantize_money(tax),
                itc_not_claimable=quantize_money(heads["not_claimable"]),
                reverse_charge_tax=quantize_money(
                    Decimal(str(bill.reverse_charge_tax_total or ZERO)) * rate
                ),
                invoice_total=quantize_money(total),
                capital_goods_tax=quantize_money(heads["capital"]),
            )
        return rows

    def _returns(self, ids: list[UUID]) -> list[PurchaseReturn]:
        """Return the purchase returns named, in one read."""
        if not ids:
            return []
        return list(
            self._session.scalars(
                select(PurchaseReturn).where(PurchaseReturn.id.in_(ids))
            ).all()
        )

    def _note_rows(
        self,
        notes: list[DebitNote],
        vendors: dict[UUID, tuple[str, str | None]],
    ) -> dict[UUID, GstPurchaseRegisterRow]:
        """Return a register row per debit note, by note id, figures negative."""
        if not notes:
            return {}
        lines = self._session.execute(
            select(
                DebitNoteLine.id,
                DebitNoteLine.debit_note_id,
                DebitNoteLine.purchase_invoice_line_id,
                DebitNoteLine.taxable_amount,
                DebitNoteLine.tax_amount,
            ).where(
                DebitNoteLine.debit_note_id.in_([note.id for note in notes]),
                DebitNoteLine.is_deleted.is_(False),
            )
        ).all()
        taken = _taken_back(
            self._session,
            [
                (
                    line_id,
                    [(bill_line_id, Decimal("1"))],
                    Decimal(str(taxable)),
                    Decimal(str(tax)),
                )
                for line_id, _, bill_line_id, taxable, tax in lines
            ],
        )
        owners = {line_id: note_id for line_id, note_id, _, _, _ in lines}
        return {
            note.id: self._minus_row(
                DEBIT_NOTE,
                document_id=note.id,
                on=note.debit_note_date,
                number=note.debit_note_number,
                supplier_number=note.supplier_credit_note_number,
                supplier_date=note.supplier_credit_note_date,
                vendor_id=note.vendor_id,
                vendors=vendors,
                taxable=Decimal(str(note.taxable_amount)),
                total=Decimal(str(note.total_amount)),
                taken=[
                    taken[line_id]
                    for line_id, owner in owners.items()
                    if owner == note.id
                ],
            )
            for note in notes
        }

    def _return_rows(
        self,
        returns: list[PurchaseReturn],
        vendors: dict[UUID, tuple[str, str | None]],
    ) -> dict[UUID, GstPurchaseRegisterRow]:
        """Return a register row per purchase return, by id, figures negative.

        Only the billed part of each line counts: its value, its tax and its
        heads. A line that names no bill line shows its value and no heads.
        """
        from app.purchase_return.services.purchase_return_service import (
            _billed_lines,
            _billed_share,
        )

        if not returns:
            return {}
        lines = self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id.in_([row.id for row in returns]),
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ).all()
        named = _billed_lines(self._session, lines)
        parts = {line.id: _return_part(line, _billed_share(line)) for line in lines}
        taken = _taken_back(
            self._session,
            [(line.id, named.get(line.id, []), *parts[line.id][1:]) for line in lines],
        )
        rows = {}
        for document in returns:
            own = [line for line in lines if line.purchase_return_id == document.id]
            taxable = sum((parts[line.id][1] for line in own), ZERO)
            tax = sum((parts[line.id][2] for line in own), ZERO)
            rows[document.id] = self._minus_row(
                PURCHASE_RETURN,
                document_id=document.id,
                on=document.return_date,
                number=document.return_number,
                supplier_number=document.supplier_return_number,
                supplier_date=document.supplier_return_date,
                vendor_id=document.vendor_id,
                vendors=vendors,
                taxable=taxable,
                total=taxable + tax,
                taken=[taken[line.id] for line in own],
                against=document.reference_invoice_number or "",
            )
        return rows

    @staticmethod
    def _minus_row(
        kind: str,
        *,
        document_id: UUID,
        on: date,
        number: str,
        supplier_number: str | None,
        supplier_date: date | None,
        vendor_id: UUID,
        vendors: dict[UUID, tuple[str, str | None]],
        taxable: Decimal,
        total: Decimal,
        taken: list[_TakenBack],
        against: str = "",
    ) -> GstPurchaseRegisterRow:
        """Build the negative row of a debit note or a purchase return."""
        heads = {
            head: sum((part.heads[head] for part in taken), ZERO) for head in HEADS
        }
        bills = sorted({bill for part in taken for bill in part.bills})
        # The document is in its bill's currency; its own value goes back at
        # the bill's rate, as each head above already has.
        rate = next((part.rate for part in taken if part.rate != ONE), ONE)
        taxable, total = taxable * rate, total * rate
        name, gstin = vendors.get(vendor_id, (str(vendor_id), None))
        return GstPurchaseRegisterRow(
            invoice_id=document_id,
            invoice_date=on,
            invoice_number=number,
            supplier_invoice_number=supplier_number or "",
            supplier_invoice_date=supplier_date or on,
            vendor_id=vendor_id,
            vendor_name=name,
            vendor_gstin=gstin,
            taxable_value=-quantize_money(taxable),
            igst=-quantize_money(heads["igst"]),
            cgst=-quantize_money(heads["cgst"]),
            sgst=-quantize_money(heads["sgst"]),
            cess=-quantize_money(heads["cess"]),
            total_tax=-quantize_money(sum(heads.values(), ZERO)),
            itc_not_claimable=-quantize_money(
                sum((part.not_claimable for part in taken), ZERO)
            ),
            reverse_charge_tax=-quantize_money(
                sum((part.reverse_charge for part in taken), ZERO)
            ),
            invoice_total=-quantize_money(total),
            capital_goods_tax=-quantize_money(
                sum((part.capital for part in taken), ZERO)
            ),
            document_type=kind,
            against_invoice_number=", ".join(bills) or against,
        )

    def _billed_units(self, bill_line_ids: set[UUID]) -> dict[UUID, str]:
        """Return the unit code each bill line named was billed in."""
        from app.uom.models import Uom

        if not bill_line_ids:
            return {}
        return {
            line_id: code
            for line_id, code in self._session.execute(
                select(PurchaseInvoiceLine.id, Uom.code)
                .join(Uom, Uom.id == PurchaseInvoiceLine.invoice_uom_id)
                .where(PurchaseInvoiceLine.id.in_(bill_line_ids))
            ).all()
        }

    def hsn_summary(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[HsnPurchaseRow]:
        """Return the window's inward supplies by HSN code and unit.

        A line with no HSN on its product is grouped under an empty code, so
        the gap is visible rather than dropped. An approved debit note dated
        in the window comes off the code and unit of the bill line it names:
        its quantity, its taxable value and its tax by head. A completed
        purchase return comes off its own product and unit the same way, for
        the part that went back after billing.
        """
        from app.products.models import Product
        from app.purchase_return.services.purchase_return_service import (
            _billed_lines,
            _billed_share,
        )
        from app.uom.models import Uom

        lines = self._session.execute(
            select(
                PurchaseInvoiceLine.id,
                PurchaseInvoiceLine.purchase_invoice_id,
                func.coalesce(Product.hsn_sac, ""),
                Product.name,
                func.coalesce(Uom.code, ""),
                # What was typed, where the bill was typed in another unit
                # than the line it bills: the row is filed under the typed
                # unit, and 7 PIECE read "0.5833 PIECE" (D-PRC-50).
                func.coalesce(
                    PurchaseInvoiceLine.entered_quantity,
                    PurchaseInvoiceLine.current_invoice_quantity,
                ),
                PurchaseInvoiceLine.net_amount,
                PurchaseInvoiceLine.tax_amount,
                PurchaseInvoice.currency_code,
                PurchaseInvoice.exchange_rate,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .join(Product, Product.id == PurchaseInvoiceLine.product_id)
            .outerjoin(
                Uom,
                Uom.id == PurchaseInvoiceLine.invoice_uom_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(CLAIMED_STATES),
                PurchaseInvoiceLine.is_deleted.is_(False),
                *window.dated(PurchaseInvoice.invoice_date),
            )
        ).all()
        line_heads = _heads_by_line(self._session, [line[0] for line in lines])
        groups: dict[tuple[str, str], HsnPurchaseRow] = {}
        for line_id, bill_id, hsn, name, unit, quantity, net, tax, code, rate in lines:
            row = groups.get((hsn, unit))
            if row is None:
                row = groups[(hsn, unit)] = HsnPurchaseRow(
                    hsn_code=hsn,
                    description=name,
                    unit=unit,
                    quantity=ZERO,
                    taxable_value=ZERO,
                )
            row.quantity += Decimal(str(quantity))
            row.taxable_value += (Decimal(str(net)) - Decimal(str(tax))) * rupee_rate(
                code, rate
            )
            for head in HEADS:
                setattr(row, head, getattr(row, head) + line_heads[line_id][head])
            row._bill_ids.add(bill_id)
        note_lines = self._session.execute(
            select(
                DebitNoteLine.id,
                DebitNoteLine.purchase_invoice_line_id,
                func.coalesce(Product.hsn_sac, ""),
                Product.name,
                func.coalesce(Uom.code, ""),
                DebitNoteLine.quantity,
                DebitNoteLine.taxable_amount,
                DebitNoteLine.tax_amount,
            )
            .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id == DebitNoteLine.purchase_invoice_line_id,
            )
            .join(Product, Product.id == PurchaseInvoiceLine.product_id)
            .outerjoin(Uom, Uom.id == PurchaseInvoiceLine.invoice_uom_id)
            .where(
                DebitNote.firm_id == firm_id,
                DebitNote.is_deleted.is_(False),
                DebitNote.status == DebitNoteStatus.APPROVED.value,
                DebitNoteLine.is_deleted.is_(False),
                *window.dated(DebitNote.debit_note_date),
            )
        ).all()
        taken = _taken_back(
            self._session,
            [
                (
                    line_id,
                    [(bill_line_id, Decimal("1"))],
                    Decimal(str(taxable)),
                    Decimal(str(tax)),
                )
                for line_id, bill_line_id, _, _, _, _, taxable, tax in note_lines
            ],
        )
        minus = [
            (hsn, name, unit, Decimal(str(quantity)), Decimal(str(taxable)), line_id)
            for line_id, _, hsn, name, unit, quantity, taxable, _ in note_lines
        ]
        returned = self._session.execute(
            select(
                PurchaseReturnLine,
                func.coalesce(Product.hsn_sac, ""),
                Product.name,
                func.coalesce(Uom.code, ""),
            )
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .join(Product, Product.id == PurchaseReturnLine.product_id)
            .outerjoin(Uom, Uom.id == PurchaseReturnLine.return_uom_id)
            .where(
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(RETURNED_STATES),
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturnLine.current_return_quantity
                > PurchaseReturnLine.unbilled_quantity,
                *window.dated(PurchaseReturn.return_date),
            )
        ).all()
        return_lines = [line for line, _, _, _ in returned]
        named = _billed_lines(self._session, return_lines)
        parts = {
            line.id: _return_part(line, _billed_share(line)) for line in return_lines
        }
        taken.update(
            _taken_back(
                self._session,
                [
                    (line.id, named.get(line.id, []), *parts[line.id][1:])
                    for line in return_lines
                ],
            )
        )
        # A return line often names no unit of its own; it is then counted
        # in the unit its bill line was billed in, or it would open a row of
        # its own beside the purchases it reverses.
        billed_in = self._billed_units(
            {bill_line_id for lines_ in named.values() for bill_line_id, _ in lines_}
        )
        minus += [
            (
                hsn,
                name,
                unit
                or next(
                    (
                        billed_in[bill_line_id]
                        for bill_line_id, _ in named.get(line.id, [])
                        if billed_in.get(bill_line_id)
                    ),
                    "",
                ),
                parts[line.id][0],
                parts[line.id][1],
                line.id,
            )
            for line, hsn, name, unit in returned
        ]
        for hsn, name, unit, quantity, taxable, line_id in minus:
            row = groups.get((hsn, unit))
            if row is None:
                row = groups[(hsn, unit)] = HsnPurchaseRow(
                    hsn_code=hsn,
                    description=name,
                    unit=unit,
                    quantity=ZERO,
                    taxable_value=ZERO,
                )
            row.quantity -= quantity
            row.taxable_value -= taxable * taken[line_id].rate
            for head in HEADS:
                setattr(row, head, getattr(row, head) - taken[line_id].heads[head])
        rows = []
        for row in sorted(groups.values(), key=lambda item: (item.hsn_code, item.unit)):
            row.taxable_value = quantize_money(row.taxable_value)
            for head in HEADS:
                setattr(row, head, quantize_money(getattr(row, head)))
            row.total_tax = quantize_money(
                sum((getattr(row, head) for head in HEADS), ZERO)
            )
            row.bills = len(row._bill_ids)
            rows.append(row)
        return rows


__all__ = [
    "GstPurchaseRegisterRow",
    "GstPurchaseRegisterService",
    "HsnPurchaseRow",
]
