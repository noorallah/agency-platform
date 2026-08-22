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
from app.finance.services.journal_engine import (
    JournalEntryEngine,
    JournalLineData,
)
from app.finance.services.journal_engine import (
    quantize_money as quantize_ledger,
)

SALES_INVOICE_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_REVENUE,
    ControlAccountPurpose.OUTPUT_TAX,
)

GOODS_ISSUE_PURPOSES = (
    ControlAccountPurpose.COST_OF_GOODS_SOLD,
    ControlAccountPurpose.INVENTORY,
)

GOODS_RECEIPT_REVERSAL_PURPOSES = (
    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED,
    ControlAccountPurpose.INVENTORY,
    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE,
)

PURCHASE_INVOICE_PURPOSES = (
    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED,
    ControlAccountPurpose.INPUT_TAX,
    ControlAccountPurpose.ACCOUNTS_PAYABLE,
    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE,
)

# Only the party side. The cash or bank account is resolved by the caller from
# the method the money moved by, so requiring both here would stop a firm that
# maps cash and not bank from recording a cash receipt.
PURCHASE_RETURN_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_PAYABLE,
    ControlAccountPurpose.INPUT_TAX,
    ControlAccountPurpose.INVENTORY,
    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE,
)

#: What a day-one customer balance moves. `post_opening_stock` already put
#: opening balance equity in the chart for exactly this: "a firm that later
#: records opening receivables or opening cash has somewhere consistent to put
#: them."
OPENING_BALANCE_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.OPENING_BALANCE_EQUITY,
)

OPENING_STOCK_PURPOSES = (
    ControlAccountPurpose.INVENTORY,
    ControlAccountPurpose.OPENING_BALANCE_EQUITY,
)

STOCK_ADJUSTMENT_PURPOSES = (
    ControlAccountPurpose.INVENTORY,
    ControlAccountPurpose.INVENTORY_ADJUSTMENT,
)

RECEIPT_PURPOSES = (ControlAccountPurpose.ACCOUNTS_RECEIVABLE,)

#: A refund is money out against the same account a receipt is money
#: in against: what the customer paid in advance is being handed back.
REFUND_PURPOSES = (ControlAccountPurpose.ACCOUNTS_RECEIVABLE,)

#: What the customer is credited and the tax that comes off with it. The same
#: three accounts a sales invoice uses, because a return is that invoice
#: undone: revenue is not debited directly -- sales returns is its contra, so
#: the year's sales and the year's returns stay separately readable.
SALES_RETURN_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_RETURNS,
    ControlAccountPurpose.OUTPUT_TAX,
)

CREDIT_NOTE_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_RETURNS,
)

PAYMENT_PURPOSES = (ControlAccountPurpose.ACCOUNTS_PAYABLE,)

GOODS_RECEIPT_PURPOSES = (
    ControlAccountPurpose.INVENTORY,
    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED,
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

        # The document is consistent at its own four decimals; the ledger holds
        # two. Derive the revenue leg from the two figures the customer sees --
        # the total they owe and the tax they were charged -- so the three legs
        # still agree once rounded. Rounding all three independently can leave
        # them a cent apart, which the engine now refuses outright.
        ledger_total = quantize_ledger(total)
        ledger_tax = quantize_ledger(tax)
        ledger_taxable = ledger_total - ledger_tax

        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                debit_amount=ledger_total,
                description=f"Invoice {invoice_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_REVENUE],
                credit_amount=ledger_taxable,
                description=f"Invoice {invoice_number}",
            ),
        ]
        if ledger_tax != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.OUTPUT_TAX],
                    credit_amount=ledger_tax,
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

    def post_purchase_return(
        self,
        *,
        firm_id: UUID,
        return_id: UUID,
        return_number: str,
        return_date: date,
        stock_value: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post goods going back to a supplier.

        The supplier owes the firm the whole credit note, so **accounts payable
        is debited** with the total including tax, and the input tax claimed on
        the way in is reversed with the goods. What leaves stock is credited to
        inventory at what the stock actually cost -- the moving average the
        issue consumed at -- not at the price on the return.

        Those two are routinely different: goods bought at several prices sit at
        one average, and a return is priced at what the supplier agrees to
        credit. The gap is a purchase price variance and belongs in the P&L,
        exactly as it does when an invoice disagrees with the receipt it clears.
        Crediting inventory at the return price instead would leave stock valued
        at something no movement ever paid.

        Args:
            firm_id: The owning firm.
            return_id: The source document.
            return_number: The document number, used as the reference.
            return_date: The date the goods went back.
            stock_value: What the goods leaving stock actually cost.
            tax_amount: Input tax being reversed.
            total_amount: What the supplier credits, tax included.
            actor_id: The user completing the return.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, PURCHASE_RETURN_PURPOSES)
        context = self.context_for(firm_id, return_date)

        # Derived at the ledger's scale from the two figures the supplier sees,
        # so payables, input tax, inventory and the variance still balance once
        # each is rounded to two decimals.
        ledger_total = quantize_ledger(quantize_money(total_amount))
        ledger_tax = quantize_ledger(quantize_money(tax_amount))
        ledger_goods = ledger_total - ledger_tax
        ledger_stock = quantize_ledger(quantize_money(stock_value))
        variance = ledger_goods - ledger_stock

        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                debit_amount=ledger_total,
                description=f"Purchase return {return_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                credit_amount=ledger_stock,
                description=f"Goods returned on {return_number}",
            ),
        ]
        if ledger_tax != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.INPUT_TAX],
                    credit_amount=ledger_tax,
                    description=f"Input tax reversed on {return_number}",
                )
            )
        if variance != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.PURCHASE_PRICE_VARIANCE
                    ],
                    debit_amount=ZERO if variance > ZERO else -variance,
                    credit_amount=variance if variance > ZERO else ZERO,
                    description=f"Price variance on {return_number}",
                )
            )

        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=return_date,
            reference_number=return_number,
            description=f"Purchase return {return_number}",
            lines=lines,
            source_module="purchase_return",
            source_id=return_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def reverse_purchase_return(
        self,
        *,
        firm_id: UUID,
        entry_id: UUID,
        return_number: str,
        stock_value: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Take a cancelled purchase return off the books.

        The return debited payables for the whole credit note, reversed the
        input tax and credited inventory with what the goods actually cost.
        Cancelling puts the goods back on the shelf, so all of that has to come
        back out -- and until 2026-08-22 none of it did: `cancel_return`
        reversed the stock and never touched the ledger, which is the same
        defect `goods_receipt` carried until 2026-08-18. Measured on a seeded
        store, one cancellation left it 199.07 out.

        Payables and input tax mirror exactly: they are document amounts and
        the supplier's credit note is void either way. Inventory is debited
        with what the movement actually put back, at the average the stock is
        carried at now, and the difference lands in purchase price variance --
        the same rule a cancelled goods receipt follows.

        Args:
            firm_id: The owning firm.
            entry_id: The entry the return posted when it completed.
            return_number: The return's number, used as the reference.
            stock_value: What the reversing movements put back on the shelf.
            actor_id: The user cancelling the return.

        Returns:
            The posted reversal.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, PURCHASE_RETURN_PURPOSES)
        original = self._journals.get_entry(entry_id, firm_id=firm_id)
        inventory_id = accounts[ControlAccountPurpose.INVENTORY]
        variance_id = accounts[ControlAccountPurpose.PURCHASE_PRICE_VARIANCE]
        stock = quantize_ledger(quantize_money(stock_value))

        lines: list[JournalLineData] = []
        credited_for_stock = ZERO
        for line in original.lines:
            if line.ledger_account_id == inventory_id:
                credited_for_stock += line.credit_amount - line.debit_amount
                continue
            if line.ledger_account_id == variance_id:
                # Folded into the one variance line below, so the reversal
                # carries a single figure rather than two that have to be read
                # together. Same sign as the inventory leg: between them they
                # carry the goods value the payable was raised for.
                credited_for_stock += line.credit_amount - line.debit_amount
                continue
            lines.append(
                JournalLineData(
                    ledger_account_id=line.ledger_account_id,
                    cost_center_id=line.cost_center_id,
                    profit_center_id=line.profit_center_id,
                    debit_amount=line.credit_amount,
                    credit_amount=line.debit_amount,
                    description=f"Cancelled {return_number}",
                )
            )
        lines.append(
            JournalLineData(
                ledger_account_id=inventory_id,
                debit_amount=stock,
                description=f"Goods back on the shelf from {return_number}",
            )
        )
        variance = quantize_ledger(credited_for_stock) - stock
        if variance != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=variance_id,
                    debit_amount=variance if variance > ZERO else ZERO,
                    credit_amount=-variance if variance < ZERO else ZERO,
                    description=f"Valuation difference cancelling {return_number}",
                )
            )
        return self._journals.reverse_entry(
            entry_id,
            firm_id=firm_id,
            reference_number=f"{return_number}-REV",
            actor_id=actor_id,
            lines=lines,
        )

    def post_stock_adjustment(
        self,
        *,
        firm_id: UUID,
        transaction_id: UUID,
        reference_number: str,
        transaction_date: date,
        value_delta: Decimal,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> JournalEntry | None:
        """Post a stock adjustment, which is the movement with no document.

        Every other movement has paperwork behind it -- a receipt, a dispatch, a
        return -- and an adjustment has none. That is what made it the worst of
        the three unposted movements: stock was written up or down and the
        ledger never heard, with nothing on any screen to hint the control
        account had stopped agreeing with the stock it controls.

        Stock going up debits inventory and credits the adjustment account;
        stock going down does the reverse, which is a write-off and a cost. The
        same account takes both sides so a firm can read its net adjustment in
        one place.

        Returns None when the adjustment moved no value at all -- a correction
        to a quantity the books valued at nothing has nothing to post, and an
        empty journal is worse than no journal.

        Args:
            firm_id: The owning firm.
            transaction_id: The inventory movement this posts.
            reference_number: What the adjustment was recorded against.
            transaction_date: The date stock moved.
            value_delta: The change in stock value, positive when stock rose.
            actor_id: The user who made the adjustment.
            remarks: Why, carried onto the journal line.

        Returns:
            The posted journal entry, or None when there was no value to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        delta = quantize_ledger(quantize_money(value_delta))
        if delta == ZERO:
            return None
        accounts = self._require_mapping(firm_id, STOCK_ADJUSTMENT_PURPOSES)
        context = self.context_for(firm_id, transaction_date)
        rising = delta > ZERO
        amount = delta if rising else -delta
        narration = remarks or f"Stock adjustment {reference_number}"
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                debit_amount=amount if rising else ZERO,
                credit_amount=ZERO if rising else amount,
                description=narration,
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY_ADJUSTMENT],
                debit_amount=ZERO if rising else amount,
                credit_amount=amount if rising else ZERO,
                description=narration,
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=transaction_date,
            reference_number=reference_number,
            description=f"Stock adjustment {reference_number}",
            lines=lines,
            source_module="inventory",
            source_id=transaction_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_opening_stock(
        self,
        *,
        firm_id: UUID,
        batch_id: UUID,
        reference_number: str,
        posting_date: date,
        stock_value: Decimal,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Post the stock a firm started with.

        Day-one stock arrived from nowhere the ledger can see: no supplier was
        invoiced for it and no money left. What it represents is what the
        owners put into the business, so inventory is debited and **opening
        balance equity** credited -- the counterpart the chart never had, which
        is why this was the one movement that could not post at all.

        The same account is what a balance sheet wants for any day-one balance,
        so a firm that later records opening receivables or opening cash has
        somewhere consistent to put them.

        Returns None when the batch carried no value: day-one stock recorded
        with no cost has nothing to post, and an empty journal claims something
        happened in the ledger when nothing did.

        Args:
            firm_id: The owning firm.
            batch_id: The opening stock batch being posted.
            reference_number: The batch reference, used as the journal reference.
            posting_date: The date the firm says it started with this stock.
            stock_value: What the stock was brought in at.
            actor_id: The user posting the batch.

        Returns:
            The posted journal entry, or None when there was no value.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        value = quantize_ledger(quantize_money(stock_value))
        if value == ZERO:
            return None
        accounts = self._require_mapping(firm_id, OPENING_STOCK_PURPOSES)
        context = self.context_for(firm_id, posting_date)
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                debit_amount=value,
                description=f"Opening stock {reference_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[
                    ControlAccountPurpose.OPENING_BALANCE_EQUITY
                ],
                credit_amount=value,
                description=f"Opening stock {reference_number}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=posting_date,
            reference_number=reference_number,
            description=f"Opening stock {reference_number}",
            lines=lines,
            source_module="inventory",
            source_id=batch_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_opening_balance(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        reference_number: str,
        posting_date: date,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Post what a customer already owed on the day the firm started here.

        A day-one receivable arrived from nowhere the ledger can see: no
        invoice was raised for it and no goods left. What it represents is what
        the owners brought into the business, so the receivable is debited and
        **opening balance equity** credited -- the same counterpart day-one
        stock takes, which is what makes a balance sheet built from these
        add up.

        A negative opening balance is a customer in credit: the firm owes them,
        so the two legs swap. Nothing about that is a receipt -- no money moved
        -- which is why it is not booked as one.

        Until now nothing posted at all. `CustomerService` wrote the balance
        and a receivable transaction and stopped there, so a firm's customers
        could owe it 885,000 against a receivable control account of zero, and
        `verify_sample_data.py` reported the gap without anything explaining
        it.

        Args:
            firm_id: The owning firm.
            customer_id: Whose balance this is.
            reference_number: The customer's code, used as the reference.
            posting_date: The date the firm says the balance stood at.
            amount: Positive when the customer owes, negative when they are in
                credit.
            actor_id: The user recording it.

        Returns:
            The posted entry, or None when the balance is nil at the ledger's
            scale -- an empty journal claims something happened when nothing
            did.

        Raises:
            ValidationError: If accounts or an open period are missing. A
                balance nobody can book is one the firm should not be told it
                has recorded.

        """
        total = quantize_ledger(quantize_money(amount))
        if total == ZERO:
            return None
        accounts = self._require_mapping(firm_id, OPENING_BALANCE_PURPOSES)
        context = self.context_for(firm_id, posting_date)
        receivable = accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE]
        equity = accounts[ControlAccountPurpose.OPENING_BALANCE_EQUITY]
        owed = total > ZERO
        description = f"Opening balance {reference_number}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=posting_date,
            reference_number=reference_number,
            description=description,
            lines=[
                JournalLineData(
                    ledger_account_id=receivable if owed else equity,
                    debit_amount=abs(total),
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=equity if owed else receivable,
                    credit_amount=abs(total),
                    description=description,
                ),
            ],
            source_module="customers",
            source_id=customer_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_credit_note(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        reference_number: str,
        note_date: date,
        amount: Decimal,
        actor_id: UUID,
        narration: str | None = None,
    ) -> JournalEntry:
        """Post a credit note raised against a customer.

        A credit note reduces what a customer owes, so it reduces the
        receivable control account: the balance and the ledger disagree by its
        value otherwise. It was left unposted on the reasoning that it moves no
        money, which is the wrong test -- what matters is whether the receivable
        moves, and this does.

        Cancelling an invoice does **not** come through here. That reverses the
        invoice's own journal instead, which mirrors the revenue and tax it
        raised; sending it here would credit the receivable a second time and
        book the whole invoice as a sales return.

        Args:
            firm_id: The owning firm.
            customer_id: Who is being credited.
            reference_number: What the note is called.
            note_date: The date it was raised.
            amount: How much the customer no longer owes.
            actor_id: The user raising it.
            narration: Why, carried onto the journal lines.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, CREDIT_NOTE_PURPOSES)
        context = self.context_for(firm_id, note_date)
        total = quantize_ledger(quantize_money(amount))
        description = narration or f"Credit note {reference_number}"
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_RETURNS],
                debit_amount=total,
                description=description,
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                credit_amount=total,
                description=description,
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=note_date,
            reference_number=reference_number,
            description=f"Credit note {reference_number}",
            lines=lines,
            source_module="customers",
            source_id=customer_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_customer_refund(
        self,
        *,
        firm_id: UUID,
        settlement_id: UUID,
        settlement_number: str,
        settlement_date: date,
        amount: Decimal,
        money_account_id: UUID,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post money handed back to a customer.

        The mirror of a receipt: the receivable is debited because the customer
        is no longer owed the advance they paid, and the cash or bank account
        the money left is credited.

        It is a separate posting from a payment despite both being money out.
        A payment settles what the firm owes a supplier and touches payables; a
        refund returns what a customer overpaid and touches receivables, and
        putting them through one method would mean a flag deciding which
        control account real money lands in.

        Args:
            firm_id: The owning firm.
            settlement_id: The source document.
            settlement_number: The document number, used as the reference.
            settlement_date: The date the money moved.
            amount: How much was handed back.
            money_account_id: The cash or bank account it left.
            actor_id: The user recording it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, REFUND_PURPOSES)
        context = self.context_for(firm_id, settlement_date)
        total = quantize_ledger(quantize_money(amount))
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                debit_amount=total,
                description=f"Refund {settlement_number}",
            ),
            JournalLineData(
                ledger_account_id=money_account_id,
                credit_amount=total,
                description=f"Refund {settlement_number}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=settlement_date,
            reference_number=settlement_number,
            description=f"Customer refund {settlement_number}",
            lines=lines,
            source_module="settlements",
            source_id=settlement_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_settlement(
        self,
        *,
        firm_id: UUID,
        settlement_id: UUID,
        settlement_number: str,
        settlement_date: date,
        amount: Decimal,
        is_receipt: bool,
        money_account_id: UUID,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post money arriving from a customer or going out to a vendor.

        Two legs and no arithmetic to get wrong: a receipt debits the cash or
        bank account the money landed in and credits the receivable; a payment
        debits the payable and credits the account the money left.

        Which invoices the settlement clears does not appear here, and should
        not. The ledger records that the firm's receivable fell by this much;
        *which* invoice fell is the subsidiary ledger's business, and posting a
        line per invoice would put the sales ledger inside the general one.

        Args:
            firm_id: The owning firm.
            settlement_id: The source document.
            settlement_number: The document number, used as the reference.
            settlement_date: The date the money moved.
            amount: How much moved.
            is_receipt: True for money in, False for money out.
            money_account_id: The cash or bank account it moved through.
            actor_id: The user recording it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        purposes = RECEIPT_PURPOSES if is_receipt else PAYMENT_PURPOSES
        accounts = self._require_mapping(firm_id, purposes)
        context = self.context_for(firm_id, settlement_date)
        total = quantize_ledger(quantize_money(amount))
        party_purpose = (
            ControlAccountPurpose.ACCOUNTS_RECEIVABLE
            if is_receipt
            else ControlAccountPurpose.ACCOUNTS_PAYABLE
        )
        kind = "Receipt" if is_receipt else "Payment"
        money_leg = JournalLineData(
            ledger_account_id=money_account_id,
            debit_amount=total if is_receipt else ZERO,
            credit_amount=ZERO if is_receipt else total,
            description=f"{kind} {settlement_number}",
        )
        party_leg = JournalLineData(
            ledger_account_id=accounts[party_purpose],
            debit_amount=ZERO if is_receipt else total,
            credit_amount=total if is_receipt else ZERO,
            description=f"{kind} {settlement_number}",
        )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=settlement_date,
            reference_number=settlement_number,
            description=f"{kind} {settlement_number}",
            lines=[money_leg, party_leg],
            source_module="settlements",
            source_id=settlement_id,
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
        # Round to the ledger's scale before the zero test, not the document's:
        # a movement worth 0.004 is not zero at four decimals but is nothing at
        # two, and it would reach the engine as a journal whose legs both round
        # to nil -- which the engine rejects, failing the dispatch.
        cost = quantize_ledger(cost_amount)
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

    def post_sales_return(
        self,
        *,
        firm_id: UUID,
        return_id: UUID,
        return_number: str,
        return_date: date,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Post what a customer is credited for goods they sent back.

        A sales invoice undone: the receivable falls by the whole credit, the
        output tax charged on the way out is reversed with the goods, and the
        rest goes to **sales returns** rather than against revenue directly.
        Debiting revenue would net the return away and leave nobody able to say
        how much was sold or how much came back -- the two numbers a firm looks
        at when deciding whether it has a quality problem.

        The cost of the goods is not posted here. Stock returns at what it cost,
        the credit is at what it sold for, and the two answer different
        questions -- ``post_goods_return_to_stock`` carries the first, the way
        ``post_goods_issue`` carries it on the way out.

        Args:
            firm_id: The owning firm.
            return_id: The source document.
            return_number: The document number, used as the reference.
            return_date: The date the goods came back.
            taxable_amount: What is credited before tax.
            tax_amount: Output tax being reversed.
            total_amount: What the customer no longer owes, tax included.
            actor_id: The user completing the return.

        Returns:
            The posted entry, or None when the credit rounds to nothing at the
            ledger's two decimals. Goods sent out free -- samples, warranty
            replacements -- come back worth nothing to say, and the engine
            refuses a journal whose legs are both nil, which failed the whole
            return with the stock already on the shelf.

        Raises:
            ValidationError: If accounts or an open period are missing, or the
                amounts do not balance.

        """
        taxable = quantize_money(taxable_amount)
        tax = quantize_money(tax_amount)
        total = quantize_money(total_amount)
        if taxable + tax != total:
            raise ValidationError(
                f"Sales return {return_number} does not balance: taxable "
                f"{taxable} plus tax {tax} is not total {total}."
            )

        # Derived from the two figures the customer sees, so the three legs
        # still agree once each is rounded to the ledger's two decimals.
        ledger_total = quantize_ledger(total)
        ledger_tax = quantize_ledger(tax)
        ledger_taxable = ledger_total - ledger_tax
        if ledger_total == ZERO:
            return None
        accounts = self._require_mapping(firm_id, SALES_RETURN_PURPOSES)
        context = self.context_for(firm_id, return_date)

        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_RETURNS],
                debit_amount=ledger_taxable,
                description=f"Sales return {return_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                credit_amount=ledger_total,
                description=f"Credit for sales return {return_number}",
            ),
        ]
        if ledger_tax != ZERO:
            lines.insert(
                1,
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.OUTPUT_TAX],
                    debit_amount=ledger_tax,
                    description=f"Output tax reversed on {return_number}",
                ),
            )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=return_date,
            reference_number=return_number,
            description=f"Sales return {return_number}",
            lines=lines,
            source_module="sales_return",
            source_id=return_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_goods_return_to_stock(
        self,
        *,
        firm_id: UUID,
        document_id: UUID,
        document_number: str,
        return_date: date,
        cost_amount: Decimal,
        source_module: str,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Move the cost of returned goods back out of expense into inventory.

        ``post_goods_issue`` exactly reversed, and it uses the same two accounts
        on purpose: what left as cost of goods sold when the delivery note
        dispatched comes back when the customer returns it. Posting only the
        customer's credit and not this would leave the goods on the shelf and
        their cost in the profit and loss.

        Args:
            firm_id: The owning firm.
            document_id: The returning document.
            document_number: Its number, used as the journal reference.
            return_date: The date the journal carries.
            cost_amount: What the movement put back into stock.
            source_module: The module raising the posting.
            actor_id: The user completing the return.

        Returns:
            The posted entry, or None when the movement carried no value --
            stock received before valuation existed still has no cost, and a
            journal whose legs both round to nil is one the engine refuses.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        cost = quantize_ledger(cost_amount)
        if cost == ZERO:
            return None
        accounts = self._require_mapping(firm_id, GOODS_ISSUE_PURPOSES)
        context = self.context_for(firm_id, return_date)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=return_date,
            reference_number=f"{document_number}-COST",
            description=f"Cost of goods returned on {document_number}",
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                    debit_amount=cost,
                    description=f"Stock returned on {document_number}",
                ),
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.COST_OF_GOODS_SOLD
                    ],
                    credit_amount=cost,
                    description=f"Cost of goods sold reversed {document_number}",
                ),
            ],
            source_module=source_module,
            source_id=document_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_goods_receipt(
        self,
        *,
        firm_id: UUID,
        document_id: UUID,
        document_number: str,
        receipt_date: date,
        cost_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Bring received stock onto the balance sheet.

        Stock arrives before the supplier's invoice does, so the credit goes to
        goods received not invoiced rather than to payables — the purchase
        invoice clears that account when it arrives. Without this the inventory
        account is only ever credited by dispatches and drifts negative while
        the warehouse fills up.

        Args:
            firm_id: The owning firm.
            document_id: The receipt.
            document_number: Its number, used as the journal reference.
            receipt_date: The date the journal carries.
            cost_amount: Total cost brought into stock.
            actor_id: The receiving user.

        Returns:
            The posted entry, or None when the receipt brought in no value.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        cost = quantize_ledger(cost_amount)
        if cost == ZERO:
            return None
        accounts = self._require_mapping(firm_id, GOODS_RECEIPT_PURPOSES)
        context = self.context_for(firm_id, receipt_date)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=receipt_date,
            reference_number=document_number,
            description=f"Goods received on {document_number}",
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                    debit_amount=cost,
                    description=f"Stock received on {document_number}",
                ),
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED
                    ],
                    credit_amount=cost,
                    description=f"Awaiting supplier invoice for {document_number}",
                ),
            ],
            source_module="goods_receipt",
            source_id=document_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def reverse_goods_receipt(
        self,
        *,
        firm_id: UUID,
        entry_id: UUID,
        document_number: str,
        stock_value: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Take a cancelled receipt off the books at what the stock gave back.

        The accrual goes in full: the firm does not owe a supplier for goods it
        has handed back, so goods received not invoiced is debited with
        everything the receipt raised. Inventory is credited with what the
        warehouse actually removed, which is the moving average the stock is
        carried at today and not the price on the receipt.

        Those two are the same number only until something else is received at
        another price. When they differ the gap is a purchase price variance,
        the same account `post_purchase_return` uses for the same reason --
        goods bought at several prices sit at one average, and any document
        that moves them at a different figure leaves a difference the P&L has
        to carry. Mirroring the original entry instead credited inventory with
        a number no movement ever removed: measured on a seeded store, 8,040.00
        mirrored out against 5,752.60 of stock, leaving it 2,287.42 out.

        Args:
            firm_id: The owning firm.
            entry_id: The entry the receipt posted when it completed.
            document_number: The receipt number, used as the reference.
            stock_value: What the reversing movements actually took out.
            actor_id: The user cancelling the receipt.

        Returns:
            The posted reversal.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, GOODS_RECEIPT_REVERSAL_PURPOSES)
        original = self._journals.get_entry(entry_id, firm_id=firm_id)
        accrued = quantize_ledger(
            sum(
                (line.debit_amount for line in original.lines),
                start=ZERO,
            )
        )
        stock = quantize_ledger(quantize_money(stock_value))
        variance = accrued - stock
        lines = [
            JournalLineData(
                ledger_account_id=accounts[
                    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED
                ],
                debit_amount=accrued,
                description=f"Cancelled {document_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                credit_amount=stock,
                description=f"Stock returned off {document_number}",
            ),
        ]
        if variance != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.PURCHASE_PRICE_VARIANCE
                    ],
                    debit_amount=-variance if variance < ZERO else ZERO,
                    credit_amount=variance if variance > ZERO else ZERO,
                    description=(f"Valuation difference cancelling {document_number}"),
                )
            )
        return self._journals.reverse_entry(
            entry_id,
            firm_id=firm_id,
            reference_number=f"{document_number}-REV",
            actor_id=actor_id,
            lines=lines,
        )

    def post_purchase_invoice(
        self,
        *,
        firm_id: UUID,
        invoice_id: UUID,
        invoice_number: str,
        invoice_date: date,
        goods_amount: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal,
        actor_id: UUID,
        accrued_amount: Decimal | None = None,
    ) -> JournalEntry:
        """Turn a supplier invoice into a payable and clear the receipt accrual.

        The goods were already brought onto the balance sheet when they were
        received, credited to goods received not invoiced. This debits that
        accrual back out and credits payables instead, so the liability moves
        from "stock we owe for" to "this supplier, this invoice".

        Inventory is deliberately untouched: it was valued at what the receipt
        cost, and re-valuing it here would double-count. Where the invoice
        disagrees with the receipt the difference is a purchase price variance,
        which this does not yet model — see the note in the module that raises
        it.

        Args:
            firm_id: The owning firm.
            invoice_id: The source document.
            invoice_number: The document number, used as the journal reference.
            invoice_date: The date the journal carries.
            goods_amount: Net of discount, before tax.
            tax_amount: Recoverable input tax.
            total_amount: What is owed to the supplier.
            actor_id: The approving user.
            accrued_amount: What the receipt actually accrued, when it differs
                from what the supplier billed. Defaults to the invoice's own
                goods value, which posts no variance.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing, or the
                amounts do not balance.

        """
        accounts = self._require_mapping(firm_id, PURCHASE_INVOICE_PURPOSES)
        context = self.context_for(firm_id, invoice_date)

        goods = quantize_money(goods_amount)
        tax = quantize_money(tax_amount)
        total = quantize_money(total_amount)
        if goods + tax != total:
            raise ValidationError(
                f"Invoice {invoice_number} does not balance: goods {goods} "
                f"plus tax {tax} is not total {total}."
            )

        # The accrual is cleared at what the receipt actually cost. Any gap
        # between that and what the supplier billed is a purchase price
        # variance, and it belongs in the P&L: clearing the accrual at the
        # invoice price instead would leave the difference sitting in the
        # accrual forever, growing quietly and explaining nothing.
        # As on the sales side: derive the goods leg at the ledger's scale from
        # the total and the tax, so payables, input tax, the accrual and the
        # variance still balance once each is rounded to two decimals.
        ledger_total = quantize_ledger(total)
        ledger_tax = quantize_ledger(tax)
        ledger_goods = ledger_total - ledger_tax

        accrued = (
            ledger_goods if accrued_amount is None else quantize_ledger(accrued_amount)
        )
        variance = ledger_goods - accrued
        lines = [
            JournalLineData(
                ledger_account_id=accounts[
                    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED
                ],
                debit_amount=accrued,
                description=f"Clearing receipt accrual for {invoice_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                credit_amount=ledger_total,
                description=f"Supplier invoice {invoice_number}",
            ),
        ]
        if ledger_tax != ZERO:
            lines.insert(
                1,
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.INPUT_TAX],
                    debit_amount=ledger_tax,
                    description=f"Input tax on {invoice_number}",
                ),
            )
        if variance != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.PURCHASE_PRICE_VARIANCE
                    ],
                    debit_amount=variance if variance > ZERO else ZERO,
                    credit_amount=-variance if variance < ZERO else ZERO,
                    description=f"Price variance on {invoice_number}",
                )
            )

        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=invoice_date,
            reference_number=invoice_number,
            description=f"Purchase invoice {invoice_number}",
            lines=lines,
            source_module="purchase_invoice",
            source_id=invoice_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
