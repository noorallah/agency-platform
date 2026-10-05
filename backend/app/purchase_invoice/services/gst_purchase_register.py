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

Both reports read a constant number of statements whatever the window holds
(`docs/PERFORMANCE_AT_VOLUME.md`): the page of documents, the bills and the
notes on it, their lines and taxes, then the supplier names.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session

from app.core.pagination.reports import (
    WHOLE_HISTORY,
    ReportRows,
    ReportWindow,
    mapped_like,
)
from app.core.utils.money import quantize_money
from app.debit_note.models import DebitNote, DebitNoteLine, DebitNoteStatus
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)

ZERO = Decimal("0")

#: A bill that has claimed its tax: approved, or approved and then closed.
CLAIMED_STATES = ("APPROVED", "CLOSED")

#: The heads a return files tax under.
HEADS = ("igst", "cgst", "sgst", "cess")

#: What a register row is: a supplier bill, or a debit note against one.
BILL = "BILL"
DEBIT_NOTE = "DEBIT_NOTE"


@dataclass
class GstPurchaseRegisterRow:
    """One supplier bill, or one debit note against a bill, by tax head.

    A debit note's row carries its own number and date in the invoice fields,
    the supplier's credit note in the supplier fields, and negative figures.
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
    #: The bill a debit note claims against; empty on a bill's own row.
    against_invoice_number: str = ""


@dataclass
class _NoteLineTax:
    """What one debit note line takes back, by head, as its bill line charged."""

    heads: dict[str, Decimal]
    reverse_charge: Decimal = ZERO
    claimable: bool = True
    capital: bool = False

    @property
    def total(self) -> Decimal:
        """Return the tax across every head."""
        return sum(self.heads.values(), ZERO)


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
    """Return IGST, CGST, SGST and cess charged on each line, by line id."""
    from app.gst_returns.services.gstr_service import _bucket

    heads: dict[UUID, dict[str, Decimal]] = defaultdict(
        lambda: dict.fromkeys(HEADS, ZERO)
    )
    if not line_ids:
        return heads
    for line_id, code, amount in session.execute(
        select(
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            PurchaseInvoiceLineTax.component_code,
            PurchaseInvoiceLineTax.amount,
        ).where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(line_ids),
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
        )
    ).all():
        bucket = _bucket(code, Decimal(str(amount)))
        for head in HEADS:
            heads[line_id][head] += getattr(bucket, head)
    return heads


def _note_line_taxes(
    session: Session, lines: list[tuple[UUID, UUID, Decimal, Decimal]]
) -> dict[UUID, _NoteLineTax]:
    """Split each debit note line's tax across the heads of its bill line.

    Args:
        session: The firm's store.
        lines: Each note line as (its id, the bill line it is against, its
            taxable value, its tax).

    Returns:
        By note line id, positive figures. The tax is shared over what the
        supplier charged on the bill line, as `debit_note_tax_by_component`
        shares it; reverse charge is the share the line's taxable value is of
        the bill line's, as `reverse_charge_share` takes it, and sits in the
        heads as a bill's own reverse charge does.

    """
    from app.gst_returns.services.gstr_service import _bucket

    found: dict[UUID, _NoteLineTax] = {}
    bill_line_ids = list({bill_line_id for _, bill_line_id, _, _ in lines})
    if not bill_line_ids:
        return found
    bill_lines = {
        line_id: (eligibility, bool(capital), Decimal(str(net)) - Decimal(str(tax)))
        for line_id, eligibility, capital, net, tax in session.execute(
            select(
                PurchaseInvoiceLine.id,
                PurchaseInvoiceLine.itc_eligibility,
                PurchaseInvoiceLine.is_capital_goods,
                PurchaseInvoiceLine.net_amount,
                PurchaseInvoiceLine.tax_amount,
            ).where(PurchaseInvoiceLine.id.in_(bill_line_ids))
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
    for note_line_id, bill_line_id, taxable, tax in lines:
        eligibility, capital, bill_value = bill_lines.get(
            bill_line_id, (None, False, ZERO)
        )
        taken = _NoteLineTax(
            heads=dict.fromkeys(HEADS, ZERO),
            claimable=(eligibility or "ELIGIBLE") == "ELIGIBLE",
            capital=capital,
        )
        parts = charged.get(bill_line_id, [])
        supplier_tax = sum((amount for _, amount, rc in parts if not rc), ZERO)
        ratio = min(taxable / bill_value, Decimal("1")) if bill_value > ZERO else ZERO
        for code, amount, reverse in parts:
            if reverse:
                share = amount * ratio
                taken.reverse_charge += share
            elif supplier_tax > ZERO:
                share = tax * amount / supplier_tax
            else:
                continue
            bucket = _bucket(code, share)
            for head in HEADS:
                taken.heads[head] += getattr(bucket, head)
        found[note_line_id] = taken
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
        vendors = _vendors(
            self._session,
            {bill.vendor_id for bill in bills} | {note.vendor_id for note in notes},
        )
        rows = {
            **self._bill_rows(bills, vendors),
            **self._note_rows(notes, vendors),
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
            total = Decimal(str(bill.grand_total))
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
                taxable_value=quantize_money(total - Decimal(str(bill.tax_total))),
                igst=quantize_money(heads["igst"]),
                cgst=quantize_money(heads["cgst"]),
                sgst=quantize_money(heads["sgst"]),
                cess=quantize_money(heads["cess"]),
                total_tax=quantize_money(tax),
                itc_not_claimable=quantize_money(heads["not_claimable"]),
                reverse_charge_tax=quantize_money(
                    Decimal(str(bill.reverse_charge_tax_total or ZERO))
                ),
                invoice_total=quantize_money(total),
                capital_goods_tax=quantize_money(heads["capital"]),
            )
        return rows

    def _note_rows(
        self,
        notes: list[DebitNote],
        vendors: dict[UUID, tuple[str, str | None]],
    ) -> dict[UUID, GstPurchaseRegisterRow]:
        """Return a register row per debit note, by note id, figures negative."""
        if not notes:
            return {}
        ids = [note.id for note in notes]
        lines = self._session.execute(
            select(
                DebitNoteLine.id,
                DebitNoteLine.debit_note_id,
                DebitNoteLine.purchase_invoice_line_id,
                DebitNoteLine.taxable_amount,
                DebitNoteLine.tax_amount,
            ).where(
                DebitNoteLine.debit_note_id.in_(ids),
                DebitNoteLine.is_deleted.is_(False),
            )
        ).all()
        taxes = _note_line_taxes(
            self._session,
            [
                (line_id, bill_line_id, Decimal(str(taxable)), Decimal(str(tax)))
                for line_id, _, bill_line_id, taxable, tax in lines
            ],
        )
        per_note: dict[UUID, dict[str, Decimal]] = defaultdict(
            lambda: dict.fromkeys(
                (*HEADS, "not_claimable", "capital", "reverse_charge"), ZERO
            )
        )
        for line_id, note_id, _, _, _ in lines:
            taken = taxes[line_id]
            for head in HEADS:
                per_note[note_id][head] += taken.heads[head]
            per_note[note_id]["reverse_charge"] += taken.reverse_charge
            if not taken.claimable:
                per_note[note_id]["not_claimable"] += taken.total
            if taken.capital:
                per_note[note_id]["capital"] += taken.total
        bill_numbers = {
            bill_id: number
            for bill_id, number in self._session.execute(
                select(PurchaseInvoice.id, PurchaseInvoice.invoice_number).where(
                    PurchaseInvoice.id.in_({note.purchase_invoice_id for note in notes})
                )
            ).all()
        }
        rows = {}
        for note in notes:
            heads = per_note[note.id]
            tax = sum((heads[head] for head in HEADS), ZERO)
            name, gstin = vendors.get(note.vendor_id, (str(note.vendor_id), None))
            rows[note.id] = GstPurchaseRegisterRow(
                invoice_id=note.id,
                invoice_date=note.debit_note_date,
                invoice_number=note.debit_note_number,
                supplier_invoice_number=note.supplier_credit_note_number or "",
                supplier_invoice_date=(
                    note.supplier_credit_note_date or note.debit_note_date
                ),
                vendor_id=note.vendor_id,
                vendor_name=name,
                vendor_gstin=gstin,
                taxable_value=-quantize_money(Decimal(str(note.taxable_amount))),
                igst=-quantize_money(heads["igst"]),
                cgst=-quantize_money(heads["cgst"]),
                sgst=-quantize_money(heads["sgst"]),
                cess=-quantize_money(heads["cess"]),
                total_tax=-quantize_money(tax),
                itc_not_claimable=-quantize_money(heads["not_claimable"]),
                reverse_charge_tax=-quantize_money(heads["reverse_charge"]),
                invoice_total=-quantize_money(Decimal(str(note.total_amount))),
                capital_goods_tax=-quantize_money(heads["capital"]),
                document_type=DEBIT_NOTE,
                against_invoice_number=bill_numbers.get(note.purchase_invoice_id, ""),
            )
        return rows

    def hsn_summary(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[HsnPurchaseRow]:
        """Return the window's inward supplies by HSN code and unit.

        A line with no HSN on its product is grouped under an empty code, so
        the gap is visible rather than dropped. An approved debit note dated
        in the window comes off the code and unit of the bill line it names:
        its quantity, its taxable value and its tax by head.
        """
        from app.products.models import Product
        from app.uom.models import Uom

        lines = self._session.execute(
            select(
                PurchaseInvoiceLine.id,
                PurchaseInvoiceLine.purchase_invoice_id,
                func.coalesce(Product.hsn_sac, ""),
                Product.name,
                func.coalesce(Uom.code, ""),
                PurchaseInvoiceLine.current_invoice_quantity,
                PurchaseInvoiceLine.net_amount,
                PurchaseInvoiceLine.tax_amount,
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
        for line_id, bill_id, hsn, name, unit, quantity, net, tax in lines:
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
            row.taxable_value += Decimal(str(net)) - Decimal(str(tax))
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
        taken = _note_line_taxes(
            self._session,
            [
                (line_id, bill_line_id, Decimal(str(taxable)), Decimal(str(tax)))
                for line_id, bill_line_id, _, _, _, _, taxable, tax in note_lines
            ],
        )
        for line_id, _, hsn, name, unit, quantity, taxable, _ in note_lines:
            row = groups.get((hsn, unit))
            if row is None:
                row = groups[(hsn, unit)] = HsnPurchaseRow(
                    hsn_code=hsn,
                    description=name,
                    unit=unit,
                    quantity=ZERO,
                    taxable_value=ZERO,
                )
            row.quantity -= Decimal(str(quantity))
            row.taxable_value -= Decimal(str(taxable))
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
