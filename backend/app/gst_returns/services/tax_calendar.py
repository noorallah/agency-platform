"""The tax calendar on Home: what is due, what is late, what is done (63.4).

For each of the last three months the firm traded in, the returns and deposits
that month owes, each with its due date and the figure it is about:

* **GSTR-1**, due the 11th of the next month: the month's output tax. Done
  once somebody says it was filed (``gst_return_filings``) -- filing happens on
  the portal, so nothing else can say so.
* **GSTR-3B**, due the 20th: the cash the month's GST payment works out to,
  reverse charge included. Done once that payment is recorded, or the return
  is said to be filed (a nil return, or tax paid outside the platform).
* **TCS deposit**, due the 7th: the tax collected at source that month. Shown
  only for a month that collected any -- section 206C(1H) ended on 1 April
  2025 -- and never done, since recording a deposit is backlog 63 item 5.

A done item is shown for the latest month only, so the calendar answers "is
last month closed" without listing every month that already is. Monthly filers
only: quarterly filing (QRMP) is backlog 74 row 11.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.gst_returns.models import (
    HEADS,
    GstPayment,
    GstPaymentStatus,
    GstReturnFiling,
    GstReturnType,
)
from app.gst_returns.services.gst_payment_service import (
    GstPaymentService,
    period_bounds,
)

#: How many finished months the calendar looks back over.
LOOKBACK_MONTHS = 3

#: The day of the next month each obligation falls due.
DUE_DAY = {"GSTR1": 11, "GSTR3B": 20, "TCS": 7}


@dataclass(frozen=True, slots=True)
class CalendarItem:
    """One return or deposit a month owes."""

    kind: str
    return_period: str
    due_date: date
    #: The figure the item is about; see the module docstring.
    amount: Decimal
    #: ``DONE``, ``DUE`` or ``LATE``.
    status: str
    days_late: int
    #: When it was filed or paid, for a done item.
    done_on: date | None = None
    #: The ARN, or the challan's CPIN, where one was kept.
    reference: str | None = None
    #: The filing row behind a done item, which can be withdrawn.
    filing_id: UUID | None = None


def _period(day: date) -> str:
    """Return the ``YYYY-MM`` month a day falls in."""
    return f"{day.year:04d}-{day.month:02d}"


def _due(return_period: str, kind: str) -> date:
    """Return the day of the next month the obligation falls due."""
    _, last = period_bounds(return_period)
    after = last + timedelta(days=1)
    return date(after.year, after.month, DUE_DAY[kind])


class TaxCalendarService:
    """Read the firm's tax calendar, and record a return as filed."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store."""
        self._session = session

    def calendar(
        self, firm_id: UUID, *, today: date | None = None
    ) -> list[CalendarItem]:
        """Return what the last few finished months owe, latest month first."""
        today = today or utc_now().date()
        months = self._months(firm_id, today)
        if not months:
            return []
        filings = self._filings(firm_id, months)
        payments = self._payments(firm_id, months)
        tcs = self._tcs_by_month(firm_id, months)
        latest = months[0]
        items: list[CalendarItem] = []
        for month in months:
            preview = GstPaymentService(self._session).preview(
                firm_id, month, payment_date=today
            )
            output_tax = quantize_ledger(
                sum((preview.set_off.liability[head] for head in HEADS), ZERO)
            )
            gstr1 = filings.get((GstReturnType.GSTR1.value, month))
            items.append(
                self._item(
                    "GSTR1",
                    month,
                    output_tax,
                    today=today,
                    done_on=None if gstr1 is None else gstr1.filed_on,
                    reference=None if gstr1 is None else gstr1.arn,
                    filing_id=None if gstr1 is None else gstr1.id,
                )
            )
            gstr3b = filings.get((GstReturnType.GSTR3B.value, month))
            paid = payments.get(month)
            items.append(
                self._item(
                    "GSTR3B",
                    month,
                    quantize_ledger(preview.cash_total),
                    today=today,
                    done_on=(
                        paid.payment_date
                        if paid is not None
                        else (None if gstr3b is None else gstr3b.filed_on)
                    ),
                    reference=(
                        paid.challan_cpin
                        if paid is not None
                        else (None if gstr3b is None else gstr3b.arn)
                    ),
                    filing_id=None if gstr3b is None else gstr3b.id,
                )
            )
            collected = tcs.get(month, ZERO)
            if collected > ZERO:
                items.append(self._item("TCS", month, collected, today=today))
        return [
            item
            for item in items
            if item.status != "DONE" or item.return_period == latest
        ]

    def mark_filed(
        self,
        firm_id: UUID,
        *,
        return_type: GstReturnType,
        return_period: str,
        filed_on: date,
        actor_id: UUID,
        arn: str | None = None,
        remarks: str | None = None,
    ) -> GstReturnFiling:
        """Record that a return was filed on the portal; does not commit."""
        _, last = period_bounds(return_period)
        if filed_on <= last:
            raise ValidationError(
                f"A return for {return_period} is filed after the month ends, "
                f"not on {filed_on.isoformat()}."
            )
        if filed_on > utc_now().date():
            raise ValidationError("A return cannot have been filed in the future.")
        existing = self._session.scalar(
            select(GstReturnFiling).where(
                GstReturnFiling.firm_id == firm_id,
                GstReturnFiling.return_type == return_type.value,
                GstReturnFiling.return_period == return_period,
                GstReturnFiling.is_deleted.is_(False),
            )
        )
        if existing is not None:
            raise ConflictError(
                f"{return_type.value} for {return_period} is already recorded as "
                f"filed on {existing.filed_on.isoformat()}."
            )
        row = GstReturnFiling(
            firm_id=firm_id,
            return_type=return_type.value,
            return_period=return_period,
            filed_on=filed_on,
            arn=(arn or "").strip().upper() or None,
            remarks=(remarks or "").strip() or None,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="gst_return.filed",
            entity_type="gst_return_filing",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "return_type": row.return_type,
                "return_period": row.return_period,
                "filed_on": row.filed_on.isoformat(),
                "arn": row.arn,
            },
        )
        return row

    def withdraw(self, filing_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Take back a return recorded as filed in error; does not commit."""
        row = self._session.get(GstReturnFiling, filing_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("Filed return not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="gst_return.withdrawn",
            entity_type="gst_return_filing",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={
                "return_type": row.return_type,
                "return_period": row.return_period,
                "filed_on": row.filed_on.isoformat(),
            },
        )

    # ---- reading ---------------------------------------------------------

    @staticmethod
    def _item(
        kind: str,
        month: str,
        amount: Decimal,
        *,
        today: date,
        done_on: date | None = None,
        reference: str | None = None,
        filing_id: UUID | None = None,
    ) -> CalendarItem:
        """Build one item, judged on today against its due date."""
        due = _due(month, kind)
        if done_on is not None:
            status, late = "DONE", 0
        elif today > due:
            status, late = "LATE", (today - due).days
        else:
            status, late = "DUE", 0
        return CalendarItem(
            kind=kind,
            return_period=month,
            due_date=due,
            amount=amount,
            status=status,
            days_late=late,
            done_on=done_on,
            reference=reference,
            filing_id=filing_id,
        )

    def _months(self, firm_id: UUID, today: date) -> list[str]:
        """Return the finished months to show, latest first.

        Never a month before the firm's first sale or bill: a firm that went
        live last week owes nothing for the quarter before it.
        """
        from app.purchase_invoice.models import PurchaseInvoice
        from app.sales_invoice.models import SalesInvoice

        firsts = [
            self._session.scalar(
                select(func.min(SalesInvoice.invoice_date)).where(
                    SalesInvoice.firm_id == firm_id,
                    SalesInvoice.is_deleted.is_(False),
                )
            ),
            self._session.scalar(
                select(func.min(PurchaseInvoice.invoice_date)).where(
                    PurchaseInvoice.firm_id == firm_id,
                    PurchaseInvoice.is_deleted.is_(False),
                )
            ),
        ]
        started = min((day for day in firsts if day is not None), default=None)
        if started is None:
            return []
        first_of_month = today.replace(day=1)
        months: list[str] = []
        cursor = first_of_month - timedelta(days=1)
        for _ in range(LOOKBACK_MONTHS):
            if _period(cursor) < _period(started):
                break
            months.append(_period(cursor))
            cursor = cursor.replace(day=1) - timedelta(days=1)
        return months

    def _filings(
        self, firm_id: UUID, months: list[str]
    ) -> dict[tuple[str, str], GstReturnFiling]:
        """Return the live filings of the months, by return and month."""
        return {
            (row.return_type, row.return_period): row
            for row in self._session.scalars(
                select(GstReturnFiling).where(
                    GstReturnFiling.firm_id == firm_id,
                    GstReturnFiling.is_deleted.is_(False),
                    GstReturnFiling.return_period.in_(months),
                )
            ).all()
        }

    def _payments(self, firm_id: UUID, months: list[str]) -> dict[str, GstPayment]:
        """Return the standing GST payment of each month that has one."""
        return {
            row.return_period: row
            for row in self._session.scalars(
                select(GstPayment).where(
                    GstPayment.firm_id == firm_id,
                    GstPayment.is_deleted.is_(False),
                    GstPayment.status == GstPaymentStatus.POSTED.value,
                    GstPayment.return_period.in_(months),
                )
            ).all()
        }

    def _tcs_by_month(self, firm_id: UUID, months: list[str]) -> dict[str, Decimal]:
        """Return the TCS collected in each month, reversed collections out."""
        from app.tcs.models.tcs import TcsCollection, TcsCollectionStatus

        first, _ = period_bounds(months[-1])
        _, last = period_bounds(months[0])
        totals: dict[str, Decimal] = {}
        for collected_on, amount in self._session.execute(
            select(TcsCollection.collected_on, TcsCollection.tcs_amount).where(
                TcsCollection.firm_id == firm_id,
                TcsCollection.is_deleted.is_(False),
                TcsCollection.status == TcsCollectionStatus.COLLECTED.value,
                TcsCollection.collected_on >= first,
                TcsCollection.collected_on <= last,
            )
        ).all():
            month = _period(collected_on)
            totals[month] = totals.get(month, ZERO) + Decimal(str(amount))
        return {month: quantize_ledger(total) for month, total in totals.items()}


__all__ = ["CalendarItem", "TaxCalendarService"]
