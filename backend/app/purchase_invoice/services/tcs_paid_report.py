"""TCS paid to suppliers (PG-6, backlog §86 #9).

A supplier selling more than 50 lakh a year to the firm may charge TCS under
section 206C(1H) on the bill. The firm claims it against its own income tax
once it shows in Form 26AS, and the CA reconciles the two by quarter -- the
supplier files the collection on its 27EQ quarterly. So the report lists each
approved bill that bore TCS, with the supplier's PAN, the base (the bill
including GST), the rate and the amount, and closes each quarter of the
financial year with a total row.

Only approved and closed bills count: a draft has charged nothing yet, and a
cancelled bill's journal was reversed. One statement whatever the window holds:
the bills joined to their suppliers' names and PANs, columns only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination.reports import WHOLE_HISTORY, ReportWindow
from app.core.utils.money import quantize_ledger
from app.purchase_invoice.models import PurchaseInvoice
from app.vendors.models import Vendor

ZERO = Decimal("0")

#: A bill whose TCS the firm owes and may claim: approved, or approved and
#: then closed.
CHARGED_STATES = ("APPROVED", "CLOSED")


def quarter_of(day: date) -> str:
    """Name the financial-year quarter ``day`` falls in, e.g. ``Q1 2026-27``.

    The Indian financial year runs April to March, and the TCS returns and
    Form 26AS are read by its quarters.
    """
    start_year = day.year if day.month >= 4 else day.year - 1
    quarter = ((day.month - 4) % 12) // 3 + 1
    return f"Q{quarter} {start_year}-{(start_year + 1) % 100:02d}"


@dataclass
class TcsPaidRow:
    """One bill that bore TCS, or one quarter's total (``row_type``)."""

    row_type: str
    quarter: str
    invoice_id: UUID | None
    invoice_number: str | None
    supplier_invoice_number: str | None
    invoice_date: date | None
    vendor_id: UUID | None
    vendor_name: str | None
    vendor_pan: str | None
    base_amount: Decimal
    tcs_rate_percent: Decimal | None
    tcs_amount: Decimal


class TcsPaidReportService:
    """Read the TCS suppliers charged on the firm's bills, by quarter."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a firm store's session."""
        self._session = session

    def rows(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[TcsPaidRow]:
        """Return the window's bills that bore TCS, oldest first, by quarter.

        Each quarter closes with a ``QUARTER_TOTAL`` row summing its bases
        and its TCS, so the figure the CA matches against 26AS is on the page.
        """
        bills = self._session.execute(
            select(
                PurchaseInvoice.id,
                PurchaseInvoice.invoice_number,
                PurchaseInvoice.supplier_invoice_number,
                PurchaseInvoice.invoice_date,
                PurchaseInvoice.vendor_id,
                PurchaseInvoice.grand_total,
                PurchaseInvoice.tcs_rate_percent,
                PurchaseInvoice.tcs_amount,
                Vendor.name,
                Vendor.pan,
            )
            .outerjoin(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(CHARGED_STATES),
                PurchaseInvoice.tcs_amount > 0,
                *window.dated(PurchaseInvoice.invoice_date),
            )
            .order_by(
                PurchaseInvoice.invoice_date.asc(),
                PurchaseInvoice.invoice_number.asc(),
            )
        ).all()
        rows: list[TcsPaidRow] = []
        current: str | None = None
        base_total = tcs_total = ZERO

        def close(quarter: str) -> None:
            """Append the total row for ``quarter``."""
            rows.append(
                TcsPaidRow(
                    row_type="QUARTER_TOTAL",
                    quarter=quarter,
                    invoice_id=None,
                    invoice_number=None,
                    supplier_invoice_number=None,
                    invoice_date=None,
                    vendor_id=None,
                    vendor_name=f"Total {quarter}",
                    vendor_pan=None,
                    base_amount=base_total,
                    tcs_rate_percent=None,
                    tcs_amount=tcs_total,
                )
            )

        for bill in bills:
            quarter = quarter_of(bill.invoice_date)
            if current is not None and quarter != current:
                close(current)
                base_total = tcs_total = ZERO
            current = quarter
            base = quantize_ledger(Decimal(str(bill.grand_total)))
            tcs = quantize_ledger(Decimal(str(bill.tcs_amount)))
            base_total += base
            tcs_total += tcs
            rows.append(
                TcsPaidRow(
                    row_type="BILL",
                    quarter=quarter,
                    invoice_id=bill.id,
                    invoice_number=bill.invoice_number,
                    supplier_invoice_number=bill.supplier_invoice_number,
                    invoice_date=bill.invoice_date,
                    vendor_id=bill.vendor_id,
                    vendor_name=bill.name,
                    vendor_pan=bill.pan,
                    base_amount=base,
                    tcs_rate_percent=bill.tcs_rate_percent,
                    tcs_amount=tcs,
                )
            )
        if current is not None:
            close(current)
        return rows
