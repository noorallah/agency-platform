"""Accounting Event Consumer - Converts transaction events to journal entries."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import (
    AccountingPeriod,
    JournalType,
    VoucherType,
    LedgerAccount,
    AccountType,
)
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData


class AccountingEventConsumer:
    """
    Consume accounting events from transaction modules and generate journal entries.
    
    Supports:
    - Purchase Invoice events (Expense, Input Tax, AP)
    - Sales Invoice events (Revenue, Output Tax, AR)
    - Purchase Return events (Expense reversal, Tax reversal, AP reversal)
    
    Auto-maps events to appropriate GL accounts based on firm configuration.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._journal_engine = JournalEntryEngine(session)

    def consume_purchase_invoice_events(
        self,
        *,
        firm_id: UUID,
        invoice_id: UUID,
        invoice_number: str,
        invoice_date: datetime,
        accounting_period_id: UUID,
        events: list[PurchaseInvoiceEvent],
        actor_id: UUID,
    ) -> None:
        """
        Consume Purchase Invoice accounting events.
        
        Events:
        - PURCHASE_EXPENSE (Dr: Expense, Cr: AP)
        - INPUT_TAX (Dr: Input Tax, Cr: AP)
        - ACCOUNTS_PAYABLE (tracking only)
        """
        if not events:
            return

        # Get journal type and voucher type
        journal_type = self._get_or_create_journal_type(firm_id, "PUR", "Purchase")
        voucher_type = self._get_or_create_voucher_type(firm_id, "INV", "Invoice")

        # Build journal lines from events
        lines = []
        for event in events:
            if event.event_type == "PURCHASE_EXPENSE":
                # Dr: Expense account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.EXPENSE, "Purchase Expense"
                        ),
                        debit_amount=Decimal(str(event.amount)),
                        description=f"Purchase Expense - {invoice_number}",
                    )
                )
                # Cr: AP account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.LIABILITY, "Accounts Payable"
                        ),
                        credit_amount=Decimal(str(event.amount)),
                        description=f"Accounts Payable - {invoice_number}",
                    )
                )
            elif event.event_type == "INPUT_TAX":
                # Dr: Input Tax account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.ASSET, "Input Tax"
                        ),
                        debit_amount=Decimal(str(event.amount)),
                        description=f"Input Tax - {invoice_number}",
                    )
                )
                # Cr: AP account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.LIABILITY, "Accounts Payable"
                        ),
                        credit_amount=Decimal(str(event.amount)),
                        description=f"Accounts Payable (Tax) - {invoice_number}",
                    )
                )

        if lines:
            self._journal_engine.create_entry(
                firm_id=firm_id,
                journal_type_id=journal_type.id,
                voucher_type_id=voucher_type.id,
                accounting_period_id=accounting_period_id,
                journal_date=invoice_date,
                reference_number=f"PI-{invoice_number}",
                description=f"Purchase Invoice {invoice_number}",
                lines=lines,
                source_module="purchase_invoice",
                source_id=invoice_id,
                actor_id=actor_id,
            )

    def consume_sales_invoice_events(
        self,
        *,
        firm_id: UUID,
        invoice_id: UUID,
        invoice_number: str,
        invoice_date: datetime,
        accounting_period_id: UUID,
        events: list[SalesInvoiceEvent],
        actor_id: UUID,
    ) -> None:
        """
        Consume Sales Invoice accounting events.
        
        Events:
        - SALES_REVENUE (Cr: Income, Dr: AR)
        - OUTPUT_TAX (Cr: Output Tax Liability, Dr: AR)
        - ACCOUNTS_RECEIVABLE (tracking only)
        """
        if not events:
            return

        journal_type = self._get_or_create_journal_type(firm_id, "SAL", "Sales")
        voucher_type = self._get_or_create_voucher_type(firm_id, "SI", "Sales Invoice")

        lines = []
        for event in events:
            if event.event_type == "SALES_REVENUE":
                # Dr: AR account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.ASSET, "Accounts Receivable"
                        ),
                        debit_amount=Decimal(str(event.amount)),
                        description=f"Sales Revenue - {invoice_number}",
                    )
                )
                # Cr: Income account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.INCOME, "Sales Revenue"
                        ),
                        credit_amount=Decimal(str(event.amount)),
                        description=f"Sales Income - {invoice_number}",
                    )
                )
            elif event.event_type == "OUTPUT_TAX":
                # Dr: AR account
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.ASSET, "Accounts Receivable"
                        ),
                        debit_amount=Decimal(str(event.amount)),
                        description=f"Output Tax - {invoice_number}",
                    )
                )
                # Cr: Output Tax Liability
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.LIABILITY, "Output Tax Payable"
                        ),
                        credit_amount=Decimal(str(event.amount)),
                        description=f"Output Tax Liability - {invoice_number}",
                    )
                )

        if lines:
            self._journal_engine.create_entry(
                firm_id=firm_id,
                journal_type_id=journal_type.id,
                voucher_type_id=voucher_type.id,
                accounting_period_id=accounting_period_id,
                journal_date=invoice_date,
                reference_number=f"SI-{invoice_number}",
                description=f"Sales Invoice {invoice_number}",
                lines=lines,
                source_module="sales_invoice",
                source_id=invoice_id,
                actor_id=actor_id,
            )

    def consume_purchase_return_events(
        self,
        *,
        firm_id: UUID,
        return_id: UUID,
        return_number: str,
        return_date: datetime,
        accounting_period_id: UUID,
        events: list[PurchaseReturnEvent],
        actor_id: UUID,
    ) -> None:
        """
        Consume Purchase Return accounting events (reversals).
        
        Mirrors purchase invoice events but in reverse (reversal entry).
        """
        if not events:
            return

        journal_type = self._get_or_create_journal_type(firm_id, "PUR", "Purchase")
        voucher_type = self._get_or_create_voucher_type(firm_id, "PR", "Purchase Return")

        lines = []
        for event in events:
            if event.event_type == "PURCHASE_EXPENSE_REVERSAL":
                # Cr: Expense account (credit reverses debit)
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.EXPENSE, "Purchase Expense"
                        ),
                        credit_amount=Decimal(str(event.amount)),
                        description=f"Purchase Return - {return_number}",
                    )
                )
                # Dr: AP account (debit reverses credit)
                lines.append(
                    JournalLineData(
                        ledger_account_id=self._get_account(
                            firm_id, AccountType.LIABILITY, "Accounts Payable"
                        ),
                        debit_amount=Decimal(str(event.amount)),
                        description=f"AP Reversal - {return_number}",
                    )
                )

        if lines:
            self._journal_engine.create_entry(
                firm_id=firm_id,
                journal_type_id=journal_type.id,
                voucher_type_id=voucher_type.id,
                accounting_period_id=accounting_period_id,
                journal_date=return_date,
                reference_number=f"PR-{return_number}",
                description=f"Purchase Return {return_number}",
                lines=lines,
                source_module="purchase_return",
                source_id=return_id,
                actor_id=actor_id,
            )

    def _get_or_create_journal_type(self, firm_id: UUID, code: str, name: str) -> JournalType:
        """Get or create journal type."""
        jtype = self._session.scalar(
            select(JournalType).where(
                JournalType.firm_id == firm_id,
                JournalType.journal_type_code == code,
            )
        )
        if jtype is None:
            jtype = JournalType(
                firm_id=firm_id,
                journal_type_code=code,
                journal_type_name=name,
                is_active=True,
                created_by=UUID(int=0),
            )
            self._session.add(jtype)
            self._session.flush()
        return jtype

    def _get_or_create_voucher_type(self, firm_id: UUID, code: str, name: str) -> VoucherType:
        """Get or create voucher type."""
        vtype = self._session.scalar(
            select(VoucherType).where(
                VoucherType.firm_id == firm_id,
                VoucherType.voucher_type_code == code,
            )
        )
        if vtype is None:
            vtype = VoucherType(
                firm_id=firm_id,
                voucher_type_code=code,
                voucher_type_name=name,
                is_active=True,
                created_by=UUID(int=0),
            )
            self._session.add(vtype)
            self._session.flush()
        return vtype

    def _get_account(
        self, firm_id: UUID, account_type: AccountType, account_name: str
    ) -> UUID:
        """
        Get standard GL account by type and name.
        
        Used for automatic GL mapping. In production, this should look up
        based on firm-specific chart of accounts.
        """
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.account_type == account_type.value,
                LedgerAccount.account_name.ilike(f"%{account_name}%"),
                LedgerAccount.is_active.is_(True),
            )
        )
        if account is None:
            raise ValidationError(
                f"GL account not found for {account_type.value}: {account_name}. "
                "Please configure Chart of Accounts."
            )
        return account.id


# Event DTOs
class PurchaseInvoiceEvent:
    def __init__(self, event_type: str, amount: Decimal, description: str = "") -> None:
        self.event_type = event_type  # PURCHASE_EXPENSE, INPUT_TAX
        self.amount = amount
        self.description = description


class SalesInvoiceEvent:
    def __init__(self, event_type: str, amount: Decimal, description: str = "") -> None:
        self.event_type = event_type  # SALES_REVENUE, OUTPUT_TAX
        self.amount = amount
        self.description = description


class PurchaseReturnEvent:
    def __init__(self, event_type: str, amount: Decimal, description: str = "") -> None:
        self.event_type = event_type  # PURCHASE_EXPENSE_REVERSAL, etc.
        self.amount = amount
        self.description = description
