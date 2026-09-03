"""What a customer's account looks like over a period, and what is overdue.

Two questions, answered separately because they have different shapes. A
**statement** is a movement: what the account stood at, everything that happened
to it in date order, and what it stands at now. An **ageing** is a position:
which bills are still unpaid, and how long they have been.

One rule runs through the whole module and is the reason it exists rather than
the raw transaction list being enough. **The running balance is recomputed in
date order, never read off `outstanding_after`.** That column is a snapshot
taken when the row was written, in the order things were *recorded*; a
statement is read in the order things were *dated*. Any backdated document --
which is most of them, since money arrives against a bill raised last month --
makes the two disagree, and the stored one then shows a balance that never
existed on any day.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.schemas.statement import (
    AgeingBucket,
    CustomerAgeing,
    CustomerStatement,
    CustomerStatementLine,
    OverdueInvoice,
)
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement, SettlementAllocation, SettlementStatus

#: The buckets a receivables ageing is read in. Open-ended at the top, because
#: a debt older than the last boundary still has to appear somewhere.
BUCKET_BOUNDS: tuple[int, ...] = (0, 30, 60, 90)

#: Invoice statuses that represent a real debt. A draft is not a sale and a
#: cancelled one has been undone, so neither is owed.
_LIVE_INVOICE_STATUSES = ("APPROVED", "CLOSED")


class CustomerStatementService:
    """Build a customer's account statement and the firm's ageing."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def statement(
        self,
        customer_id: UUID,
        *,
        firm_scope: UUID,
        from_date: date,
        to_date: date,
    ) -> CustomerStatement:
        """Return one customer's account movement over a period.

        The opening balance is **summed from the deltas before the period**,
        which is the same arithmetic that produced the current balance, so the
        two cannot drift apart. Deriving it by subtracting the period's
        movement from today's balance would give the right answer only while
        nothing was ever backdated.

        Args:
            customer_id: The account to report.
            firm_scope: The owning firm.
            from_date: First day of the period.
            to_date: Last day.

        Returns:
            The opening balance, the movement, and the closing balance.

        Raises:
            ValidationError: If the period runs backwards.
            ResourceNotFoundError: If the customer is not this firm's.

        """
        if to_date < from_date:
            raise ValidationError("to_date cannot be before from_date.")
        customer = self._customer(customer_id, firm_scope=firm_scope)

        opening = quantize_ledger(
            self._session.scalar(
                select(
                    func.coalesce(
                        func.sum(CustomerReceivableTransaction.outstanding_delta), 0
                    )
                ).where(
                    CustomerReceivableTransaction.customer_id == customer_id,
                    CustomerReceivableTransaction.firm_id == firm_scope,
                    CustomerReceivableTransaction.is_deleted.is_(False),
                    CustomerReceivableTransaction.transaction_date < from_date,
                )
            )
            or 0
        )

        rows = list(
            self._session.scalars(
                select(CustomerReceivableTransaction).where(
                    CustomerReceivableTransaction.customer_id == customer_id,
                    CustomerReceivableTransaction.firm_id == firm_scope,
                    CustomerReceivableTransaction.is_deleted.is_(False),
                    CustomerReceivableTransaction.transaction_date >= from_date,
                    CustomerReceivableTransaction.transaction_date <= to_date,
                )
                # Date first, then the order they were written. Two things on
                # one day have no other order, and the id is stable where a
                # timestamp would tie.
                .order_by(
                    CustomerReceivableTransaction.transaction_date.asc(),
                    CustomerReceivableTransaction.created_at.asc(),
                    CustomerReceivableTransaction.id.asc(),
                )
            ).all()
        )

        running = opening
        lines: list[CustomerStatementLine] = []
        for row in rows:
            delta = Decimal(str(row.outstanding_delta))
            running += delta
            lines.append(
                CustomerStatementLine(
                    transaction_date=row.transaction_date,
                    transaction_type=row.transaction_type,
                    reference_number=row.reference_number,
                    remarks=row.remarks,
                    # A debit is what the customer owes more of; a credit is
                    # what they owe less of. Split from one signed delta so
                    # the statement reads the way a ledger does.
                    debit=quantize_ledger(delta) if delta > ZERO else ZERO,
                    credit=quantize_ledger(-delta) if delta < ZERO else ZERO,
                    balance=quantize_ledger(running),
                )
            )

        return CustomerStatement(
            customer_id=customer.id,
            customer_code=customer.code,
            customer_name=customer.name,
            from_date=from_date,
            to_date=to_date,
            opening_balance=opening,
            closing_balance=quantize_ledger(running),
            # What is held on account and not yet applied to any bill. Beside
            # the closing balance rather than folded into it: they are
            # different money, and netting them hides an advance a customer is
            # entitled to have applied.
            unapplied_advance=quantize_ledger(customer.unapplied_advance_balance),
            lines=lines,
        )

    def ageing(
        self,
        *,
        firm_scope: UUID,
        customer_id: UUID | None = None,
        as_of: date | None = None,
    ) -> list[CustomerAgeing]:
        """Report what is still unpaid, by how long it has been.

        Outstanding is **derived from the allocations**, never read off the
        invoice: what a bill still owes is a fact about the money received
        against it, and this repo deliberately stores it nowhere.

        Age is counted from the invoice's own due date where it has one, and
        from its date otherwise -- a bill with no terms is due when it is
        raised. `as_of` defaults to today **in UTC**, because everything
        stored here is UTC and the server's local date is already tomorrow, or
        still yesterday, for part of every day.

        Args:
            firm_scope: The owning firm.
            customer_id: Narrow to one customer.
            as_of: The day to age against.

        Returns:
            One row per customer with anything outstanding, buckets and all.

        """
        today = as_of or utc_now().date()
        cleared = (
            select(
                SettlementAllocation.sales_invoice_id.label("invoice_id"),
                func.coalesce(func.sum(SettlementAllocation.amount), 0).label("paid"),
            )
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .where(
                SettlementAllocation.firm_id == firm_scope,
                SettlementAllocation.is_deleted.is_(False),
                SettlementAllocation.sales_invoice_id.is_not(None),
                # A reversed settlement cleared nothing. Counting it would
                # report a bill as paid that the firm has no money for.
                Settlement.status != SettlementStatus.REVERSED.value,
                Settlement.is_deleted.is_(False),
            )
            .group_by(SettlementAllocation.sales_invoice_id)
            .subquery()
        )

        query = (
            select(
                SalesInvoice.id,
                SalesInvoice.customer_id,
                SalesInvoice.invoice_number,
                SalesInvoice.invoice_date,
                SalesInvoice.due_date,
                SalesInvoice.grand_total,
                func.coalesce(cleared.c.paid, 0),
            )
            .outerjoin(cleared, cleared.c.invoice_id == SalesInvoice.id)
            .where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status.in_(_LIVE_INVOICE_STATUSES),
            )
        )
        if customer_id is not None:
            query = query.where(SalesInvoice.customer_id == customer_id)

        overdue: dict[UUID, list[OverdueInvoice]] = defaultdict(list)
        for (
            _invoice_id,
            owner_id,
            number,
            invoice_date,
            due_date,
            total,
            paid,
        ) in self._session.execute(query).all():
            balance = quantize_ledger(Decimal(str(total)) - Decimal(str(paid)))
            if balance <= ZERO:
                continue
            due = due_date or invoice_date
            overdue[owner_id].append(
                OverdueInvoice(
                    invoice_number=number,
                    invoice_date=invoice_date,
                    due_date=due,
                    outstanding=balance,
                    days_overdue=max((today - due).days, 0),
                )
            )
        if not overdue:
            return []

        names = {
            row.id: row
            for row in self._session.scalars(
                select(Customer).where(Customer.id.in_(overdue))
            ).all()
        }
        answer: list[CustomerAgeing] = []
        for owner_id, invoices in overdue.items():
            customer = names.get(owner_id)
            bills = quantize_ledger(sum((row.outstanding for row in invoices), ZERO))
            # What the account says, which is not what the bills say. A credit
            # note or a sales return reduces the account and sits on no
            # invoice; tax collected at source raises it without being billed.
            # The gap is named rather than left for somebody to discover by
            # subtracting two reports.
            balance = quantize_ledger(
                getattr(customer, "current_outstanding", ZERO) or ZERO
            )
            gap = bills - balance
            answer.append(
                CustomerAgeing(
                    customer_id=owner_id,
                    customer_code=getattr(customer, "code", ""),
                    customer_name=getattr(customer, "name", ""),
                    as_of=today,
                    total_outstanding=bills,
                    account_balance=balance,
                    unapplied_credits=quantize_ledger(gap) if gap > ZERO else ZERO,
                    charges_not_billed=quantize_ledger(-gap) if gap < ZERO else ZERO,
                    buckets=self._bucketed(invoices),
                    invoices=sorted(
                        invoices, key=lambda row: row.days_overdue, reverse=True
                    ),
                )
            )
        return sorted(answer, key=lambda row: row.total_outstanding, reverse=True)

    @staticmethod
    def _bucketed(invoices: list[OverdueInvoice]) -> list[AgeingBucket]:
        """Split what is outstanding into the ageing buckets.

        Built from `BUCKET_BOUNDS` rather than written out, so the boundaries
        are stated once. The last bucket is open-ended: a debt older than the
        final boundary still has to appear somewhere, and a set of buckets
        that does not add up to the total is one nobody can reconcile.

        Args:
            invoices: What is outstanding for one customer.

        Returns:
            One bucket per band, in order, including empty ones.

        """
        buckets = [
            AgeingBucket(
                from_days=lower,
                to_days=(
                    BUCKET_BOUNDS[index + 1] - 1
                    if index + 1 < len(BUCKET_BOUNDS)
                    else None
                ),
                amount=ZERO,
            )
            for index, lower in enumerate(BUCKET_BOUNDS)
        ]
        for invoice in invoices:
            slot = 0
            for index, lower in enumerate(BUCKET_BOUNDS):
                if invoice.days_overdue >= lower:
                    slot = index
            buckets[slot].amount = quantize_ledger(
                buckets[slot].amount + invoice.outstanding
            )
        return buckets

    def _customer(self, customer_id: UUID, *, firm_scope: UUID) -> Customer:
        """Return one of this firm's customers."""
        row = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_scope,
                Customer.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Customer not found.")
        return row
