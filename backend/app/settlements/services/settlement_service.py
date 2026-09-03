"""Record money arriving and money going out, and put it in the ledger.

The gap this closes: `POST /customers/{id}/receivables/transactions` could
already record a receipt, and it moved the customer's outstanding balance
without writing a journal. Using it made the subsidiary ledger and the general
ledger disagree by the amount collected, silently and permanently. Nothing on
the vendor side existed at all.

So a settlement is not a balance adjustment that also posts. It is a document
that posts, and the posting is what makes it real: if the journal cannot be
written -- no control account, no open period -- the settlement is refused
rather than recorded half-way.
"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.models import LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrder
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementMethod,
    SettlementStatus,
)
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementCreate,
)
from app.tcs.services import TcsService
from app.vendors.models import Vendor

#: Which control account the money moved through, by method.
METHOD_PURPOSE = {
    SettlementMethod.CASH: ControlAccountPurpose.CASH,
    SettlementMethod.BANK: ControlAccountPurpose.BANK,
}

#: Invoice states that owe anything. A draft invoice is not a debt, and
#: cancelled invoices are not owed by anybody.
SETTLEABLE_INVOICE_STATES = (
    "APPROVED",
    "COMPLETED",
    "CLOSED",
    "PARTIALLY_PAID",
    "PAID",
)


class SettlementService(TransactionalDocumentService):
    """Record a settlement, allocate it to invoices, and post it."""

    DIRECTION: SettlementDirection

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)
        self._controls = ControlAccountService(session)
        self._customers = CustomerService(session)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def outstanding_invoices(
        self, *, firm_id: UUID, party_id: UUID
    ) -> list[OutstandingInvoiceRecord]:
        """Return the party's invoices that still owe something.

        Outstanding is the invoice total less everything allocated against it,
        computed here rather than stored. A paid-to-date column on the invoice
        would be a second copy of the allocations, and the copy is wrong the
        first time anything writes one without going through this service.

        Totals are rounded to the two decimals money moves in. A document is
        consistent at its own four -- the seeded invoices carry totals like
        `8429.6250` -- and a customer settling one in full pays `8429.63`,
        which an unrounded comparison refuses as more than the invoice owes.
        """
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        invoice: type[SalesInvoice] | type[PurchaseInvoice]
        if is_receipt:
            invoice = SalesInvoice
            party_column = SalesInvoice.customer_id
            allocation_column = SettlementAllocation.sales_invoice_id
        else:
            invoice = PurchaseInvoice
            party_column = PurchaseInvoice.vendor_id
            allocation_column = SettlementAllocation.purchase_invoice_id
        # Joined to the settlement so a reversed one stops clearing anything.
        # The allocation rows stay: the reversed settlement still shows what it
        # had been applied to, which is what somebody asks first when a
        # correction is queried.
        allocated = (
            select(
                allocation_column.label("invoice_id"),
                func.coalesce(func.sum(SettlementAllocation.amount), 0).label("total"),
            )
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .where(
                SettlementAllocation.firm_id == firm_id,
                SettlementAllocation.is_deleted.is_(False),
                Settlement.status == SettlementStatus.POSTED.value,
                allocation_column.is_not(None),
            )
            .group_by(allocation_column)
            .subquery()
        )
        rows = self._session.execute(
            select(invoice, func.coalesce(allocated.c.total, 0))
            .outerjoin(allocated, allocated.c.invoice_id == invoice.id)
            .where(
                invoice.firm_id == firm_id,
                party_column == party_id,
                invoice.is_deleted.is_(False),
                invoice.status.in_(SETTLEABLE_INVOICE_STATES),
            )
            .order_by(invoice.invoice_date.asc(), invoice.invoice_number.asc())
        ).all()
        records: list[OutstandingInvoiceRecord] = []
        for row, allocated_amount in rows:
            already = quantize_ledger(Decimal(allocated_amount))
            total = quantize_ledger(row.grand_total)
            outstanding = total - already
            if outstanding <= ZERO:
                continue
            records.append(
                OutstandingInvoiceRecord(
                    invoice_id=row.id,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_date,
                    invoice_total=total,
                    allocated_amount=already,
                    outstanding_amount=outstanding,
                )
            )
        return records

    def list_settlements(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str = "",
        party_id: UUID | None = None,
    ) -> tuple[Sequence[Settlement], int]:
        """Return one page of settlements, newest first."""
        statement = self._scoped(select(Settlement), firm_id)
        if party_id is not None:
            statement = statement.where(
                Settlement.customer_id == party_id
                if self.DIRECTION == SettlementDirection.RECEIPT
                else Settlement.vendor_id == party_id
            )
        if search.strip():
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                Settlement.settlement_number.ilike(pattern)
                | Settlement.instrument_reference.ilike(pattern)
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                Settlement.settlement_date.desc(),
                Settlement.settlement_number.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, settlement_id: UUID, *, firm_id: UUID) -> Settlement:
        """Return one settlement or raise when it is unavailable."""
        row = self._session.scalar(
            self._scoped(select(Settlement), firm_id).where(
                Settlement.id == settlement_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Settlement not found.")
        return row

    def allocations_for(self, settlement_id: UUID) -> Sequence[SettlementAllocation]:
        """Return the allocations of one settlement, oldest invoice first."""
        return self._session.scalars(
            select(SettlementAllocation)
            .where(
                SettlementAllocation.settlement_id == settlement_id,
                SettlementAllocation.is_deleted.is_(False),
            )
            .order_by(SettlementAllocation.created_at.asc())
        ).all()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(
        self, data: SettlementCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Settlement:
        """Record one settlement, allocate it, and post it to the ledger."""
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        is_refund = self.DIRECTION == SettlementDirection.REFUND
        if is_refund and data.allocations:
            # A refund hands back what was never applied to a
            # document. Allocating it to one would claim it settled
            # something, when it did the opposite.
            raise ValidationError(
                "A refund returns money held on account, so it is not "
                "applied to an invoice."
            )
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        party = self._require_party(firm_id=firm_id, party_id=data.party_id)
        order = self._advance_order(data, firm_id=firm_id)
        amount = quantize_ledger(data.amount)
        allocated = self._validate_allocations(
            data, firm_id=firm_id, party_id=data.party_id, amount=amount
        )
        money_account_id = self._money_account(
            firm_id=firm_id, method=SettlementMethod(data.method.value)
        )
        number = (
            data.settlement_number.strip().upper()
            if data.settlement_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.settlement_date, firm_id
                ),
                company_code=self._company_code(firm_id),
                document_date=data.settlement_date,
                actor_id=actor_id,
            )
        )

        # Both directions of the link are set before either row is written:
        # the journal names the settlement as its source, and the settlement
        # names the journal it wrote. Inserting the settlement first with a
        # placeholder would leave a row referencing nothing if the posting
        # failed, which is the state this module exists to make impossible.
        settlement_id = uuid4()
        entry = (
            self._posting.post_customer_refund(
                firm_id=firm_id,
                settlement_id=settlement_id,
                settlement_number=number,
                settlement_date=data.settlement_date,
                amount=amount,
                money_account_id=money_account_id,
                actor_id=actor_id,
            )
            if is_refund
            else self._posting.post_settlement(
                firm_id=firm_id,
                settlement_id=settlement_id,
                settlement_number=number,
                settlement_date=data.settlement_date,
                amount=amount,
                is_receipt=is_receipt,
                money_account_id=money_account_id,
                actor_id=actor_id,
            )
        )
        row = Settlement(
            id=settlement_id,
            firm_id=firm_id,
            direction=self.DIRECTION.value,
            customer_id=data.party_id if is_receipt or is_refund else None,
            vendor_id=None if is_receipt or is_refund else data.party_id,
            settlement_number=number,
            settlement_date=data.settlement_date,
            amount=amount,
            allocated_amount=allocated,
            unallocated_amount=amount - allocated,
            sales_order_id=None if order is None else order.id,
            method=data.method.value,
            ledger_account_id=money_account_id,
            instrument_reference=(
                data.instrument_reference.strip() if data.instrument_reference else None
            ),
            narration=data.narration,
            status=SettlementStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()

        for allocation in data.allocations:
            self._session.add(
                SettlementAllocation(
                    firm_id=firm_id,
                    settlement_id=row.id,
                    sales_invoice_id=allocation.invoice_id if is_receipt else None,
                    purchase_invoice_id=(None if is_receipt else allocation.invoice_id),
                    amount=quantize_ledger(allocation.amount),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

        if is_refund:
            # The receivable service holds the rule that a refund cannot
            # exceed the advance the customer is actually holding, and
            # refuses it by name.
            self._customers.post_receivable_transaction(
                data.party_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=(CustomerReceivableTransactionType.REFUND),
                    amount=amount,
                    transaction_date=data.settlement_date,
                    reference_type="settlement",
                    reference_id=row.id,
                    reference_number=number,
                    remarks=data.narration,
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
        if is_receipt:
            # Keep the customer's outstanding and advance balances in step, so
            # credit control keeps answering with the money already collected.
            # The receivable service decides for itself how much of a receipt
            # clears the balance and how much becomes an advance, which is the
            # one place that rule should live.
            self._customers.post_receivable_transaction(
                data.party_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.RECEIPT,
                    amount=amount,
                    transaction_date=data.settlement_date,
                    reference_type="settlement",
                    reference_id=row.id,
                    reference_number=number,
                    remarks=data.narration,
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
            # Tax collected at source is charged **here**, on the money, not
            # when the invoice was raised: section 206C(1H) says "at the time
            # of receipt of such amount". Staged rather than committed, so a
            # receipt that posts and a collection that does not cannot both
            # happen -- that would leave the buyer under-charged with nothing
            # on the record to say why. Nothing is charged unless the firm has
            # switched the section on and this buyer is past the threshold.
            TcsService(self._session).stage_collection(
                row, firm_id=firm_id, actor_id=actor_id
            )

        record_audit(
            self._session,
            action=f"settlement.{self.DIRECTION.value.lower()}.recorded",
            entity_type="settlement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "settlement_number": number,
                "amount": str(amount),
                "allocated_amount": str(allocated),
                "party": party.code,
            },
        )
        self._session.flush()
        return row

    def order_number_of(self, row: Settlement) -> str | None:
        """Return the order a receipt came in against, by number."""
        if row.sales_order_id is None:
            return None
        order = self._session.get(SalesOrder, row.sales_order_id)
        return None if order is None else order.order_number

    def _advance_order(
        self, data: SettlementCreate, *, firm_id: UUID
    ) -> SalesOrder | None:
        """Return the order this money came in against, if one was named.

        Refused where it is not this firm's, or not this customer's: an advance
        filed against somebody else's order answers "what has this customer
        paid us for order X" with another customer's money.

        A payment to a vendor has no sales order behind it, so naming one is
        refused rather than quietly ignored -- a field that is accepted and
        discarded is worse than one that is not accepted at all.

        Args:
            data: The settlement being recorded.
            firm_id: The owning firm.

        Returns:
            The order, or None where none was named.

        Raises:
            ValidationError: If the order is not the customer's, or this is not
                a receipt.
            ResourceNotFoundError: If the order is not this firm's.

        """
        if data.sales_order_id is None:
            return None
        if self.DIRECTION != SettlementDirection.RECEIPT:
            raise ValidationError(
                "Only a receipt can be recorded against a sales order."
            )
        order = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == data.sales_order_id,
                SalesOrder.firm_id == firm_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Sales order not found.")
        if order.customer_id != data.party_id:
            raise ValidationError("That sales order belongs to a different customer.")
        return order

    def _advance_part_of(self, row: Settlement, *, allocating: Decimal) -> Decimal:
        """Return how much of this allocation comes out of the advance.

        A receipt splits when it is recorded: `min(amount, outstanding)` comes
        straight off what the customer owes, and only the excess becomes an
        advance. The receivable row it wrote remembers the split, and it is
        the only thing that does.

        So allocating to an invoice has two halves. The part covered by what
        already came off the balance needs **no** receivable transaction --
        the balance moved when the money arrived, and moving it again would
        take the same rupees off twice. Only the part drawn from the advance
        posts `ADVANCE_APPLY`, which is what that type is for.

        In the ordinary case -- a deposit taken while the customer already
        owed something -- the answer is zero, and the allocation is purely a
        statement about which invoice the money cleared.

        Args:
            row: The receipt being allocated.
            allocating: How much of it is being set against an invoice now.

        Returns:
            The part that must come out of the advance, never negative.

        """
        original = self._session.scalar(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.reference_type == "settlement",
                CustomerReceivableTransaction.reference_id == row.id,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
        )
        if original is None:
            # Nothing recorded the split, so nothing can be claimed about it.
            # Treating it as advance would risk the double count this method
            # exists to avoid.
            return ZERO
        off_the_balance = quantize_ledger(-Decimal(str(original.outstanding_delta)))
        if off_the_balance <= ZERO:
            # The whole receipt became an advance.
            return quantize_ledger(allocating)
        already = quantize_ledger(row.allocated_amount)
        remaining = off_the_balance - already
        if remaining >= allocating:
            return ZERO
        return quantize_ledger(allocating - max(remaining, ZERO))

    def allocate(
        self,
        settlement_id: UUID,
        *,
        invoice_id: UUID,
        amount: Decimal,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Settlement:
        """Set money already received against an invoice raised since.

        The missing half of an advance. `ADVANCE_APPLY` has been a declared
        receivable transaction type since the module shipped and **nothing
        could reach it**: a deposit taken before the bill existed sat on the
        customer's account with no way to say which bill it settled.

        **Nothing is posted to the general ledger, and that is correct.** The
        receipt already debited cash and credited receivables; the invoice
        already debited receivables and credited revenue and tax. Applying the
        advance changes no account -- it decides which invoice the receivable
        credit belongs to, which is the subsidiary ledger's business. A journal
        here would count the money twice.

        Args:
            settlement_id: The receipt holding the money.
            invoice_id: The invoice to set it against.
            amount: How much of it.
            firm_id: The owning firm.
            actor_id: The user applying it.

        Returns:
            The settlement, with its allocated and unallocated figures moved.

        Raises:
            ValidationError: If the receipt is reversed, holds less than was
                asked for, or the invoice is not this customer's or owes less.

        """
        row = self.get(settlement_id, firm_id=firm_id)
        if row.status == SettlementStatus.REVERSED.value:
            raise ValidationError(
                f"{row.settlement_number} has been reversed and holds nothing."
            )
        if row.direction != SettlementDirection.RECEIPT.value:
            raise ValidationError("Only a receipt can be applied to an invoice.")
        asked = quantize_ledger(amount)
        if asked <= ZERO:
            raise ValidationError("An allocation must be for more than nothing.")
        if asked > quantize_ledger(row.unallocated_amount):
            raise ValidationError(
                f"{row.settlement_number} has only "
                f"{quantize_ledger(row.unallocated_amount)} left unapplied."
            )
        if row.customer_id is None:  # pragma: no cover - direction guarantees it
            raise ValidationError("Only a receipt can be applied to an invoice.")
        outstanding = {
            record.invoice_id: record
            for record in self.outstanding_invoices(
                firm_id=firm_id, party_id=row.customer_id
            )
        }
        record = outstanding.get(invoice_id)
        if record is None:
            raise ValidationError(
                "That invoice does not belong to this customer, is not "
                "approved, or is already settled in full."
            )
        if asked > record.outstanding_amount:
            raise ValidationError(
                f"{record.invoice_number} owes only {record.outstanding_amount}."
            )
        existing = self._session.scalar(
            select(SettlementAllocation).where(
                SettlementAllocation.settlement_id == row.id,
                SettlementAllocation.sales_invoice_id == invoice_id,
                SettlementAllocation.is_deleted.is_(False),
            )
        )
        if existing is not None:
            # The unique key refuses it anyway; saying so in the language of
            # the request beats a constraint violation.
            raise ValidationError(
                f"{row.settlement_number} is already applied to "
                f"{record.invoice_number}."
            )
        self._session.add(
            SettlementAllocation(
                firm_id=firm_id,
                settlement_id=row.id,
                sales_invoice_id=invoice_id,
                amount=asked,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        from_advance = self._advance_part_of(row, allocating=asked)
        row.allocated_amount = quantize_ledger(row.allocated_amount + asked)
        row.unallocated_amount = quantize_ledger(row.unallocated_amount - asked)
        row.updated_by = actor_id
        if from_advance > ZERO:
            # Only the part that actually became an advance. The rest of the
            # receipt already reduced what the customer owes -- posting
            # ADVANCE_APPLY for it would take the same money off the balance
            # twice. Found by driving it: a deposit taken while the customer
            # owed money creates no advance at all, and the whole allocation
            # was refused with "exceeds unapplied advance".
            self._customers.post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.ADVANCE_APPLY,
                    amount=from_advance,
                    transaction_date=record.invoice_date,
                    reference_type="settlement",
                    reference_id=row.id,
                    reference_number=row.settlement_number,
                    remarks=f"Applied to {record.invoice_number}.",
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
        record_audit(
            self._session,
            action="settlement.receipt.allocated",
            entity_type="settlement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "settlement_number": row.settlement_number,
                "invoice_number": record.invoice_number,
                "amount": str(asked),
                "unallocated_amount": str(row.unallocated_amount),
            },
        )
        self._session.commit()
        return row

    def reverse(
        self,
        settlement_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> Settlement:
        """Take a settlement back, in the ledger and on the party's account.

        Nothing is edited or deleted. A mirror journal cancels the original,
        the allocations stop clearing their invoices, and where the settlement
        moved the customer's outstanding and advance balances they are put back
        by the exact amounts it moved them -- read from the transaction row it
        wrote, not recomputed. A receipt of 500 against an outstanding 300
        became 300 off the balance and 200 of advance, and only that row
        remembers the split.

        **A refund moves that balance too** and is undone the same way. It was
        excluded until 2026-08-22, which was invisible only because no endpoint
        exposed it: `create` posts a receivable transaction for a refund as
        well as for a receipt -- a refund hands back an advance, so the advance
        has to come back when the refund is taken back. Reversing the journal
        alone would have left the ledger right and the customer's advance short
        by the refunded amount. A payment faces a vendor and writes no
        receivable transaction, so there is nothing to put back.

        Args:
            settlement_id: The settlement to take back.
            firm_id: The owning firm.
            actor_id: The user reversing it.
            reason: Why, kept on the record.

        Returns:
            The reversed settlement.

        Raises:
            ValidationError: If it is already reversed, or the customer has
                traded since in a way that makes the undo impossible.

        """
        row = self.get(settlement_id, firm_id=firm_id)
        if row.status == SettlementStatus.REVERSED.value:
            raise ValidationError(f"{row.settlement_number} has already been reversed.")
        mirror = self._journals.reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.settlement_number}-REV",
            actor_id=actor_id,
        )
        if self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        ):
            original = self._session.scalar(
                select(CustomerReceivableTransaction).where(
                    CustomerReceivableTransaction.reference_type == "settlement",
                    CustomerReceivableTransaction.reference_id == row.id,
                    CustomerReceivableTransaction.is_deleted.is_(False),
                )
            )
            if original is not None:
                self._customers.reverse_receivable_transaction(
                    original.id,
                    firm_scope=firm_id,
                    actor_id=actor_id,
                    reference_number=f"{row.settlement_number}-REV",
                    remarks=reason,
                    commit=False,
                )
        if self.DIRECTION == SettlementDirection.RECEIPT:
            # The money is going back, so the tax collected on it goes back
            # too. Mirrored rather than deleted: a quarterly return may
            # already have reported it.
            TcsService(self._session).stage_reversal(
                row, firm_id=firm_id, actor_id=actor_id
            )
        row.status = SettlementStatus.REVERSED.value
        row.reversal_journal_entry_id = mirror.id
        row.reversed_at = utc_now()
        row.reversed_by = actor_id
        row.reversal_reason = reason
        row.updated_by = actor_id
        record_audit(
            self._session,
            action=f"settlement.{self.DIRECTION.value.lower()}.reversed",
            entity_type="settlement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": SettlementStatus.POSTED.value},
            after_data={
                "status": SettlementStatus.REVERSED.value,
                "reversal_journal_entry_id": str(mirror.id),
                "reason": reason,
            },
        )
        self._session.flush()
        return row

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[Settlement]], firm_id: UUID
    ) -> Select[tuple[Settlement]]:
        """Restrict a query to this firm, this direction and live rows."""
        return statement.where(
            Settlement.firm_id == firm_id,
            Settlement.direction == self.DIRECTION.value,
            Settlement.is_deleted.is_(False),
        )

    def _require_party(self, *, firm_id: UUID, party_id: UUID) -> Customer | Vendor:
        """Return the customer or vendor this settlement is with."""
        if self.DIRECTION in (
            SettlementDirection.RECEIPT,
            SettlementDirection.REFUND,
        ):
            customer = self._session.scalar(
                select(Customer).where(
                    Customer.id == party_id,
                    Customer.firm_id == firm_id,
                    Customer.is_deleted.is_(False),
                )
            )
            if customer is None:
                raise ResourceNotFoundError("Customer not found.")
            return customer
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == party_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ResourceNotFoundError("Vendor not found.")
        return vendor

    def _money_account(self, *, firm_id: UUID, method: SettlementMethod) -> UUID:
        """Return the cash or bank account this method moves money through.

        `resolve` refuses with a message naming the purpose when the firm has
        not mapped one, which is the right failure: money cannot be recorded
        as arriving somewhere the firm has not said exists.
        """
        return self._controls.resolve(firm_id, METHOD_PURPOSE[method])

    def _validate_allocations(
        self,
        data: SettlementCreate,
        *,
        firm_id: UUID,
        party_id: UUID,
        amount: Decimal,
    ) -> Decimal:
        """Check every allocation and return the total allocated.

        Three things can be wrong, and each of them writes a lie into the
        books if it is let through: allocating more than arrived, allocating to
        somebody else's invoice, and allocating more to an invoice than is left
        owing on it.
        """
        if not data.allocations:
            return ZERO
        outstanding = {
            record.invoice_id: record
            for record in self.outstanding_invoices(firm_id=firm_id, party_id=party_id)
        }
        total = ZERO
        for allocation in data.allocations:
            record = outstanding.get(allocation.invoice_id)
            if record is None:
                raise ValidationError(
                    "An allocated invoice does not belong to this party, is "
                    "not approved, or is already settled in full."
                )
            allocated = quantize_ledger(allocation.amount)
            if allocated > record.outstanding_amount:
                raise ValidationError(
                    f"Invoice {record.invoice_number} has "
                    f"{record.outstanding_amount} outstanding, so "
                    f"{allocated} cannot be allocated to it."
                )
            total += allocated
        if total > amount:
            raise ValidationError(
                f"Allocations total {total}, which is more than the "
                f"{amount} that moved."
            )
        return total

    def ledger_account_name(self, account_id: UUID) -> str:
        """Return the name of the account money moved through."""
        name = self._session.scalar(
            select(LedgerAccount.name).where(LedgerAccount.id == account_id)
        )
        return name or ""

    def party_of(self, row: Settlement) -> Customer | Vendor:
        """Return the party of one settlement, for the response."""
        party_id = (
            row.customer_id
            if self.DIRECTION
            in (SettlementDirection.RECEIPT, SettlementDirection.REFUND)
            else row.vendor_id
        )
        if party_id is None:  # pragma: no cover - the check constraint forbids it
            raise ValidationError("Settlement has no party.")
        return self._require_party(firm_id=row.firm_id, party_id=party_id)

    def invoice_summaries(
        self, allocations: Sequence[SettlementAllocation]
    ) -> dict[UUID, tuple[str, object, Decimal]]:
        """Return number, date and total for every allocated invoice."""
        is_receipt = self.DIRECTION == SettlementDirection.RECEIPT
        invoice = SalesInvoice if is_receipt else PurchaseInvoice
        ids = [
            (
                allocation.sales_invoice_id
                if is_receipt
                else allocation.purchase_invoice_id
            )
            for allocation in allocations
        ]
        wanted = [value for value in ids if value is not None]
        if not wanted:
            return {}
        rows = self._session.execute(
            select(
                invoice.id,
                invoice.invoice_number,
                invoice.invoice_date,
                invoice.grand_total,
            ).where(invoice.id.in_(wanted))
        ).all()
        return {row[0]: (row[1], row[2], quantize_ledger(row[3])) for row in rows}


class RefundService(SettlementService):
    """Money handed back to a customer.

    Money out, like a payment, and about a customer, like a receipt -- which is
    why it is neither. It returns what a customer paid in advance rather than
    settling anything owed to a supplier, so it touches receivables and not
    payables, and it is not applied to an invoice.
    """

    DIRECTION = SettlementDirection.REFUND
    DOCUMENT = DocumentTypeSpec(
        code="CUSTOMER_REFUND",
        name="Customer Refund",
        description="Money returned to a customer",
        category="FINANCE",
        module="settlements",
        prefix="RF",
        states=(DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),),
    )


class ReceiptService(SettlementService):
    """Money arriving from a customer."""

    DIRECTION = SettlementDirection.RECEIPT
    DOCUMENT = DocumentTypeSpec(
        code="RECEIPT",
        name="Receipt",
        description="Money received from a customer",
        category="FINANCE",
        module="settlements",
        prefix="RC",
        states=(DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),),
    )


class PaymentService(SettlementService):
    """Money going out to a vendor."""

    DIRECTION = SettlementDirection.PAYMENT
    DOCUMENT = DocumentTypeSpec(
        code="PAYMENT",
        name="Payment",
        description="Money paid to a vendor",
        category="FINANCE",
        module="settlements",
        prefix="PY",
        states=(DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),),
    )
