"""Payables by supplier and month, checked against the books (§85, PG-2).

One row per supplier: what each of its bills still owes, in the month of the
bill (or of its due date), bills older than the months shown in **Older**,
then a **Credits** column and **Outstanding** -- what is really owed once the
supplier's credits are netted. It replaces *Vendor outstanding*, which listed
the bills alone and so read 2,124.00 on QA01 while Trade Payables held
1,770.00 (D-BUY-32).

**What a bill owes is derived, never read off the bill**: its total less the
money ``settlement_allocations`` put on it, the completed returns off its own
lines, the approved debit notes against it, the write-backs and set-offs
against it and the supplier credit set against it -- each rounded to the
ledger as Record Payment rounds it (`PaymentService.outstanding_invoices`).

**Credits** are everything on the supplier's account that names no bill:

* what completed purchase returns debited payables with beyond their
  bill-sourced lines (a return off a goods receipt gives all of it; what went
  back before billing raised no payable, D-BUY-26);
* what a bill could not absorb -- a return or a debit note on a bill already
  paid (D-BUY-20, A4) -- which shows as the bill's figure below zero;
* money paid on account and not yet allocated to a bill (an advance);

less the credit already set against bills and what the supplier has paid
back. So Outstanding sums every document that posts to accounts payable, and
the **books check** reads the payables account's balance at the as-of date
from the journal: a difference is shown, never hidden.

**As of** a date: documents dated after it are left out, as is money
allocated after it; a payment, write-back or refund reversed after it still
stood. A bill, return or debit note cancelled since is left out while its
journal stood on that date, so the books check then shows the difference.

The **Paid** view is the other question on the same grid: what was paid to
each supplier in each month of the window, checked against the payables
debits the payments posted.

Grouped in SQL: a fixed number of statements whatever the number of bills or
suppliers (`docs/PERFORMANCE_AT_VOLUME.md`). Only bills that still owe
something, or are owed back, reach Python.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session, aliased

from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.debit_note.models import DebitNote
from app.finance.currency import rupee_rate_sql
from app.finance.models import JournalEntry, JournalLine, JournalStatus
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.party_adjustments.models import (
    PartyAdjustment,
    PartyAdjustmentAllocation,
    PartyAdjustmentStatus,
)
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.services.vendor_ageing import _vendors
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementStatus,
    SupplierCreditApplication,
    SupplierCreditRefund,
)
from app.vendors.models import VendorOpeningBill
from app.vendors.models.opening_bill import VendorOpeningBillStatus

Basis = Literal["invoice", "due"]
View = Literal["owed", "paid"]

#: Bill states that owe anything (`SETTLEABLE_INVOICE_STATES`, repeated here
#: because the settlement service imports this module's package).
OWING_STATES = ("APPROVED", "COMPLETED", "CLOSED", "PARTIALLY_PAID", "PAID")
#: Completing a return is what debits payables; cancelling takes it back.
CREDITING_RETURN_STATES = ("COMPLETED", "CLOSED")
#: A posted journal counts, and so does one later reversed: its mirror is
#: what takes it back, on the day it was reversed.
COUNTED_JOURNALS = (JournalStatus.POSTED.value, JournalStatus.REVERSED.value)
#: Below this a bill's figure is rounding noise, not a debt.
NOISE = Decimal("0.004")
MAX_MONTHS = 24


@dataclass
class PayablesLine:
    """One supplier's figures, or the total row (no supplier)."""

    vendor_id: UUID | None
    vendor_code: str
    vendor_name: str
    older: Decimal
    amounts: list[Decimal]
    later: Decimal
    credits: Decimal
    total: Decimal
    counts: list[int]
    documents: int


@dataclass
class PayablesBooksCheck:
    """The report's total against the payables account."""

    ledger_balance: Decimal | None
    difference: Decimal | None
    note: str | None = None


@dataclass
class PayablesReport:
    """The whole report: months, supplier rows, total, books check."""

    as_of: date
    basis: str
    view: str
    months: list[str]
    month_starts: list[date]
    rows: list[PayablesLine]
    total: PayablesLine
    books_check: PayablesBooksCheck


@dataclass
class _Acc:
    """One supplier's running figures while the report is built."""

    older: Decimal = ZERO
    later: Decimal = ZERO
    credits: Decimal = ZERO
    amounts: list[Decimal] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    documents: int = 0


def month_starts(as_of: date, months: int) -> list[date]:
    """Return the first day of each month shown, the as-of month last."""
    starts: list[date] = []
    year, month = as_of.year, as_of.month
    for _ in range(months):
        starts.append(date(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(starts))


def _month_after(day: date) -> date:
    """Return the first day of the month after ``day``'s."""
    return (
        date(day.year + 1, 1, 1)
        if day.month == 12
        else date(day.year, day.month + 1, 1)
    )


def _day_after(as_of: date) -> datetime:
    """Return the first instant after ``as_of`` in UTC."""
    return datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=UTC)


def _money(value: object) -> Decimal:
    """Read a database figure as money at the ledger's two decimals."""
    return quantize_ledger(Decimal(str(value or 0)))


class PayablesReportService:
    """Build the payables report for one firm."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def report(
        self,
        firm_id: UUID,
        *,
        as_of: date,
        basis: Basis = "invoice",
        months: int = 6,
        vendor_id: UUID | None = None,
        branch_id: UUID | None = None,
        view: View = "owed",
    ) -> PayablesReport:
        """Return what each supplier is owed (or was paid) by month.

        Raises:
            ValidationError: For a month count out of range, or a branch on
                the Paid view (a payment names no branch).

        """
        if not 1 <= months <= MAX_MONTHS:
            raise ValidationError(f"months must be between 1 and {MAX_MONTHS}.")
        starts = month_starts(as_of, months)
        if view == "paid":
            if branch_id is not None:
                raise ValidationError(
                    "A payment names no branch, so the Paid view cannot be "
                    "narrowed to one. Clear the branch filter."
                )
            figures = self._paid(firm_id, as_of, starts, vendor_id)
            ledger = self._ledger_payments(firm_id, as_of, starts[0], vendor_id)
        else:
            figures = self._owed(firm_id, as_of, starts, basis, vendor_id, branch_id)
            ledger = (
                None
                if branch_id is not None
                else self._ledger_balance(firm_id, as_of, vendor_id)
            )
        return self._assemble(
            firm_id,
            figures,
            as_of=as_of,
            basis=basis,
            view=view,
            starts=starts,
            ledger=ledger,
            branch_filtered=branch_id is not None,
        )

    # ------------------------------------------------------------------
    # Owed
    # ------------------------------------------------------------------

    def _owed(
        self,
        firm_id: UUID,
        as_of: date,
        starts: list[date],
        basis: Basis,
        vendor_id: UUID | None,
        branch_id: UUID | None,
    ) -> dict[UUID, _Acc]:
        """Put each open bill in its month and each credit in Credits."""
        width = len(starts)
        end = _month_after(starts[-1])
        figures: dict[UUID, _Acc] = {}

        def acc(vendor: UUID) -> _Acc:
            if vendor not in figures:
                figures[vendor] = _Acc(amounts=[ZERO] * width, counts=[0] * width)
            return figures[vendor]

        for row in self._session.execute(
            self._bills_statement(firm_id, as_of, vendor_id, branch_id)
        ).all():
            owed = (
                _money(row.total)
                - _money(row.allocated)
                - _money(row.returned)
                - _money(row.debited)
                - _money(row.adjusted)
                - _money(row.applied)
            )
            if abs(owed) <= NOISE:
                continue
            figures_for = acc(row.vendor_id)
            if owed < ZERO:
                # More came off the bill than it was for: the supplier's to
                # give back (D-BUY-20, A4), so it is credit, not a bill.
                figures_for.credits += owed
                continue
            on = row.bill_date if basis == "invoice" else row.due_date or row.bill_date
            figures_for.documents += 1
            if on < starts[0]:
                figures_for.older += owed
            elif on >= end:
                figures_for.later += owed
            else:
                index = sum(1 for start in starts[1:] if on >= start)
                figures_for.amounts[index] += owed
                figures_for.counts[index] += 1
        for vendor, amount in self._unbilled_returns(
            firm_id, as_of, vendor_id, branch_id
        ).items():
            acc(vendor).credits -= amount
        for vendor, amount in self._credit_applied(
            firm_id, as_of, vendor_id, branch_id
        ).items():
            acc(vendor).credits += amount
        if branch_id is None:
            for vendor, amount in self._advances(firm_id, as_of, vendor_id).items():
                acc(vendor).credits -= amount
            for vendor, amount in self._refunds(firm_id, as_of, vendor_id).items():
                acc(vendor).credits += amount
        return figures

    def _bills_statement(
        self,
        firm_id: UUID,
        as_of: date,
        vendor_id: UUID | None,
        branch_id: UUID | None,
    ) -> Select[Any]:
        """Select every bill with each thing that came off it, in one statement.

        Purchase bills and the bills brought over from the old books are one
        list -- both are owed in payables -- and each reduction is grouped by
        bill in its own subquery, so the bills that still owe nothing are
        dropped in SQL.
        """
        day_after = _day_after(as_of)
        bills_part = select(
            PurchaseInvoice.id.label("bill_id"),
            PurchaseInvoice.vendor_id.label("vendor_id"),
            PurchaseInvoice.invoice_date.label("bill_date"),
            PurchaseInvoice.due_date.label("due_date"),
            # TDS deducted on the bill went to TDS Payable, not the supplier
            # (PG-5), so the bill is owed that less; TCS the supplier charged
            # (PG-6) is owed on top.
            # A bill in another currency is owed in rupees at its own rate
            # (PG-12).
            (
                func.coalesce(
                    PurchaseInvoice.base_grand_total, PurchaseInvoice.grand_total
                )
                + PurchaseInvoice.tcs_amount
                - PurchaseInvoice.tds_amount
            ).label("total"),
        ).where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(OWING_STATES),
            PurchaseInvoice.invoice_date <= as_of,
            *(() if vendor_id is None else (PurchaseInvoice.vendor_id == vendor_id,)),
            *(() if branch_id is None else (PurchaseInvoice.branch_id == branch_id,)),
        )
        parts: list[Any] = [bills_part]
        if branch_id is None:
            # A bill from the old books names no branch.
            parts.append(
                select(
                    VendorOpeningBill.id.label("bill_id"),
                    VendorOpeningBill.vendor_id.label("vendor_id"),
                    VendorOpeningBill.bill_date.label("bill_date"),
                    VendorOpeningBill.due_date.label("due_date"),
                    VendorOpeningBill.amount.label("total"),
                ).where(
                    VendorOpeningBill.firm_id == firm_id,
                    VendorOpeningBill.is_deleted.is_(False),
                    VendorOpeningBill.status == VendorOpeningBillStatus.POSTED.value,
                    VendorOpeningBill.posting_date <= as_of,
                    *(
                        ()
                        if vendor_id is None
                        else (VendorOpeningBill.vendor_id == vendor_id,)
                    ),
                )
            )
        bills = (union_all(*parts) if len(parts) > 1 else parts[0]).subquery("bills")

        allocation_bill = func.coalesce(
            SettlementAllocation.purchase_invoice_id,
            SettlementAllocation.vendor_opening_bill_id,
        )
        # What came off a bill in another currency is its rupee value at the
        # bill's rate (PG-12); the rest of the rupees paid was an exchange
        # gain or loss, never the supplier's.
        allocated = (
            select(
                allocation_bill.label("bill_id"),
                func.sum(
                    func.coalesce(
                        SettlementAllocation.base_amount, SettlementAllocation.amount
                    )
                ).label("amount"),
            )
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .where(
                SettlementAllocation.firm_id == firm_id,
                SettlementAllocation.is_deleted.is_(False),
                allocation_bill.is_not(None),
                Settlement.is_deleted.is_(False),
                _settlement_stood(day_after),
                func.coalesce(
                    SettlementAllocation.allocated_on, Settlement.settlement_date
                )
                <= as_of,
            )
            .group_by(allocation_bill)
            .subquery("allocated")
        )
        # A return or a debit note against a bill in another currency came
        # off it in rupees at the bill's own rate (D-BUY-41).
        returned_bill = aliased(PurchaseInvoice)
        returned_rupees = rupee_rate_sql(
            returned_bill.currency_code, returned_bill.exchange_rate
        )
        per_return = (
            select(
                PurchaseReturnLine.source_document_id.label("bill_id"),
                func.round(
                    func.sum(PurchaseReturnLine.net_amount * returned_rupees), 2
                ).label("amount"),
            )
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .join(
                returned_bill,
                returned_bill.id == PurchaseReturnLine.source_document_id,
            )
            .where(
                PurchaseReturnLine.firm_id == firm_id,
                PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(CREDITING_RETURN_STATES),
                PurchaseReturn.return_date <= as_of,
            )
            .group_by(
                PurchaseReturnLine.purchase_return_id,
                PurchaseReturnLine.source_document_id,
            )
            .subquery("per_return")
        )
        returned = (
            select(
                per_return.c.bill_id.label("bill_id"),
                func.sum(per_return.c.amount).label("amount"),
            )
            .group_by(per_return.c.bill_id)
            .subquery("returned")
        )
        debited = (
            select(
                DebitNote.purchase_invoice_id.label("bill_id"),
                func.sum(
                    func.round(DebitNote.taxable_amount * returned_rupees, 2)
                    + func.round(DebitNote.tax_amount * returned_rupees, 2)
                ).label("amount"),
            )
            .join(returned_bill, returned_bill.id == DebitNote.purchase_invoice_id)
            .where(
                DebitNote.firm_id == firm_id,
                DebitNote.is_deleted.is_(False),
                DebitNote.status == "APPROVED",
                DebitNote.debit_note_date <= as_of,
            )
            .group_by(DebitNote.purchase_invoice_id)
            .subquery("debited")
        )
        adjustment_bill = func.coalesce(
            PartyAdjustmentAllocation.purchase_invoice_id,
            PartyAdjustmentAllocation.vendor_opening_bill_id,
        )
        adjusted = (
            select(
                adjustment_bill.label("bill_id"),
                func.sum(PartyAdjustmentAllocation.amount).label("amount"),
            )
            .join(
                PartyAdjustment,
                PartyAdjustment.id == PartyAdjustmentAllocation.party_adjustment_id,
            )
            .where(
                PartyAdjustmentAllocation.firm_id == firm_id,
                PartyAdjustmentAllocation.is_deleted.is_(False),
                adjustment_bill.is_not(None),
                PartyAdjustment.is_deleted.is_(False),
                PartyAdjustment.adjustment_date <= as_of,
                or_(
                    PartyAdjustment.status == PartyAdjustmentStatus.APPROVED.value,
                    and_(
                        PartyAdjustment.status == PartyAdjustmentStatus.CANCELLED.value,
                        PartyAdjustment.approved_at.is_not(None),
                        PartyAdjustment.cancelled_at >= day_after,
                    ),
                ),
            )
            .group_by(adjustment_bill)
            .subquery("adjusted")
        )
        application_bill = func.coalesce(
            SupplierCreditApplication.purchase_invoice_id,
            SupplierCreditApplication.vendor_opening_bill_id,
        )
        applied = (
            select(
                application_bill.label("bill_id"),
                func.sum(SupplierCreditApplication.amount).label("amount"),
            )
            .where(
                SupplierCreditApplication.firm_id == firm_id,
                SupplierCreditApplication.is_deleted.is_(False),
                application_bill.is_not(None),
                SupplierCreditApplication.applied_on <= as_of,
            )
            .group_by(application_bill)
            .subquery("applied")
        )
        reductions = (allocated, returned, debited, adjusted, applied)
        left = bills.c.total - sum(
            (func.coalesce(part.c.amount, 0) for part in reductions), literal(0)
        )
        statement = select(
            bills.c.bill_id,
            bills.c.vendor_id,
            bills.c.bill_date,
            bills.c.due_date,
            bills.c.total,
            allocated.c.amount.label("allocated"),
            returned.c.amount.label("returned"),
            debited.c.amount.label("debited"),
            adjusted.c.amount.label("adjusted"),
            applied.c.amount.label("applied"),
        )
        for part in reductions:
            statement = statement.outerjoin(part, part.c.bill_id == bills.c.bill_id)
        # Coarse in SQL (SQLite sums in floating point), exact in Python.
        return statement.where(func.abs(left) > 0.001)

    def _unbilled_returns(
        self,
        firm_id: UUID,
        as_of: date,
        vendor_id: UUID | None,
        branch_id: UUID | None,
    ) -> dict[UUID, Decimal]:
        """Sum what returns debited payables with beyond their bills' lines.

        What a return's posting debited (`return_billed_amounts`, D-BUY-26)
        less its bill-sourced lines, each rounded per bill as the bill counts
        them, so the two parts add up to the journal exactly.
        """
        from app.purchase_return.services.purchase_return_service import (
            return_billed_amounts,
        )

        returns = self._session.scalars(
            select(PurchaseReturn).where(
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(CREDITING_RETURN_STATES),
                PurchaseReturn.return_date <= as_of,
                *(
                    ()
                    if vendor_id is None
                    else (PurchaseReturn.vendor_id == vendor_id,)
                ),
                *(
                    ()
                    if branch_id is None
                    else (PurchaseReturn.branch_id == branch_id,)
                ),
            )
        ).all()
        if not returns:
            return {}
        posted = return_billed_amounts(self._session, returns)
        on_bills: dict[UUID, Decimal] = {}
        for return_id, _bill, amount in self._session.execute(
            select(
                PurchaseReturnLine.purchase_return_id,
                PurchaseReturnLine.source_document_id,
                func.sum(
                    PurchaseReturnLine.net_amount
                    * rupee_rate_sql(
                        PurchaseInvoice.currency_code, PurchaseInvoice.exchange_rate
                    )
                ),
            )
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseReturnLine.source_document_id,
            )
            .where(
                PurchaseReturnLine.firm_id == firm_id,
                PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(CREDITING_RETURN_STATES),
                PurchaseReturn.return_date <= as_of,
                *(
                    ()
                    if vendor_id is None
                    else (PurchaseReturn.vendor_id == vendor_id,)
                ),
            )
            .group_by(
                PurchaseReturnLine.purchase_return_id,
                PurchaseReturnLine.source_document_id,
            )
        ).all():
            on_bills[return_id] = on_bills.get(return_id, ZERO) + _money(amount)
        credit: dict[UUID, Decimal] = {}
        for row in returns:
            # What the posting debited payables with, at the ledger's scale.
            amount = _money(posted[row.id][0]) - on_bills.get(row.id, ZERO)
            if amount != ZERO:
                credit[row.vendor_id] = credit.get(row.vendor_id, ZERO) + amount
        return credit

    def _credit_applied(
        self,
        firm_id: UUID,
        as_of: date,
        vendor_id: UUID | None,
        branch_id: UUID | None,
    ) -> dict[UUID, Decimal]:
        """Sum the supplier credit set against bills, which is credit used."""
        statement = select(
            SupplierCreditApplication.vendor_id,
            func.sum(SupplierCreditApplication.amount),
        ).where(
            SupplierCreditApplication.firm_id == firm_id,
            SupplierCreditApplication.is_deleted.is_(False),
            SupplierCreditApplication.applied_on <= as_of,
            *(
                ()
                if vendor_id is None
                else (SupplierCreditApplication.vendor_id == vendor_id,)
            ),
        )
        if branch_id is not None:
            # Used against this branch's bills, which is where it shows.
            statement = statement.join(
                PurchaseInvoice,
                PurchaseInvoice.id == SupplierCreditApplication.purchase_invoice_id,
            ).where(PurchaseInvoice.branch_id == branch_id)
        return {
            vendor: _money(amount)
            for vendor, amount in self._session.execute(
                statement.group_by(SupplierCreditApplication.vendor_id)
            ).all()
        }

    def _advances(
        self, firm_id: UUID, as_of: date, vendor_id: UUID | None
    ) -> dict[UUID, Decimal]:
        """Sum the money paid to each supplier and not allocated to a bill."""
        day_after = _day_after(as_of)
        allocated = (
            select(
                SettlementAllocation.settlement_id.label("settlement_id"),
                func.sum(SettlementAllocation.amount).label("amount"),
            )
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .where(
                SettlementAllocation.firm_id == firm_id,
                SettlementAllocation.is_deleted.is_(False),
                func.coalesce(
                    SettlementAllocation.allocated_on, Settlement.settlement_date
                )
                <= as_of,
            )
            .group_by(SettlementAllocation.settlement_id)
            .subquery("allocated")
        )
        advances: dict[UUID, Decimal] = {}
        for vendor, paid, allocated_amount in self._session.execute(
            select(
                Settlement.vendor_id,
                func.sum(Settlement.amount),
                func.sum(func.coalesce(allocated.c.amount, 0)),
            )
            .outerjoin(allocated, allocated.c.settlement_id == Settlement.id)
            .where(
                Settlement.firm_id == firm_id,
                Settlement.direction == SettlementDirection.PAYMENT.value,
                Settlement.is_deleted.is_(False),
                Settlement.settlement_date <= as_of,
                _settlement_stood(day_after),
                *(() if vendor_id is None else (Settlement.vendor_id == vendor_id,)),
            )
            .group_by(Settlement.vendor_id)
        ).all():
            amount = _money(paid) - _money(allocated_amount)
            if vendor is not None and amount != ZERO:
                advances[vendor] = amount
        return advances

    def _refunds(
        self, firm_id: UUID, as_of: date, vendor_id: UUID | None
    ) -> dict[UUID, Decimal]:
        """Sum what suppliers paid back against their credit (Cr payable)."""
        day_after = _day_after(as_of)
        return {
            vendor: _money(amount)
            for vendor, amount in self._session.execute(
                select(
                    SupplierCreditRefund.vendor_id,
                    func.sum(SupplierCreditRefund.amount),
                )
                .where(
                    SupplierCreditRefund.firm_id == firm_id,
                    SupplierCreditRefund.is_deleted.is_(False),
                    SupplierCreditRefund.refunded_on <= as_of,
                    or_(
                        SupplierCreditRefund.status == "POSTED",
                        and_(
                            SupplierCreditRefund.status == "REVERSED",
                            SupplierCreditRefund.reversed_at >= day_after,
                        ),
                    ),
                    *(
                        ()
                        if vendor_id is None
                        else (SupplierCreditRefund.vendor_id == vendor_id,)
                    ),
                )
                .group_by(SupplierCreditRefund.vendor_id)
            ).all()
        }

    # ------------------------------------------------------------------
    # Paid
    # ------------------------------------------------------------------

    def _paid(
        self,
        firm_id: UUID,
        as_of: date,
        starts: list[date],
        vendor_id: UUID | None,
    ) -> dict[UUID, _Acc]:
        """Sum the payments to each supplier in each month of the window."""
        width = len(starts)
        bucket = case(
            *(
                (Settlement.settlement_date < start, index)
                for index, start in enumerate(starts[1:])
            ),
            else_=width - 1,
        )
        # A payment in another currency took the bills' rupee value off the
        # payable, not the rupees it cost (PG-12); the rest was an exchange
        # gain or loss, so it is counted at what it cleared.
        cleared = (
            select(func.coalesce(func.sum(SettlementAllocation.base_amount), 0))
            .where(
                SettlementAllocation.settlement_id == Settlement.id,
                SettlementAllocation.is_deleted.is_(False),
            )
            .scalar_subquery()
        )
        paid = case(
            (Settlement.currency_code.is_(None), Settlement.amount), else_=cleared
        )
        figures: dict[UUID, _Acc] = {}
        for vendor, index, amount, count in self._session.execute(
            select(
                Settlement.vendor_id,
                bucket,
                func.sum(paid),
                func.count(Settlement.id),
            )
            .where(
                Settlement.firm_id == firm_id,
                Settlement.direction == SettlementDirection.PAYMENT.value,
                Settlement.is_deleted.is_(False),
                Settlement.settlement_date >= starts[0],
                Settlement.settlement_date <= as_of,
                _settlement_stood(_day_after(as_of)),
                *(() if vendor_id is None else (Settlement.vendor_id == vendor_id,)),
            )
            .group_by(Settlement.vendor_id, bucket)
        ).all():
            if vendor is None:  # pragma: no cover - a payment names its supplier
                continue
            row = figures.setdefault(
                vendor, _Acc(amounts=[ZERO] * width, counts=[0] * width)
            )
            row.amounts[int(index)] += _money(amount)
            row.counts[int(index)] += int(count)
            row.documents += int(count)
        return figures

    # ------------------------------------------------------------------
    # The books
    # ------------------------------------------------------------------

    def _payables_account(self, firm_id: UUID) -> UUID | None:
        """Return the account the firm's payables post to, if it has one."""
        return (
            ControlAccountService(self._session)
            .mapping(firm_id)
            .get(ControlAccountPurpose.ACCOUNTS_PAYABLE.value)
        )

    def _ledger_balance(
        self, firm_id: UUID, as_of: date, vendor_id: UUID | None
    ) -> Decimal | None:
        """Read the payables balance at the end of ``as_of`` from the journal.

        For one supplier, the payables lines its documents posted -- the
        supplier statement's own reading, so the two cannot disagree.
        """
        account_id = self._payables_account(firm_id)
        if account_id is None:
            return None
        if vendor_id is not None:
            from app.vendors.services.statement_service import (
                SupplierStatementService,
            )

            movements = (
                SupplierStatementService(self._session)
                ._movements(firm_id, account_id, vendor_id)
                .subquery()
            )
            total = self._session.scalar(
                select(
                    func.coalesce(func.sum(movements.c.credit - movements.c.debit), 0)
                ).where(movements.c.journal_date <= as_of)
            )
            return _money(total)
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(JournalLine.credit_amount - JournalLine.debit_amount), 0
                )
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalLine.ledger_account_id == account_id,
                JournalLine.is_deleted.is_(False),
                JournalEntry.firm_id == firm_id,
                JournalEntry.is_deleted.is_(False),
                JournalEntry.status.in_(COUNTED_JOURNALS),
                JournalEntry.journal_date <= as_of,
            )
        )
        return _money(total)

    def _ledger_payments(
        self, firm_id: UUID, as_of: date, start: date, vendor_id: UUID | None
    ) -> Decimal | None:
        """Read what payments debited payables with in the window."""
        account_id = self._payables_account(firm_id)
        if account_id is None:
            return None
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(JournalLine.debit_amount - JournalLine.credit_amount), 0
                )
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .join(
                Settlement,
                and_(
                    Settlement.id == JournalEntry.source_id,
                    JournalEntry.source_module == "settlements",
                ),
            )
            .where(
                JournalLine.ledger_account_id == account_id,
                JournalLine.is_deleted.is_(False),
                JournalEntry.firm_id == firm_id,
                JournalEntry.is_deleted.is_(False),
                JournalEntry.status.in_(COUNTED_JOURNALS),
                JournalEntry.journal_date >= start,
                JournalEntry.journal_date <= as_of,
                Settlement.direction == SettlementDirection.PAYMENT.value,
                *(() if vendor_id is None else (Settlement.vendor_id == vendor_id,)),
            )
        )
        return _money(total)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _assemble(
        self,
        firm_id: UUID,
        figures: dict[UUID, _Acc],
        *,
        as_of: date,
        basis: str,
        view: str,
        starts: list[date],
        ledger: Decimal | None,
        branch_filtered: bool,
    ) -> PayablesReport:
        """Name the suppliers, add the total row and check it against the books."""
        width = len(starts)
        kept = {
            vendor: acc
            for vendor, acc in figures.items()
            if acc.documents
            or acc.older
            or acc.later
            or acc.credits
            or any(acc.amounts)
        }
        names = _vendors(self._session, vendor_ids=list(kept))
        rows = [
            _line(vendor, names.get(vendor, ("", str(vendor))), acc)
            for vendor, acc in kept.items()
        ]
        rows.sort(key=lambda row: (-row.total, row.vendor_name))
        total_acc = _Acc(
            older=sum((row.older for row in rows), ZERO),
            later=sum((row.later for row in rows), ZERO),
            credits=sum((row.credits for row in rows), ZERO),
            amounts=[sum((row.amounts[i] for row in rows), ZERO) for i in range(width)],
            counts=[sum(row.counts[i] for row in rows) for i in range(width)],
            documents=sum(row.documents for row in rows),
        )
        total = _line(None, ("", "Total"), total_acc)
        note = None
        if branch_filtered:
            note = (
                "Narrowed to a branch: advances and refunds name no branch, "
                "so there is no books check."
            )
        elif ledger is None:
            note = "No payables account is mapped for this firm."
        return PayablesReport(
            as_of=as_of,
            basis=basis,
            view=view,
            months=[start.strftime("%Y-%m") for start in starts],
            month_starts=starts,
            rows=rows,
            total=total,
            books_check=PayablesBooksCheck(
                ledger_balance=ledger,
                difference=None if ledger is None else total.total - ledger,
                note=note,
            ),
        )


def _line(vendor_id: UUID | None, naming: tuple[str, str], acc: _Acc) -> PayablesLine:
    """Turn running figures into a row, its total summed from its cells."""
    return PayablesLine(
        vendor_id=vendor_id,
        vendor_code=naming[0],
        vendor_name=naming[1],
        older=acc.older,
        amounts=list(acc.amounts),
        later=acc.later,
        credits=acc.credits,
        total=acc.older + sum(acc.amounts, ZERO) + acc.later + acc.credits,
        counts=list(acc.counts),
        documents=acc.documents,
    )


def _settlement_stood(day_after: datetime) -> ColumnElement[bool]:
    """Say a settlement stood just before ``day_after``: posted, or reversed later."""
    return or_(
        Settlement.status == SettlementStatus.POSTED.value,
        and_(
            Settlement.status == SettlementStatus.REVERSED.value,
            Settlement.reversed_at >= day_after,
        ),
    )
