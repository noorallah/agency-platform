"""The collector's end-of-day line on each handed-out bill (backlog 124, M6).

In the evening every bill in a collector's bag gets one line for the day:
collected, part collected, promised, or not collected.

**The line states; a receipt records.** What a line says was taken moves no
balance and posts nothing. The money enters the books through
``ReceiptService`` and no other way, and the line names that receipt. Who
writes the receipt is the firm's choice (``collector_records_receipt`` on its
credit settings):

* the office writing a line holds ``RECEIPT_CREATE``, so its line records the
  receipt in the same act;
* a collector writing his own line records the receipt only where the firm
  has switched that on. Where it is off his line is a statement, and the
  office records the receipt from the day's sheet.

So a day's sheet shows three figures -- stated, in a receipt, and the
difference -- and adds up when the difference is nothing.

**A promise is a promise.** PROMISED, and PART with a day named for the rest,
write a row through ``PromiseService`` rather than a second kind of promise.

**A line is withdrawn, never edited**, and not while a live receipt stands on
it: the receipt is reversed first, where receipts are reversed.
"""

from contextlib import suppress
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collections.models import BillHandover, CollectionReturn, PaymentPromise
from app.collections.schemas import (
    CollectionDaySheet,
    CollectionReturnCreate,
    CollectionReturnResponse,
    PaymentPromiseCreate,
    ReturnOutcome,
    ReturnPaymentMode,
)
from app.collections.services.promises import (
    FORMER_MEMBER,
    PromiseService,
    member_names,
)
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import Customer, CustomerOpeningBill
from app.customers.services.credit_control import CreditControlService
from app.customers.services.opening_bill_service import opening_bill_label
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement, SettlementStatus
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
    SettlementModeEnum,
)
from app.settlements.services import ReceiptService

_CENT = Decimal("0.01")
_TAKES_MONEY = (ReturnOutcome.COLLECTED.value, ReturnOutcome.PART.value)


def _money(value: object) -> Decimal:
    """Read a figure to two places; NULL is nothing."""
    return Decimal(str(value or 0)).quantize(_CENT)


class CollectionReturnService:
    """Write and read the day's lines on a firm's handed-out bills."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's session."""
        self._session = session

    # ---- writes ------------------------------------------------------------

    def stage_record(
        self,
        data: CollectionReturnCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        own: bool,
        today: date | None = None,
    ) -> CollectionReturn:
        """Stage one day's line, with its receipt and promise; no commit.

        Args:
            data: The handed-out bill and what happened on it.
            firm_id: The owning firm.
            actor_id: Who is writing the line.
            own: True where a collector writes his own line: the bill must be
                in his bag, the day is today, and the receipt is recorded
                only where the firm lets its collectors record. False for the
                office, whose line always records the receipt.
            today: The firm's day; read when omitted.

        Raises:
            ResourceNotFoundError: If the firm has no such handover, or it is
                another collector's and ``own`` is set.
            ConflictError: If the bill was taken back, or already has a line
                for that day.
            ValidationError: If the day is in the future or before the bill
                went out, the bill owes nothing, or the amount does not fit
                the outcome.

        """
        handover = self._session.scalar(
            select(BillHandover).where(
                BillHandover.id == data.handover_id,
                BillHandover.firm_id == firm_id,
                BillHandover.is_deleted.is_(False),
            )
        )
        # Another collector's bill reads as no bill at all: whose bag a bill
        # is in is not his to learn.
        if handover is None or (own and handover.collector_id != actor_id):
            raise ResourceNotFoundError("Handover not found.")
        if handover.returned_at is not None:
            raise ConflictError(
                "That bill was taken back into the office; it has no line to " "write."
            )
        on = today or firm_today(self._session, firm_id)
        day = data.return_date or on
        if day > on:
            raise ValidationError("A day's line is for today or a past day.")
        if own and day != on:
            raise ValidationError(
                "A collector writes today's line. A past day's is written "
                "in the office."
            )
        if day < handover.handed_on:
            raise ValidationError(
                f"That bill went out on {handover.handed_on.isoformat()}; it "
                "has no line before then."
            )
        if self._live_line(handover.id, day) is not None:
            raise ConflictError(
                "That bill already has a line for that day. Withdraw it "
                "before writing another."
            )
        bill_id = handover.sales_invoice_id or handover.customer_opening_bill_id
        # The check constraint holds one of the two.
        assert bill_id is not None
        owed = self._owed(firm_id, handover.customer_id, bill_id)
        outcome = data.outcome
        amount = ZERO
        if outcome != ReturnOutcome.NOT_COLLECTED and owed <= ZERO:
            raise ValidationError("That bill owes nothing now. Read the list again.")
        if outcome == ReturnOutcome.COLLECTED:
            amount = _money(data.amount_collected) if data.amount_collected else owed
            if amount != owed:
                raise ValidationError(
                    f"The bill owes {owed:,.2f}. Collected in full is exactly "
                    "that; anything less is part collected."
                )
        elif outcome == ReturnOutcome.PART:
            amount = _money(data.amount_collected)
            if amount >= owed:
                raise ValidationError(
                    f"The bill owes {owed:,.2f}. Part collected is less than "
                    "that; the whole of it is collected in full."
                )
        took_money = outcome.value in _TAKES_MONEY
        mode = (data.payment_mode or ReturnPaymentMode.CASH) if took_money else None
        row = CollectionReturn(
            firm_id=firm_id,
            handover_id=handover.id,
            collector_id=handover.collector_id,
            return_date=day,
            outcome=outcome.value,
            outstanding_before=owed,
            amount_collected=amount,
            payment_mode=None if mode is None else mode.value,
            instrument_reference=data.instrument_reference if took_money else None,
            note=data.note,
            recorded_by=actor_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as error:
            # Two people writing the same bill's line: the index let one in.
            self._session.rollback()
            raise ConflictError(
                "That bill's line for the day was written a moment ago. Read "
                "the sheet again."
            ) from error
        if took_money and (not own or self.collector_records_receipt(firm_id)):
            self._stage_receipt(row, handover, firm_id=firm_id, actor_id=actor_id)
        if data.promised_on is not None:
            # After the receipt, so a promise for the rest is checked against
            # what the bill still owes.
            promise = PromiseService(self._session).stage_record(
                PaymentPromiseCreate(
                    customer_id=handover.customer_id,
                    # A bill from before the firm started here carries no
                    # promise of its own; it goes on the account.
                    sales_invoice_id=handover.sales_invoice_id,
                    promised_on=data.promised_on,
                    amount=owed - amount,
                    note=data.note,
                    collector_id=handover.collector_id,
                ),
                firm_id=firm_id,
                actor_id=actor_id,
                today=on,
            )
            row.payment_promise_id = promise.id
            self._session.flush()
        record_audit(
            self._session,
            action="collection_return.recorded",
            entity_type="collection_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def record(
        self,
        data: CollectionReturnCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        own: bool,
        today: date | None = None,
    ) -> CollectionReturnResponse:
        """Write one day's line; commit once. See ``stage_record``."""
        row = self.stage_record(
            data, firm_id=firm_id, actor_id=actor_id, own=own, today=today
        )
        self._session.commit()
        return self.responses([row], firm_id=firm_id)[0]

    def record_receipt(
        self, return_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> CollectionReturnResponse:
        """Record the receipt for a line that only states its money; commit.

        The office's act where a collector's line did not record one, and
        again where the receipt first recorded was reversed.

        Raises:
            ResourceNotFoundError: If the firm has no such line.
            ConflictError: If the line was withdrawn, or a live receipt
                already stands on it.
            ValidationError: If the line took no money, or the bill no longer
                owes what the line states.

        """
        row = self._line(return_id, firm_id=firm_id)
        if row.cancelled_at is not None:
            raise ConflictError("That line was withdrawn.")
        if row.outcome not in _TAKES_MONEY:
            raise ValidationError("Nothing was collected on that line.")
        if row.settlement_id is not None:
            receipt = self._session.get(Settlement, row.settlement_id)
            if receipt is not None and receipt.status != SettlementStatus.REVERSED:
                raise ConflictError(
                    f"Receipt {receipt.settlement_number} already records " "that line."
                )
        handover = self._session.get(BillHandover, row.handover_id)
        # The foreign key holds it.
        assert handover is not None
        before = self._snapshot(row)
        self._stage_receipt(row, handover, firm_id=firm_id, actor_id=actor_id)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="collection_return.receipt_recorded",
            entity_type="collection_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self.responses([row], firm_id=firm_id)[0]

    def withdraw(
        self,
        return_id: UUID,
        reason: str,
        *,
        firm_id: UUID,
        actor_id: UUID,
        own: bool,
    ) -> CollectionReturnResponse:
        """Take a day's line back, keeping the row; commit once.

        The promise taken with the line is withdrawn with it, unless the
        customer has kept it since.

        Raises:
            ResourceNotFoundError: If the firm has no such line, or it is
                another collector's and ``own`` is set.
            ConflictError: If it was already withdrawn, or a live receipt
                stands on it.

        """
        row = self._line(return_id, firm_id=firm_id)
        if own and row.collector_id != actor_id:
            raise ResourceNotFoundError("Line not found.")
        if row.cancelled_at is not None:
            raise ConflictError("That line was already withdrawn.")
        if row.settlement_id is not None:
            receipt = self._session.get(Settlement, row.settlement_id)
            if receipt is not None and receipt.status != SettlementStatus.REVERSED:
                raise ConflictError(
                    f"Receipt {receipt.settlement_number} records that line's "
                    "money. Reverse the receipt first; then the line can be "
                    "withdrawn."
                )
        before = self._snapshot(row)
        if row.payment_promise_id is not None:
            promise = self._session.get(PaymentPromise, row.payment_promise_id)
            if promise is not None and promise.cancelled_at is None:
                # Kept since: the money came, and its record stands. The
                # check raises before it changes anything.
                with suppress(ValidationError):
                    PromiseService(self._session).stage_withdraw(
                        promise.id,
                        f"Its collection line was withdrawn: {reason}",
                        firm_id=firm_id,
                        actor_id=actor_id,
                    )
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.cancel_reason = reason
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="collection_return.withdrawn",
            entity_type="collection_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self.responses([row], firm_id=firm_id)[0]

    # ---- reads -------------------------------------------------------------

    def collector_records_receipt(self, firm_id: UUID) -> bool:
        """Say whether the firm lets a collector's own line record a receipt."""
        return bool(
            getattr(
                CreditControlService(self._session).settings_for(firm_id),
                "collector_records_receipt",
                False,
            )
        )

    def lines_by_handover(
        self, firm_id: UUID, *, collector_id: UUID, day: date
    ) -> dict[UUID, CollectionReturn]:
        """Return a collector's live lines of one day, by handover."""
        return {
            row.handover_id: row
            for row in self._session.scalars(
                select(CollectionReturn).where(
                    CollectionReturn.firm_id == firm_id,
                    CollectionReturn.collector_id == collector_id,
                    CollectionReturn.return_date == day,
                    CollectionReturn.is_deleted.is_(False),
                    CollectionReturn.cancelled_at.is_(None),
                )
            )
        }

    def day_sheet(
        self,
        firm_id: UUID,
        *,
        day: date | None = None,
        collector_id: UUID | None = None,
    ) -> CollectionDaySheet:
        """Return a day's live lines and whether they add up to the receipts.

        Args:
            firm_id: The firm whose sheet to read.
            day: The firm's day; today when omitted.
            collector_id: One collector's sheet; every collector's when
                omitted.

        """
        on = day or firm_today(self._session, firm_id)
        filters = [
            CollectionReturn.firm_id == firm_id,
            CollectionReturn.return_date == on,
            CollectionReturn.is_deleted.is_(False),
            CollectionReturn.cancelled_at.is_(None),
        ]
        if collector_id is not None:
            filters.append(CollectionReturn.collector_id == collector_id)
        lines = list(
            self._session.scalars(
                select(CollectionReturn)
                .where(*filters)
                .order_by(
                    CollectionReturn.collector_id,
                    CollectionReturn.created_at,
                    CollectionReturn.id,
                )
            )
        )
        rows = self.responses(lines, firm_id=firm_id)
        rows.sort(
            key=lambda row: (
                row.collector_name.casefold(),
                row.customer_name.casefold(),
                row.invoice_number,
            )
        )
        out = [
            BillHandover.firm_id == firm_id,
            BillHandover.is_deleted.is_(False),
            BillHandover.returned_at.is_(None),
            BillHandover.handed_on <= on,
        ]
        if collector_id is not None:
            out.append(BillHandover.collector_id == collector_id)
        carried = int(
            self._session.scalar(
                select(func.count()).select_from(BillHandover).where(*out)
            )
            or 0
        )
        still_out = (
            {
                handover_id
                for handover_id in self._session.scalars(
                    select(BillHandover.id).where(
                        *out, BillHandover.id.in_([line.handover_id for line in lines])
                    )
                )
            }
            if lines
            else set()
        )
        stated = sum((row.amount_collected for row in rows), ZERO).quantize(_CENT)
        receipted = sum((row.receipt_amount for row in rows), ZERO).quantize(_CENT)

        def count(outcome: ReturnOutcome) -> int:
            """Count the day's lines of one outcome."""
            return sum(1 for row in rows if row.outcome == outcome)

        return CollectionDaySheet(
            day=on,
            collector_id=collector_id,
            collector_name=(
                None
                if collector_id is None
                else member_names(self._session, firm_id).get(
                    collector_id, FORMER_MEMBER
                )
            ),
            collector_records_receipt=self.collector_records_receipt(firm_id),
            rows=rows,
            collected_bills=count(ReturnOutcome.COLLECTED),
            part_bills=count(ReturnOutcome.PART),
            promised_bills=count(ReturnOutcome.PROMISED),
            not_collected_bills=count(ReturnOutcome.NOT_COLLECTED),
            bills_without_a_line=carried - len(still_out),
            amount_stated=stated,
            amount_receipted=receipted,
            amount_not_receipted=(stated - receipted).quantize(_CENT),
            adds_up=stated == receipted,
        )

    def responses(
        self, rows: list[CollectionReturn], *, firm_id: UUID
    ) -> list[CollectionReturnResponse]:
        """Build a page of lines, reading each name once for the page."""
        if not rows:
            return []
        handovers = {
            handover.id: handover
            for handover in self._session.scalars(
                select(BillHandover).where(
                    BillHandover.id.in_({row.handover_id for row in rows})
                )
            )
        }
        invoice_ids = [
            handover.sales_invoice_id
            for handover in handovers.values()
            if handover.sales_invoice_id
        ]
        opening_ids = [
            handover.customer_opening_bill_id
            for handover in handovers.values()
            if handover.customer_opening_bill_id
        ]
        numbers: dict[UUID, str] = {}
        if invoice_ids:
            numbers.update(
                {
                    invoice_id: number
                    for invoice_id, number in self._session.execute(
                        select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                            SalesInvoice.id.in_(invoice_ids)
                        )
                    ).all()
                }
            )
        if opening_ids:
            numbers.update(
                {
                    bill.id: opening_bill_label(bill)
                    for bill in self._session.scalars(
                        select(CustomerOpeningBill).where(
                            CustomerOpeningBill.id.in_(opening_ids)
                        )
                    )
                }
            )
        parties = {
            customer_id: (code, name)
            for customer_id, code, name in self._session.execute(
                select(Customer.id, Customer.code, Customer.name).where(
                    Customer.id.in_(
                        {handover.customer_id for handover in handovers.values()}
                    )
                )
            ).all()
        }
        settlement_ids = [row.settlement_id for row in rows if row.settlement_id]
        receipts: dict[UUID, tuple[str, Decimal, bool]] = {}
        if settlement_ids:
            receipts = {
                settlement_id: (
                    number,
                    _money(amount),
                    status == SettlementStatus.REVERSED,
                )
                for settlement_id, number, amount, status in self._session.execute(
                    select(
                        Settlement.id,
                        Settlement.settlement_number,
                        Settlement.amount,
                        Settlement.status,
                    ).where(Settlement.id.in_(settlement_ids))
                ).all()
            }
        promise_ids = [row.payment_promise_id for row in rows if row.payment_promise_id]
        promises: dict[UUID, tuple[date, Decimal]] = {}
        if promise_ids:
            promises = {
                promise_id: (promised_on, _money(amount))
                for promise_id, promised_on, amount in self._session.execute(
                    select(
                        PaymentPromise.id,
                        PaymentPromise.promised_on,
                        PaymentPromise.amount,
                    ).where(PaymentPromise.id.in_(promise_ids))
                ).all()
            }
        members = member_names(self._session, firm_id)
        page: list[CollectionReturnResponse] = []
        for row in rows:
            handover = handovers[row.handover_id]
            bill_id = handover.sales_invoice_id or handover.customer_opening_bill_id
            # The check constraint holds one of the two.
            assert bill_id is not None
            code, name = parties.get(handover.customer_id, ("", ""))
            number, receipt_amount, reversed_ = (
                receipts.get(row.settlement_id, (None, ZERO, False))
                if row.settlement_id
                else (None, ZERO, False)
            )
            promised_on, promised_amount = (
                promises.get(row.payment_promise_id, (None, None))
                if row.payment_promise_id
                else (None, None)
            )
            page.append(
                CollectionReturnResponse(
                    id=row.id,
                    handover_id=row.handover_id,
                    return_date=row.return_date,
                    outcome=ReturnOutcome(row.outcome),
                    invoice_id=bill_id,
                    invoice_number=numbers.get(bill_id, ""),
                    is_opening_bill=handover.sales_invoice_id is None,
                    customer_id=handover.customer_id,
                    customer_code=code,
                    customer_name=name,
                    collector_id=row.collector_id,
                    collector_name=members.get(row.collector_id, FORMER_MEMBER),
                    outstanding_before=_money(row.outstanding_before),
                    amount_collected=_money(row.amount_collected),
                    payment_mode=(
                        None
                        if row.payment_mode is None
                        else ReturnPaymentMode(row.payment_mode)
                    ),
                    instrument_reference=row.instrument_reference,
                    settlement_id=row.settlement_id,
                    settlement_number=number,
                    # A reversed receipt took nothing into the books.
                    receipt_amount=ZERO if reversed_ else receipt_amount,
                    receipt_reversed=reversed_,
                    payment_promise_id=row.payment_promise_id,
                    promised_on=promised_on,
                    promised_amount=promised_amount,
                    note=row.note,
                    recorded_by=row.recorded_by,
                    recorded_by_name=members.get(row.recorded_by, FORMER_MEMBER),
                    cancelled_at=row.cancelled_at,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                )
            )
        return page

    # ---- helpers -----------------------------------------------------------

    def _line(self, return_id: UUID, *, firm_id: UUID) -> CollectionReturn:
        """Return one of the firm's lines, or refuse."""
        row = self._session.scalar(
            select(CollectionReturn).where(
                CollectionReturn.id == return_id,
                CollectionReturn.firm_id == firm_id,
                CollectionReturn.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Line not found.")
        return row

    def _live_line(self, handover_id: UUID, day: date) -> CollectionReturn | None:
        """Return the live line a handed-out bill has for a day, if any."""
        return self._session.scalar(
            select(CollectionReturn).where(
                CollectionReturn.handover_id == handover_id,
                CollectionReturn.return_date == day,
                CollectionReturn.is_deleted.is_(False),
                CollectionReturn.cancelled_at.is_(None),
            )
        )

    def _owed(self, firm_id: UUID, customer_id: UUID, bill_id: UUID) -> Decimal:
        """Return what one bill owes now, from Record Receipt's own list."""
        return next(
            (
                _money(record.outstanding_amount)
                for record in ReceiptService(self._session).outstanding_invoices(
                    firm_id=firm_id, party_id=customer_id
                )
                if record.invoice_id == bill_id
            ),
            ZERO,
        )

    def _stage_receipt(
        self,
        row: CollectionReturn,
        handover: BillHandover,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Record the line's money as a receipt against its bill; no commit.

        Through ``ReceiptService.create``, the one way money is recorded, so
        the journal, the customer's balance and every refusal are the
        receipt's own.
        """
        bill_id = handover.sales_invoice_id or handover.customer_opening_bill_id
        # The check constraint holds one of the two.
        assert bill_id is not None
        mode = SettlementModeEnum(row.payment_mode or SettlementModeEnum.CASH.value)
        amount = _money(row.amount_collected)
        collector = member_names(self._session, firm_id).get(
            row.collector_id, FORMER_MEMBER
        )
        receipt = ReceiptService(self._session).create(
            SettlementCreate(
                party_id=handover.customer_id,
                settlement_date=row.return_date,
                amount=amount,
                method=(
                    SettlementMethodEnum.CASH
                    if mode == SettlementModeEnum.CASH
                    else SettlementMethodEnum.BANK
                ),
                payment_mode=mode,
                instrument_reference=row.instrument_reference,
                narration=f"Collected by {collector}",
                allocations=[
                    SettlementAllocationWrite(invoice_id=bill_id, amount=amount)
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        row.settlement_id = receipt.id
        self._session.flush()

    @staticmethod
    def _snapshot(row: CollectionReturn) -> dict[str, object]:
        """Return the line as the audit trail keeps it."""
        return {
            "handover_id": str(row.handover_id),
            "collector_id": str(row.collector_id),
            "return_date": row.return_date.isoformat(),
            "outcome": row.outcome,
            "outstanding_before": str(_money(row.outstanding_before)),
            "amount_collected": str(_money(row.amount_collected)),
            "payment_mode": row.payment_mode,
            "instrument_reference": row.instrument_reference,
            "settlement_id": (
                None if row.settlement_id is None else str(row.settlement_id)
            ),
            "payment_promise_id": (
                None if row.payment_promise_id is None else str(row.payment_promise_id)
            ),
            "note": row.note,
            "cancelled_at": (
                None if row.cancelled_at is None else row.cancelled_at.isoformat()
            ),
            "cancel_reason": row.cancel_reason,
        }


__all__ = ["CollectionReturnService"]
