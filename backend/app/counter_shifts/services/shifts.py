"""Open a till, read what it took, and close it on a count (SG-7).

**What the drawer should hold is derived, never incremented.** Every figure
here -- the bills, the money by mode, the cash expected -- is summed in SQL
from the bills stamped with the shift and the receipts their tenders became,
on every read. A bill counts while it is approved or closed; a tender counts
while its receipt is still posted, so money handed back by reversing the
receipt (which cancelling a bill requires first) drops out by itself.

The statements are the same number whether the shift took two bills or two
thousand, and a page of shifts is read in the same few statements as one.

Nothing here hands cash back against a bill: the codebase has no counter
refund tied to a bill (a customer refund returns an advance and names no
bill), so expected cash is the float plus the cash tenders and nothing is
taken off.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader, firm_date_of
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import as_utc, utc_now
from app.core.utils.money import quantize_ledger
from app.counter_shifts.models import CounterShift, CounterShiftStatus
from app.counter_shifts.schemas import (
    CounterShiftClose,
    CounterShiftOpen,
    CounterShiftResponse,
    CounterShiftSummary,
)
from app.finance.models import LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceTender
from app.settlements.models import Settlement, SettlementStatus

ZERO = Decimal("0.00")
CASH = "CASH"
#: The modes a counter bill is paid by, in the order they are shown.
TENDER_MODES: tuple[str, ...] = ("CASH", "UPI", "CARD", "BANK_TRANSFER")
#: A bill with no tenders records one method, CASH or BANK. Money to the bank
#: with no mode named is shown as a bank transfer.
_METHOD_MODE = {"CASH": "CASH", "BANK": "BANK_TRANSFER"}
#: Bills whose money is in the drawer: a draft took none, a cancelled one
#: gave it back.
_COUNTED_STATES = ("APPROVED", "CLOSED")


@dataclass(slots=True)
class ShiftFigures:
    """What one shift took, summed from its bills and their receipts."""

    bills: int = 0
    total_billed: Decimal = ZERO
    tenders: dict[str, Decimal] = field(
        default_factory=lambda: dict.fromkeys(TENDER_MODES, ZERO)
    )
    held_bills: int = 0

    @property
    def cash(self) -> Decimal:
        """Return the cash the shift's bills put in the drawer."""
        return self.tenders[CASH]


def _money(value: Decimal | None) -> Decimal:
    """Read a summed column as two-decimal money."""
    return quantize_ledger(Decimal(str(value or 0)))


def utc_stamp(value: datetime | None) -> str:
    """Write a moment as its UTC day and minute, labelled as such.

    PostgreSQL hands a stored timestamp back in the session's zone, so
    printing its clock face under "UTC" said 19:12 UTC for a shift opened at
    13:42 UTC (D-SELL-67). Converted first; SQLite's naive value is UTC that
    lost its label (``as_utc``).
    """
    if value is None:
        return ""
    return as_utc(value).astimezone(UTC).strftime("%d-%m-%Y %H:%M UTC")


def open_shift_of(
    session: Session, firm_id: UUID, cashier_id: UUID, *, lock: bool = False
) -> CounterShift | None:
    """Return the cashier's open shift, if they have one.

    ``lock`` holds the row for the caller's transaction: a bill being stamped
    and the shift being closed then wait for each other, so no bill lands in
    a shift after its cash was counted.
    """
    statement = select(CounterShift).where(
        CounterShift.firm_id == firm_id,
        CounterShift.cashier_id == cashier_id,
        CounterShift.status == CounterShiftStatus.OPEN.value,
        CounterShift.is_deleted.is_(False),
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


class CounterShiftService:
    """Coordinate a cashier's shifts for one firm."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the caller's session."""
        self._session = session

    # ---- reading -----------------------------------------------------------

    def get(self, shift_id: UUID, *, firm_id: UUID) -> CounterShift:
        """Return one shift of the firm.

        Raises:
            ResourceNotFoundError: If the firm has no such shift.

        """
        row = self._session.scalar(
            select(CounterShift).where(
                CounterShift.id == shift_id,
                CounterShift.firm_id == firm_id,
                CounterShift.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Counter shift not found.")
        return row

    def current(self, *, firm_id: UUID, cashier_id: UUID) -> CounterShift | None:
        """Return the cashier's open shift, or None when the till is shut."""
        return open_shift_of(self._session, firm_id, cashier_id)

    def list_shifts(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        status: CounterShiftStatus | None = None,
        cashier_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[CounterShift], int]:
        """List the firm's shifts, the latest opened first.

        The dates are inclusive UTC calendar days of when a shift was opened.
        """
        conditions = [
            CounterShift.firm_id == firm_id,
            CounterShift.is_deleted.is_(False),
        ]
        if status is not None:
            conditions.append(CounterShift.status == status.value)
        if cashier_id is not None:
            conditions.append(CounterShift.cashier_id == cashier_id)
        if from_date is not None:
            conditions.append(
                CounterShift.opened_at
                >= datetime.combine(from_date, time.min, tzinfo=UTC)
            )
        if to_date is not None:
            conditions.append(
                CounterShift.opened_at
                <= datetime.combine(to_date, time.max, tzinfo=UTC)
            )
        rows = list(
            self._session.scalars(
                select(CounterShift)
                .where(*conditions)
                .order_by(CounterShift.opened_at.desc(), CounterShift.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self._session.scalar(
            select(func.count()).select_from(CounterShift).where(*conditions)
        )
        return rows, int(total or 0)

    def figures(self, shifts: Sequence[CounterShift]) -> dict[UUID, ShiftFigures]:
        """Sum what each shift took: four statements, however many bills.

        Args:
            shifts: The shifts to read; a page of them costs what one does.

        Returns:
            Every shift's figures by its id, zero where it took nothing.

        """
        result = {shift.id: ShiftFigures() for shift in shifts}
        if not shifts:
            return result
        ids = list(result)
        counted = (
            SalesInvoice.counter_shift_id.in_(ids),
            SalesInvoice.status.in_(_COUNTED_STATES),
            SalesInvoice.is_deleted.is_(False),
        )
        for shift_id, bills, billed in self._session.execute(
            select(
                SalesInvoice.counter_shift_id,
                func.count(),
                # Each bill at what its buyer is asked to pay, in whole
                # paise, and then summed: a bill of 97.1376 is paid with
                # 97.14 (D-SELL-83), and adding the unrounded totals put the
                # shift a paisa from its own tenders over many such bills.
                func.coalesce(func.sum(func.round(SalesInvoice.grand_total, 2)), 0),
            )
            .where(*counted)
            .group_by(SalesInvoice.counter_shift_id)
        ):
            result[shift_id].bills = int(bills)
            result[shift_id].total_billed = _money(billed)
        # Each tender through the receipt it became: one that was reversed
        # is money handed back, and is no longer in the drawer or the bank.
        for shift_id, mode, amount in self._session.execute(
            select(
                SalesInvoice.counter_shift_id,
                SalesInvoiceTender.mode,
                func.coalesce(func.sum(SalesInvoiceTender.amount), 0),
            )
            .join(
                SalesInvoiceTender,
                SalesInvoiceTender.sales_invoice_id == SalesInvoice.id,
            )
            .join(Settlement, Settlement.id == SalesInvoiceTender.settlement_id)
            .where(
                *counted,
                SalesInvoiceTender.is_deleted.is_(False),
                Settlement.status == SettlementStatus.POSTED.value,
            )
            .group_by(SalesInvoice.counter_shift_id, SalesInvoiceTender.mode)
        ):
            figures = result[shift_id]
            figures.tenders[mode] = figures.tenders.get(mode, ZERO) + _money(amount)
        # A bill paid one way, with no tenders listed, records its method on
        # itself. A bill with tenders is left to the statement above.
        has_tenders = exists().where(
            SalesInvoiceTender.sales_invoice_id == SalesInvoice.id,
            SalesInvoiceTender.is_deleted.is_(False),
        )
        for shift_id, method, amount in self._session.execute(
            select(
                SalesInvoice.counter_shift_id,
                SalesInvoice.received_now_method,
                func.coalesce(func.sum(SalesInvoice.received_now_amount), 0),
            )
            .join(Settlement, Settlement.id == SalesInvoice.received_now_settlement_id)
            .where(
                *counted,
                ~has_tenders,
                Settlement.status == SettlementStatus.POSTED.value,
            )
            .group_by(SalesInvoice.counter_shift_id, SalesInvoice.received_now_method)
        ):
            mode = _METHOD_MODE.get(method or CASH, "BANK_TRANSFER")
            figures = result[shift_id]
            figures.tenders[mode] = figures.tenders[mode] + _money(amount)
        # Bills the cashier parked during the shift and has not recalled.
        for shift_id, held in self._session.execute(
            select(CounterShift.id, func.count(SalesInvoice.id))
            .join(
                SalesInvoice,
                and_(
                    SalesInvoice.firm_id == CounterShift.firm_id,
                    SalesInvoice.created_by == CounterShift.cashier_id,
                    SalesInvoice.is_held.is_(True),
                    SalesInvoice.status == "DRAFT",
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.held_at >= CounterShift.opened_at,
                    or_(
                        CounterShift.closed_at.is_(None),
                        SalesInvoice.held_at <= CounterShift.closed_at,
                    ),
                ),
            )
            .where(CounterShift.id.in_(ids))
            .group_by(CounterShift.id)
        ):
            result[shift_id].held_bills = int(held)
        return result

    def expected_cash(self, shift: CounterShift, figures: ShiftFigures) -> Decimal:
        """Return what the drawer should hold: the float and the cash taken."""
        return quantize_ledger(Decimal(str(shift.opening_float)) + figures.cash)

    def responses(self, shifts: Sequence[CounterShift]) -> list[CounterShiftResponse]:
        """Render a page of shifts, reading the figures and the names once."""
        if not shifts:
            return []
        figures = self.figures(shifts)
        names = {
            member.user_id: member.full_name or member.email
            for member in FirmMetadataReader(self._session).active_members(
                shifts[0].firm_id
            )
        }
        return [self._response(shift, figures[shift.id], names) for shift in shifts]

    def response(self, shift: CounterShift) -> CounterShiftResponse:
        """Render one shift exactly as a list row renders it."""
        return self.responses([shift])[0]

    def _response(
        self,
        shift: CounterShift,
        figures: ShiftFigures,
        names: dict[UUID, str],
    ) -> CounterShiftResponse:
        """Build one shift's response from what the page already read."""
        closed = shift.status == CounterShiftStatus.CLOSED.value
        return CounterShiftResponse(
            id=shift.id,
            version=shift.version,
            firm_id=shift.firm_id,
            branch_id=shift.branch_id,
            cashier_id=shift.cashier_id,
            cashier_name=names.get(shift.cashier_id),
            cash_account_id=shift.cash_account_id,
            shift_number=shift.shift_number,
            status=CounterShiftStatus(shift.status),
            opened_at=as_utc(shift.opened_at),
            opening_float=shift.opening_float,
            # The snapshot once closed: what the count was judged against.
            expected_cash=(
                shift.expected_cash
                if closed and shift.expected_cash is not None
                else self.expected_cash(shift, figures)
            ),
            closed_at=None if shift.closed_at is None else as_utc(shift.closed_at),
            closed_by=shift.closed_by,
            closed_by_name=(
                None if shift.closed_by is None else names.get(shift.closed_by)
            ),
            counted_cash=shift.counted_cash,
            difference=shift.difference,
            difference_journal_entry_id=shift.difference_journal_entry_id,
            closing_note=shift.closing_note,
            summary=CounterShiftSummary(
                bills=figures.bills,
                total_billed=figures.total_billed,
                tenders=dict(figures.tenders),
                held_bills=figures.held_bills,
            ),
        )

    # ---- opening -----------------------------------------------------------

    def stage_open(
        self,
        data: CounterShiftOpen,
        *,
        firm_id: UUID,
        actor_id: UUID,
        now: datetime | None = None,
    ) -> CounterShift:
        """Open the caller's till without committing.

        Raises:
            ConflictError: If the cashier already has a shift open.
            ValidationError: If the branch or the cash account will not do.

        """
        already = open_shift_of(self._session, firm_id, actor_id)
        if already is not None:
            raise ConflictError(
                f"You already have {already.shift_number} open. Close it "
                "before opening another."
            )
        row = CounterShift(
            firm_id=firm_id,
            branch_id=self._branch(firm_id, data.branch_id),
            cashier_id=actor_id,
            cash_account_id=self._cash_account(firm_id, data.cash_account_id),
            shift_number=self._next_number(firm_id),
            opened_at=now or utc_now(),
            opening_float=quantize_ledger(data.opening_float),
            status=CounterShiftStatus.OPEN.value,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as error:
            # Two tills opened at once: the key lets one through.
            self._session.rollback()
            raise ConflictError(
                "A shift was opened for you a moment ago. Open the counter again."
            ) from error
        record_audit(
            self._session,
            action="counter_shift.opened",
            entity_type="counter_shift",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "shift_number": row.shift_number,
                "branch_id": str(row.branch_id),
                "cash_account_id": str(row.cash_account_id),
                "opening_float": str(row.opening_float),
            },
        )
        return row

    def open(
        self,
        data: CounterShiftOpen,
        *,
        firm_id: UUID,
        actor_id: UUID,
        now: datetime | None = None,
    ) -> CounterShift:
        """Open the caller's till; commit. See ``stage_open``."""
        row = self.stage_open(data, firm_id=firm_id, actor_id=actor_id, now=now)
        self._session.commit()
        return row

    # ---- closing -----------------------------------------------------------

    def stage_close(
        self,
        shift_id: UUID,
        data: CounterShiftClose,
        *,
        firm_id: UUID,
        actor_id: UUID,
        may_close_others: bool = False,
        now: datetime | None = None,
    ) -> CounterShift:
        """Close a shift on what was counted, without committing.

        The expected cash is snapshotted, the difference worked out and, when
        there is one, posted as a single journal to *Cash short and over*.
        The row is locked first, so a bill being approved by this cashier
        either lands before the count or waits and finds no open shift.

        Args:
            shift_id: The shift to close.
            data: What was counted, and a note.
            firm_id: The owning firm.
            actor_id: Who is closing it.
            may_close_others: Whether the caller may close a till that is not
                their own -- the router passes whether they may approve sales.
            now: The moment of the close; the clock when omitted.

        Raises:
            AuthorizationError: If it is somebody else's till and the caller
                may not close those.
            ValidationError: If the shift is not open, or a difference cannot
                be posted (no account mapped, no open period).

        """
        row = self._session.scalar(
            select(CounterShift)
            .where(
                CounterShift.id == shift_id,
                CounterShift.firm_id == firm_id,
                CounterShift.is_deleted.is_(False),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError("Counter shift not found.")
        if row.cashier_id != actor_id and not may_close_others:
            raise AuthorizationError(
                "Only the cashier who opened this shift, or somebody who may "
                "approve sales, can close it."
            )
        if row.status != CounterShiftStatus.OPEN.value:
            raise ValidationError(f"{row.shift_number} is already closed.")
        moment = now or utc_now()
        figures = self.figures([row])[row.id]
        expected = self.expected_cash(row, figures)
        counted = quantize_ledger(data.counted_cash)
        difference = quantize_ledger(counted - expected)
        entry = DocumentPostingService(self._session).post_cash_short_and_over(
            firm_id=firm_id,
            shift_id=row.id,
            shift_number=row.shift_number,
            closed_on=firm_date_of(self._session, firm_id, moment),
            cash_account_id=row.cash_account_id,
            difference=difference,
            actor_id=actor_id,
        )
        row.status = CounterShiftStatus.CLOSED.value
        row.closed_at = moment
        row.closed_by = actor_id
        row.counted_cash = counted
        row.expected_cash = expected
        row.difference = difference
        row.difference_journal_entry_id = None if entry is None else entry.id
        row.closing_note = data.note
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="counter_shift.closed",
            entity_type="counter_shift",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "shift_number": row.shift_number,
                "expected_cash": str(expected),
                "counted_cash": str(counted),
                "difference": str(difference),
                "journal_entry_id": None if entry is None else str(entry.id),
                "bills": figures.bills,
                "held_bills": figures.held_bills,
                "note": data.note,
            },
        )
        return row

    def close(
        self,
        shift_id: UUID,
        data: CounterShiftClose,
        *,
        firm_id: UUID,
        actor_id: UUID,
        may_close_others: bool = False,
        now: datetime | None = None,
    ) -> CounterShift:
        """Close a shift on what was counted; commit. See ``stage_close``."""
        row = self.stage_close(
            shift_id,
            data,
            firm_id=firm_id,
            actor_id=actor_id,
            may_close_others=may_close_others,
            now=now,
        )
        self._session.commit()
        return row

    # ---- the shift report --------------------------------------------------

    _styles = getSampleStyleSheet()

    def report_pdf(self, shift_id: UUID, *, firm_id: UUID) -> bytes:
        """Return the shift report as an A4 PDF: what it took and the count."""
        shift = self.get(shift_id, firm_id=firm_id)
        view = self.response(shift)
        firm = FirmMetadataReader(self._session).get(firm_id)
        account = self._session.get(LedgerAccount, shift.cash_account_id)

        def money(value: Decimal | None) -> str:
            """Write an amount the way the report prints it."""
            return "" if value is None else f"{value:,.2f}"

        stamp = utc_stamp

        details = [
            ["Shift", view.shift_number],
            ["Cashier", view.cashier_name or ""],
            ["Cash account", "" if account is None else account.name],
            ["Opened", stamp(view.opened_at)],
            ["Closed", stamp(view.closed_at) or "Still open"],
        ]
        takings: list[list[str]] = [
            ["Bills", str(view.summary.bills)],
            ["Total billed", money(view.summary.total_billed)],
        ]
        takings += [
            [f"Received by {mode.replace('_', ' ').lower()}", money(amount)]
            for mode, amount in view.summary.tenders.items()
        ]
        drawer = [
            ["Opening float", money(view.opening_float)],
            ["Cash received", money(view.summary.tenders.get(CASH, ZERO))],
            ["Cash expected", money(view.expected_cash)],
            ["Cash counted", money(view.counted_cash)],
            ["Difference (short is negative)", money(view.difference)],
        ]
        if view.summary.held_bills:
            drawer.append(["Bills still held", str(view.summary.held_bills)])
        parts: list[object] = [
            Paragraph(firm.name or "", self._styles["Title"]),
            Paragraph(
                f"Shift report -- {view.shift_number} -- printed "
                f"{utc_now().date().strftime('%d-%m-%Y')}",
                self._styles["Normal"],
            ),
            Spacer(1, 4 * mm),
        ]
        for heading, rows in (
            ("Shift", details),
            ("Takings", takings),
            ("Cash drawer", drawer),
        ):
            parts.append(Paragraph(heading, self._styles["Heading3"]))
            parts.append(self._table(rows))
            parts.append(Spacer(1, 4 * mm))
        if view.closing_note:
            parts.append(
                Paragraph(f"Note: {view.closing_note}", self._styles["BodyText"])
            )
        parts.append(Spacer(1, 16 * mm))
        parts.append(
            Paragraph(
                "Cashier: ____________________"
                "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                "Checked by: ____________________",
                self._styles["Normal"],
            )
        )
        buffer = BytesIO()
        SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=f"Shift report {view.shift_number}",
        ).build(parts)
        return buffer.getvalue()

    @staticmethod
    def _table(rows: list[list[str]]) -> Table:
        """Return a ruled two-column table, the figures right-aligned."""
        table = Table(rows, colWidths=[90 * mm, 60 * mm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ]
            )
        )
        return table

    # ---- helpers -----------------------------------------------------------

    def _branch(self, firm_id: UUID, branch_id: UUID | None) -> UUID:
        """Return the branch the till is in: the one named, else the default."""
        conditions = [Branch.firm_id == firm_id, Branch.is_deleted.is_(False)]
        if branch_id is not None:
            conditions.append(Branch.id == branch_id)
        else:
            conditions.append(Branch.is_default.is_(True))
        found = self._session.scalar(select(Branch.id).where(*conditions))
        if found is None:
            raise ValidationError(
                "Branch not found."
                if branch_id is not None
                else "This firm has no default branch: name the branch the "
                "counter is in."
            )
        return found

    def _cash_account(self, firm_id: UUID, account_id: UUID | None) -> UUID:
        """Return the cash account the till is booked to.

        The firm's cash control account unless another is named, and one
        that is named must be an active asset account of the firm.
        """
        if account_id is None:
            return ControlAccountService(self._session).resolve(
                firm_id, ControlAccountPurpose.CASH
            )
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ValidationError("Cash account not found.")
        if account.account_type != "ASSET" or not account.is_active:
            raise ValidationError(
                f"{account.name} cannot hold a till's cash: choose an active "
                "cash account."
            )
        return account.id

    def _next_number(self, firm_id: UUID) -> str:
        """Return the firm's next shift number, ``SHIFT-000123``.

        Counted from the shifts the firm has, deleted ones included, and
        stepped past any number already taken. Two opened at once are settled
        by ``UQ_counter_shifts_number``.
        """
        taken = int(
            self._session.scalar(
                select(func.count())
                .select_from(CounterShift)
                .where(CounterShift.firm_id == firm_id)
            )
            or 0
        )
        while True:
            taken += 1
            number = f"SHIFT-{taken:06d}"
            clash = self._session.scalar(
                select(CounterShift.id).where(
                    CounterShift.firm_id == firm_id,
                    CounterShift.shift_number == number,
                )
            )
            if clash is None:
                return number


__all__ = [
    "TENDER_MODES",
    "CounterShiftService",
    "ShiftFigures",
    "open_shift_of",
]
