"""Bills handed to a collector, and taken back (backlog 122, row M4).

The office hands out a bundle of unpaid bills -- the ones ticked, or every
one of a day, an area, a customer or a run of bill numbers -- and takes back
what comes home.

**Nothing here touches the books.** A handover writes one row in
``bill_handovers`` and an audit record. It posts no journal, moves no
customer balance and is read by no report: what a bill owes is Record
Receipt's own list (``ReceiptService.outstanding_invoices``), the same before
a bill goes out, while it is out and after it is back.

**Only a bill that still owes something is handed out**, a sales invoice or a
bill owed from before the firm started here. A bill paid while it is out
stays out until somebody takes it back: the paper is still in the bag.

**A bill is out with one person at a time.** Ticking a bill somebody already
carries is refused by name; a matched bundle leaves such bills where they are
and says how many. The partial unique indexes are what settle two people
handing out the same bill at once.
"""

import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collections.models import BillHandover
from app.collections.schemas import (
    HandedFilter,
    HandoverBillRow,
    HandoverCreate,
    HandoverMatching,
    HandoverResponse,
    HandoverResult,
    HandoverState,
    HandoverTakeBack,
)
from app.collections.services.promises import FORMER_MEMBER, member_names
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader, firm_today
from app.common.party_places import customer_places
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import Customer, CustomerOpeningBill
from app.customers.services.opening_bill_service import opening_bill_label
from app.sales_invoice.models import SalesInvoice
from app.settlements.schemas import OutstandingInvoiceRecord
from app.settlements.services import ReceiptService

_CENT = Decimal("0.01")
#: A bill number as a series and a running number: "INV-", 42.
_NUMBER = re.compile(r"^(.*?)(\d+)$")
#: How many bill numbers a refusal names before it says "and N more".
_NAMED = 5


def _money(value: object) -> Decimal:
    """Read a figure to two places; NULL is nothing."""
    return Decimal(str(value or 0)).quantize(_CENT)


def _series(number: str) -> tuple[str, int] | None:
    """Split a bill number into its series and its running number."""
    match = _NUMBER.match(number.strip())
    if match is None:
        return None
    return match.group(1).casefold(), int(match.group(2))


def _run(matching: HandoverMatching) -> tuple[str, int | None, int | None] | None:
    """Read the run of bill numbers asked for: its series and its two ends.

    Raises:
        ValidationError: If an end does not finish in digits, the two are of
            different series, or the run ends before it starts.

    """
    ends = [
        None if text is None else _series(text)
        for text in (matching.number_from, matching.number_to)
    ]
    if matching.number_from is None and matching.number_to is None:
        return None
    if (matching.number_from is not None and ends[0] is None) or (
        matching.number_to is not None and ends[1] is None
    ):
        raise ValidationError("A bill number in a run must end in digits.")
    first, last = ends
    if first is not None and last is not None:
        if first[0] != last[0]:
            raise ValidationError(
                "The two bill numbers are of different series; a run stays "
                "inside one."
            )
        if last[1] < first[1]:
            raise ValidationError("The last bill number is before the first.")
    named = first or last
    # One of the two is set, or the function returned above.
    assert named is not None
    return (
        named[0],
        None if first is None else first[1],
        None if last is None else last[1],
    )


def _names(numbers: list[str]) -> str:
    """List a few bill numbers, and count the rest."""
    shown = ", ".join(numbers[:_NAMED])
    more = len(numbers) - _NAMED
    return shown if more <= 0 else f"{shown} and {more} more"


class BillHandoverService:
    """Hand a firm's unpaid bills to its collectors and take them back."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's session."""
        self._session = session

    # ---- reads -------------------------------------------------------------

    def bills(
        self,
        firm_id: UUID,
        *,
        handed: HandedFilter = HandedFilter.ALL,
        collector_id: UUID | None = None,
        matching: HandoverMatching | None = None,
        today: date | None = None,
    ) -> list[HandoverBillRow]:
        """Return the firm's unpaid bills, each with who carries it.

        Oldest bill first. The bills, the customers, their places, the live
        handovers and the members are each read once, whatever the length.

        Args:
            firm_id: The firm whose bills to list.
            handed: All of them, only those out, or only those in the office.
            collector_id: Only bills out with this person.
            matching: Only bills of this day, area, customer or run.
            today: The day the overdue count is for; the firm's own today
                when omitted.

        Raises:
            ValidationError: If the run of bill numbers cannot be read.

        """
        on = today or firm_today(self._session, firm_id)
        run = _run(matching) if matching else None
        records = ReceiptService(self._session).outstanding_invoices(
            firm_id=firm_id, party_id=matching.customer_id if matching else None
        )
        if matching is not None:
            records = [
                record
                for record in records
                if not (matching.date_from and record.invoice_date < matching.date_from)
                and not (matching.date_to and record.invoice_date > matching.date_to)
                and self._in_run(record.invoice_number, run)
            ]
        out = self._out(firm_id)
        if collector_id is not None or handed == HandedFilter.OUT:
            records = [
                record
                for record in records
                if record.invoice_id in out
                and collector_id in (None, out[record.invoice_id].collector_id)
            ]
        elif handed == HandedFilter.NOT_OUT:
            records = [record for record in records if record.invoice_id not in out]
        if not records:
            return []
        parties = {
            customer_id: (code, name)
            for customer_id, code, name in self._session.execute(
                select(Customer.id, Customer.code, Customer.name).where(
                    Customer.firm_id == firm_id
                )
            ).all()
        }
        places = customer_places(
            self._session,
            {record.party_id for record in records if record.party_id is not None},
        )
        if matching is not None and matching.area is not None:
            wanted = matching.area.casefold()
            records = [
                record
                for record in records
                if record.party_id is not None
                and wanted in places.get(record.party_id, "").casefold()
            ]
        members = member_names(self._session, firm_id)
        rows: list[HandoverBillRow] = []
        for record in records:
            # A bill always has a party when asked firm-wide.
            if record.party_id is None:  # pragma: no cover
                continue
            code, name = parties.get(record.party_id, ("", ""))
            held = out.get(record.invoice_id)
            rows.append(
                HandoverBillRow(
                    invoice_id=record.invoice_id,
                    invoice_number=record.invoice_number,
                    invoice_date=record.invoice_date,
                    due_date=record.due_date,
                    days_overdue=(
                        max((on - record.due_date).days, 0) if record.due_date else 0
                    ),
                    is_opening_bill=record.is_opening_bill,
                    customer_id=record.party_id,
                    customer_code=code,
                    customer_name=name,
                    customer_place=places.get(record.party_id, ""),
                    invoice_total=record.invoice_total,
                    outstanding=record.outstanding_amount,
                    handover_id=held.id if held else None,
                    collector_id=held.collector_id if held else None,
                    collector_name=(
                        members.get(held.collector_id, FORMER_MEMBER) if held else None
                    ),
                    handed_on=held.handed_on if held else None,
                )
            )
        return rows

    def bills_page(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        handed: HandedFilter = HandedFilter.ALL,
        collector_id: UUID | None = None,
        matching: HandoverMatching | None = None,
    ) -> tuple[list[HandoverBillRow], int]:
        """Return one page of the unpaid bills and how many there are in all."""
        rows = self.bills(
            firm_id, handed=handed, collector_id=collector_id, matching=matching
        )
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    def list_handovers(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        collector_id: UUID | None = None,
        state: HandoverState | None = None,
        handed_from: date | None = None,
        handed_to: date | None = None,
    ) -> tuple[list[HandoverResponse], int]:
        """Return one page of handovers: those still out first, newest first.

        A bill paid while it is out is listed here and nowhere among the
        unpaid bills, which is how it is found and taken back.
        """
        filters = [
            BillHandover.firm_id == firm_id,
            BillHandover.is_deleted.is_(False),
        ]
        if collector_id is not None:
            filters.append(BillHandover.collector_id == collector_id)
        if state == HandoverState.OUT:
            filters.append(BillHandover.returned_at.is_(None))
        elif state == HandoverState.RETURNED:
            filters.append(BillHandover.returned_at.is_not(None))
        if handed_from is not None:
            filters.append(BillHandover.handed_on >= handed_from)
        if handed_to is not None:
            filters.append(BillHandover.handed_on <= handed_to)
        total = int(
            self._session.scalar(
                select(func.count()).select_from(BillHandover).where(*filters)
            )
            or 0
        )
        rows = list(
            self._session.scalars(
                select(BillHandover)
                .where(*filters)
                .order_by(
                    # Ranked, never left to where a NULL happens to sort.
                    case((BillHandover.returned_at.is_(None), 0), else_=1),
                    BillHandover.handed_on.desc(),
                    BillHandover.created_at.desc(),
                    BillHandover.id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return self.responses(rows, firm_id=firm_id), total

    def responses(
        self, rows: list[BillHandover], *, firm_id: UUID
    ) -> list[HandoverResponse]:
        """Build a page of handovers, reading each name once for the page."""
        if not rows:
            return []
        invoice_ids = [row.sales_invoice_id for row in rows if row.sales_invoice_id]
        opening_ids = [
            row.customer_opening_bill_id for row in rows if row.customer_opening_bill_id
        ]
        bills: dict[UUID, tuple[str, date]] = {}
        if invoice_ids:
            bills.update(
                {
                    invoice_id: (number, dated)
                    for invoice_id, number, dated in self._session.execute(
                        select(
                            SalesInvoice.id,
                            SalesInvoice.invoice_number,
                            SalesInvoice.invoice_date,
                        ).where(SalesInvoice.id.in_(invoice_ids))
                    ).all()
                }
            )
        if opening_ids:
            bills.update(
                {
                    bill.id: (opening_bill_label(bill), bill.bill_date)
                    for bill in self._session.scalars(
                        select(CustomerOpeningBill).where(
                            CustomerOpeningBill.id.in_(opening_ids)
                        )
                    )
                }
            )
        customer_ids = {row.customer_id for row in rows}
        parties = {
            customer_id: (code, name)
            for customer_id, code, name in self._session.execute(
                select(Customer.id, Customer.code, Customer.name).where(
                    Customer.id.in_(customer_ids)
                )
            ).all()
        }
        places = customer_places(self._session, customer_ids)
        members = member_names(self._session, firm_id)
        owing = self._owing(firm_id)
        page: list[HandoverResponse] = []
        for row in rows:
            bill_id = row.sales_invoice_id or row.customer_opening_bill_id
            # The check constraint holds one of the two.
            assert bill_id is not None
            number, dated = bills.get(bill_id, ("", row.handed_on))
            code, name = parties.get(row.customer_id, ("", ""))
            record = owing.get(bill_id)
            page.append(
                HandoverResponse(
                    id=row.id,
                    state=(
                        HandoverState.OUT
                        if row.returned_at is None
                        else HandoverState.RETURNED
                    ),
                    invoice_id=bill_id,
                    invoice_number=number,
                    invoice_date=dated,
                    is_opening_bill=row.sales_invoice_id is None,
                    customer_id=row.customer_id,
                    customer_code=code,
                    customer_name=name,
                    customer_place=places.get(row.customer_id, ""),
                    collector_id=row.collector_id,
                    collector_name=members.get(row.collector_id, FORMER_MEMBER),
                    handed_on=row.handed_on,
                    handed_by=row.handed_by,
                    handed_by_name=members.get(row.handed_by, FORMER_MEMBER),
                    outstanding_at_handover=_money(row.outstanding_at_handover),
                    outstanding=record.outstanding_amount if record else ZERO,
                    returned_at=row.returned_at,
                    returned_by_name=(
                        None
                        if row.returned_by is None
                        else members.get(row.returned_by, FORMER_MEMBER)
                    ),
                    return_note=row.return_note,
                    version=row.version,
                )
            )
        return page

    # ---- writes ------------------------------------------------------------

    def stage_hand_out(
        self,
        data: HandoverCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        today: date | None = None,
    ) -> HandoverResult:
        """Stage the handovers and their audit records without committing.

        Args:
            data: The collector, the day, and the bills ticked or the bundle.
            firm_id: The owning firm.
            actor_id: Who is handing them out.
            today: The firm's day; read when omitted.

        Raises:
            ValidationError: If the collector is not an active member of the
                firm, the day is in the future, or a ticked bill owes nothing
                or is not the firm's.
            ConflictError: If a ticked bill is already out with somebody.

        """
        on = today or firm_today(self._session, firm_id)
        handed_on = data.handed_on or on
        if handed_on > on:
            raise ValidationError("A bill is handed out today or on a past day.")
        if (
            FirmMetadataReader(self._session).active_member_count(
                firm_id, [data.collector_id]
            )
            != 1
        ):
            raise ValidationError("The collector must be an active member of the firm.")
        already_out = 0
        if data.invoice_ids is not None:
            asked = list(dict.fromkeys(data.invoice_ids))
            by_id = {row.invoice_id: row for row in self.bills(firm_id, today=on)}
            missing = [bill_id for bill_id in asked if bill_id not in by_id]
            if missing:
                raise ValidationError(
                    f"{len(missing)} of the bills ticked owe nothing now, or "
                    "are not this firm's bills. Read the list again."
                )
            chosen = [by_id[bill_id] for bill_id in asked]
            held = [row for row in chosen if row.handover_id is not None]
            if held:
                raise ConflictError(
                    f"Already out with a collector: "
                    f"{_names([row.invoice_number for row in held])}. Take a "
                    "bill back before handing it to somebody else."
                )
        else:
            matched = self.bills(firm_id, matching=data.matching, today=on)
            chosen = [row for row in matched if row.handover_id is None]
            already_out = len(matched) - len(chosen)
        rows = [
            BillHandover(
                firm_id=firm_id,
                customer_id=bill.customer_id,
                sales_invoice_id=None if bill.is_opening_bill else bill.invoice_id,
                customer_opening_bill_id=(
                    bill.invoice_id if bill.is_opening_bill else None
                ),
                collector_id=data.collector_id,
                handed_on=handed_on,
                handed_by=actor_id,
                outstanding_at_handover=bill.outstanding,
                created_by=actor_id,
                updated_by=actor_id,
            )
            for bill in chosen
        ]
        self._session.add_all(rows)
        try:
            self._session.flush()
        except IntegrityError as error:
            # Two people handing out the same bill: the index let one in.
            self._session.rollback()
            raise ConflictError(
                "One of those bills was handed out a moment ago. Read the "
                "list again."
            ) from error
        for row in rows:
            record_audit(
                self._session,
                action="bill_handover.handed_out",
                entity_type="bill_handover",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                after_data=self._snapshot(row),
            )
        return HandoverResult(
            bills=len(rows),
            amount=sum((bill.outstanding for bill in chosen), ZERO).quantize(_CENT),
            already_out=already_out,
        )

    def hand_out(
        self,
        data: HandoverCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        today: date | None = None,
    ) -> HandoverResult:
        """Hand the bills out; commit once. See ``stage_hand_out``."""
        result = self.stage_hand_out(
            data, firm_id=firm_id, actor_id=actor_id, today=today
        )
        self._session.commit()
        return result

    def take_back(
        self, data: HandoverTakeBack, *, firm_id: UUID, actor_id: UUID
    ) -> HandoverResult:
        """Take handed-out bills back, keeping each row; commit once.

        All of them or none.

        Raises:
            ResourceNotFoundError: If one is not a handover of the firm.
            ConflictError: If one was already taken back.

        """
        asked = list(dict.fromkeys(data.handover_ids))
        rows = list(
            self._session.scalars(
                select(BillHandover).where(
                    BillHandover.id.in_(asked),
                    BillHandover.firm_id == firm_id,
                    BillHandover.is_deleted.is_(False),
                )
            )
        )
        if len(rows) != len(asked):
            raise ResourceNotFoundError("Handover not found.")
        back = [row for row in rows if row.returned_at is not None]
        if back:
            raise ConflictError(
                f"{len(back)} of those bills were already taken back. Read "
                "the list again."
            )
        owing = self._owing(firm_id)
        amount = ZERO
        now = utc_now()
        for row in rows:
            before = self._snapshot(row)
            row.returned_at = now
            row.returned_by = actor_id
            row.return_note = data.note
            row.updated_by = actor_id
            record = owing.get(row.sales_invoice_id or row.customer_opening_bill_id)
            if record is not None:
                amount += record.outstanding_amount
            self._session.flush()
            record_audit(
                self._session,
                action="bill_handover.taken_back",
                entity_type="bill_handover",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data=before,
                after_data=self._snapshot(row),
            )
        self._session.commit()
        return HandoverResult(bills=len(rows), amount=amount.quantize(_CENT))

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _in_run(number: str, run: tuple[str, int | None, int | None] | None) -> bool:
        """Say whether a bill number falls inside the run asked for."""
        if run is None:
            return True
        parts = _series(number)
        if parts is None or parts[0] != run[0]:
            return False
        return (run[1] is None or parts[1] >= run[1]) and (
            run[2] is None or parts[1] <= run[2]
        )

    def _out(self, firm_id: UUID) -> dict[UUID, BillHandover]:
        """Return the firm's live handovers by the bill each one carries."""
        return {
            row.sales_invoice_id or row.customer_opening_bill_id: row  # type: ignore[misc]
            for row in self._session.scalars(
                select(BillHandover).where(
                    BillHandover.firm_id == firm_id,
                    BillHandover.is_deleted.is_(False),
                    BillHandover.returned_at.is_(None),
                )
            )
        }

    def _owing(self, firm_id: UUID) -> dict[UUID | None, OutstandingInvoiceRecord]:
        """Return what each of the firm's unpaid bills owes now, read once."""
        return {
            record.invoice_id: record
            for record in ReceiptService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=None
            )
        }

    @staticmethod
    def _snapshot(row: BillHandover) -> dict[str, object]:
        """Return the handover as the audit trail keeps it."""
        return {
            "customer_id": str(row.customer_id),
            "sales_invoice_id": (
                None if row.sales_invoice_id is None else str(row.sales_invoice_id)
            ),
            "customer_opening_bill_id": (
                None
                if row.customer_opening_bill_id is None
                else str(row.customer_opening_bill_id)
            ),
            "collector_id": str(row.collector_id),
            "handed_on": row.handed_on.isoformat(),
            "outstanding_at_handover": str(_money(row.outstanding_at_handover)),
            "returned_at": (
                None if row.returned_at is None else row.returned_at.isoformat()
            ),
            "return_note": row.return_note,
        }


__all__ = ["BillHandoverService"]
