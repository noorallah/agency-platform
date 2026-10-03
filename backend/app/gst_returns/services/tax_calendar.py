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
last month closed" without listing every month that already is.

**A quarterly filer (QRMP, GST-7)** owes different things by the month's place
in its quarter. Months 1 and 2: the **IFF**, due the 13th -- optional, so it
is never late, only done once filed -- and the **PMT-06** deposit, due the
25th, done once a deposit is recorded. Month 3: the quarter's **GSTR-1**, due
the 13th, and its **GSTR-3B**, due the 22nd or 24th by state, whose figure is
the cash still to pay after the deposits. Both name the quarter's last month as
their period, as the portal's filings and the settlement do.
"""

from dataclasses import dataclass, replace
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
    GstCashDepositStatus,
    GstPayment,
    GstPaymentStatus,
    GstReturnFiling,
    GstReturnType,
)
from app.gst_returns.services.filing_frequency import (
    FilingFrequencyService,
    FilingPlan,
    month_bounds,
    position_in_quarter,
    quarter_label,
    quarter_months,
)
from app.gst_returns.services.gst_payment_service import (
    GstPaymentService,
    period_bounds,
)

#: How many finished months the calendar looks back over.
LOOKBACK_MONTHS = 3

#: The day of the next month TCS is deposited by; the returns' days are the
#: filing plan's (``FilingPlan``).
TCS_DUE_DAY = 7


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
    #: The first day the item covers: its month's, or its quarter's.
    period_from: date | None = None


def _period(day: date) -> str:
    """Return the ``YYYY-MM`` month a day falls in."""
    return f"{day.year:04d}-{day.month:02d}"


def _tcs_due(return_period: str) -> date:
    """Return the 7th of the month after the period: TCS's deposit date."""
    _, last = period_bounds(return_period)
    after = last + timedelta(days=1)
    return date(after.year, after.month, TCS_DUE_DAY)


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
        plan = FilingFrequencyService(self._session).plan(firm_id)
        filings = self._filings(
            firm_id,
            sorted({plan.return_period(month) for month in months} | set(months)),
        )
        payments = self._payments(
            firm_id, sorted({plan.return_period(month) for month in months})
        )
        tcs = self._tcs_by_month(firm_id, months)
        latest = months[0]
        items: list[CalendarItem] = []
        for month in months:
            if plan.is_quarterly(month) and position_in_quarter(month) < 3:
                items += self._early_quarter_items(firm_id, plan, month, filings, today)
            else:
                items += self._return_items(
                    firm_id, plan, month, filings, payments, today
                )
            collected = tcs.get(month, ZERO)
            if collected > ZERO:
                items.append(
                    self._item(
                        "TCS", month, collected, due=_tcs_due(month), today=today
                    )
                )
        return [
            item
            for item in items
            if item.status != "DONE" or item.return_period == latest
        ]

    def _return_items(
        self,
        firm_id: UUID,
        plan: FilingPlan,
        month: str,
        filings: dict[tuple[str, str], GstReturnFiling],
        payments: dict[str, GstPayment],
        today: date,
    ) -> list[CalendarItem]:
        """Return GSTR-1 and 3B for a month, or for the quarter it closes."""
        period = plan.return_period(month)
        first, _ = plan.span(period)
        preview = GstPaymentService(self._session).preview(
            firm_id, period, payment_date=today
        )
        output_tax = quantize_ledger(
            sum((preview.set_off.liability[head] for head in HEADS), ZERO)
        )
        gstr1 = filings.get((GstReturnType.GSTR1.value, period))
        gstr3b = filings.get((GstReturnType.GSTR3B.value, period))
        paid = payments.get(period)
        return [
            self._item(
                "GSTR1",
                period,
                output_tax,
                due=plan.gstr1_due(period),
                today=today,
                done_on=None if gstr1 is None else gstr1.filed_on,
                reference=None if gstr1 is None else gstr1.arn,
                filing_id=None if gstr1 is None else gstr1.id,
                period_from=first,
            ),
            self._item(
                "GSTR3B",
                period,
                quantize_ledger(preview.bank_total),
                due=plan.gstr3b_due(period),
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
                period_from=first,
            ),
        ]

    def _early_quarter_items(
        self,
        firm_id: UUID,
        plan: FilingPlan,
        month: str,
        filings: dict[tuple[str, str], GstReturnFiling],
        today: date,
    ) -> list[CalendarItem]:
        """Return the IFF and the PMT-06 deposit of a quarter's month 1 or 2."""
        from app.gst_returns.services.gst_cash_deposits import GstCashDepositService

        first, _ = period_bounds(month)
        iff = filings.get((GstReturnType.IFF.value, month))
        iff_item = self._item(
            "IFF",
            month,
            self._b2b_value(firm_id, month),
            due=plan.iff_due(month),
            today=today,
            done_on=None if iff is None else iff.filed_on,
            reference=None if iff is None else iff.arn,
            filing_id=None if iff is None else iff.id,
            period_from=first,
        )
        early: list[CalendarItem] = [iff_item]
        if iff is None:
            # Optional: a month whose B2B invoices wait for the quarter's
            # GSTR-1 is not late, it is simply not furnished early -- and once
            # the 13th has passed the portal no longer offers it at all.
            early = (
                [replace(iff_item, status="OPTIONAL", days_late=0)]
                if today <= iff_item.due_date
                else []
            )
        deposits = GstCashDepositService(self._session)
        standing = [
            row
            for row in deposits.list_deposits(firm_id)
            if row.return_period == month
            and row.status == GstCashDepositStatus.POSTED.value
        ]
        if standing:
            amount = quantize_ledger(
                sum(
                    (
                        Decimal(str(getattr(row, f"amount_{head}")))
                        for row in standing
                        for head in HEADS
                    ),
                    ZERO,
                )
            )
            done_on: date | None = max(row.deposit_date for row in standing)
            reference = standing[0].challan_cpin
        else:
            amount = deposits.suggestion(firm_id, month).total
            done_on, reference = None, None
        return [
            *early,
            self._item(
                "PMT06",
                month,
                amount,
                due=plan.pmt06_due(month),
                today=today,
                done_on=done_on,
                reference=reference,
                period_from=first,
            ),
        ]

    def _b2b_value(self, firm_id: UUID, month: str) -> Decimal:
        """Return the value of the month's B2B invoices, what an IFF carries."""
        from app.gst_returns.services.qrmp import QrmpReturnService

        return QrmpReturnService(self._session).b2b_value(firm_id, month)

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
        """Record that a return was filed on the portal; does not commit.

        A quarterly filer files GSTR-1 and 3B under the quarter's last month
        and the IFF only for months 1 and 2; anything else is refused by name.
        """
        plan = FilingFrequencyService(self._session).plan(firm_id)
        quarterly = plan.is_quarterly(return_period)
        if return_type == GstReturnType.IFF:
            if not quarterly or position_in_quarter(return_period) == 3:
                raise ValidationError(
                    "The IFF is furnished only for the first two months of a "
                    f"quarter filed quarterly, not for {return_period}."
                )
        elif quarterly and position_in_quarter(return_period) < 3:
            raise ValidationError(
                f"{return_type.value} for {quarter_label(return_period)} is filed "
                f"as {plan.return_period(return_period)}, the quarter's last month."
            )
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
        if return_type == GstReturnType.GSTR1:
            self._snapshot(row, quarterly=quarterly, actor_id=actor_id)
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

    def _snapshot(
        self, filing: GstReturnFiling, *, quarterly: bool, actor_id: UUID
    ) -> None:
        """Keep the GSTR-1 being filed, as the documents stand now (GST-6).

        A quarterly filer's return covers the quarter it closes.
        """
        # Imported here: the return service reads this module's filings.
        from app.gst_returns.services.amendments import GstAmendmentService
        from app.gst_returns.services.gstr_service import GstReturnService

        first = (
            quarter_months(filing.return_period)[0]
            if quarterly
            else filing.return_period
        )
        from_date, _ = month_bounds(first)
        _, to_date = month_bounds(filing.return_period)
        payload = GstReturnService(self._session).gstr1(
            firm_scope=filing.firm_id, from_date=from_date, to_date=to_date, live=True
        )
        GstAmendmentService(self._session).record(
            filing,
            gstin=str(payload.get("gstin") or ""),
            from_date=from_date,
            to_date=to_date,
            payload=payload,
            actor_id=actor_id,
        )

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
        due: date,
        today: date,
        done_on: date | None = None,
        reference: str | None = None,
        filing_id: UUID | None = None,
        period_from: date | None = None,
    ) -> CalendarItem:
        """Build one item, judged on today against its due date."""
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
            period_from=period_from or period_bounds(month)[0],
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
