"""Payment runs and the bank's bulk file (BUY-11, decision A110).

Propose: every supplier bill still owing that falls due by a date. A draft
run holds the chosen bills and amounts (never more than a bill still owes).
Approving -- PAYMENT_RUN_APPROVE, which the cashier does not hold -- records
one payment per supplier through ``PaymentService``, by bank transfer,
allocated to that supplier's bills, and commits once: a run that cannot pay
every supplier pays none. The bank file is a generic NEFT layout, one row per
supplier, from each supplier's primary bank account; a firm's own bank's
layout is added when the firm shares it.
"""

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.common.audit.services import record_audit
from app.common.report_names import vendor_names
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.settlements.models.payment_run import PaymentRun, PaymentRunLine
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
    SettlementModeEnum,
)
from app.settlements.schemas.payment_run import (
    PaymentRunLineResponse,
    PaymentRunResponse,
    PaymentRunWrite,
)
from app.vendors.models import Vendor, VendorBankAccount

ZERO = Decimal("0")

#: The generic NEFT bulk-upload columns, in order.
BANK_FILE_COLUMNS = (
    "Beneficiary Code",
    "Beneficiary Name",
    "Account Number",
    "IFSC",
    "Amount",
    "Payment Date",
    "Payment Mode",
    "Reference",
)


class PaymentRunService(TransactionalDocumentService):
    """Propose, keep, approve and export payment runs."""

    DOCUMENT = DocumentTypeSpec(
        code="PAYMENT_RUN",
        name="Payment Run",
        description="Supplier bills paid in one go.",
        category="FINANCE",
        module="settlements",
        prefix="PRN",
        rule_code="PAYMENT_RUN_DEFAULT",
        rule_name="Payment Run Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 80, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def propose(self, firm_id: UUID, due_by: date) -> list[OutstandingInvoiceRecord]:
        """Return every supplier bill still owing that is due by ``due_by``."""
        from app.settlements.services.settlement_service import PaymentService

        return [
            record
            for record in PaymentService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=None
            )
            if record.outstanding_amount > ZERO
            and (record.due_date or record.invoice_date) <= due_by
        ]

    def create(
        self, data: PaymentRunWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PaymentRun:
        """Keep a draft run of the chosen bills and commit."""
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=PaymentRun.run_number,
            firm_id=firm_id,
            document_date=data.payment_date,
            actor_id=actor_id,
            branch_code=None,
            company_code=self._company_code(firm_id),
        )
        row = PaymentRun(
            firm_id=firm_id,
            run_number=number,
            payment_date=data.payment_date,
            due_by=data.due_by,
            status="DRAFT",
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Payment run number already exists in this firm.")
        self._write_lines(row, data, actor_id=actor_id)
        self._audit("payment_run.created", row, actor_id)
        self._session.commit()
        return row

    def update(
        self, run_id: UUID, data: PaymentRunWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PaymentRun:
        """Change a draft run's date and bills."""
        row = self._draft(run_id, firm_id)
        row.payment_date = data.payment_date
        row.due_by = data.due_by
        row.remarks = data.remarks
        row.updated_by = actor_id
        for line in self.lines(row.id):
            line.is_deleted = True
            line.deleted_at = utc_now()
        self._session.flush()
        self._write_lines(row, data, actor_id=actor_id)
        self._audit("payment_run.updated", row, actor_id)
        self._session.commit()
        return row

    def approve(self, run_id: UUID, *, firm_id: UUID, actor_id: UUID) -> PaymentRun:
        """Record one payment per supplier and commit once.

        Raises:
            ValidationError: If it is not a draft, or a bill now owes less
                than the run would pay -- the payment service names it.

        """
        from app.settlements.services.settlement_service import PaymentService

        row = self._draft(run_id, firm_id)
        lines = self.lines(row.id)
        if not lines:
            raise ValidationError("A payment run with no bills pays nothing.")
        by_vendor: dict[UUID, list[PaymentRunLine]] = defaultdict(list)
        for line in lines:
            by_vendor[line.vendor_id].append(line)
        payments = PaymentService(self._session)
        for vendor_id, vendor_lines in by_vendor.items():
            payment = payments.create(
                SettlementCreate(
                    party_id=vendor_id,
                    settlement_date=row.payment_date,
                    amount=sum(
                        (Decimal(str(line.amount)) for line in vendor_lines), ZERO
                    ),
                    method=SettlementMethodEnum.BANK,
                    payment_mode=SettlementModeEnum.BANK_TRANSFER,
                    instrument_reference=row.run_number,
                    narration=f"Payment run {row.run_number}",
                    allocations=[
                        SettlementAllocationWrite(
                            invoice_id=line.invoice_id, amount=Decimal(str(line.amount))
                        )
                        for line in vendor_lines
                    ],
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            for line in vendor_lines:
                line.settlement_id = payment.id
                line.updated_by = actor_id
        row.status = "APPROVED"
        row.approved_by = actor_id
        row.approved_at = utc_now()
        row.updated_by = actor_id
        self._audit("payment_run.approved", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self, run_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> PaymentRun:
        """Call off a draft run; an approved one is undone payment by payment."""
        row = self._draft(run_id, firm_id)
        if not reason.strip():
            raise ValidationError("Say why the payment run is cancelled.")
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("payment_run.cancelled", row, actor_id)
        self._session.commit()
        return row

    def bank_file(self, run_id: UUID, *, firm_id: UUID) -> tuple[str, str]:
        """Return the run's NEFT bulk file as CSV, and a file name.

        Raises:
            ValidationError: Naming every supplier with no bank account.

        """
        row = self.get(run_id, firm_id=firm_id)
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        bills: dict[UUID, list[str]] = defaultdict(list)
        for line in self.lines(row.id):
            totals[line.vendor_id] += Decimal(str(line.amount))
            bills[line.vendor_id].append(line.invoice_number)
        vendors = {
            v.id: v
            for v in self._session.scalars(
                select(Vendor).where(Vendor.id.in_(list(totals)))
            ).all()
        }
        accounts: dict[UUID, VendorBankAccount] = {}
        for account in self._session.scalars(
            select(VendorBankAccount)
            .where(
                VendorBankAccount.vendor_id.in_(list(totals)),
                VendorBankAccount.is_deleted.is_(False),
            )
            .order_by(VendorBankAccount.created_at.asc())
        ).all():
            current = accounts.get(account.vendor_id)
            if current is None or (account.is_primary and not current.is_primary):
                accounts[account.vendor_id] = account
        missing = [
            vendors[v].display_name if v in vendors else str(v)
            for v in totals
            if v not in accounts
        ]
        if missing:
            raise ValidationError(
                "These suppliers have no bank account to pay into: "
                + ", ".join(sorted(missing))
                + "."
            )
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(BANK_FILE_COLUMNS)
        for vendor_id, amount in sorted(
            totals.items(), key=lambda item: vendors[item[0]].code
        ):
            vendor = vendors[vendor_id]
            account = accounts[vendor_id]
            writer.writerow(
                [
                    vendor.code,
                    account.account_name,
                    account.account_number,
                    account.ifsc or "",
                    f"{amount:.2f}",
                    row.payment_date.strftime("%d/%m/%Y"),
                    "NEFT",
                    f"{row.run_number} {' '.join(bills[vendor_id])}"[:140],
                ]
            )
        return buffer.getvalue(), f"{row.run_number.replace('/', '-')}-neft.csv"

    def get(self, run_id: UUID, *, firm_id: UUID) -> PaymentRun:
        """Return one of the firm's runs."""
        row = self._session.get(PaymentRun, run_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Payment run not found.")
        return row

    def list_rows(self, firm_id: UUID) -> list[PaymentRun]:
        """Return the firm's runs, newest first."""
        return list(
            self._session.scalars(
                select(PaymentRun)
                .where(PaymentRun.firm_id == firm_id, PaymentRun.is_deleted.is_(False))
                .order_by(PaymentRun.payment_date.desc(), PaymentRun.run_number.desc())
            ).all()
        )

    def lines(self, run_id: UUID) -> list[PaymentRunLine]:
        """Return a run's live lines."""
        return list(
            self._session.scalars(
                select(PaymentRunLine).where(
                    PaymentRunLine.payment_run_id == run_id,
                    PaymentRunLine.is_deleted.is_(False),
                )
            ).all()
        )

    def responses(self, rows: list[PaymentRun]) -> list[PaymentRunResponse]:
        """Shape runs with their lines, one read per table."""
        if not rows:
            return []
        lines = list(
            self._session.scalars(
                select(PaymentRunLine).where(
                    PaymentRunLine.payment_run_id.in_([r.id for r in rows]),
                    PaymentRunLine.is_deleted.is_(False),
                )
            ).all()
        )
        names = vendor_names(self._session, (line.vendor_id for line in lines))
        grouped: dict[UUID, list[PaymentRunLine]] = defaultdict(list)
        for line in lines:
            grouped[line.payment_run_id].append(line)
        return [
            PaymentRunResponse(
                id=row.id,
                run_number=row.run_number,
                payment_date=row.payment_date,
                due_by=row.due_by,
                status=row.status,
                remarks=row.remarks,
                approved_by=row.approved_by,
                approved_at=row.approved_at,
                cancel_reason=row.cancel_reason,
                total=sum(
                    (Decimal(str(line.amount)) for line in grouped[row.id]), ZERO
                ),
                version=row.version,
                lines=[
                    PaymentRunLineResponse(
                        id=line.id,
                        vendor_id=line.vendor_id,
                        vendor_name=names.get(line.vendor_id, ""),
                        invoice_id=line.invoice_id,
                        invoice_number=line.invoice_number,
                        is_opening_bill=line.is_opening_bill,
                        amount=line.amount,
                        settlement_id=line.settlement_id,
                    )
                    for line in sorted(
                        grouped[row.id],
                        key=lambda line: (
                            names.get(line.vendor_id, ""),
                            line.invoice_number,
                        ),
                    )
                ],
            )
            for row in rows
        ]

    def _write_lines(
        self, row: PaymentRun, data: PaymentRunWrite, *, actor_id: UUID
    ) -> None:
        """Check each chosen bill against what it still owes, and keep it."""
        owing = {
            record.invoice_id: record for record in self.propose(row.firm_id, date.max)
        }
        problems: list[str] = []
        seen: set[UUID] = set()
        for item in data.lines:
            record = owing.get(item.invoice_id)
            if item.invoice_id in seen:
                problems.append(f"{item.invoice_id} is listed twice")
                continue
            seen.add(item.invoice_id)
            if record is None or record.party_id is None:
                problems.append(f"{item.invoice_id} owes nothing")
                continue
            amount = (
                item.amount if item.amount is not None else record.outstanding_amount
            )
            if amount > record.outstanding_amount:
                problems.append(
                    f"{record.invoice_number} owes {record.outstanding_amount}, "
                    f"not {amount}"
                )
                continue
            self._session.add(
                PaymentRunLine(
                    payment_run_id=row.id,
                    firm_id=row.firm_id,
                    vendor_id=record.party_id,
                    invoice_id=record.invoice_id,
                    is_opening_bill=record.is_opening_bill,
                    invoice_number=record.invoice_number,
                    amount=amount,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        if problems:
            raise ValidationError("; ".join(problems) + ".")
        self._session.flush()

    def _draft(self, run_id: UUID, firm_id: UUID) -> PaymentRun:
        """Return a run still in draft."""
        row = self.get(run_id, firm_id=firm_id)
        if row.status != "DRAFT":
            raise ValidationError(f"This payment run is already {row.status.lower()}.")
        return row

    def _audit(self, action: str, row: PaymentRun, actor_id: UUID) -> None:
        """Write one audit row for a run."""
        record_audit(
            self._session,
            action=action,
            entity_type="payment_run",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={"run_number": row.run_number, "status": row.status},
        )
