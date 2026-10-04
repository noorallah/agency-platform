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

Supplier debit notes (the supplier's credit notes) are not netted in yet: a
`DebitNoteLine` keeps one `tax_amount` and a rate, not its components by head,
so it cannot be split into IGST, CGST, SGST and cess the way a bill line is
(backlog §86 row 17).

Both reports read a constant number of statements whatever the window holds
(`docs/PERFORMANCE_AT_VOLUME.md`): the bills, then their taxes for that page,
then the supplier names.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.pagination.reports import WHOLE_HISTORY, ReportRows, ReportWindow
from app.core.utils.money import quantize_money
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


@dataclass
class GstPurchaseRegisterRow:
    """One supplier bill by tax head."""

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
        """Return the window's claimed bills, newest first, by tax head."""
        bills = window.fetch(
            self._session,
            select(PurchaseInvoice)
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(CLAIMED_STATES),
                *window.dated(PurchaseInvoice.invoice_date),
            )
            .order_by(
                PurchaseInvoice.invoice_date.desc(),
                PurchaseInvoice.created_at.desc(),
                PurchaseInvoice.id.desc(),
            ),
        )
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
        vendors = _vendors(self._session, {bill.vendor_id for bill in bills})
        rows = []
        for bill in bills:
            heads = per_bill[bill.id]
            tax = sum((heads[head] for head in HEADS), ZERO)
            total = Decimal(str(bill.grand_total))
            name, gstin = vendors.get(bill.vendor_id, (str(bill.vendor_id), None))
            rows.append(
                GstPurchaseRegisterRow(
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
            )
        if isinstance(bills, ReportRows):
            return ReportRows(rows, total_records=bills.total_records)
        return rows

    def hsn_summary(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[HsnPurchaseRow]:
        """Return the window's inward supplies by HSN code and unit.

        A line with no HSN on its product is grouped under an empty code, so
        the gap is visible rather than dropped.
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
