"""The collection sheet: the bills each collector is to chase (SG-8).

One row per bill that still owes something, with its customer, how long it is
overdue, the latest live promise on it and whose job it is to collect.

**What a bill owes is not derived here.** The rows are Record Receipt's own
list (``ReceiptService.outstanding_invoices``) for every customer of the firm,
so the sheet, the receipt screen and the ageing cannot disagree -- bills owed
from before the firm started here included, since they are collected the same
way.

**The collector** is the customer's own (``customers.collector_id``) and,
where it names none, its account manager (``customers.salesman_id``). A
customer with neither is on the sheet under nobody, last.

**The day** (``as_of``, today when omitted) dates the overdue count and the
promise's status. What a bill owes is always what it owes now: the sheet is
paper for today's round, not a statement of a past day.

The sheet reads the firm's open bills, its customers, its latest promises and
its members once each, whatever its length; a page is a slice of it.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.collections.models import PaymentPromise
from app.collections.schemas import CollectionSheetRow
from app.collections.services.promises import (
    FORMER_MEMBER,
    latest_live_promises,
    member_names,
    status_of,
)
from app.common.firm_metadata import FirmMetadataReader, firm_today
from app.customers.models import Customer
from app.sales.models.territory import (
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
)
from app.settlements.services import ReceiptService

NO_COLLECTOR = "No collector"


@dataclass(frozen=True, slots=True)
class _Party:
    """What the sheet shows of one customer."""

    code: str
    name: str
    phone: str | None
    collector_id: UUID | None


def _money(value: Decimal) -> str:
    """Write an amount the way the sheet prints it."""
    return f"{value:,.2f}"


def _day(value: date | None) -> str:
    """Write a date the way the sheet prints it; none is blank."""
    return value.strftime("%d-%m-%Y") if value else ""


class CollectionSheetService:
    """Build the collection sheet, on screen and on paper."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def rows(
        self,
        firm_id: UUID,
        *,
        collector_id: UUID | None = None,
        route_id: UUID | None = None,
        as_of: date | None = None,
        overdue_only: bool = False,
    ) -> list[CollectionSheetRow]:
        """Return the whole sheet: by collector, then customer, then due date.

        Args:
            firm_id: The firm whose bills to list.
            collector_id: Only customers this person collects from -- as
                their collector, or as account manager where they name none.
            route_id: Only customers on this route's round.
            as_of: The day the sheet is for; the firm's today when omitted.
            overdue_only: Only bills past their due date on that day.

        """
        on = as_of or firm_today(self._session, firm_id)
        parties = self._parties(firm_id, collector_id=collector_id, route_id=route_id)
        if not parties:
            return []
        bills = [
            record
            for record in ReceiptService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=None
            )
            if record.party_id in parties
            and not (
                overdue_only and (record.due_date is None or record.due_date >= on)
            )
        ]
        if not bills:
            return []
        on_bill: dict[UUID, tuple[PaymentPromise, Decimal]] = {}
        on_account: dict[UUID, tuple[PaymentPromise, Decimal]] = {}
        for latest, paid in latest_live_promises(self._session, firm_id):
            if latest.sales_invoice_id is None:
                on_account[latest.customer_id] = (latest, paid)
            else:
                on_bill[latest.sales_invoice_id] = (latest, paid)
        members = member_names(self._session, firm_id)
        rows: list[CollectionSheetRow] = []
        for record in bills:
            # Narrowed above; a bill always has a party when asked firm-wide.
            if record.party_id is None:  # pragma: no cover
                continue
            party = parties[record.party_id]
            held = (
                None if record.is_opening_bill else on_bill.get(record.invoice_id)
            ) or on_account.get(record.party_id)
            promise: PaymentPromise | None = held[0] if held else None
            received = held[1] if held else Decimal("0")
            rows.append(
                CollectionSheetRow(
                    collector_id=party.collector_id,
                    collector_name=(
                        None
                        if party.collector_id is None
                        else members.get(party.collector_id, FORMER_MEMBER)
                    ),
                    customer_id=record.party_id,
                    customer_code=party.code,
                    customer_name=party.name,
                    customer_phone=party.phone,
                    invoice_id=record.invoice_id,
                    invoice_number=record.invoice_number,
                    invoice_date=record.invoice_date,
                    due_date=record.due_date,
                    days_overdue=(
                        max((on - record.due_date).days, 0) if record.due_date else 0
                    ),
                    invoice_total=record.invoice_total,
                    outstanding=record.outstanding_amount,
                    is_opening_bill=record.is_opening_bill,
                    promise_id=promise.id if promise else None,
                    promised_on=promise.promised_on if promise else None,
                    promised_amount=(
                        Decimal(str(promise.amount)).quantize(Decimal("0.01"))
                        if promise
                        else None
                    ),
                    promise_status=(
                        status_of(promise, received, today=on) if promise else None
                    ),
                    promise_note=promise.note if promise else None,
                    promise_is_for_account=bool(
                        promise and promise.sales_invoice_id is None
                    ),
                )
            )
        # Nobody's customers last, and never by where a NULL happens to sort.
        rows.sort(
            key=lambda row: (
                row.collector_id is None,
                (row.collector_name or "").casefold(),
                str(row.collector_id or ""),
                row.customer_name.casefold(),
                str(row.customer_id),
                row.due_date is None,
                row.due_date or date.max,
                row.invoice_number,
            )
        )
        return rows

    def page(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        collector_id: UUID | None = None,
        route_id: UUID | None = None,
        as_of: date | None = None,
        overdue_only: bool = False,
    ) -> tuple[list[CollectionSheetRow], int]:
        """Return one page of the sheet and how many bills it holds in all."""
        rows = self.rows(
            firm_id,
            collector_id=collector_id,
            route_id=route_id,
            as_of=as_of,
            overdue_only=overdue_only,
        )
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    def pdf(
        self,
        firm_id: UUID,
        *,
        collector_id: UUID | None = None,
        route_id: UUID | None = None,
        as_of: date | None = None,
        overdue_only: bool = False,
    ) -> bytes:
        """Return the sheet as an A4 PDF, one table per collector.

        The last column is left empty: it is where the collector writes what
        was handed over.
        """
        on = as_of or firm_today(self._session, firm_id)
        rows = self.rows(
            firm_id,
            collector_id=collector_id,
            route_id=route_id,
            as_of=on,
            overdue_only=overdue_only,
        )
        styles = getSampleStyleSheet()
        parts: list[object] = []
        groups: dict[UUID | None, list[CollectionSheetRow]] = {}
        for row in rows:
            groups.setdefault(row.collector_id, []).append(row)
        for bills in groups.values():
            parts.append(
                Paragraph(
                    f"Collector: {bills[0].collector_name or NO_COLLECTOR}",
                    styles["Heading3"],
                )
            )
            table: list[list[object]] = [
                [
                    "Customer",
                    "Bill",
                    "Due",
                    "Days",
                    "Outstanding",
                    "Promise",
                    "Collected",
                ]
            ]
            for row in bills:
                who = escape(row.customer_name) + (
                    f"<br/>{escape(row.customer_phone)}" if row.customer_phone else ""
                )
                promise = (
                    f"{_day(row.promised_on)}\n{_money(row.promised_amount)}"
                    if row.promised_on and row.promised_amount is not None
                    else ""
                )
                table.append(
                    [
                        Paragraph(who, styles["BodyText"]),
                        f"{row.invoice_number}\n{_day(row.invoice_date)}",
                        _day(row.due_date),
                        str(row.days_overdue) if row.days_overdue else "",
                        _money(row.outstanding),
                        promise,
                        "",
                    ]
                )
            table.append(
                [
                    "Total",
                    f"{len(bills)} bill(s)",
                    "",
                    "",
                    _money(sum((row.outstanding for row in bills), Decimal("0"))),
                    "",
                    "",
                ]
            )
            parts.append(self._table(table))
            parts.append(Spacer(1, 6 * mm))
        if not rows:
            parts.append(Paragraph("Nothing to collect.", styles["Normal"]))
        firm = FirmMetadataReader(self._session).get(firm_id)
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="Collection sheet",
        )
        header = [
            Paragraph(firm.name or "", styles["Title"]),
            Paragraph(
                f"Collection sheet -- {len(rows)} bill(s) -- for {_day(on)}"
                + (" -- overdue only" if overdue_only else ""),
                styles["Normal"],
            ),
            Spacer(1, 4 * mm),
        ]
        document.build([*header, *parts])
        return buffer.getvalue()

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _table(rows: list[list[object]]) -> Table:
        """Return a ruled table, the money right-aligned."""
        table = Table(
            rows,
            colWidths=[
                50 * mm,
                30 * mm,
                20 * mm,
                12 * mm,
                25 * mm,
                25 * mm,
                24 * mm,
            ],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                    ("GRID", (0, 1), (-1, -1), 0.25, colors.grey),
                    ("ALIGN", (3, 0), (4, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    def _parties(
        self, firm_id: UUID, *, collector_id: UUID | None, route_id: UUID | None
    ) -> dict[UUID, _Party]:
        """Return the firm's customers the sheet may list, read once.

        The firm's query rather than the open bills' ids, which grow with the
        firm past what one statement can bind.
        """
        # The collector, falling back to the account manager.
        collects = func.coalesce(Customer.collector_id, Customer.salesman_id)
        statement = select(
            Customer.id, Customer.code, Customer.name, Customer.phone, collects
        ).where(Customer.firm_id == firm_id, Customer.is_deleted.is_(False))
        if collector_id is not None:
            statement = statement.where(collects == collector_id)
        if route_id is not None:
            # A route is a territory with a route profile; its round is the
            # customers assigned to that territory. Either id names it: a
            # delivery note carries the profile's, the territory tree its own.
            statement = statement.where(
                Customer.id.in_(
                    select(TerritoryCustomerAssignment.customer_id).where(
                        TerritoryCustomerAssignment.is_deleted.is_(False),
                        or_(
                            TerritoryCustomerAssignment.territory_id == route_id,
                            TerritoryCustomerAssignment.territory_id.in_(
                                select(TerritoryRouteProfile.territory_id).where(
                                    TerritoryRouteProfile.id == route_id,
                                    TerritoryRouteProfile.is_deleted.is_(False),
                                )
                            ),
                        ),
                    )
                )
            )
        return {
            customer_id: _Party(code=code, name=name, phone=phone, collector_id=who)
            for customer_id, code, name, phone, who in self._session.execute(
                statement
            ).all()
        }


__all__ = ["NO_COLLECTOR", "CollectionSheetService"]
