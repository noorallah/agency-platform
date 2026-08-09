"""Post business documents to the general ledger.

Until now nothing did. Finance held a chart of accounts, a journal engine and a
trial balance that could only ever reflect hand-keyed journals, because no
module outside ``app/finance`` imported it. Approving a sales invoice moved a
customer balance and left the ledger untouched.

Posting **fails the operation it belongs to** rather than being skipped. An
approved invoice with no journal is the silent gap this is meant to close, so a
missing control account or a closed period refuses the approval outright.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_money
from app.finance.models import (
    AccountingPeriod,
    JournalEntry,
    JournalType,
    PeriodStatus,
    VoucherType,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData

SALES_INVOICE_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_REVENUE,
    ControlAccountPurpose.OUTPUT_TAX,
)

GOODS_ISSUE_PURPOSES = (
    ControlAccountPurpose.COST_OF_GOODS_SOLD,
    ControlAccountPurpose.INVENTORY,
)


@dataclass(frozen=True, slots=True)
class PostingContext:
    """The firm references every journal needs, resolved once."""

    journal_type_id: UUID
    voucher_type_id: UUID
    accounting_period_id: UUID


class DocumentPostingService:
    """Turn approved documents into balanced journal entries."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session
        self._control = ControlAccountService(session)
        self._journals = JournalEntryEngine(session)

    def context_for(self, firm_id: UUID, on: date) -> PostingContext:
        """Resolve the journal, voucher type and open period for a date.

        Args:
            firm_id: The owning firm.
            on: The document date the journal will carry.

        Returns:
            The references the journal engine requires.

        Raises:
            ValidationError: If the firm has no journal or voucher type, or no
                open accounting period covering the date.

        """
        journal_type_id = self._session.scalar(
            select(JournalType.id)
            .where(JournalType.firm_id == firm_id, JournalType.is_deleted.is_(False))
            .order_by(JournalType.code.asc())
        )
        if journal_type_id is None:
            raise ValidationError(
                "This firm has no journal type configured, so documents cannot post."
            )
        voucher_type_id = self._session.scalar(
            select(VoucherType.id)
            .where(VoucherType.firm_id == firm_id, VoucherType.is_deleted.is_(False))
            .order_by(VoucherType.code.asc())
        )
        if voucher_type_id is None:
            raise ValidationError(
                "This firm has no voucher type configured, so documents cannot post."
            )
        period_id = self._session.scalar(
            select(AccountingPeriod.id).where(
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.starts_on <= on,
                AccountingPeriod.ends_on >= on,
                AccountingPeriod.status == PeriodStatus.OPEN.value,
                AccountingPeriod.is_deleted.is_(False),
            )
        )
        if period_id is None:
            raise ValidationError(
                f"No open accounting period covers {on.isoformat()}. "
                "Open the period before approving documents dated in it."
            )
        return PostingContext(
            journal_type_id=journal_type_id,
            voucher_type_id=voucher_type_id,
            accounting_period_id=period_id,
        )

    def _require_mapping(
        self, firm_id: UUID, purposes: tuple[ControlAccountPurpose, ...]
    ) -> dict[ControlAccountPurpose, UUID]:
        """Resolve every account a posting needs, reporting all gaps at once."""
        missing = self._control.missing(firm_id, purposes)
        if missing:
            names = ", ".join(purpose.value for purpose in missing)
            raise ValidationError(
                f"This firm has no ledger account configured for: {names}. "
                "Set the firm's control accounts before approving this document."
            )
        return {
            purpose: self._control.resolve(firm_id, purpose) for purpose in purposes
        }

    def post_sales_invoice(
        self,
        *,
        firm_id: UUID,
        invoice_id: UUID,
        invoice_number: str,
        invoice_date: date,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post revenue, output tax and the receivable for an approved invoice.

        Cost of goods sold is not posted here. Goods leave stock when a delivery
        note dispatches, not when an invoice is raised, so the inventory side
        belongs to that movement and would double-count if posted twice.

        Args:
            firm_id: The owning firm.
            invoice_id: The source document.
            invoice_number: The document number, used as the journal reference.
            invoice_date: The date the journal carries.
            taxable_amount: Net of discount, before tax.
            tax_amount: Output tax charged.
            total_amount: What the customer owes.
            actor_id: The approving user.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing, or the
                amounts do not balance.

        """
        accounts = self._require_mapping(firm_id, SALES_INVOICE_PURPOSES)
        context = self.context_for(firm_id, invoice_date)

        taxable = quantize_money(taxable_amount)
        tax = quantize_money(tax_amount)
        total = quantize_money(total_amount)
        if taxable + tax != total:
            raise ValidationError(
                f"Invoice {invoice_number} does not balance: taxable {taxable} "
                f"plus tax {tax} is not total {total}."
            )

        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                debit_amount=total,
                description=f"Invoice {invoice_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_REVENUE],
                credit_amount=taxable,
                description=f"Invoice {invoice_number}",
            ),
        ]
        if tax != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.OUTPUT_TAX],
                    credit_amount=tax,
                    description=f"Output tax on {invoice_number}",
                )
            )

        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=invoice_date,
            reference_number=invoice_number,
            description=f"Sales invoice {invoice_number}",
            lines=lines,
            source_module="sales_invoice",
            source_id=invoice_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_goods_issue(
        self,
        *,
        firm_id: UUID,
        document_id: UUID,
        document_number: str,
        issue_date: date,
        cost_amount: Decimal,
        source_module: str,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Move the cost of dispatched goods from inventory into expense.

        Goods leave stock when they are dispatched, not when they are invoiced,
        so this is where cost of goods sold belongs. The amount is what the
        stock ledger actually released at the moving average — the invoice's
        selling price has nothing to do with it.

        Args:
            firm_id: The owning firm.
            document_id: The dispatching document.
            document_number: Its number, used as the journal reference.
            issue_date: The date the journal carries.
            cost_amount: Total cost released by the movement.
            source_module: The module raising the posting.
            actor_id: The dispatching user.

        Returns:
            The posted entry, or None when the movement released no value —
            stock received before valuation existed still has no cost, and a
            zero journal is not worth writing.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        cost = quantize_money(cost_amount)
        if cost == ZERO:
            return None
        accounts = self._require_mapping(firm_id, GOODS_ISSUE_PURPOSES)
        context = self.context_for(firm_id, issue_date)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=issue_date,
            reference_number=document_number,
            description=f"Cost of goods issued on {document_number}",
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.COST_OF_GOODS_SOLD
                    ],
                    debit_amount=cost,
                    description=f"Cost of goods sold {document_number}",
                ),
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                    credit_amount=cost,
                    description=f"Stock released on {document_number}",
                ),
            ],
            source_module=source_module,
            source_id=document_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
