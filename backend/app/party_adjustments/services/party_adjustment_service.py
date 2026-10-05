"""Drafting, approving and cancelling a party adjustment (backlog 74 row 2).

A balance moved without money and without tax: a customer's debt written off,
a supplier's balance written back, or the two set off against each other when
the customer and the supplier are the same business.

**It posts at approval and nowhere else.** A draft moves nothing -- its
allocations are not counted by any derivation of what a bill owes, because
`adjusted_against` reads approved adjustments only. Approval posts the journal,
writes the customer's receivable row where a customer is named, and from that
moment the bills it names owe less. Cancelling mirrors the journal and puts the
customer's balance back **by the deltas the approval stored**, and the bills
owe again because the derivation stops counting a cancelled adjustment.

**Approval above the firm's threshold is a second person's.** At or below it
(1,000.00 unless the firm sets another) anyone who may manage adjustments may
approve one, their own included -- clearing a few rupees should not need two
people. Above it the approver must hold `PARTY_ADJUSTMENT_APPROVE` and must not
be the person who drafted it: writing off a debt is giving away profit, and the
maker-checker split is the control an auditor looks for.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.report_names import (
    customer_names,
    customers_matching,
    vendor_names,
    vendors_matching,
)
from app.core.concurrency import assert_version
from app.core.database.batch import children_by_parent
from app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer, CustomerOpeningBill
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.customers.services.opening_bill_service import (
    opening_bill_label as customer_opening_bill_label,
)
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.party_adjustments.models import (
    PartyAdjustment,
    PartyAdjustmentAllocation,
    PartyAdjustmentKind,
    PartyAdjustmentStatus,
)
from app.party_adjustments.schemas import (
    PartyAdjustmentAllocationResponse,
    PartyAdjustmentAllocationWrite,
    PartyAdjustmentCreate,
    PartyAdjustmentKindEnum,
    PartyAdjustmentOpenBills,
    PartyAdjustmentRegisterRecord,
    PartyAdjustmentResponse,
    PartyAdjustmentSideEnum,
    PartyAdjustmentStatusEnum,
    PartyAdjustmentUpdate,
)
from app.party_adjustments.services.settings import adjustment_limits
from app.purchase_invoice.models import PurchaseInvoice
from app.sales_invoice.models import SalesInvoice
from app.settlements.schemas import OutstandingInvoiceRecord
from app.settlements.services.settlement_service import (
    PaymentService,
    ReceiptService,
)
from app.vendors.models import Vendor, VendorOpeningBill
from app.vendors.services.opening_bill_service import opening_bill_label

#: The receivable row each kind writes on the customer's account.
_RECEIVABLE_TYPE = {
    PartyAdjustmentKind.CUSTOMER_WRITE_OFF.value: (
        CustomerReceivableTransactionType.WRITE_OFF
    ),
    PartyAdjustmentKind.SET_OFF.value: CustomerReceivableTransactionType.SET_OFF,
    PartyAdjustmentKind.CUSTOMER_REBATE.value: (
        CustomerReceivableTransactionType.REBATE
    ),
}

_KIND_NAMES = {
    PartyAdjustmentKind.CUSTOMER_WRITE_OFF.value: "write-off",
    PartyAdjustmentKind.SUPPLIER_WRITE_BACK.value: "write-back",
    PartyAdjustmentKind.SET_OFF.value: "set-off",
    PartyAdjustmentKind.SUPPLIER_REBATE.value: "rebate settlement",
    PartyAdjustmentKind.PRINCIPAL_CLAIM.value: "claim settlement",
    PartyAdjustmentKind.CUSTOMER_REBATE.value: "rebate settlement",
}


def _has_customer(kind: str) -> bool:
    """Say whether a kind names a customer."""
    return kind not in (
        PartyAdjustmentKind.SUPPLIER_WRITE_BACK.value,
        PartyAdjustmentKind.SUPPLIER_REBATE.value,
        PartyAdjustmentKind.PRINCIPAL_CLAIM.value,
    )


def _has_vendor(kind: str) -> bool:
    """Say whether a kind names a supplier."""
    return kind not in (
        PartyAdjustmentKind.CUSTOMER_WRITE_OFF.value,
        PartyAdjustmentKind.CUSTOMER_REBATE.value,
    )


def _pan_of(pan: str | None, gstin: str | None) -> str | None:
    """Return a party's PAN, read off its GSTIN where none is recorded.

    Characters three to twelve of a GSTIN are the holder's PAN.
    """
    if pan and pan.strip():
        return pan.strip().upper()
    if gstin and len(gstin.strip()) >= 12:
        return gstin.strip().upper()[2:12]
    return None


class PartyAdjustmentService(TransactionalDocumentService):
    """Move a party's balance without money and without tax."""

    DOCUMENT = DocumentTypeSpec(
        code="PARTY_ADJUSTMENT",
        name="Party Adjustment",
        description="Write-off, write-back or set-off of a party balance",
        category="FINANCE",
        module="party_adjustments",
        prefix="PA",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 2),
            DocumentStateSpec("CANCELLED", "Cancelled", 3, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)
        self._customers = CustomerService(session)

    # ---- reads ---------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[PartyAdjustment]], firm_id: UUID
    ) -> Select[tuple[PartyAdjustment]]:
        """Restrict a query to one firm's live adjustments."""
        return statement.where(
            PartyAdjustment.firm_id == firm_id,
            PartyAdjustment.is_deleted.is_(False),
        )

    def list_adjustments(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        kind: PartyAdjustmentKindEnum | None = None,
        status: PartyAdjustmentStatusEnum | None = None,
        customer_id: UUID | None = None,
        vendor_id: UUID | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[PartyAdjustment], int]:
        """Return one page of adjustments, newest first.

        Args:
            firm_scope: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            kind: Restrict to one kind.
            status: Restrict to one state.
            customer_id: Restrict to one customer.
            vendor_id: Restrict to one supplier.
            search: Match the number or reason, or either party.
            date_from: The first adjustment date to include.
            date_to: The last adjustment date to include.

        Returns:
            The page of adjustments and the total matching count.

        """
        statement = self._scoped(select(PartyAdjustment), firm_scope)
        if kind is not None:
            statement = statement.where(PartyAdjustment.kind == kind.value)
        if status is not None:
            statement = statement.where(PartyAdjustment.status == status.value)
        if customer_id is not None:
            statement = statement.where(PartyAdjustment.customer_id == customer_id)
        if vendor_id is not None:
            statement = statement.where(PartyAdjustment.vendor_id == vendor_id)
        if search and search.strip():
            token = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    PartyAdjustment.adjustment_number.ilike(token),
                    PartyAdjustment.reason.ilike(token),
                    PartyAdjustment.customer_id.in_(customers_matching(token)),
                    PartyAdjustment.vendor_id.in_(vendors_matching(token)),
                )
            )
        if date_from is not None:
            statement = statement.where(PartyAdjustment.adjustment_date >= date_from)
        if date_to is not None:
            statement = statement.where(PartyAdjustment.adjustment_date <= date_to)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                PartyAdjustment.adjustment_date.desc(),
                PartyAdjustment.adjustment_number.desc(),
                PartyAdjustment.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, adjustment_id: UUID, *, firm_scope: UUID) -> PartyAdjustment:
        """Return one adjustment.

        Raises:
            ResourceNotFoundError: If the firm has no such live adjustment.

        """
        row = self._session.scalar(
            self._scoped(select(PartyAdjustment), firm_scope).where(
                PartyAdjustment.id == adjustment_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Party adjustment not found.")
        return row

    def allocations_of(self, row: PartyAdjustment) -> list[PartyAdjustmentAllocation]:
        """Return one adjustment's allocations, in the order written."""
        return list(
            self._session.scalars(
                select(PartyAdjustmentAllocation)
                .where(
                    PartyAdjustmentAllocation.party_adjustment_id == row.id,
                    PartyAdjustmentAllocation.is_deleted.is_(False),
                )
                .order_by(
                    PartyAdjustmentAllocation.created_at.asc(),
                    PartyAdjustmentAllocation.id.asc(),
                )
            ).all()
        )

    def open_bills(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        vendor_id: UUID | None,
    ) -> PartyAdjustmentOpenBills:
        """Return what each named party still owes, or is owed, bill by bill.

        Through the one derivation Record Receipt and Record Payment read, so
        the editor offers exactly the bills those screens would.
        """
        customer_bills: list[OutstandingInvoiceRecord] = []
        supplier_bills: list[OutstandingInvoiceRecord] = []
        balance: Decimal | None = None
        owed: Decimal | None = None
        if customer_id is not None:
            customer = self._customer(customer_id, firm_id=firm_id)
            customer_bills = ReceiptService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=customer_id
            )
            balance = quantize_ledger(customer.current_outstanding)
        if vendor_id is not None:
            self._vendor(vendor_id, firm_id=firm_id)
            supplier_bills = PaymentService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=vendor_id
            )
            owed = sum((bill.outstanding_amount for bill in supplier_bills), ZERO)
        return PartyAdjustmentOpenBills(
            customer_bills=customer_bills,
            supplier_bills=supplier_bills,
            customer_balance=balance,
            supplier_outstanding=owed,
        )

    # ---- writes --------------------------------------------------------

    def create(
        self, data: PartyAdjustmentCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PartyAdjustment:
        """Stage a draft; the caller commits.

        Checked now as well as at approval, so a draft that could never be
        approved is refused while somebody is still looking at it.

        Raises:
            ValidationError: If the parties do not fit the kind, an allocation
                does not fit its bill, or the amount is more than can move.

        """
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        kind = data.kind.value
        amount = quantize_ledger(data.amount)
        self._check(
            firm_id=firm_id,
            kind=kind,
            customer_id=data.customer_id,
            vendor_id=data.vendor_id,
            amount=amount,
            allocations=data.allocations,
            rebate_agreement_id=data.rebate_agreement_id,
            principal_claim_id=data.principal_claim_id,
            customer_rebate_agreement_id=data.customer_rebate_agreement_id,
        )
        number = self._issue_number(
            numbering_rule,
            typed=(
                data.adjustment_number.strip().upper()
                if data.adjustment_number
                else None
            ),
            number_column=PartyAdjustment.adjustment_number,
            firm_id=firm_id,
            document_date=data.adjustment_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        row = PartyAdjustment(
            firm_id=firm_id,
            adjustment_number=number,
            adjustment_date=data.adjustment_date,
            kind=kind,
            customer_id=data.customer_id if _has_customer(kind) else None,
            vendor_id=data.vendor_id if _has_vendor(kind) else None,
            amount=amount,
            reason=data.reason,
            status=PartyAdjustmentStatus.DRAFT.value,
            rebate_agreement_id=data.rebate_agreement_id,
            principal_claim_id=data.principal_claim_id,
            customer_rebate_agreement_id=data.customer_rebate_agreement_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Party adjustment number already exists in this firm.")
        self._replace_allocations(row, data.allocations, actor_id=actor_id)
        self._record_event(row, action="CREATED", from_state=None, actor_id=actor_id)
        record_audit(
            self._session,
            action="party_adjustment.created",
            entity_type="party_adjustment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def update(
        self,
        adjustment_id: UUID,
        data: PartyAdjustmentUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> PartyAdjustment:
        """Change a draft; absent fields are left alone. The caller commits.

        The kind and the status are not in the write model: the kind decides
        which parties and accounts the adjustment has, and the status belongs
        to approve and cancel.

        Raises:
            ValidationError: If it has left DRAFT, or the result fails the
                checks a new draft must pass.

        """
        row = self.get(adjustment_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != PartyAdjustmentStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft adjustment can be changed. Cancel this one and "
                "raise another."
            )
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        customer_id = values.get("customer_id", row.customer_id)
        vendor_id = values.get("vendor_id", row.vendor_id)
        amount = quantize_ledger(values.get("amount") or row.amount)
        allocations = (
            data.allocations
            if "allocations" in data.model_fields_set and data.allocations is not None
            else self._as_writes(row)
        )
        self._check(
            firm_id=firm_scope,
            kind=row.kind,
            customer_id=customer_id,
            vendor_id=vendor_id,
            amount=amount,
            allocations=allocations,
            # What a settlement settles is fixed at creation, like its kind;
            # without these an edited draft was told to name what it names.
            rebate_agreement_id=row.rebate_agreement_id,
            principal_claim_id=row.principal_claim_id,
            customer_rebate_agreement_id=row.customer_rebate_agreement_id,
        )
        if values.get("adjustment_date") is not None:
            row.adjustment_date = values["adjustment_date"]
        if values.get("reason") is not None:
            row.reason = values["reason"]
        row.customer_id = customer_id if _has_customer(row.kind) else None
        row.vendor_id = vendor_id if _has_vendor(row.kind) else None
        row.amount = amount
        if "allocations" in data.model_fields_set and data.allocations is not None:
            self._replace_allocations(row, data.allocations, actor_id=actor_id)
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row, action="EDITED", from_state=row.status, actor_id=actor_id
        )
        record_audit(
            self._session,
            action="party_adjustment.updated",
            entity_type="party_adjustment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def approve(
        self,
        adjustment_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_approve_above_threshold: bool,
        expected_version: int | None = None,
    ) -> PartyAdjustment:
        """Post the adjustment: the journal, the customer's account, the bills.

        The caller commits.

        Args:
            adjustment_id: The draft to approve.
            firm_scope: The owning firm.
            actor_id: The user approving it.
            may_approve_above_threshold: Whether they hold
                `PARTY_ADJUSTMENT_APPROVE`.
            expected_version: The version the caller last read, if any.

        Returns:
            The approved adjustment.

        Raises:
            ValidationError: If it is not a draft, or no longer fits what the
                parties and bills owe.
            AuthorizationError: If it is above the threshold and the approver
                lacks the authority or drafted it.

        """
        row = self.get(adjustment_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != PartyAdjustmentStatus.DRAFT.value:
            raise ValidationError("Only a draft adjustment can be approved.")
        self._assert_may_decide(
            row,
            actor_id=actor_id,
            may_approve_above_threshold=may_approve_above_threshold,
            doing="approve",
        )
        self._lock_parties(row)
        # Checked again under the lock: a receipt or another adjustment may
        # have cleared the bills since the draft was written.
        self._check(
            firm_id=firm_scope,
            kind=row.kind,
            customer_id=row.customer_id,
            vendor_id=row.vendor_id,
            amount=quantize_ledger(row.amount),
            allocations=self._as_writes(row),
            rebate_agreement_id=row.rebate_agreement_id,
            principal_claim_id=row.principal_claim_id,
            customer_rebate_agreement_id=row.customer_rebate_agreement_id,
        )
        before = self._snapshot(row)
        entry = self._posting.post_party_adjustment(
            firm_id=firm_scope,
            adjustment_id=row.id,
            adjustment_number=row.adjustment_number,
            adjustment_date=row.adjustment_date,
            kind=row.kind,
            amount=Decimal(str(row.amount)),
            actor_id=actor_id,
        )
        row.journal_entry_id = entry.id
        receivable_type = _RECEIVABLE_TYPE.get(row.kind)
        if receivable_type is not None and row.customer_id is not None:
            # The customer's own account moves with the ledger, both or
            # neither: the journal above credited the receivable by exactly
            # this amount.
            written = self._customers.post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=receivable_type,
                    amount=quantize_ledger(row.amount),
                    transaction_date=row.adjustment_date,
                    reference_type="party_adjustment",
                    reference_id=row.id,
                    reference_number=row.adjustment_number,
                    remarks=row.reason,
                ),
                firm_scope=firm_scope,
                actor_id=actor_id,
                commit=False,
            )
            row.receivable_transaction_id = written.id
        row.status = PartyAdjustmentStatus.APPROVED.value
        row.approved_at = utc_now()
        row.approved_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="APPROVED",
            from_state=PartyAdjustmentStatus.DRAFT.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="party_adjustment.approved",
            entity_type="party_adjustment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def cancel(
        self,
        adjustment_id: UUID,
        *,
        reason: str,
        firm_scope: UUID,
        actor_id: UUID,
        may_approve_above_threshold: bool,
        expected_version: int | None = None,
    ) -> PartyAdjustment:
        """Withdraw an adjustment, undoing whatever it did. The caller commits.

        A draft simply stops. An approved one has its journal mirrored and the
        customer's receivable row undone by its own stored deltas; the bills
        owe again because a cancelled adjustment is no longer counted.
        Cancelling an approved adjustment above the threshold needs the same
        authority approving it did -- undoing a write-off is as much a
        decision about the books as making one.

        Raises:
            ValidationError: If it is already cancelled or no reason is given.
            AuthorizationError: If it is an approved one above the threshold
                and the actor lacks `PARTY_ADJUSTMENT_APPROVE`.

        """
        row = self.get(adjustment_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status == PartyAdjustmentStatus.CANCELLED.value:
            raise ValidationError("This adjustment is already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the adjustment is being cancelled.")
        was = row.status
        before = self._snapshot(row)
        if was == PartyAdjustmentStatus.APPROVED.value:
            limits = adjustment_limits(self._session, firm_scope)
            if (
                quantize_ledger(row.amount) > limits.approval_threshold
                and not may_approve_above_threshold
            ):
                raise AuthorizationError(
                    f"{row.adjustment_number} is above "
                    f"{quantize_ledger(limits.approval_threshold)}, so cancelling "
                    "it needs PARTY_ADJUSTMENT_APPROVE."
                )
            if row.journal_entry_id is None:  # pragma: no cover - approval sets it
                raise ValidationError("This adjustment never posted a journal.")
            mirror = self._journals.reverse_entry(
                row.journal_entry_id,
                firm_id=firm_scope,
                reference_number=f"{row.adjustment_number}-REV",
                actor_id=actor_id,
            )
            row.reversal_journal_entry_id = mirror.id
            if row.receivable_transaction_id is not None:
                self._customers.reverse_receivable_transaction(
                    row.receivable_transaction_id,
                    firm_scope=firm_scope,
                    actor_id=actor_id,
                    reference_number=f"{row.adjustment_number}-REV",
                    remarks=reason.strip(),
                    commit=False,
                    on=mirror.journal_date,
                )
        row.status = PartyAdjustmentStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="CANCELLED",
            from_state=was,
            actor_id=actor_id,
            remarks=row.cancel_reason,
        )
        record_audit(
            self._session,
            action="party_adjustment.cancelled",
            entity_type="party_adjustment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    # ---- rules ---------------------------------------------------------

    def _assert_may_decide(
        self,
        row: PartyAdjustment,
        *,
        actor_id: UUID,
        may_approve_above_threshold: bool,
        doing: str,
    ) -> None:
        """Refuse an approval the firm's threshold reserves for somebody else.

        Raises:
            AuthorizationError: If the amount is above the threshold and the
                actor lacks `PARTY_ADJUSTMENT_APPROVE` or drafted it.

        """
        limits = adjustment_limits(self._session, row.firm_id)
        if quantize_ledger(row.amount) <= limits.approval_threshold:
            return
        threshold = quantize_ledger(limits.approval_threshold)
        if not may_approve_above_threshold:
            raise AuthorizationError(
                f"{row.adjustment_number} is for {quantize_ledger(row.amount)}, "
                f"above this firm's {threshold}, so to {doing} it needs "
                "PARTY_ADJUSTMENT_APPROVE."
            )
        if row.created_by == actor_id:
            raise AuthorizationError(
                f"{row.adjustment_number} is above {threshold}, so somebody "
                "other than the person who drafted it has to approve it."
            )

    def _check(
        self,
        *,
        firm_id: UUID,
        kind: str,
        customer_id: UUID | None,
        vendor_id: UUID | None,
        amount: Decimal,
        allocations: Sequence[PartyAdjustmentAllocationWrite],
        rebate_agreement_id: UUID | None = None,
        principal_claim_id: UUID | None = None,
        customer_rebate_agreement_id: UUID | None = None,
    ) -> None:
        """Refuse an adjustment that does not fit its parties and bills.

        Each side is capped by what that party actually owes or is owed: the
        customer's balance on account (a write-off past it would turn given-up
        debt into an advance), the supplier's open bills (a write-back past
        them would leave the firm owed by its supplier), and, for a set-off,
        both. Each allocation is capped by what its bill still owes, and a
        side's allocations by the amount.

        Raises:
            ValidationError: Naming the first thing that does not fit.

        """
        name = _KIND_NAMES[kind]
        customer: Customer | None = None
        vendor: Vendor | None = None
        if _has_customer(kind):
            if customer_id is None:
                raise ValidationError(f"Name the customer for a {name}.")
            customer = self._customer(customer_id, firm_id=firm_id)
        elif customer_id is not None:
            raise ValidationError(f"A {name} names no customer.")
        if _has_vendor(kind):
            if vendor_id is None:
                raise ValidationError(f"Name the supplier for a {name}.")
            vendor = self._vendor(vendor_id, firm_id=firm_id)
        elif vendor_id is not None:
            raise ValidationError(f"A {name} names no supplier.")
        if customer is not None and vendor is not None:
            self._same_business(customer, vendor)
        if kind == PartyAdjustmentKind.SUPPLIER_REBATE.value:
            # Imported here: the rebate service reads these adjustments.
            from app.supplier_rebates.services import SupplierRebateService

            if vendor is None or rebate_agreement_id is None:
                raise ValidationError("Name the rebate agreement this settles.")
            due = SupplierRebateService(self._session).to_settle(
                rebate_agreement_id, firm_id=firm_id, vendor_id=vendor.id
            )
            if amount > due:
                raise ValidationError(
                    f"The rebate has {due} still to settle, so {amount} cannot "
                    "be set against the supplier's bills."
                )

        if kind == PartyAdjustmentKind.PRINCIPAL_CLAIM.value:
            # Imported here: the claim service reads these adjustments.
            from app.principal_claims.services import PrincipalClaimService

            if vendor is None or principal_claim_id is None:
                raise ValidationError("Name the claim this settles.")
            owed = PrincipalClaimService(self._session).to_settle(
                principal_claim_id, firm_id=firm_id, vendor_id=vendor.id
            )
            if amount > owed:
                raise ValidationError(
                    f"The claim has {owed} still to settle, so {amount} cannot "
                    "be set against the supplier's bills."
                )

        if kind == PartyAdjustmentKind.CUSTOMER_REBATE.value:
            # Imported here: the rebate service reads these adjustments.
            from app.customer_rebates.services import CustomerRebateService

            if customer is None or customer_rebate_agreement_id is None:
                raise ValidationError("Name the rebate agreement this settles.")
            unsettled = CustomerRebateService(self._session).to_settle(
                customer_rebate_agreement_id,
                firm_id=firm_id,
                customer_id=customer.id,
            )
            if amount > unsettled:
                raise ValidationError(
                    f"The rebate has {unsettled} still to settle, so {amount} "
                    "cannot be set against the customer's account."
                )

        sides: dict[PartyAdjustmentSideEnum, list[PartyAdjustmentAllocationWrite]] = {
            PartyAdjustmentSideEnum.CUSTOMER: [],
            PartyAdjustmentSideEnum.SUPPLIER: [],
        }
        for item in allocations:
            sides[item.side].append(item)
        if customer is None and sides[PartyAdjustmentSideEnum.CUSTOMER]:
            raise ValidationError(f"A {name} clears no customer's bills.")
        if vendor is None and sides[PartyAdjustmentSideEnum.SUPPLIER]:
            raise ValidationError(f"A {name} clears no supplier's bills.")

        if customer is not None:
            balance = quantize_ledger(customer.current_outstanding)
            if amount > balance:
                raise ValidationError(
                    f"{customer.name} owes {balance} on account, so {amount} "
                    f"cannot be moved by a {name}."
                )
            self._check_side(
                sides[PartyAdjustmentSideEnum.CUSTOMER],
                ReceiptService(self._session).outstanding_invoices(
                    firm_id=firm_id, party_id=customer.id
                ),
                amount=amount,
                party=customer.name,
            )
        if vendor is not None:
            open_bills = PaymentService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=vendor.id
            )
            owed = sum((bill.outstanding_amount for bill in open_bills), ZERO)
            if amount > owed:
                raise ValidationError(
                    f"{vendor.name}'s open bills add up to {owed}, so {amount} "
                    f"cannot be moved by a {name}."
                )
            self._check_side(
                sides[PartyAdjustmentSideEnum.SUPPLIER],
                open_bills,
                amount=amount,
                party=vendor.name,
            )

    @staticmethod
    def _check_side(
        allocations: Sequence[PartyAdjustmentAllocationWrite],
        open_bills: Sequence[OutstandingInvoiceRecord],
        *,
        amount: Decimal,
        party: str,
    ) -> None:
        """Refuse an allocation past its bill, or a side past the amount."""
        owing = {bill.invoice_id: bill for bill in open_bills}
        total = ZERO
        for item in allocations:
            bill = owing.get(item.bill_id)
            if bill is None:
                raise ValidationError(
                    f"A bill named is not {party}'s, is not approved, or is "
                    "already settled in full."
                )
            asked = quantize_ledger(item.amount)
            if asked > bill.outstanding_amount:
                raise ValidationError(
                    f"{bill.invoice_number} owes {bill.outstanding_amount}, so "
                    f"{asked} cannot come off it."
                )
            total += asked
        if total > amount:
            raise ValidationError(
                f"The bills of {party} named take {total}, more than the "
                f"{amount} being adjusted."
            )

    @staticmethod
    def _same_business(customer: Customer, vendor: Vendor) -> None:
        """Refuse a set-off between two businesses that are plainly different.

        Decided by convention (2026-10-01): the person setting off states that
        they are one business -- since ACC-11 the customer may name its
        supplier record (``linked_vendor_id``), which the screen preselects,
        but an unlinked pair is still allowed. Where both carry a PAN --
        recorded, or read off the GSTIN -- and the two differ, they are not,
        and settling one's debt with the other's money is refused.
        """
        ours = _pan_of(customer.pan_number, customer.gst_number)
        theirs = _pan_of(vendor.pan, vendor.gstin)
        if ours and theirs and ours != theirs:
            raise ValidationError(
                f"{customer.name} (PAN {ours}) and {vendor.name} (PAN {theirs}) "
                "are different businesses, so one's balance cannot be set off "
                "against the other's."
            )

    def _lock_parties(self, row: PartyAdjustment) -> None:
        """Hold the parties' rows while their balances are re-read and moved.

        Two approvals for one party would otherwise both read the same room
        under the balance -- a sum, which no row version protects.
        """
        if row.customer_id is not None:
            self._session.execute(
                select(Customer.id)
                .where(Customer.id == row.customer_id)
                .with_for_update()
            )
        if row.vendor_id is not None:
            self._session.execute(
                select(Vendor.id).where(Vendor.id == row.vendor_id).with_for_update()
            )

    def _customer(self, customer_id: UUID, *, firm_id: UUID) -> Customer:
        """Return one of this firm's customers."""
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

    def _vendor(self, vendor_id: UUID, *, firm_id: UUID) -> Vendor:
        """Return one of this firm's suppliers."""
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ResourceNotFoundError("Vendor not found.")
        return vendor

    # ---- allocations ---------------------------------------------------

    def _replace_allocations(
        self,
        row: PartyAdjustment,
        allocations: Sequence[PartyAdjustmentAllocationWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Write a draft's allocations, replacing whatever it had.

        A draft's rows are deleted outright rather than soft-deleted: nothing
        has ever counted them, and a soft-deleted row would hold the unique
        key against the same bill being named again.
        """
        for existing in self.allocations_of(row):
            self._session.delete(existing)
        self._session.flush()
        customer_opening = self._opening_ids(
            CustomerOpeningBill,
            [
                item.bill_id
                for item in allocations
                if item.side == PartyAdjustmentSideEnum.CUSTOMER
            ],
        )
        vendor_opening = self._opening_ids(
            VendorOpeningBill,
            [
                item.bill_id
                for item in allocations
                if item.side == PartyAdjustmentSideEnum.SUPPLIER
            ],
        )
        for item in allocations:
            on_customer = item.side == PartyAdjustmentSideEnum.CUSTOMER
            opening = item.bill_id in (
                customer_opening if on_customer else vendor_opening
            )
            self._session.add(
                PartyAdjustmentAllocation(
                    firm_id=row.firm_id,
                    party_adjustment_id=row.id,
                    sales_invoice_id=(
                        item.bill_id if on_customer and not opening else None
                    ),
                    customer_opening_bill_id=(
                        item.bill_id if on_customer and opening else None
                    ),
                    purchase_invoice_id=(
                        item.bill_id if not on_customer and not opening else None
                    ),
                    vendor_opening_bill_id=(
                        item.bill_id if not on_customer and opening else None
                    ),
                    amount=quantize_ledger(item.amount),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def _opening_ids(
        self,
        model: type[CustomerOpeningBill] | type[VendorOpeningBill],
        ids: Sequence[UUID],
    ) -> set[UUID]:
        """Say which of the ids are opening bills of one kind."""
        if not ids:
            return set()
        return set(
            self._session.scalars(select(model.id).where(model.id.in_(list(ids))))
        )

    def _as_writes(self, row: PartyAdjustment) -> list[PartyAdjustmentAllocationWrite]:
        """Return a stored adjustment's allocations in their write shape."""
        writes: list[PartyAdjustmentAllocationWrite] = []
        for item in self.allocations_of(row):
            side, bill_id = _side_of(item)
            writes.append(
                PartyAdjustmentAllocationWrite(
                    side=side, bill_id=bill_id, amount=item.amount
                )
            )
        return writes

    def _record_event(
        self,
        row: PartyAdjustment,
        *,
        action: str,
        from_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> None:
        """Append one step to the adjustment's timeline."""
        self._record_lifecycle_event(
            firm_id=row.firm_id,
            document_type=self._document_type(row.firm_id),
            document_id=row.id,
            document_number=row.adjustment_number,
            action=action,
            from_state=from_state,
            to_state=row.status,
            actor_id=actor_id,
            remarks=remarks,
            details={
                "adjustment_number": row.adjustment_number,
                "kind": row.kind,
                "amount": str(row.amount),
            },
            snapshot={"status": row.status},
        )

    def _snapshot(self, row: PartyAdjustment) -> dict[str, object]:
        """Describe an adjustment for the audit trail."""
        return {
            "adjustment_number": row.adjustment_number,
            "adjustment_date": row.adjustment_date.isoformat(),
            "kind": row.kind,
            "status": row.status,
            "customer_id": str(row.customer_id) if row.customer_id else None,
            "vendor_id": str(row.vendor_id) if row.vendor_id else None,
            "amount": str(row.amount),
            "reason": row.reason,
            "allocations": [
                {"bill_id": str(_side_of(item)[1]), "amount": str(item.amount)}
                for item in self.allocations_of(row)
            ],
            "journal_entry_id": (
                str(row.journal_entry_id) if row.journal_entry_id else None
            ),
            "cancel_reason": row.cancel_reason,
        }

    # ---- responses -----------------------------------------------------

    def response(self, row: PartyAdjustment) -> PartyAdjustmentResponse:
        """Build the response for one adjustment."""
        return self.responses([row])[0]

    def responses(
        self, rows: Sequence[PartyAdjustment]
    ) -> list[PartyAdjustmentResponse]:
        """Build the responses for a page, one read per table."""
        if not rows:
            return []
        allocations = children_by_parent(
            self._session,
            PartyAdjustmentAllocation,
            PartyAdjustmentAllocation.party_adjustment_id,
            [row.id for row in rows],
            PartyAdjustmentAllocation.created_at.asc(),
        )
        bills = self._bill_labels(
            [item for group in allocations.values() for item in group]
        )
        customers = customer_names(self._session, (row.customer_id for row in rows))
        suppliers = vendor_names(self._session, (row.vendor_id for row in rows))
        thresholds = {
            firm_id: adjustment_limits(self._session, firm_id).approval_threshold
            for firm_id in {row.firm_id for row in rows}
        }
        answer: list[PartyAdjustmentResponse] = []
        for row in rows:
            lines: list[PartyAdjustmentAllocationResponse] = []
            on_customer = ZERO
            on_supplier = ZERO
            for item in allocations.get(row.id, []):
                side, bill_id = _side_of(item)
                number, bill_date = bills.get(bill_id, ("", None))
                lines.append(
                    PartyAdjustmentAllocationResponse(
                        id=item.id,
                        side=side,
                        bill_id=bill_id,
                        bill_number=number,
                        bill_date=bill_date,
                        amount=item.amount,
                    )
                )
                if side == PartyAdjustmentSideEnum.CUSTOMER:
                    on_customer += quantize_ledger(item.amount)
                else:
                    on_supplier += quantize_ledger(item.amount)
            answer.append(
                PartyAdjustmentResponse(
                    id=row.id,
                    adjustment_number=row.adjustment_number,
                    adjustment_date=row.adjustment_date,
                    kind=PartyAdjustmentKindEnum(row.kind),
                    status=PartyAdjustmentStatusEnum(row.status),
                    customer_id=row.customer_id,
                    customer_name=(
                        None
                        if row.customer_id is None
                        else customers.get(row.customer_id)
                    ),
                    vendor_id=row.vendor_id,
                    vendor_name=(
                        None if row.vendor_id is None else suppliers.get(row.vendor_id)
                    ),
                    amount=row.amount,
                    reason=row.reason,
                    customer_allocated=on_customer,
                    supplier_allocated=on_supplier,
                    needs_second_approver=(
                        quantize_ledger(row.amount) > thresholds[row.firm_id]
                    ),
                    journal_entry_id=row.journal_entry_id,
                    reversal_journal_entry_id=row.reversal_journal_entry_id,
                    approved_at=row.approved_at,
                    approved_by=row.approved_by,
                    created_by=row.created_by,
                    cancelled_at=row.cancelled_at,
                    cancel_reason=row.cancel_reason,
                    allocations=lines,
                    version=row.version,
                    rebate_agreement_id=row.rebate_agreement_id,
                    principal_claim_id=row.principal_claim_id,
                    customer_rebate_agreement_id=row.customer_rebate_agreement_id,
                )
            )
        return answer

    def _bill_labels(
        self, allocations: Sequence[PartyAdjustmentAllocation]
    ) -> dict[UUID, tuple[str, date | None]]:
        """Return the number and date of every bill a page of allocations names."""
        wanted: dict[str, set[UUID]] = {}
        for item in allocations:
            for column in (
                "sales_invoice_id",
                "purchase_invoice_id",
                "customer_opening_bill_id",
                "vendor_opening_bill_id",
            ):
                value = getattr(item, column)
                if value is not None:
                    wanted.setdefault(column, set()).add(value)
        labels: dict[UUID, tuple[str, date | None]] = {}
        for model in (SalesInvoice, PurchaseInvoice):
            column = (
                "sales_invoice_id" if model is SalesInvoice else "purchase_invoice_id"
            )
            ids = wanted.get(column)
            if ids:
                for bill_id, number, bill_date in self._session.execute(
                    select(model.id, model.invoice_number, model.invoice_date).where(
                        model.id.in_(ids)
                    )
                ):
                    labels[bill_id] = (number, bill_date)
        customer_ids = wanted.get("customer_opening_bill_id")
        if customer_ids:
            for customer_bill in self._session.scalars(
                select(CustomerOpeningBill).where(
                    CustomerOpeningBill.id.in_(customer_ids)
                )
            ):
                labels[customer_bill.id] = (
                    customer_opening_bill_label(customer_bill),
                    customer_bill.bill_date,
                )
        vendor_ids = wanted.get("vendor_opening_bill_id")
        if vendor_ids:
            for vendor_bill in self._session.scalars(
                select(VendorOpeningBill).where(VendorOpeningBill.id.in_(vendor_ids))
            ):
                labels[vendor_bill.id] = (
                    opening_bill_label(vendor_bill),
                    vendor_bill.bill_date,
                )
        return labels

    # ---- reports -------------------------------------------------------

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PartyAdjustmentRegisterRecord]:
        """Every adjustment in the window, newest first; paged in SQL."""
        rows = window.fetch(
            self._session,
            select(PartyAdjustment)
            .where(
                PartyAdjustment.firm_id == firm_scope,
                PartyAdjustment.is_deleted.is_(False),
                *window.dated(PartyAdjustment.adjustment_date),
            )
            .order_by(
                PartyAdjustment.adjustment_date.desc(),
                PartyAdjustment.adjustment_number.desc(),
                PartyAdjustment.id.desc(),
            ),
        )
        customers = customer_names(self._session, (row.customer_id for row in rows))
        suppliers = vendor_names(self._session, (row.vendor_id for row in rows))
        records = [
            PartyAdjustmentRegisterRecord(
                adjustment_id=row.id,
                adjustment_number=row.adjustment_number,
                adjustment_date=row.adjustment_date,
                kind=PartyAdjustmentKindEnum(row.kind),
                status=PartyAdjustmentStatusEnum(row.status),
                customer_name=(
                    None if row.customer_id is None else customers.get(row.customer_id)
                ),
                vendor_name=(
                    None if row.vendor_id is None else suppliers.get(row.vendor_id)
                ),
                amount=row.amount,
                reason=row.reason,
            )
            for row in rows
        ]
        return mapped_like(rows, records)


def _side_of(item: PartyAdjustmentAllocation) -> tuple[PartyAdjustmentSideEnum, UUID]:
    """Say whose bill an allocation clears, and which bill."""
    if item.sales_invoice_id is not None:
        return PartyAdjustmentSideEnum.CUSTOMER, item.sales_invoice_id
    if item.customer_opening_bill_id is not None:
        return PartyAdjustmentSideEnum.CUSTOMER, item.customer_opening_bill_id
    if item.purchase_invoice_id is not None:
        return PartyAdjustmentSideEnum.SUPPLIER, item.purchase_invoice_id
    if item.vendor_opening_bill_id is not None:
        return PartyAdjustmentSideEnum.SUPPLIER, item.vendor_opening_bill_id
    raise ValidationError(  # pragma: no cover - a check constraint would be better
        "An allocation names no bill."
    )


__all__ = ["PartyAdjustmentService"]
