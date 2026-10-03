"""Recording and cancelling a TDS challan (ACC-7, decision A79).

The firm deducts tax on a payment to a supplier or on an expense, holds it in
*TDS Payable*, and deposits it with challan ITNS 281 by the seventh of the
next month (30 April for March). This module records that deposit the way the
bank's counterfoil states it and ties each deduction to the challan that paid
it, which is what the quarterly return (26Q) files every deduction under.

**What a challan may carry.** Deductions on posted payments and expenses,
under the challan's own section -- ITNS 281 names one nature of payment --
that no live challan already carries. The tax is their sum, never typed: a
counterfoil amount may be given, and is refused if it differs, so a slip keyed
wrong is caught at the counter rather than in the return. Tally's *Stat
Payment* and Zoho Books' *Record TDS payment* both work this way.

**A deduction is paid once.** A partial unique key on the item holds it, not a
read: two challans saved together would both pass a check that counted first.
Cancelling a challan marks its items no longer live, which frees them.

**Interest and the late fee** go on the same challan and post to their own
cost, *Interest and Fees on TDS*; they were never deducted from anybody, so
they never touch TDS Payable.
"""

from collections.abc import Sequence
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.expenses.models import Expense
from app.finance.models import LedgerAccount
from app.finance.models.tds_challan import (
    TdsChallan,
    TdsChallanItem,
    TdsChallanStatus,
)
from app.finance.schemas.tds_challans import (
    DeductionKind,
    OpenDeductionRecord,
    TdsChallanCreate,
    TdsChallanItemResponse,
    TdsChallanResponse,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.tds_return import due_date
from app.finance.tds import TDS_SECTIONS
from app.settlements.models import Settlement
from app.vendors.models import Vendor

_LIVE = "POSTED"


def challan_cin(bsr_code: str, deposited_on: date, serial: str) -> str:
    """Write the Challan Identification Number: BSR, ddmmyyyy, serial."""
    return f"{bsr_code}{deposited_on:%d%m%Y}{serial}"


class TdsChallanService(TransactionalDocumentService):
    """Deposit what the firm deducted, and take a deposit back."""

    DOCUMENT = DocumentTypeSpec(
        code="TDS_CHALLAN",
        name="TDS Challan",
        description="Tax deducted at source deposited with the government",
        category="FINANCE",
        module="tds_challan",
        prefix="TDC",
        states=(
            DocumentStateSpec("POSTED", "Posted", 1),
            DocumentStateSpec("CANCELLED", "Cancelled", 2, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus the ledger collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)

    # ---- open deductions -----------------------------------------------

    def _carried(self) -> tuple[Select[tuple[UUID | None]], Select[tuple[UUID | None]]]:
        """Select the payments and expenses a live challan already carries."""
        live = TdsChallanItem.is_live.is_(True)
        return (
            select(TdsChallanItem.settlement_id).where(
                live, TdsChallanItem.settlement_id.is_not(None)
            ),
            select(TdsChallanItem.expense_id).where(
                live, TdsChallanItem.expense_id.is_not(None)
            ),
        )

    def open_deductions(
        self,
        firm_id: UUID,
        *,
        section: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[OpenDeductionRecord]:
        """Every deduction on a posted document that no live challan pays.

        Oldest first, so the challan due soonest is at the top.
        """
        carried_payments, carried_expenses = self._carried()
        payments = select(Settlement, Vendor).join(
            Vendor, Vendor.id == Settlement.vendor_id
        )
        payments = payments.where(
            Settlement.firm_id == firm_id,
            Settlement.is_deleted.is_(False),
            Settlement.direction == "PAYMENT",
            Settlement.status == _LIVE,
            Settlement.tds_amount > 0,
            Settlement.id.not_in(carried_payments),
        )
        expenses = select(Expense).where(
            Expense.firm_id == firm_id,
            Expense.is_deleted.is_(False),
            Expense.status == _LIVE,
            Expense.tds_amount > 0,
            Expense.id.not_in(carried_expenses),
        )
        if section:
            payments = payments.where(Settlement.tds_section == section)
            expenses = expenses.where(Expense.tds_section == section)
        if date_from is not None:
            payments = payments.where(Settlement.settlement_date >= date_from)
            expenses = expenses.where(Expense.expense_date >= date_from)
        if date_to is not None:
            payments = payments.where(Settlement.settlement_date <= date_to)
            expenses = expenses.where(Expense.expense_date <= date_to)
        rows = [
            OpenDeductionRecord(
                kind=DeductionKind.PAYMENT,
                id=payment.id,
                document_number=payment.settlement_number,
                document_date=payment.settlement_date,
                party_name=vendor.display_name or vendor.name,
                pan=vendor.pan,
                section=payment.tds_section or "",
                gross_amount=payment.amount,
                tds_amount=payment.tds_amount,
                due_date=due_date(payment.settlement_date),
            )
            for payment, vendor in self._session.execute(payments).all()
        ]
        rows.extend(
            OpenDeductionRecord(
                kind=DeductionKind.EXPENSE,
                id=expense.id,
                document_number=expense.expense_number,
                document_date=expense.expense_date,
                party_name=expense.payee or "",
                pan=expense.payee_pan,
                section=expense.tds_section or "",
                gross_amount=expense.amount,
                tds_amount=expense.tds_amount,
                due_date=due_date(expense.expense_date),
            )
            for expense in self._session.scalars(expenses).all()
        )
        rows.sort(key=lambda row: (row.document_date, row.document_number))
        return rows

    # ---- reads ---------------------------------------------------------

    def list_challans(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        section: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[TdsChallan], int]:
        """Return one page of challans, newest first, and the total matching."""
        statement = select(TdsChallan).where(
            TdsChallan.firm_id == firm_id, TdsChallan.is_deleted.is_(False)
        )
        if section:
            statement = statement.where(TdsChallan.section == section)
        if status:
            statement = statement.where(TdsChallan.status == status)
        if date_from is not None:
            statement = statement.where(TdsChallan.deposited_on >= date_from)
        if date_to is not None:
            statement = statement.where(TdsChallan.deposited_on <= date_to)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                TdsChallan.deposited_on.desc(),
                TdsChallan.challan_number.desc(),
                TdsChallan.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, challan_id: UUID, *, firm_id: UUID) -> TdsChallan:
        """Return one challan.

        Raises:
            ResourceNotFoundError: If the firm has no such live challan.

        """
        row = self._session.scalar(
            select(TdsChallan).where(
                TdsChallan.id == challan_id,
                TdsChallan.firm_id == firm_id,
                TdsChallan.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("TDS challan not found.")
        return row

    # ---- writes --------------------------------------------------------

    def create(
        self, data: TdsChallanCreate, *, firm_id: UUID, actor_id: UUID
    ) -> TdsChallan:
        """Record the deposit, tie its deductions and post. The caller commits.

        Raises:
            ValidationError: If the account is not a bank or cash account, a
                deduction is not open or is under another section, the
                counterfoil's tax differs, or no period is open.
            ConflictError: If the CIN is already on a live challan, or a
                deduction was taken by another challan saved at the same time.

        """
        # Imported here: the contra module imports this package's services.
        from app.contra.services.contra_service import ContraVoucherService

        accounts = {
            row.id: row
            for row in ContraVoucherService(self._session).money_accounts(firm_id)
        }
        bank = accounts.get(data.paid_from_account_id)
        if bank is None:
            raise ValidationError(
                "Choose the bank or cash account the challan was paid from.",
                details={"field": "paid_from_account_id"},
            )
        if len({(ref.kind, ref.id) for ref in data.deductions}) != len(data.deductions):
            raise ValidationError("A deduction is named twice on the challan.")
        open_rows = {
            (row.kind, row.id): row
            for row in self.open_deductions(firm_id, date_to=data.deposited_on)
        }
        chosen: list[OpenDeductionRecord] = []
        for ref in data.deductions:
            found = open_rows.get((ref.kind, ref.id))
            if found is None:
                raise ValidationError(
                    "A deduction on the challan is not open: it is on another "
                    "challan, its document was reversed, or it is dated after "
                    "the deposit.",
                    details={"kind": ref.kind.value, "id": str(ref.id)},
                )
            if found.section != data.section:
                raise ValidationError(
                    f"{found.document_number} was deducted under "
                    f"{found.section}; a challan pays one section, and this "
                    f"one is {data.section}."
                )
            chosen.append(found)
        tax = quantize_ledger(sum((row.tds_amount for row in chosen), ZERO))
        if data.tax_amount is not None and quantize_ledger(data.tax_amount) != tax:
            raise ValidationError(
                f"The counterfoil says {quantize_ledger(data.tax_amount)} but the "
                f"deductions chosen come to {tax}.",
                details={"field": "tax_amount"},
            )
        if self._session.scalar(
            select(TdsChallan.challan_number).where(
                TdsChallan.firm_id == firm_id,
                TdsChallan.is_deleted.is_(False),
                TdsChallan.status == TdsChallanStatus.POSTED.value,
                TdsChallan.bsr_code == data.bsr_code,
                TdsChallan.deposited_on == data.deposited_on,
                TdsChallan.challan_serial == data.challan_serial,
            )
        ):
            raise ValidationError(
                "That challan (BSR code, date and serial) is already recorded.",
                details={"field": "challan_serial"},
            )
        interest = quantize_ledger(data.interest_amount)
        fee = quantize_ledger(data.fee_amount)
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        number = self._issue_number(
            numbering_rule,
            typed=None,
            number_column=TdsChallan.challan_number,
            firm_id=firm_id,
            document_date=data.deposited_on,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        cin = challan_cin(data.bsr_code, data.deposited_on, data.challan_serial)
        challan_id = uuid4()
        entry = self._posting.post_tds_challan(
            firm_id=firm_id,
            challan_id=challan_id,
            challan_number=number,
            deposited_on=data.deposited_on,
            bank_account_id=bank.id,
            tax_amount=tax,
            charges_amount=interest + fee,
            description=f"TDS {data.section} deposited, challan {cin} ({number})"[:500],
            actor_id=actor_id,
        )
        remarks = (
            data.remarks.strip() if data.remarks and data.remarks.strip() else None
        )
        row = TdsChallan(
            id=challan_id,
            firm_id=firm_id,
            challan_number=number,
            deposited_on=data.deposited_on,
            bsr_code=data.bsr_code,
            challan_serial=data.challan_serial,
            section=data.section,
            tax_amount=tax,
            interest_amount=interest,
            fee_amount=fee,
            paid_from_account_id=bank.id,
            remarks=remarks,
            status=TdsChallanStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        for item in chosen:
            self._session.add(
                TdsChallanItem(
                    firm_id=firm_id,
                    challan_id=challan_id,
                    settlement_id=(
                        item.id if item.kind == DeductionKind.PAYMENT else None
                    ),
                    expense_id=item.id if item.kind == DeductionKind.EXPENSE else None,
                    tds_amount=item.tds_amount,
                    is_live=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._flush_or_conflict(
            "Another challan took one of these deductions, or this challan is "
            "already recorded. Reload and choose again."
        )
        self._record_event(row, action="POSTED", from_state=None, actor_id=actor_id)
        record_audit(
            self._session,
            action="tds_challan.posted",
            entity_type="tds_challan",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row, len(chosen)),
        )
        self._session.flush()
        return row

    def cancel(
        self, challan_id: UUID, *, firm_id: UUID, actor_id: UUID, reason: str
    ) -> TdsChallan:
        """Take a challan back with a mirror journal and free its deductions.

        Raises:
            ValidationError: If it is already cancelled, or no reason is given.

        """
        row = self.get(challan_id, firm_id=firm_id)
        if row.status == TdsChallanStatus.CANCELLED.value:
            raise ValidationError(f"{row.challan_number} has already been cancelled.")
        why = reason.strip()
        if not why:
            raise ValidationError("Say why the challan is being cancelled.")
        items = self._session.scalars(
            select(TdsChallanItem).where(
                TdsChallanItem.challan_id == row.id,
                TdsChallanItem.is_live.is_(True),
            )
        ).all()
        before = self._snapshot(row, len(items))
        mirror = self._journals.reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.challan_number}-CAN",
            actor_id=actor_id,
        )
        for item in items:
            item.is_live = False
            item.updated_by = actor_id
        row.status = TdsChallanStatus.CANCELLED.value
        row.reversal_journal_entry_id = mirror.id
        row.cancel_reason = why
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="CANCELLED",
            from_state=TdsChallanStatus.POSTED.value,
            actor_id=actor_id,
            remarks=why,
        )
        record_audit(
            self._session,
            action="tds_challan.cancelled",
            entity_type="tds_challan",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row, len(items)),
        )
        self._session.flush()
        return row

    def _record_event(
        self,
        row: TdsChallan,
        *,
        action: str,
        from_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> None:
        """Append one step to the challan's timeline."""
        self._record_lifecycle_event(
            firm_id=row.firm_id,
            document_type=self._document_type(row.firm_id),
            document_id=row.id,
            document_number=row.challan_number,
            action=action,
            from_state=from_state,
            to_state=row.status,
            actor_id=actor_id,
            remarks=remarks,
            details={
                "challan_number": row.challan_number,
                "section": row.section,
                "tax_amount": str(row.tax_amount),
            },
            snapshot={"status": row.status},
        )

    @staticmethod
    def _snapshot(row: TdsChallan, deductions: int) -> dict[str, object]:
        """Describe a challan for the audit trail."""
        return {
            "challan_number": row.challan_number,
            "cin": challan_cin(row.bsr_code, row.deposited_on, row.challan_serial),
            "section": row.section,
            "status": row.status,
            "tax_amount": str(row.tax_amount),
            "interest_amount": str(row.interest_amount),
            "fee_amount": str(row.fee_amount),
            "paid_from_account_id": str(row.paid_from_account_id),
            "deductions": deductions,
            "journal_entry_id": str(row.journal_entry_id),
            "reversal_journal_entry_id": (
                str(row.reversal_journal_entry_id)
                if row.reversal_journal_entry_id
                else None
            ),
            "cancel_reason": row.cancel_reason,
        }

    # ---- responses -----------------------------------------------------

    def responses(self, rows: Sequence[TdsChallan]) -> list[TdsChallanResponse]:
        """Build the responses for a page, reading accounts and items once."""
        if not rows:
            return []
        ids = [row.id for row in rows]
        accounts = {
            account_id: (code, name)
            for account_id, code, name in self._session.execute(
                select(LedgerAccount.id, LedgerAccount.code, LedgerAccount.name).where(
                    LedgerAccount.id.in_({row.paid_from_account_id for row in rows})
                )
            ).all()
        }
        # A cancelled challan shows what it carried, so its items are read
        # whether live or not.
        items = self._session.scalars(
            select(TdsChallanItem).where(
                TdsChallanItem.challan_id.in_(ids),
                TdsChallanItem.is_deleted.is_(False),
            )
        ).all()
        payments = {
            payment.id: (payment, vendor)
            for payment, vendor in self._session.execute(
                select(Settlement, Vendor)
                .join(Vendor, Vendor.id == Settlement.vendor_id)
                .where(
                    Settlement.id.in_(
                        {i.settlement_id for i in items if i.settlement_id}
                    )
                )
            ).all()
        }
        expenses = {
            expense.id: expense
            for expense in self._session.scalars(
                select(Expense).where(
                    Expense.id.in_({i.expense_id for i in items if i.expense_id})
                )
            ).all()
        }
        by_challan: dict[UUID, list[TdsChallanItemResponse]] = {}
        for item in items:
            if item.settlement_id is not None and item.settlement_id in payments:
                payment, vendor = payments[item.settlement_id]
                line = TdsChallanItemResponse(
                    kind=DeductionKind.PAYMENT,
                    document_id=payment.id,
                    document_number=payment.settlement_number,
                    document_date=payment.settlement_date,
                    party_name=vendor.display_name or vendor.name,
                    pan=vendor.pan,
                    tds_amount=item.tds_amount,
                )
            elif item.expense_id is not None and item.expense_id in expenses:
                expense = expenses[item.expense_id]
                line = TdsChallanItemResponse(
                    kind=DeductionKind.EXPENSE,
                    document_id=expense.id,
                    document_number=expense.expense_number,
                    document_date=expense.expense_date,
                    party_name=expense.payee or "",
                    pan=expense.payee_pan,
                    tds_amount=item.tds_amount,
                )
            else:
                continue
            by_challan.setdefault(item.challan_id, []).append(line)
        missing = ("", "")
        answers: list[TdsChallanResponse] = []
        for row in rows:
            lines = sorted(
                by_challan.get(row.id, []),
                key=lambda line: (line.document_date, line.document_number),
            )
            earliest = min((line.document_date for line in lines), default=None)
            answers.append(
                TdsChallanResponse(
                    id=row.id,
                    challan_number=row.challan_number,
                    deposited_on=row.deposited_on,
                    bsr_code=row.bsr_code,
                    challan_serial=row.challan_serial,
                    cin=challan_cin(row.bsr_code, row.deposited_on, row.challan_serial),
                    section=row.section,
                    section_name=TDS_SECTIONS.get(row.section, ""),
                    tax_amount=row.tax_amount,
                    interest_amount=row.interest_amount,
                    fee_amount=row.fee_amount,
                    total_amount=row.tax_amount + row.interest_amount + row.fee_amount,
                    paid_from_account_id=row.paid_from_account_id,
                    paid_from_account_code=accounts.get(
                        row.paid_from_account_id, missing
                    )[0],
                    paid_from_account_name=accounts.get(
                        row.paid_from_account_id, missing
                    )[1],
                    remarks=row.remarks,
                    status=row.status,
                    journal_entry_id=row.journal_entry_id,
                    reversal_journal_entry_id=row.reversal_journal_entry_id,
                    cancelled_at=row.cancelled_at,
                    cancel_reason=row.cancel_reason,
                    is_late=(
                        earliest is not None and row.deposited_on > due_date(earliest)
                    ),
                    items=lines,
                    created_at=row.created_at,
                    version=row.version,
                )
            )
        return answers
