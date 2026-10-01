"""Record, list, import and cancel the bills customers owed on day one.

The receivable twin of `VendorOpeningBillService`. Why these are bills rather
than one figure per customer, and why they are not sales invoices, is on
`CustomerOpeningBill`. What one still owes is derived -- the amount at cutover
less the posted receipts applied to it -- exactly as a sales invoice's is, and
`ReceiptService.outstanding_invoices` offers them to Record Receipt beside the
ordinary bills. Unlike a supplier, a customer also carries a running balance
(`current_outstanding`), so each bill writes an `OPENING_BILL` receivable
transaction beside its journal and cancelling one reverses both.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.customers.models import (
    Customer,
    CustomerOpeningBill,
    CustomerOpeningBillStatus,
    CustomerReceivableTransaction,
)
from app.customers.schemas.customer import CustomerReceivableTransactionType
from app.customers.schemas.opening_bill import (
    CustomerOpeningBillImportRow,
    CustomerOpeningBillResponse,
    CustomerOpeningBillWrite,
)

ZERO = Decimal("0.00")

#: What the receivable row an opening bill writes names as its reference.
REFERENCE_TYPE = "customer_opening_bill"


def opening_bill_receipts(
    session: Session,
    *,
    firm_id: UUID,
    bill_ids: Sequence[UUID],
    as_of: date | None = None,
) -> dict[UUID, Decimal]:
    """Sum the posted receipts applied to each customer opening bill.

    Joined to the settlement so a reversed receipt stops clearing anything --
    the rule `settled_against` applies to a sales invoice, including its
    reading of ``as_of``: a receipt dated after the day had not arrived, and
    one reversed after it still stood.
    """
    # Imported here: the settlement models import the customer models.
    from app.settlements.models import (
        Settlement,
        SettlementAllocation,
        SettlementStatus,
    )

    if not bill_ids:
        return {}
    if as_of is None:
        standing = Settlement.status == SettlementStatus.POSTED.value
        dated: tuple[Any, ...] = ()
    else:
        day_after = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=UTC)
        standing = or_(
            Settlement.status == SettlementStatus.POSTED.value,
            and_(
                Settlement.status == SettlementStatus.REVERSED.value,
                Settlement.reversed_at >= day_after,
            ),
        )
        dated = (Settlement.settlement_date <= as_of,)
    rows = session.execute(
        select(
            SettlementAllocation.customer_opening_bill_id,
            func.coalesce(func.sum(SettlementAllocation.amount), 0),
        )
        .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
        .where(
            SettlementAllocation.firm_id == firm_id,
            SettlementAllocation.is_deleted.is_(False),
            SettlementAllocation.customer_opening_bill_id.in_(list(bill_ids)),
            Settlement.is_deleted.is_(False),
            standing,
            *dated,
        )
        .group_by(SettlementAllocation.customer_opening_bill_id)
    ).all()
    received = {
        bill_id: quantize_ledger(Decimal(str(total)))
        for bill_id, total in rows
        if bill_id is not None
    }
    # And what a write-off or set-off took off the bill (backlog 74 row 2).
    from app.party_adjustments.services.allocations import adjusted_against

    for bill_id, amount in adjusted_against(
        session,
        firm_id=firm_id,
        column="customer_opening_bill_id",
        bill_ids=list(bill_ids),
        as_of=as_of,
    ).items():
        received[bill_id] = received.get(bill_id, ZERO) + amount
    return received


def standing_opening_bills(
    session: Session, *, firm_id: UUID, customer_id: UUID | None
) -> list[CustomerOpeningBill]:
    """Return the opening bills not cancelled, for one customer or all."""
    return list(
        session.scalars(
            select(CustomerOpeningBill)
            .where(
                CustomerOpeningBill.firm_id == firm_id,
                *(
                    ()
                    if customer_id is None
                    else (CustomerOpeningBill.customer_id == customer_id,)
                ),
                CustomerOpeningBill.is_deleted.is_(False),
                CustomerOpeningBill.status == CustomerOpeningBillStatus.POSTED.value,
            )
            .order_by(
                CustomerOpeningBill.bill_date.asc(), CustomerOpeningBill.bill_number
            )
        ).all()
    )


def opening_bills_owed_on(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID | None,
    as_of: date,
) -> list[CustomerOpeningBill]:
    """Return the opening bills that stood on ``as_of``, for the ageing.

    Posted by then, and not cancelled by then: a bill cancelled after the day
    was owed on it (the rule D-FIN-21 set for a sales invoice).
    """
    day_after = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=UTC)
    return list(
        session.scalars(
            select(CustomerOpeningBill).where(
                CustomerOpeningBill.firm_id == firm_id,
                *(
                    ()
                    if customer_id is None
                    else (CustomerOpeningBill.customer_id == customer_id,)
                ),
                CustomerOpeningBill.is_deleted.is_(False),
                CustomerOpeningBill.posting_date <= as_of,
                or_(
                    CustomerOpeningBill.status
                    == CustomerOpeningBillStatus.POSTED.value,
                    CustomerOpeningBill.cancelled_at >= day_after,
                ),
            )
        ).all()
    )


def opening_bill_label(row: CustomerOpeningBill) -> str:
    """Name an opening bill the way the customer would recognise it."""
    if row.reference_number:
        return f"{row.reference_number} (opening)"
    return row.bill_number


class CustomerOpeningBillService:
    """Own the day-one bills a firm's customers owed it."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session

    def list_for_customer(
        self, customer_id: UUID, *, firm_id: UUID, include_cancelled: bool = True
    ) -> list[CustomerOpeningBillResponse]:
        """Return one customer's opening bills, oldest first."""
        customer = self._customer(customer_id, firm_id=firm_id)
        rows = self._session.scalars(
            select(CustomerOpeningBill)
            .where(
                CustomerOpeningBill.firm_id == firm_id,
                CustomerOpeningBill.customer_id == customer.id,
                CustomerOpeningBill.is_deleted.is_(False),
                *(
                    ()
                    if include_cancelled
                    else (
                        CustomerOpeningBill.status
                        == CustomerOpeningBillStatus.POSTED.value,
                    )
                ),
            )
            .order_by(
                CustomerOpeningBill.bill_date.asc(), CustomerOpeningBill.bill_number
            )
        ).all()
        received = opening_bill_receipts(
            self._session, firm_id=firm_id, bill_ids=[row.id for row in rows]
        )
        return [
            self.to_response(row, customer=customer, received=received) for row in rows
        ]

    def get(self, bill_id: UUID, *, firm_id: UUID) -> CustomerOpeningBill:
        """Return one opening bill the firm owns."""
        row = self._session.scalar(
            select(CustomerOpeningBill).where(
                CustomerOpeningBill.id == bill_id,
                CustomerOpeningBill.firm_id == firm_id,
                CustomerOpeningBill.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Opening bill not found.")
        return row

    def response_for(
        self, row: CustomerOpeningBill, *, firm_id: UUID
    ) -> CustomerOpeningBillResponse:
        """Build the response for one opening bill."""
        customer = self._session.get(Customer, row.customer_id)
        if customer is None:  # pragma: no cover - the foreign key guarantees it
            raise ResourceNotFoundError("Customer not found.")
        received = opening_bill_receipts(
            self._session, firm_id=firm_id, bill_ids=[row.id]
        )
        return self.to_response(row, customer=customer, received=received)

    def create(
        self,
        customer_id: UUID,
        data: CustomerOpeningBillWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> CustomerOpeningBill:
        """Record and post one opening bill."""
        customer = self._customer(customer_id, firm_id=firm_id)
        try:
            row = self._stage(customer, data, firm_id=firm_id, actor_id=actor_id)
        except Exception:
            self._session.rollback()
            raise
        self._session.commit()
        return row

    def import_bills(
        self,
        records: list[CustomerOpeningBillImportRow],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[CustomerOpeningBill]:
        """Record a file of opening bills, all of them or none.

        Every customer code is resolved before anything is written, and every
        unknown one is named with its row number in one refusal, so a file is
        corrected in one pass. Then each bill is staged and the batch
        committed once: a posting refused on row 40 leaves nothing of rows 1
        to 39 behind.
        """
        codes = {record.customer_code.strip().upper() for record in records}
        customers = {
            customer.code.upper(): customer
            for customer in self._session.scalars(
                select(Customer).where(
                    Customer.firm_id == firm_id,
                    Customer.is_deleted.is_(False),
                    func.upper(Customer.code).in_(codes),
                )
            ).all()
        }
        unknown = [
            f"row {index}: {record.customer_code}"
            for index, record in enumerate(records, start=1)
            if record.customer_code.strip().upper() not in customers
        ]
        if unknown:
            shown = "; ".join(unknown[:20])
            more = len(unknown) - 20
            raise ValidationError(
                f"No customer has the code given on {len(unknown)} "
                f"row{'' if len(unknown) == 1 else 's'} -- {shown}"
                f"{f' and {more} more' if more > 0 else ''}. Nothing was imported."
            )
        rows: list[CustomerOpeningBill] = []
        try:
            for index, record in enumerate(records, start=1):
                try:
                    rows.append(
                        self._stage(
                            customers[record.customer_code.strip().upper()],
                            record,
                            firm_id=firm_id,
                            actor_id=actor_id,
                        )
                    )
                except ValidationError as error:
                    raise ValidationError(
                        f"Row {index}: {error.message} Nothing was imported."
                    ) from error
        except Exception:
            self._session.rollback()
            raise
        self._session.commit()
        return rows

    def cancel(
        self, bill_id: UUID, *, reason: str, firm_id: UUID, actor_id: UUID
    ) -> CustomerOpeningBill:
        """Take back an opening bill entered in error.

        Refused while any receipt is applied to it: the receipt would be left
        clearing a debt that no longer exists. Reverse the receipt first. The
        journal is mirrored and the customer's balance put back by the exact
        delta the bill's receivable row recorded.
        """
        # Imported here: the journal engine and the customer service reach the
        # settlement models, which import the customer models.
        from app.customers.services.customer_service import CustomerService
        from app.finance.services.journal_engine import JournalEntryEngine

        row = self.get(bill_id, firm_id=firm_id)
        if row.status == CustomerOpeningBillStatus.CANCELLED.value:
            raise ValidationError(f"{row.bill_number} is already cancelled.")
        received = opening_bill_receipts(
            self._session, firm_id=firm_id, bill_ids=[row.id]
        ).get(row.id, ZERO)
        if received > ZERO:
            raise ValidationError(
                f"{received} has been received against {row.bill_number}. "
                "Reverse those receipts before cancelling it."
            )
        try:
            mirror = JournalEntryEngine(self._session).reverse_entry(
                row.journal_entry_id,
                firm_id=firm_id,
                reference_number=f"{row.bill_number}-REV",
                actor_id=actor_id,
            )
            written = self._session.scalar(
                select(CustomerReceivableTransaction).where(
                    CustomerReceivableTransaction.reference_type == REFERENCE_TYPE,
                    CustomerReceivableTransaction.reference_id == row.id,
                    CustomerReceivableTransaction.transaction_type
                    == CustomerReceivableTransactionType.OPENING_BILL.value,
                    CustomerReceivableTransaction.is_deleted.is_(False),
                )
            )
            if written is not None:
                CustomerService(self._session).reverse_receivable_transaction(
                    written.id,
                    firm_scope=firm_id,
                    actor_id=actor_id,
                    reference_number=f"{row.bill_number}-REV",
                    remarks=reason.strip(),
                    commit=False,
                    on=mirror.journal_date,
                )
            row.status = CustomerOpeningBillStatus.CANCELLED.value
            row.reversal_journal_entry_id = mirror.id
            row.cancelled_at = utc_now()
            row.cancelled_by = actor_id
            row.cancellation_reason = reason.strip()
            row.updated_by = actor_id
            record_audit(
                self._session,
                action="customer_opening_bill.cancelled",
                entity_type="customer_opening_bill",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                after_data={"bill_number": row.bill_number, "reason": reason.strip()},
            )
        except Exception:
            self._session.rollback()
            raise
        self._session.commit()
        return row

    def to_response(
        self,
        row: CustomerOpeningBill,
        *,
        customer: Customer,
        received: dict[UUID, Decimal],
    ) -> CustomerOpeningBillResponse:
        """Shape one row, with what is received and still owed on it."""
        amount = quantize_ledger(row.amount)
        received_amount = received.get(row.id, ZERO)
        standing = row.status == CustomerOpeningBillStatus.POSTED.value
        return CustomerOpeningBillResponse(
            id=row.id,
            customer_id=row.customer_id,
            customer_code=customer.code,
            customer_name=customer.display_name,
            bill_number=row.bill_number,
            reference_number=row.reference_number,
            bill_date=row.bill_date,
            due_date=row.due_date,
            posting_date=row.posting_date,
            amount=amount,
            received_amount=received_amount,
            outstanding_amount=amount - received_amount if standing else ZERO,
            narration=row.narration,
            status=row.status,
            journal_entry_id=row.journal_entry_id,
            cancelled_at=row.cancelled_at,
            cancellation_reason=row.cancellation_reason,
            version=row.version,
            created_at=row.created_at,
        )

    def _customer(self, customer_id: UUID, *, firm_id: UUID) -> Customer:
        """Return a live customer of the firm, or refuse."""
        customer = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if customer is None:
            raise ResourceNotFoundError("Customer not found.")
        return customer

    def _stage(
        self,
        customer: Customer,
        data: CustomerOpeningBillWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> CustomerOpeningBill:
        """Post one opening bill, move the balance, and add its row; no commit."""
        # Imported here: the posting service and the customer service reach
        # the settlement models, which import the customer models.
        from app.customers.services.customer_service import CustomerService
        from app.finance.services.document_posting import DocumentPostingService

        if customer.opening_balance != 0:
            raise ValidationError(
                f"{customer.code} carries an opening balance of "
                f"{quantize_ledger(customer.opening_balance)}. Enter the opening "
                "balance either as one figure on the customer or bill by bill, "
                "not both -- set the customer's opening balance to 0 first."
            )
        posting_date = data.posting_date or utc_now().date()
        if data.bill_date > posting_date:
            raise ValidationError(
                "An opening bill is one raised before the books here start, so "
                f"its date cannot be after {posting_date}."
            )
        reference = data.reference_number.strip() if data.reference_number else None
        if reference:
            taken = self._session.scalar(
                select(CustomerOpeningBill.bill_number).where(
                    CustomerOpeningBill.firm_id == firm_id,
                    CustomerOpeningBill.customer_id == customer.id,
                    func.upper(CustomerOpeningBill.reference_number)
                    == reference.upper(),
                    CustomerOpeningBill.status
                    == CustomerOpeningBillStatus.POSTED.value,
                    CustomerOpeningBill.is_deleted.is_(False),
                )
            )
            if taken is not None:
                raise ValidationError(
                    f"{customer.display_name}'s bill {reference} is already "
                    f"recorded as {taken}."
                )
        # A bill with no due date given falls due on the customer's terms, as
        # a sales invoice does -- stored, so later terms do not re-age it.
        due_date = data.due_date or (
            data.bill_date + timedelta(days=int(customer.payment_terms_days or 0))
        )
        amount = quantize_ledger(data.amount)
        number = self._next_number(firm_id=firm_id)
        bill_id = uuid4()
        entry = DocumentPostingService(self._session).post_customer_opening_bill(
            firm_id=firm_id,
            opening_bill_id=bill_id,
            bill_number=number,
            posting_date=posting_date,
            amount=amount,
            actor_id=actor_id,
        )
        row = CustomerOpeningBill(
            id=bill_id,
            firm_id=firm_id,
            customer_id=customer.id,
            bill_number=number,
            reference_number=reference,
            bill_date=data.bill_date,
            due_date=due_date,
            posting_date=posting_date,
            amount=amount,
            narration=data.narration,
            status=CustomerOpeningBillStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        CustomerService(self._session).record_opening_bill(
            customer,
            amount=amount,
            posting_date=posting_date,
            bill_id=row.id,
            bill_number=number,
            label=opening_bill_label(row),
            journal_entry_id=entry.id,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="customer_opening_bill.recorded",
            entity_type="customer_opening_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "bill_number": number,
                "customer": customer.code,
                "reference_number": reference,
                "amount": str(row.amount),
                "posting_date": posting_date.isoformat(),
            },
        )
        return row

    def _next_number(self, *, firm_id: UUID) -> str:
        """Issue the next `OBC-` number, counting cancelled bills too.

        A cancelled bill keeps its number and its journal keeps the reference,
        so counting only standing bills would hand the same number out twice.
        """
        issued = self._session.scalar(
            select(func.count(CustomerOpeningBill.id)).where(
                CustomerOpeningBill.firm_id == firm_id
            )
        )
        return f"OBC-{int(issued or 0) + 1:05d}"
