"""Promises to pay: record, withdraw, and say what became of each (SG-8).

**The status is derived on every read.** A promise is *kept* when the receipts
recorded after it was taken, and dated up to and including the day it was
promised for, cover its amount (D-SELL-56: after by time, not by day) -- for
a bill promise, what those receipts allocated to the bill; for a promise on
the account, what the customer paid in all. Only a
posted receipt counts, so reversing one un-keeps the promise it had kept. A
promise is *broken* once its day has passed without that, *due today* on its
day, *pending* before it, and *withdrawn* when it was taken back.

The amount received is one correlated expression (``received_amount``), so a
list filters on status and pages in SQL, and a page costs the same number of
statements however long it is.

**The chase list** is what a collector works from in the morning: promises for
today not yet paid, and broken ones nobody has taken a newer promise on. A
bill that has since stopped owing -- paid late, or credited -- drops off it;
the promise still reads as broken, because it was.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from app.collections.models import PaymentPromise
from app.collections.schemas import (
    PaymentPromiseCreate,
    PaymentPromiseResponse,
    PromiseStatus,
)
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader, firm_today
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import Customer
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementStatus,
)
from app.settlements.services import ReceiptService
from app.settlements.services.settlement_service import SETTLEABLE_INVOICE_STATES

#: What a member who has since left the firm is shown as.
FORMER_MEMBER = "Former member"
_CENT = Decimal("0.01")


def _money(value: object) -> Decimal:
    """Read a summed figure to two places; NULL is nothing."""
    return Decimal(str(value or 0)).quantize(_CENT)


def _counted_receipt() -> tuple[ColumnElement[bool], ...]:
    """Return what makes a receipt count toward the promise being read.

    Posted -- a reversed receipt keeps nothing -- **written after the promise
    was**, and dated no later than the day promised for. The day alone let
    money received that morning keep a promise taken in the afternoon: it
    came back KEPT while the bill still owed, and never reached the chase
    list (D-SELL-56). A promise is about money still to come, so only a
    receipt recorded after it counts.

    **Recorded after is the whole test of "after"**: the receipt's own date
    is not a lower bound. A receipt entered after the promise and dated the
    day before -- yesterday's cash, keyed in today -- pays the bill and keeps
    the promise; it used to leave it PENDING, to read Broken on its day
    (D-SELL-73).
    """
    return (
        Settlement.firm_id == PaymentPromise.firm_id,
        Settlement.direction == SettlementDirection.RECEIPT.value,
        Settlement.status == SettlementStatus.POSTED.value,
        Settlement.is_deleted.is_(False),
        Settlement.settlement_date <= PaymentPromise.promised_on,
        Settlement.created_at >= PaymentPromise.created_at,
    )


def received_amount() -> ColumnElement[Any]:
    """Return what each promise has had paid toward it, as a SQL expression.

    Correlated to ``PaymentPromise``: what the receipts in its window
    allocated to its bill, or -- for a promise on the account -- what the
    customer paid in that window.
    """
    on_the_bill = (
        select(func.coalesce(func.sum(SettlementAllocation.amount), 0))
        .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
        .where(
            SettlementAllocation.sales_invoice_id == PaymentPromise.sales_invoice_id,
            SettlementAllocation.is_deleted.is_(False),
            *_counted_receipt(),
        )
        .correlate(PaymentPromise)
        .scalar_subquery()
    )
    on_the_account = (
        select(func.coalesce(func.sum(Settlement.amount), 0))
        .where(
            Settlement.customer_id == PaymentPromise.customer_id,
            *_counted_receipt(),
        )
        .correlate(PaymentPromise)
        .scalar_subquery()
    )
    return case(
        (PaymentPromise.sales_invoice_id.is_not(None), on_the_bill),
        else_=on_the_account,
    )


def status_of(
    promise: PaymentPromise, received: Decimal, *, today: date
) -> PromiseStatus:
    """Say what became of one promise, given what was received toward it."""
    if promise.cancelled_at is not None:
        return PromiseStatus.WITHDRAWN
    if received >= Decimal(str(promise.amount)):
        return PromiseStatus.KEPT
    if promise.promised_on < today:
        return PromiseStatus.BROKEN
    if promise.promised_on == today:
        return PromiseStatus.DUE_TODAY
    return PromiseStatus.PENDING


def _having_status(status: PromiseStatus, *, today: date) -> ColumnElement[bool]:
    """Return ``status_of`` as a filter, so a list can page in SQL."""
    if status == PromiseStatus.WITHDRAWN:
        return PaymentPromise.cancelled_at.is_not(None)
    live = PaymentPromise.cancelled_at.is_(None)
    if status == PromiseStatus.KEPT:
        return and_(live, received_amount() >= PaymentPromise.amount)
    unpaid = and_(live, received_amount() < PaymentPromise.amount)
    if status == PromiseStatus.BROKEN:
        return and_(unpaid, PaymentPromise.promised_on < today)
    if status == PromiseStatus.DUE_TODAY:
        return and_(unpaid, PaymentPromise.promised_on == today)
    return and_(unpaid, PaymentPromise.promised_on > today)


def _no_newer_promise() -> ColumnElement[bool]:
    """Return "nobody has taken a live promise on the same thing since".

    The same bill, or the same customer's account for a promise that names no
    bill. Newer by the day it was taken, then by when it was written.
    """
    newer = aliased(PaymentPromise)
    same_subject = or_(
        newer.sales_invoice_id == PaymentPromise.sales_invoice_id,
        and_(
            newer.sales_invoice_id.is_(None),
            PaymentPromise.sales_invoice_id.is_(None),
        ),
    )
    return ~(
        select(newer.id)
        .where(
            newer.firm_id == PaymentPromise.firm_id,
            newer.customer_id == PaymentPromise.customer_id,
            same_subject,
            newer.is_deleted.is_(False),
            newer.cancelled_at.is_(None),
            or_(
                newer.recorded_on > PaymentPromise.recorded_on,
                and_(
                    newer.recorded_on == PaymentPromise.recorded_on,
                    newer.created_at > PaymentPromise.created_at,
                ),
            ),
        )
        .correlate(PaymentPromise)
        .exists()
    )


def latest_live_promises(
    session: Session, firm_id: UUID
) -> list[tuple[PaymentPromise, Decimal]]:
    """Return the firm's latest live promise per bill and per account.

    One statement for the whole firm, which is what the collection sheet
    wants: it reads every open bill, so it sends the firm's query rather than
    the bills' ids.
    """
    return [
        (promise, _money(received))
        for promise, received in session.execute(
            select(PaymentPromise, received_amount()).where(
                PaymentPromise.firm_id == firm_id,
                PaymentPromise.is_deleted.is_(False),
                PaymentPromise.cancelled_at.is_(None),
                _no_newer_promise(),
            )
        ).all()
    ]


class PromiseService:
    """Record and read a firm's promises to pay."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's session."""
        self._session = session

    # ---- writes ------------------------------------------------------------

    def stage_record(
        self,
        data: PaymentPromiseCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        today: date | None = None,
    ) -> PaymentPromise:
        """Stage one promise and its audit record without committing.

        Args:
            data: What was promised.
            firm_id: The owning firm.
            actor_id: Who is writing it down.
            today: The day it is taken; the firm's own today when omitted.

        Raises:
            ResourceNotFoundError: If the customer or the bill is not the
                firm's.
            ValidationError: If the day has passed, the bill is another
                customer's, is not approved, owes nothing or owes less than
                the amount, or the collector is not a member of the firm.

        """
        on = today or firm_today(self._session, firm_id)
        if data.promised_on < on:
            raise ValidationError("A promise is for today or a later day.")
        customer = self._session.scalar(
            select(Customer).where(
                Customer.id == data.customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if customer is None:
            raise ResourceNotFoundError("Customer not found.")
        if data.sales_invoice_id is not None:
            self._assert_bill_owes(
                firm_id, customer, data.sales_invoice_id, Decimal(data.amount)
            )
        collector_id = data.collector_id
        if collector_id is None:
            # Who would have taken it: the customer's collector that day.
            collector_id = customer.collector_id or customer.salesman_id
        elif (
            FirmMetadataReader(self._session).active_member_count(
                firm_id, [collector_id]
            )
            != 1
        ):
            raise ValidationError("The collector must be an active member of the firm.")
        row = PaymentPromise(
            firm_id=firm_id,
            customer_id=customer.id,
            sales_invoice_id=data.sales_invoice_id,
            promised_on=data.promised_on,
            amount=data.amount,
            note=data.note,
            recorded_on=on,
            recorded_by=actor_id,
            collector_id=collector_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="payment_promise.recorded",
            entity_type="payment_promise",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def record(
        self,
        data: PaymentPromiseCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        today: date | None = None,
    ) -> PaymentPromiseResponse:
        """Record one promise; commit. See ``stage_record``."""
        on = today or firm_today(self._session, firm_id)
        row = self.stage_record(data, firm_id=firm_id, actor_id=actor_id, today=on)
        self._session.commit()
        return self.get(row.id, firm_id=firm_id, today=on)

    def withdraw(
        self,
        promise_id: UUID,
        reason: str,
        *,
        firm_id: UUID,
        actor_id: UUID,
        today: date | None = None,
    ) -> PaymentPromiseResponse:
        """Take a promise back, keeping the row; commit.

        Raises:
            ResourceNotFoundError: If the firm has no such promise.
            ConflictError: If it was already withdrawn.
            ValidationError: If it was kept: the money came, so there is
                nothing to take back (D-SELL-62).

        """
        row = self._session.scalar(
            select(PaymentPromise).where(
                PaymentPromise.id == promise_id,
                PaymentPromise.firm_id == firm_id,
                PaymentPromise.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Promise not found.")
        if row.cancelled_at is not None:
            raise ConflictError("That promise was already withdrawn.")
        # Only the screen held this back: the server withdrew a promise the
        # customer had kept, and its record then read as though they had not.
        received = _money(
            self._session.scalar(
                select(received_amount()).where(PaymentPromise.id == row.id)
            )
        )
        if received >= Decimal(str(row.amount)):
            raise ValidationError(
                "That promise was kept: the money promised was received, so "
                "there is nothing to withdraw."
            )
        before = self._snapshot(row)
        row.cancelled_at = utc_now()
        row.cancel_reason = reason
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="payment_promise.withdrawn",
            entity_type="payment_promise",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self.get(row.id, firm_id=firm_id, today=today)

    # ---- reads -------------------------------------------------------------

    def get(
        self, promise_id: UUID, *, firm_id: UUID, today: date | None = None
    ) -> PaymentPromiseResponse:
        """Return one promise with what became of it.

        Raises:
            ResourceNotFoundError: If the firm has no such promise.

        """
        found = self._session.execute(
            self._promises(firm_id).where(PaymentPromise.id == promise_id)
        ).all()
        if not found:
            raise ResourceNotFoundError("Promise not found.")
        return self.responses(
            [(found[0][0], _money(found[0][1]))], firm_id=firm_id, today=today
        )[0]

    def list_promises(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        customer_id: UUID | None = None,
        sales_invoice_id: UUID | None = None,
        status: PromiseStatus | None = None,
        due_from: date | None = None,
        due_to: date | None = None,
        collector_id: UUID | None = None,
        today: date | None = None,
    ) -> tuple[list[PaymentPromiseResponse], int]:
        """Return one page of promises, latest promised day first, and the count.

        ``due_from`` and ``due_to`` bound the day promised for, both included;
        ``collector_id`` is who took the promise.
        """
        on = today or firm_today(self._session, firm_id)
        conditions: list[ColumnElement[bool]] = []
        if customer_id is not None:
            conditions.append(PaymentPromise.customer_id == customer_id)
        if sales_invoice_id is not None:
            conditions.append(PaymentPromise.sales_invoice_id == sales_invoice_id)
        if collector_id is not None:
            conditions.append(PaymentPromise.collector_id == collector_id)
        if due_from is not None:
            conditions.append(PaymentPromise.promised_on >= due_from)
        if due_to is not None:
            conditions.append(PaymentPromise.promised_on <= due_to)
        if status is not None:
            conditions.append(_having_status(status, today=on))
        total = int(
            self._session.scalar(
                select(func.count())
                .select_from(PaymentPromise)
                .where(
                    PaymentPromise.firm_id == firm_id,
                    PaymentPromise.is_deleted.is_(False),
                    *conditions,
                )
            )
            or 0
        )
        found = self._session.execute(
            self._promises(firm_id)
            .where(*conditions)
            .order_by(
                PaymentPromise.promised_on.desc(),
                PaymentPromise.recorded_on.desc(),
                PaymentPromise.created_at.desc(),
                PaymentPromise.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return (
            self.responses(
                [(promise, _money(received)) for promise, received in found],
                firm_id=firm_id,
                today=on,
            ),
            total,
        )

    def chase_list(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        collector_id: UUID | None = None,
        today: date | None = None,
    ) -> tuple[list[PaymentPromiseResponse], int]:
        """Return one page of the promises to chase today, and the count.

        Promises for today not yet paid, and broken ones with no newer live
        promise on the same bill (or the same account), oldest first. A bill
        promise whose bill no longer owes anything is left out.
        """
        on = today or firm_today(self._session, firm_id)
        statement = self._promises(firm_id).where(
            PaymentPromise.cancelled_at.is_(None),
            received_amount() < PaymentPromise.amount,
            or_(
                PaymentPromise.promised_on == on,
                and_(PaymentPromise.promised_on < on, _no_newer_promise()),
            ),
        )
        if collector_id is not None:
            statement = statement.where(PaymentPromise.collector_id == collector_id)
        found = [
            (promise, _money(received))
            for promise, received in self._session.execute(
                statement.order_by(
                    PaymentPromise.promised_on.asc(),
                    PaymentPromise.recorded_on.asc(),
                    PaymentPromise.created_at.asc(),
                    PaymentPromise.id.asc(),
                )
            ).all()
        ]
        if any(promise.sales_invoice_id is not None for promise, _ in found):
            # The one derivation of what a bill still owes, firm-wide: the
            # candidates are few, the open bills are what it already reads.
            owing = {
                record.invoice_id
                for record in ReceiptService(self._session).outstanding_invoices(
                    firm_id=firm_id, party_id=None
                )
                if not record.is_opening_bill
            }
            found = [
                (promise, received)
                for promise, received in found
                if promise.sales_invoice_id is None or promise.sales_invoice_id in owing
            ]
        start = (page - 1) * page_size
        return (
            self.responses(found[start : start + page_size], firm_id=firm_id, today=on),
            len(found),
        )

    def responses(
        self,
        rows: Sequence[tuple[PaymentPromise, Decimal]],
        *,
        firm_id: UUID,
        today: date | None = None,
    ) -> list[PaymentPromiseResponse]:
        """Build the responses for a page of promises, one read per table.

        Customers, bills and the firm's members are each read once for the
        page; the single-row builder is this with a list of one.
        """
        if not rows:
            return []
        on = today or firm_today(self._session, firm_id)
        customers: dict[UUID, tuple[str, str]] = {
            customer_id: (code, name)
            for customer_id, code, name in self._session.execute(
                select(Customer.id, Customer.code, Customer.name).where(
                    Customer.id.in_({promise.customer_id for promise, _ in rows})
                )
            ).all()
        }
        invoice_ids = {
            promise.sales_invoice_id
            for promise, _ in rows
            if promise.sales_invoice_id is not None
        }
        numbers: dict[UUID, str] = (
            {
                invoice_id: number
                for invoice_id, number in self._session.execute(
                    select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                        SalesInvoice.id.in_(invoice_ids)
                    )
                ).all()
            }
            if invoice_ids
            else {}
        )
        members = member_names(self._session, firm_id)
        responses: list[PaymentPromiseResponse] = []
        for promise, received in rows:
            code, name = customers.get(promise.customer_id, ("", "?"))
            responses.append(
                PaymentPromiseResponse(
                    id=promise.id,
                    customer_id=promise.customer_id,
                    customer_code=code,
                    customer_name=name,
                    sales_invoice_id=promise.sales_invoice_id,
                    invoice_number=(
                        None
                        if promise.sales_invoice_id is None
                        else numbers.get(promise.sales_invoice_id)
                    ),
                    promised_on=promise.promised_on,
                    amount=_money(promise.amount),
                    received_amount=received,
                    status=status_of(promise, received, today=on),
                    note=promise.note,
                    recorded_on=promise.recorded_on,
                    recorded_by=promise.recorded_by,
                    recorded_by_name=members.get(promise.recorded_by, FORMER_MEMBER),
                    collector_id=promise.collector_id,
                    collector_name=(
                        None
                        if promise.collector_id is None
                        else members.get(promise.collector_id, FORMER_MEMBER)
                    ),
                    cancelled_at=promise.cancelled_at,
                    cancel_reason=promise.cancel_reason,
                    version=promise.version,
                )
            )
        return responses

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _promises(firm_id: UUID) -> Select[tuple[PaymentPromise, Any]]:
        """Select the firm's promises, each with what was received toward it."""
        return select(PaymentPromise, received_amount()).where(
            PaymentPromise.firm_id == firm_id,
            PaymentPromise.is_deleted.is_(False),
        )

    def _assert_bill_owes(
        self, firm_id: UUID, customer: Customer, invoice_id: UUID, amount: Decimal
    ) -> None:
        """Refuse a promise on a bill that cannot carry it.

        What the bill owes is read from Record Receipt's own list
        (``outstanding_invoices``), so the two cannot disagree.
        """
        bill = self._session.execute(
            select(
                SalesInvoice.customer_id,
                SalesInvoice.status,
                SalesInvoice.invoice_number,
            ).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
            )
        ).first()
        if bill is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        if bill.customer_id != customer.id:
            raise ValidationError(
                f"Bill {bill.invoice_number} belongs to another customer."
            )
        if bill.status not in SETTLEABLE_INVOICE_STATES:
            raise ValidationError(
                f"Bill {bill.invoice_number} is not approved, so nothing is "
                "owed on it yet."
            )
        owed = next(
            (
                record.outstanding_amount
                for record in ReceiptService(self._session).outstanding_invoices(
                    firm_id=firm_id, party_id=customer.id
                )
                if record.invoice_id == invoice_id and not record.is_opening_bill
            ),
            ZERO,
        )
        if owed <= ZERO:
            raise ValidationError(f"Bill {bill.invoice_number} owes nothing.")
        if amount > owed:
            raise ValidationError(
                f"Bill {bill.invoice_number} owes {owed:,.2f}; a promise "
                "cannot be for more than that."
            )

    @staticmethod
    def _snapshot(row: PaymentPromise) -> dict[str, object]:
        """Return what the audit trail keeps of a promise."""
        return {
            "customer_id": str(row.customer_id),
            "sales_invoice_id": (
                None if row.sales_invoice_id is None else str(row.sales_invoice_id)
            ),
            "promised_on": row.promised_on.isoformat(),
            "amount": str(row.amount),
            "recorded_on": row.recorded_on.isoformat(),
            "collector_id": None if row.collector_id is None else str(row.collector_id),
            "note": row.note,
            "cancelled_at": (
                None if row.cancelled_at is None else row.cancelled_at.isoformat()
            ),
            "cancel_reason": row.cancel_reason,
        }


def member_names(session: Session, firm_id: UUID) -> dict[UUID, str]:
    """Return the firm's active members by id, read once.

    Through ``FirmMetadataReader``: ``users`` lives only in the platform
    store.
    """
    return {
        member.user_id: member.full_name or member.email
        for member in FirmMetadataReader(session).active_members(firm_id)
    }


__all__ = [
    "FORMER_MEMBER",
    "PromiseService",
    "latest_live_promises",
    "member_names",
    "received_amount",
    "status_of",
]
