"""Post business documents to the general ledger.

Until now nothing did. Finance held a chart of accounts, a journal engine and a
trial balance that could only ever reflect hand-keyed journals, because no
module outside ``app/finance`` imported it. Approving a sales invoice moved a
customer balance and left the ledger untouched.

Posting **fails the operation it belongs to** rather than being skipped. An
approved invoice with no journal is the silent gap this is meant to close, so a
missing control account or a closed period refuses the approval outright.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, select
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
    PURPOSE_LABELS,
    ControlAccountPurpose,
    ControlAccountService,
    input_tax_purpose,
    output_tax_purpose,
    rcm_payable_purpose,
)
from app.finance.services.journal_engine import (
    COVERING_PERIOD_ORDER,
    JournalEntryEngine,
    JournalLineData,
)
from app.finance.services.journal_engine import (
    quantize_money as quantize_ledger,
)

#: The output-tax legs resolve their own purposes per GST head (backlog
#: 63.3), as a purchase's input-tax legs do -- here and on the two below.
SALES_INVOICE_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_REVENUE,
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

#: What a day-one supplier bill moves: the payable twin of the above.
VENDOR_OPENING_BILL_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_PAYABLE,
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

#: Recognising what a salesman has earned: a cost the firm has incurred
#: and a debt it has not yet settled.
COMMISSION_ACCRUAL_PURPOSES = (
    ControlAccountPurpose.COMMISSION_EXPENSE,
    ControlAccountPurpose.COMMISSION_PAYABLE,
)

#: Settling it. The money account is chosen per payment, so only the debt
#: side is resolved from the mapping.
COMMISSION_PAYMENT_PURPOSES = (ControlAccountPurpose.COMMISSION_PAYABLE,)

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
)

#: A credit note raised as a document, which states its tax. The bare
#: receivable adjustment it replaced could not: it carried one figure and no
#: lines, so it had nothing to say what rate to reverse (D-FIN-23).
CREDIT_NOTE_DOCUMENT_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_RETURNS,
)

#: A debit note to a customer: the receivable it raises and the revenue it
#: adds -- a sale's own accounts, because it is more of that sale, not a
#: separate supply (backlog 77 row 5). The output tax legs resolve their own
#: purposes per GST head, as the invoice's do.
CUSTOMER_DEBIT_NOTE_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.SALES_REVENUE,
)

#: A debit note to a supplier: the payable it reduces and the account the
#: value comes back through. The input tax legs resolve their own purposes per
#: GST head, as a purchase return's do.
DEBIT_NOTE_DOCUMENT_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_PAYABLE,
    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE,
)

PAYMENT_PURPOSES = (ControlAccountPurpose.ACCOUNTS_PAYABLE,)

#: A loyalty scheme. Earning costs the firm money there and then, which is
#: what makes the cost land in the month it was incurred rather than whenever
#: customers happen to collect; redeeming settles a receivable with credit the
#: firm already owed.
LOYALTY_EARN_PURPOSES = (
    ControlAccountPurpose.LOYALTY_EXPENSE,
    ControlAccountPurpose.LOYALTY_PAYABLE,
)
LOYALTY_REDEEM_PURPOSES = (
    ControlAccountPurpose.LOYALTY_PAYABLE,
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
)
#: Points that ran out of time. The mirror of the accrual rather than of a
#: redemption: nothing was settled, so the liability is released and the cost
#: it raised comes back. Without it `Loyalty Payable` keeps a debt no customer
#: can ever claim, growing with every sweep.
LOYALTY_EXPIRY_PURPOSES = LOYALTY_EARN_PURPOSES

#: Tax collected at source. The buyer owes it on top of the bill, so it raises
#: a receivable rather than reducing one -- collecting it is not the same event
#: as being paid it.
TCS_PURPOSES = (
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ControlAccountPurpose.TCS_PAYABLE,
)

GOODS_RECEIPT_PURPOSES = (
    ControlAccountPurpose.INVENTORY,
    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED,
)


#: Which head carries the paisa that rounding leaves, first one charged wins:
#: the order the GST returns settle a document in (`app/tax/services/gst_buckets`).
_RESIDUAL_HEADS = ("IGST", "SGST", "UTGST", "CGST")


def _split_by_purpose(
    ledger_tax: Decimal,
    tax_by_component: dict[str, Decimal] | None,
    *,
    purpose_of: Callable[[str | None], ControlAccountPurpose],
    fallback: ControlAccountPurpose,
) -> dict[ControlAccountPurpose, Decimal]:
    """Split a ledger tax figure across the purposes its components name.

    Each head is quantized to the ledger's two decimals and the residual
    against ``ledger_tax`` goes on **the head the returns put it on**, so the
    parts sum exactly and the books agree with the return head by head:
    IGST where it was charged, else SGST, else CGST -- the order
    `settle_to_ledger` and `intra_state_halves` use. It used to go on the
    largest, which on two equal halves is the first, CGST: a bill taxed
    36.855 + 36.855 was filed as CGST 36.86 / SGST 36.85 and booked the other
    way round (D-SELL-48). A split naming none of the three keeps the largest.
    Nothing named -- no map, or only zeros -- puts the whole on ``fallback``.
    """
    if ledger_tax == ZERO:
        return {}
    by_purpose: dict[ControlAccountPurpose, Decimal] = {}
    for code, amount in (tax_by_component or {}).items():
        purpose = purpose_of(code)
        by_purpose[purpose] = by_purpose.get(purpose, ZERO) + quantize_ledger(
            quantize_money(amount)
        )
    by_purpose = {p: a for p, a in by_purpose.items() if a != ZERO}
    if not by_purpose:
        return {fallback: ledger_tax}
    residual = ledger_tax - sum(by_purpose.values(), ZERO)
    if residual != ZERO:
        charged = {
            code.upper()
            for code, amount in (tax_by_component or {}).items()
            if amount != ZERO
        }
        carrier = next(
            (
                purpose_of(head)
                for head in _RESIDUAL_HEADS
                if head in charged and purpose_of(head) in by_purpose
            ),
            max(by_purpose, key=lambda p: by_purpose[p]),
        )
        by_purpose[carrier] += residual
    return by_purpose


def output_tax_purposes(
    tax_amount: Decimal, tax_by_component: dict[str, Decimal] | None
) -> tuple[ControlAccountPurpose, ...]:
    """Return the output-tax purposes a document's tax will post to.

    So a posting can name every unmapped account in one refusal, the tax
    heads included, rather than failing on the first gap it reaches.
    """
    return tuple(
        _split_by_purpose(
            quantize_ledger(quantize_money(tax_amount)),
            tax_by_component,
            purpose_of=output_tax_purpose,
            fallback=ControlAccountPurpose.OUTPUT_TAX,
        )
    )


@dataclass(frozen=True, slots=True)
class PostingContext:
    """The firm references every journal needs, resolved once."""

    journal_type_id: UUID
    voucher_type_id: UUID
    accounting_period_id: UUID


def prefixed_reference(prefix: str, number: str) -> str:
    """Return a journal reference that says what it is, once.

    A landed cost voucher and a Bill of Entry are referenced under ``LCV-``
    and ``BOE-``. Their own numbers start that way by default, and the
    posting added the prefix regardless: ``LCV-LCV-2026-2027-000001``
    (D-BUY-47). The prefix is kept for a firm that numbers the document some
    other way.
    """
    if number.upper().startswith(f"{prefix}-"):
        return number
    return f"{prefix}-{number}"


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
        # D-FIN-15: the first type by code was taken whether or not it was in
        # use. Decided by the usual convention: documents post under the
        # firm's general journal (GEN) and journal voucher (JV) -- the pair
        # Open the books creates -- while they are active, and otherwise
        # under the first active type by code. An inactive type is never used.
        journal_type_id = self._session.scalar(
            select(JournalType.id)
            .where(
                JournalType.firm_id == firm_id,
                JournalType.is_deleted.is_(False),
                JournalType.is_active.is_(True),
            )
            .order_by(
                case((JournalType.code == "GEN", 0), else_=1),
                JournalType.code.asc(),
            )
            .limit(1)
        )
        if journal_type_id is None:
            raise ValidationError(
                "This firm has no active journal type configured, so documents "
                "cannot post."
            )
        voucher_type_id = self._session.scalar(
            select(VoucherType.id)
            .where(
                VoucherType.firm_id == firm_id,
                VoucherType.is_deleted.is_(False),
                VoucherType.is_active.is_(True),
            )
            .order_by(
                case((VoucherType.code == "JV", 0), else_=1),
                VoucherType.code.asc(),
            )
            .limit(1)
        )
        if voucher_type_id is None:
            raise ValidationError(
                "This firm has no active voucher type configured, so documents "
                "cannot post."
            )
        period_id = self._session.scalar(
            select(AccountingPeriod.id)
            .where(
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.starts_on <= on,
                AccountingPeriod.ends_on >= on,
                AccountingPeriod.status == PeriodStatus.OPEN.value,
                AccountingPeriod.is_deleted.is_(False),
            )
            # Deterministic where more than one covers the date (D-FIN-6).
            .order_by(*COVERING_PERIOD_ORDER)
            .limit(1)
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

    def _input_tax_legs(
        self,
        *,
        firm_id: UUID,
        ledger_tax: Decimal,
        tax_by_component: dict[str, Decimal] | None,
        describe: str,
        credit: bool = False,
    ) -> list[JournalLineData]:
        """Return the input-tax legs of a purchase posting, one per GST head.

        With a component map -- what `purchase_invoice_line_taxes` recorded --
        each head is posted to its own account (`input_tax_purpose`), so GSTR-3B
        can read the credit it claims per head straight off the books
        (D-CMP-20). Without one -- a bill written before the rows existed, or
        a tax system this does not split -- the whole amount posts to
        `INPUT_TAX` as it always did.
        """
        return self._tax_legs(
            firm_id=firm_id,
            ledger_tax=ledger_tax,
            tax_by_component=tax_by_component,
            describe=describe,
            purpose_of=input_tax_purpose,
            fallback=ControlAccountPurpose.INPUT_TAX,
            credit=credit,
        )

    def _blocked_tax_legs(
        self,
        *,
        firm_id: UUID,
        ledger_blocked: Decimal,
        describe: str,
        credit: bool = False,
    ) -> list[JournalLineData]:
        """Return the leg booking tax the firm may not claim (backlog 78 row 1).

        Blocked under s.17(5) or otherwise ineligible, the tax a supplier
        charged is a cost of the purchase, not input credit: it goes to
        `INELIGIBLE_INPUT_TAX`, debited on the bill and credited back when the
        goods or the price come off. Resolved only when there is some, so a
        firm that never buys a blocked supply needs no mapping for it.
        """
        if ledger_blocked <= ZERO:
            return []
        account = self._require_mapping(
            firm_id, (ControlAccountPurpose.INELIGIBLE_INPUT_TAX,)
        )[ControlAccountPurpose.INELIGIBLE_INPUT_TAX]
        return [
            JournalLineData(
                ledger_account_id=account,
                debit_amount=ZERO if credit else ledger_blocked,
                credit_amount=ledger_blocked if credit else ZERO,
                description=f"Input tax not claimable {describe}",
            )
        ]

    def _output_tax_legs(
        self,
        *,
        firm_id: UUID,
        ledger_tax: Decimal,
        tax_by_component: dict[str, Decimal] | None,
        describe: str,
        credit: bool = True,
    ) -> list[JournalLineData]:
        """Return the output-tax legs of a sales posting, one per GST head.

        The mirror of :meth:`_input_tax_legs` (backlog 63.3): IGST, CGST and
        SGST (UTGST with it) each to its own account, so the ledger answers
        "how much CGST do we owe" without a report. Cess, another tax system,
        or a document with no component map posts to `OUTPUT_TAX` -- where
        every sale went before the split.
        """
        return self._tax_legs(
            firm_id=firm_id,
            ledger_tax=ledger_tax,
            tax_by_component=tax_by_component,
            describe=describe,
            purpose_of=output_tax_purpose,
            fallback=ControlAccountPurpose.OUTPUT_TAX,
            credit=credit,
        )

    def _tax_legs(
        self,
        *,
        firm_id: UUID,
        ledger_tax: Decimal,
        tax_by_component: dict[str, Decimal] | None,
        describe: str,
        purpose_of: Callable[[str | None], ControlAccountPurpose],
        fallback: ControlAccountPurpose,
        credit: bool,
    ) -> list[JournalLineData]:
        """Split one tax leg across the accounts its components belong to.

        Rounding the sum is not rounding the parts: each head is quantized to
        the ledger's two decimals and the residual against ``ledger_tax`` goes
        on the largest head, so the legs sum to exactly what the document's
        tax leg must be.
        """
        by_purpose = _split_by_purpose(
            ledger_tax, tax_by_component, purpose_of=purpose_of, fallback=fallback
        )
        if not by_purpose:
            return []
        accounts = self._require_mapping(firm_id, tuple(by_purpose))
        return [
            JournalLineData(
                ledger_account_id=accounts[purpose],
                debit_amount=ZERO if credit else amount,
                credit_amount=amount if credit else ZERO,
                description=f"{PURPOSE_LABELS[purpose]} {describe}",
            )
            for purpose, amount in by_purpose.items()
        ]

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
        tax_by_component: dict[str, Decimal] | None = None,
        other_charges_amount: Decimal = ZERO,
    ) -> JournalEntry | None:
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
            tax_by_component: The tax per component code as the invoice's
                lines recorded it, so each GST head is owed through its own
                account (backlog 63.3). None posts the total to `OUTPUT_TAX`.
            other_charges_amount: The part of ``taxable_amount`` that is the
                bill's separately taxed charges, before tax (SG-4). Credited
                to `OTHER_CHARGES_RECOVERED` and taken off the revenue leg.

        Returns:
            The posted journal entry, or None for a bill whose every leg is
            nothing: no zero lines are written (D-SELL-53).

        Raises:
            ValidationError: If accounts or an open period are missing, or the
                amounts do not balance.

        """
        # Rounded once, as the ledger holds it, and the same figure comes off
        # revenue, so the entry balances whatever the fourth decimal was.
        ledger_charges = quantize_ledger(quantize_money(other_charges_amount))
        accounts = self._require_mapping(
            firm_id,
            SALES_INVOICE_PURPOSES + output_tax_purposes(tax_amount, tax_by_component)
            # Asked for only by a bill that carries a charge, so a firm that
            # never uses them is never refused for the want of the account.
            + (
                (ControlAccountPurpose.OTHER_CHARGES_RECOVERED,)
                if ledger_charges != ZERO
                else ()
            ),
        )
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

        # What is left for revenue once tax and charges are taken out of the
        # total. On a bill that comes to nothing but still carries tax it is
        # negative -- the firm bore the tax -- and is debited rather than
        # credited as a negative (D-SELL-53).
        ledger_revenue = ledger_taxable - ledger_charges
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                debit_amount=ledger_total,
                description=f"Invoice {invoice_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_REVENUE],
                debit_amount=max(-ledger_revenue, ZERO),
                credit_amount=max(ledger_revenue, ZERO),
                description=f"Invoice {invoice_number}",
            ),
        ]
        if ledger_charges != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.OTHER_CHARGES_RECOVERED
                    ],
                    credit_amount=ledger_charges,
                    description=f"Charges on invoice {invoice_number}",
                )
            )
        lines.extend(
            self._output_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_tax,
                tax_by_component=tax_by_component,
                describe=f"on {invoice_number}",
            )
        )
        # A bill that comes to nothing -- a 100% discount, or goods given
        # free -- has legs of 0.00, and one whose every leg is nothing has no
        # entry to post. The goods' cost was posted by the dispatch.
        lines = [
            line
            for line in lines
            if line.debit_amount != ZERO or line.credit_amount != ZERO
        ]
        if not lines:
            return None

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
        tax_by_component: dict[str, Decimal] | None = None,
        reverse_charge_by_component: dict[str, Decimal] | None = None,
        blocked_tax_amount: Decimal = ZERO,
        grni_amount: Decimal = ZERO,
    ) -> JournalEntry | None:
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
            tax_by_component: The tax per component as the bill the goods came
                off recorded it, so each head's credit is reversed through its
                own account (D-CMP-20). None credits `INPUT_TAX` as a whole.
            reverse_charge_by_component: The returned goods' share of their
                bill's reverse charge, per component (backlog 68 row 8). The
                liability and the credit the bill raised both come off.
            blocked_tax_amount: The returned goods' share of tax their bill
                could not claim (backlog 78 row 1), credited back to
                `INELIGIBLE_INPUT_TAX` rather than off input tax.
            grni_amount: What the part returned before any bill reached it
                takes off goods received not invoiced, at the receipt's cost
                (D-BUY-26). That part is no payable and took no input
                credit, so ``total_amount`` and ``tax_amount`` are only the
                billed part's; a return wholly before billing posts Dr GRNI /
                Cr inventory and nothing else.

        Returns:
            The posted journal entry, or None when the return moved no value
            at all -- goods that cost nothing, sent back before any bill.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, PURCHASE_RETURN_PURPOSES)
        ledger_grni = quantize_ledger(quantize_money(grni_amount))
        if ledger_grni != ZERO:
            accounts.update(
                self._require_mapping(
                    firm_id, (ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED,)
                )
            )
        context = self.context_for(firm_id, return_date)

        # Derived at the ledger's scale from the two figures the supplier sees,
        # so payables, input tax, inventory and the variance still balance once
        # each is rounded to two decimals.
        ledger_total = quantize_ledger(quantize_money(total_amount))
        ledger_tax = quantize_ledger(quantize_money(tax_amount))
        ledger_goods = ledger_total - ledger_tax
        ledger_stock = quantize_ledger(quantize_money(stock_value))
        variance = ledger_goods + ledger_grni - ledger_stock

        lines = []
        if ledger_total != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                    debit_amount=ledger_total,
                    description=f"Purchase return {return_number}",
                )
            )
        if ledger_grni != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED
                    ],
                    debit_amount=ledger_grni,
                    description=f"Returned before billing on {return_number}",
                )
            )
        lines.append(
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                credit_amount=ledger_stock,
                description=f"Goods returned on {return_number}",
            )
        )
        # The share the bill could not claim goes back to the cost account
        # it was booked to, not off input tax (backlog 78 row 1).
        ledger_blocked = min(
            quantize_ledger(quantize_money(blocked_tax_amount)), ledger_tax
        )
        lines.extend(
            self._input_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_tax - ledger_blocked,
                tax_by_component=tax_by_component,
                describe=f"reversed on {return_number}",
                credit=True,
            )
        )
        lines.extend(
            self._blocked_tax_legs(
                firm_id=firm_id,
                ledger_blocked=ledger_blocked,
                describe=f"reversed on {return_number}",
                credit=True,
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
        lines.extend(
            self._reverse_charge_taken_off(
                firm_id=firm_id,
                reverse_charge_by_component=reverse_charge_by_component,
                describe=return_number,
            )
        )

        if all(
            line.debit_amount == ZERO and line.credit_amount == ZERO for line in lines
        ):
            return None
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
        expense_purpose: ControlAccountPurpose = (
            ControlAccountPurpose.INVENTORY_ADJUSTMENT
        ),
        expense_account_id: UUID | None = None,
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
            expense_purpose: The account the other side lands in: the
                inventory adjustment account, or for stock issued rather than
                lost, its own expense (STK-3).
            expense_account_id: The reason's own account, when it names one
                (STK-7); it outranks ``expense_purpose``.

        Returns:
            The posted journal entry, or None when there was no value to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        delta = quantize_ledger(quantize_money(value_delta))
        if delta == ZERO:
            return None
        # A reason that names its own account (STK-7) takes the other side;
        # otherwise the purpose's mapped account does.
        accounts = self._require_mapping(
            firm_id,
            (
                (ControlAccountPurpose.INVENTORY,)
                if expense_account_id is not None
                else (ControlAccountPurpose.INVENTORY, expense_purpose)
            ),
        )
        if expense_account_id is not None:
            accounts[expense_purpose] = expense_account_id
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
                ledger_account_id=accounts[expense_purpose],
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

    def post_supplier_gift(
        self,
        *,
        firm_id: UUID,
        gift_id: UUID,
        reference_number: str,
        gift_date: date,
        value: Decimal,
        debit_account_id: UUID | None,
        actor_id: UUID,
        narration: str,
    ) -> JournalEntry:
        """Post a supplier's gift (BUY-2): Dr asset, expense or drawings.

        ``debit_account_id`` is the asset or expense account named; None means
        the owner kept it, and *Drawings* takes the debit. The credit is always
        *Supplier Incentives Received*. No input tax: a gift is not bought.

        Raises:
            ValidationError: If an account mapping or an open period is missing.

        """
        purposes = (ControlAccountPurpose.SUPPLIER_INCENTIVE_INCOME,) + (
            () if debit_account_id is not None else (ControlAccountPurpose.DRAWINGS,)
        )
        accounts = self._require_mapping(firm_id, purposes)
        debit = (
            debit_account_id
            if debit_account_id is not None
            else accounts[ControlAccountPurpose.DRAWINGS]
        )
        amount = quantize_ledger(quantize_money(value))
        context = self.context_for(firm_id, gift_date)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=gift_date,
            reference_number=reference_number,
            description=f"Supplier gift {reference_number}",
            lines=[
                JournalLineData(
                    ledger_account_id=debit,
                    debit_amount=amount,
                    credit_amount=ZERO,
                    description=narration,
                ),
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.SUPPLIER_INCENTIVE_INCOME
                    ],
                    debit_amount=ZERO,
                    credit_amount=amount,
                    description=narration,
                ),
            ],
            source_module="supplier_gifts",
            source_id=gift_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def reverse_supplier_gift(
        self,
        *,
        firm_id: UUID,
        journal_entry_id: UUID,
        reference_number: str,
        actor_id: UUID,
    ) -> JournalEntry:
        """Reverse a gift's journal line for line (BUY-2)."""
        return self._journals.reverse_entry(
            journal_entry_id,
            firm_id=firm_id,
            reference_number=reference_number,
            actor_id=actor_id,
        )

    def post_physical_count(
        self,
        *,
        firm_id: UUID,
        count_id: UUID,
        count_number: str,
        count_date: date,
        differences: list[tuple[str, Decimal]],
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Post one journal for a whole stock count.

        Each difference used to post its own journal under the count's number,
        and a journal reference is unique per firm -- so a count with two or
        more differences could never be posted (D-STK-11). The owner chose one
        journal per count (2026-09-19): one voucher per stock-take, with a pair
        of lines per difference, so each one still reads on its own -- a
        shortage credits inventory and debits the adjustment account, a surplus
        the reverse, as `post_stock_adjustment` does for one.

        Args:
            firm_id: The owning firm.
            count_id: The count sheet this posts.
            count_number: The sheet's number, used as the journal reference.
            count_date: The date the stock was counted.
            differences: One (description, value change) per adjusted line,
                positive when stock rose.
            actor_id: The user posting the sheet.

        Returns:
            The posted journal, or None when no difference moved any value.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        valued = [
            (description, quantize_ledger(quantize_money(value)))
            for description, value in differences
        ]
        valued = [(description, value) for description, value in valued if value]
        if not valued:
            return None
        accounts = self._require_mapping(firm_id, STOCK_ADJUSTMENT_PURPOSES)
        context = self.context_for(firm_id, count_date)
        lines: list[JournalLineData] = []
        for description, value in valued:
            rising = value > ZERO
            amount = value if rising else -value
            lines.extend(
                [
                    JournalLineData(
                        ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                        debit_amount=amount if rising else ZERO,
                        credit_amount=ZERO if rising else amount,
                        description=description,
                    ),
                    JournalLineData(
                        ledger_account_id=accounts[
                            ControlAccountPurpose.INVENTORY_ADJUSTMENT
                        ],
                        debit_amount=ZERO if rising else amount,
                        credit_amount=amount if rising else ZERO,
                        description=description,
                    ),
                ]
            )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=count_date,
            reference_number=count_number,
            description=f"Physical count {count_number}",
            lines=lines,
            source_module="physical_count",
            source_id=count_id,
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

    def post_vendor_opening_bill(
        self,
        *,
        firm_id: UUID,
        opening_bill_id: UUID,
        bill_number: str,
        posting_date: date,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post one bill a supplier was owed on the day the firm started here.

        The payable twin of `post_opening_balance`: the debt arrived from books
        this ledger never saw, so its counterpart is opening balance equity --
        Dr equity, Cr accounts payable. No goods and no tax: those belong to
        the period in which the bill was raised, in the other books.

        Raises:
            ValidationError: If the amount is nil, or accounts or an open
                period are missing on the posting date.

        """
        total = quantize_ledger(quantize_money(amount))
        if total <= ZERO:
            raise ValidationError("An opening bill must be for more than nothing.")
        accounts = self._require_mapping(firm_id, VENDOR_OPENING_BILL_PURPOSES)
        context = self.context_for(firm_id, posting_date)
        description = f"Opening bill {bill_number}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=posting_date,
            reference_number=bill_number,
            description=description,
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.OPENING_BALANCE_EQUITY
                    ],
                    debit_amount=total,
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                    credit_amount=total,
                    description=description,
                ),
            ],
            source_module="vendor_opening_bills",
            source_id=opening_bill_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_customer_opening_bill(
        self,
        *,
        firm_id: UUID,
        opening_bill_id: UUID,
        bill_number: str,
        posting_date: date,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post one bill a customer owed on the day the firm started here.

        The receivable twin of `post_vendor_opening_bill`, and the bill-wise
        form of `post_opening_balance`: the debt arrived from books this ledger
        never saw, so its counterpart is opening balance equity -- Dr accounts
        receivable, Cr equity. No revenue and no tax: those belong to the
        period the bill was raised in, in the other books. The customer is the
        receivable's party through the `OPENING_BILL` receivable transaction
        the caller writes beside it, which is what the statement reads.

        Raises:
            ValidationError: If the amount is nil, or accounts or an open
                period are missing on the posting date.

        """
        total = quantize_ledger(quantize_money(amount))
        if total <= ZERO:
            raise ValidationError("An opening bill must be for more than nothing.")
        accounts = self._require_mapping(firm_id, OPENING_BALANCE_PURPOSES)
        context = self.context_for(firm_id, posting_date)
        description = f"Opening bill {bill_number}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=posting_date,
            reference_number=bill_number,
            description=description,
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.ACCOUNTS_RECEIVABLE
                    ],
                    debit_amount=total,
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.OPENING_BALANCE_EQUITY
                    ],
                    credit_amount=total,
                    description=description,
                ),
            ],
            source_module="customer_opening_bills",
            source_id=opening_bill_id,
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

    def post_supplier_refund(
        self,
        *,
        firm_id: UUID,
        refund_id: UUID,
        reference_number: str,
        refunded_on: date,
        amount: Decimal,
        money_account_id: UUID,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post money a supplier paid back against a return's credit (69.7).

        The purchase return debited payables when it completed, leaving the
        supplier owing the firm. Their money arriving clears that:
        ``Dr cash or bank / Cr accounts payable``. The mirror of a payment, and
        kept apart from one because a payment settles what the firm owes and
        this collects what it is owed.

        Args:
            firm_id: The owning firm.
            refund_id: The supplier refund row this posts for.
            reference_number: The journal reference, unique per entry.
            refunded_on: The date the money arrived.
            amount: How much the supplier paid back.
            money_account_id: The cash or bank account it landed in.
            actor_id: The user recording it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, PAYMENT_PURPOSES)
        context = self.context_for(firm_id, refunded_on)
        total = quantize_ledger(quantize_money(amount))
        lines = [
            JournalLineData(
                ledger_account_id=money_account_id,
                debit_amount=total,
                description=f"Supplier refund {reference_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                credit_amount=total,
                description=f"Supplier refund {reference_number}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=refunded_on,
            reference_number=reference_number,
            description=f"Supplier refund {reference_number}",
            lines=lines,
            source_module="supplier_credit_refund",
            source_id=refund_id,
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
        tds_amount: Decimal = ZERO,
        deductions: dict[ControlAccountPurpose, Decimal] | None = None,
        exchange_difference: Decimal = ZERO,
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
            amount: How much settles the party, tax deducted included.
            is_receipt: True for money in, False for money out.
            money_account_id: The cash or bank account it moved through.
            actor_id: The user recording it.
            tds_amount: Tax deducted at source out of ``amount`` (53.1). The
                money leg is the rest; the deduction posts to TDS Receivable
                on a receipt and TDS Payable on a payment, so the party leg
                still clears the whole ``amount``.
            deductions: The rest of ``amount`` that settled the bill without
                moving as money (backlog 74 row 2) -- rounding, bank charges,
                discount -- by the purpose each posts to. A receipt debits
                each (a cost the firm accepted); a payment credits each (what
                the supplier let go). The money leg shrinks by their total and
                the party leg still clears the whole ``amount``.
            exchange_difference: On a payment to bills in another currency
                (PG-12), the rupees paid less the bills' rupee value at their
                own rate. The payable is debited only with that value, so it
                clears exactly what the bills credited; a loss (above zero)
                is debited to `EXCHANGE_GAIN_LOSS`, a gain credited to it.
                The money leg is still the whole ``amount``.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        purposes: tuple[ControlAccountPurpose, ...] = (
            RECEIPT_PURPOSES if is_receipt else PAYMENT_PURPOSES
        )
        fx = quantize_ledger(quantize_money(exchange_difference))
        if fx != ZERO:
            purposes = (*purposes, ControlAccountPurpose.EXCHANGE_GAIN_LOSS)
        tds_purpose = (
            ControlAccountPurpose.TDS_RECEIVABLE
            if is_receipt
            else ControlAccountPurpose.TDS_PAYABLE
        )
        deducted = quantize_ledger(quantize_money(tds_amount))
        if deducted > ZERO:
            purposes = (*purposes, tds_purpose)
        # Each deduction rounded to the ledger on its own, then summed: the
        # money leg is what is left of the rounded parts, so the entry
        # balances to the paisa however the parts were typed.
        settled_otherwise = {
            purpose: quantize_ledger(quantize_money(value))
            for purpose, value in (deductions or {}).items()
            if quantize_ledger(quantize_money(value)) > ZERO
        }
        purposes = (*purposes, *settled_otherwise)
        accounts = self._require_mapping(firm_id, purposes)
        context = self.context_for(firm_id, settlement_date)
        total = quantize_ledger(quantize_money(amount))
        moved = total - deducted - sum(settled_otherwise.values(), ZERO)
        if moved <= ZERO:
            raise ValidationError(
                "Deductions and TDS take up the whole amount, so no money "
                "moved. A balance cleared without money is a party adjustment."
            )
        party_purpose = (
            ControlAccountPurpose.ACCOUNTS_RECEIVABLE
            if is_receipt
            else ControlAccountPurpose.ACCOUNTS_PAYABLE
        )
        kind = "Receipt" if is_receipt else "Payment"
        money_leg = JournalLineData(
            ledger_account_id=money_account_id,
            debit_amount=moved if is_receipt else ZERO,
            credit_amount=ZERO if is_receipt else moved,
            description=f"{kind} {settlement_number}",
        )
        tds_legs = (
            [
                JournalLineData(
                    ledger_account_id=accounts[tds_purpose],
                    debit_amount=deducted if is_receipt else ZERO,
                    credit_amount=ZERO if is_receipt else deducted,
                    description=f"TDS on {kind.lower()} {settlement_number}",
                )
            ]
            if deducted > ZERO
            else []
        )
        deduction_legs = [
            JournalLineData(
                ledger_account_id=accounts[purpose],
                debit_amount=value if is_receipt else ZERO,
                credit_amount=ZERO if is_receipt else value,
                description=(
                    f"{PURPOSE_LABELS[purpose]} on {kind.lower()} {settlement_number}"
                ),
            )
            for purpose, value in settled_otherwise.items()
        ]
        tds_legs = [*tds_legs, *deduction_legs]
        party_leg = JournalLineData(
            ledger_account_id=accounts[party_purpose],
            debit_amount=ZERO if is_receipt else total - fx,
            credit_amount=total if is_receipt else ZERO,
            description=f"{kind} {settlement_number}",
        )
        if fx != ZERO:
            # Paid abroad (PG-12): the payable clears at the bills' rupee
            # value, and the rupee's movement since is a loss or a gain.
            tds_legs.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.EXCHANGE_GAIN_LOSS
                    ],
                    debit_amount=fx if fx > ZERO else ZERO,
                    credit_amount=-fx if fx < ZERO else ZERO,
                    description=(
                        f"Exchange {'loss' if fx > ZERO else 'gain'} on "
                        f"{kind.lower()} {settlement_number}"
                    ),
                )
            )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=settlement_date,
            reference_number=settlement_number,
            description=f"{kind} {settlement_number}",
            lines=[money_leg, *tds_legs, party_leg],
            source_module="settlements",
            source_id=settlement_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_fx_revaluation(
        self,
        *,
        firm_id: UUID,
        revaluation_id: UUID,
        reference: str,
        as_of: date,
        difference: Decimal,
        actor_id: UUID,
    ) -> tuple[JournalEntry, JournalEntry]:
        """Post an unrealised exchange difference and its reversal (PG-12).

        Open payables in another currency are restated at the period end's
        rate: a payable worth more in rupees is a loss -- Dr exchange
        gain/loss, Cr payables -- and one worth less a gain. Unrealised, so
        it is reversed the next day, as Tally and ERPNext do: the payment
        still settles against the bill's own rate and realises the whole
        difference then. Both entries are posted here, so a period end
        either has both or neither.

        Args:
            firm_id: The owning firm.
            revaluation_id: The source id both journals carry.
            reference: The journal reference; the reversal adds ``-REV``.
            as_of: The period end the entry is dated; the reversal is dated
                the day after.
            difference: Revalued rupees less carried rupees: a loss above
                zero, a gain below.
            actor_id: The user revaluing.

        Returns:
            The posted entry and its reversal.

        Raises:
            ValidationError: If accounts are missing, or no open period
                covers the period end or the day after it.

        """
        amount = quantize_ledger(quantize_money(abs(difference)))
        if amount == ZERO:
            raise ValidationError("There is no exchange difference to post.")
        accounts = self._require_mapping(
            firm_id,
            (
                ControlAccountPurpose.ACCOUNTS_PAYABLE,
                ControlAccountPurpose.EXCHANGE_GAIN_LOSS,
            ),
        )
        context = self.context_for(firm_id, as_of)
        next_day = as_of + timedelta(days=1)
        # Checked first, so a reversal with nowhere to go refuses the whole
        # revaluation rather than leaving an unrealised entry standing.
        self.context_for(firm_id, next_day)
        loss = difference > ZERO
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.EXCHANGE_GAIN_LOSS],
                debit_amount=amount if loss else ZERO,
                credit_amount=ZERO if loss else amount,
                description=(
                    f"Unrealised exchange {'loss' if loss else 'gain'} {reference}"
                ),
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                debit_amount=ZERO if loss else amount,
                credit_amount=amount if loss else ZERO,
                description=f"Foreign-currency payables restated {reference}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=as_of,
            reference_number=reference,
            description=f"Exchange revaluation {reference}",
            lines=lines,
            source_module="fx_revaluation",
            source_id=revaluation_id,
            actor_id=actor_id,
        )
        posted = self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
        reversal = self._journals.reverse_entry(
            posted.id,
            firm_id=firm_id,
            reference_number=f"{reference}-REV",
            journal_date=next_day,
            actor_id=actor_id,
        )
        return posted, reversal

    def post_party_adjustment(
        self,
        *,
        firm_id: UUID,
        adjustment_id: UUID,
        adjustment_number: str,
        adjustment_date: date,
        kind: str,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post a party balance moved without money and without tax (74 row 2).

        Two legs, by kind:

        * ``CUSTOMER_WRITE_OFF`` -- Dr bad debts, Cr receivable: the debt is
          given up and becomes a cost.
        * ``SUPPLIER_WRITE_BACK`` -- Dr payable, Cr balances written back: what
          the firm will not pay becomes other income.
        * ``SET_OFF`` -- Dr payable, Cr receivable: what the business owes the
          firm as a customer is settled by what the firm owes it as a supplier.
        * ``SUPPLIER_REBATE`` -- Dr payable, Cr supplier rebates receivable:
          the supplier's credit for an accrued volume rebate (BUY-13) set
          against what the firm owes it.
        * ``PRINCIPAL_CLAIM`` -- Dr payable, Cr claims receivable: a
          principal's credit note settling a claim (SEL-11).
        * ``CUSTOMER_REBATE`` -- Dr customer rebate payable, Cr receivable:
          an accrued turnover rebate (SG-9) set against what the customer
          owes.

        No tax leg, ever. Reducing the value of a supply is a credit or debit
        note, which reverses tax; this only says the balance will not be paid.

        Args:
            firm_id: The owning firm.
            adjustment_id: The source document.
            adjustment_number: Its number, used as the journal reference.
            adjustment_date: The day the balance moved.
            kind: One of the three kinds above.
            amount: How much moves.
            actor_id: The user approving it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If the kind is unknown, or accounts or an open
                period are missing.

        """
        legs: dict[str, tuple[ControlAccountPurpose, ControlAccountPurpose]] = {
            "CUSTOMER_WRITE_OFF": (
                ControlAccountPurpose.BAD_DEBTS,
                ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
            ),
            "SUPPLIER_WRITE_BACK": (
                ControlAccountPurpose.ACCOUNTS_PAYABLE,
                ControlAccountPurpose.BALANCES_WRITTEN_BACK,
            ),
            "SET_OFF": (
                ControlAccountPurpose.ACCOUNTS_PAYABLE,
                ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
            ),
            "SUPPLIER_REBATE": (
                ControlAccountPurpose.ACCOUNTS_PAYABLE,
                ControlAccountPurpose.SUPPLIER_REBATE_RECEIVABLE,
            ),
            "PRINCIPAL_CLAIM": (
                ControlAccountPurpose.ACCOUNTS_PAYABLE,
                ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE,
            ),
            "CUSTOMER_REBATE": (
                ControlAccountPurpose.CUSTOMER_REBATE_PAYABLE,
                ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
            ),
        }
        if kind not in legs:
            raise ValidationError(f"{kind} is not a kind of party adjustment.")
        debit_purpose, credit_purpose = legs[kind]
        accounts = self._require_mapping(firm_id, (debit_purpose, credit_purpose))
        context = self.context_for(firm_id, adjustment_date)
        value = quantize_ledger(quantize_money(amount))
        describe = f"Party adjustment {adjustment_number}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=adjustment_date,
            reference_number=adjustment_number,
            description=describe,
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[debit_purpose],
                    debit_amount=value,
                    credit_amount=ZERO,
                    description=describe,
                ),
                JournalLineData(
                    ledger_account_id=accounts[credit_purpose],
                    debit_amount=ZERO,
                    credit_amount=value,
                    description=describe,
                ),
            ],
            source_module="party_adjustments",
            source_id=adjustment_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_supplier_rebate_accrual(
        self,
        *,
        firm_id: UUID,
        agreement_id: UUID,
        agreement_code: str,
        accrual_date: date,
        amount: Decimal,
        actor_id: UUID,
        reference_number: str | None = None,
    ) -> JournalEntry:
        """Book a supplier's volume rebate earned over a period (BUY-13).

        ``reference_number`` is the caller's when this is not the agreement's
        first accrual: a reference is unique in a firm, and a reversed accrual
        keeps the one it posted under (D-BUY-34).

        Dr supplier rebates receivable, Cr supplier incentives received: the
        supplier owes the firm the rebate from the day the period closes,
        whether its credit note comes that week or that quarter.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        receivable = ControlAccountPurpose.SUPPLIER_REBATE_RECEIVABLE
        income = ControlAccountPurpose.SUPPLIER_INCENTIVE_INCOME
        accounts = self._require_mapping(firm_id, (receivable, income))
        context = self.context_for(firm_id, accrual_date)
        value = quantize_ledger(quantize_money(amount))
        describe = f"Volume rebate {agreement_code}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=accrual_date,
            reference_number=reference_number or f"REBATE-{agreement_code}",
            description=describe,
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[receivable],
                    debit_amount=value,
                    credit_amount=ZERO,
                    description=describe,
                ),
                JournalLineData(
                    ledger_account_id=accounts[income],
                    debit_amount=ZERO,
                    credit_amount=value,
                    description=describe,
                ),
            ],
            source_module="supplier_rebates",
            source_id=agreement_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_customer_rebate_accrual(
        self,
        *,
        firm_id: UUID,
        agreement_id: UUID,
        reference_number: str,
        agreement_code: str,
        accrual_date: date,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Book a customer's turnover rebate earned over a period (SG-9).

        Dr rebates allowed, Cr customer rebate payable: the firm owes the
        customer the rebate from the day the period closes, whether it is set
        against their account that week or that quarter. No tax leg: a rebate
        does not move a bill's taxable value (CGST Act s.15(3)).

        ``reference_number`` is the caller's, because an agreement accrued,
        reversed and accrued again needs a reference per accrual.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        expense = ControlAccountPurpose.REBATES_ALLOWED
        payable = ControlAccountPurpose.CUSTOMER_REBATE_PAYABLE
        accounts = self._require_mapping(firm_id, (expense, payable))
        context = self.context_for(firm_id, accrual_date)
        value = quantize_ledger(quantize_money(amount))
        describe = f"Turnover rebate {agreement_code}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=accrual_date,
            reference_number=reference_number,
            description=describe,
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[expense],
                    debit_amount=value,
                    credit_amount=ZERO,
                    description=describe,
                ),
                JournalLineData(
                    ledger_account_id=accounts[payable],
                    debit_amount=ZERO,
                    credit_amount=value,
                    description=describe,
                ),
            ],
            source_module="customer_rebates",
            source_id=agreement_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_principal_claim(
        self,
        *,
        firm_id: UUID,
        claim_id: UUID,
        claim_number: str,
        claim_date: date,
        scheme_amount: Decimal,
        stock_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Book what a principal owes on a claim (SEL-11).

        Dr claims receivable for the whole claim. The other side gives back
        the cost where the firm carried it: a scheme's share to promotional
        expense, expired and broken stock to the inventory adjustment account
        their write-off and return were charged to.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        receivable = ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE
        promotion = ControlAccountPurpose.PROMOTIONAL_EXPENSE
        stock = ControlAccountPurpose.INVENTORY_ADJUSTMENT
        scheme = quantize_ledger(quantize_money(scheme_amount))
        loss = quantize_ledger(quantize_money(stock_amount))
        wanted = [receivable]
        if scheme > ZERO:
            wanted.append(promotion)
        if loss > ZERO:
            wanted.append(stock)
        accounts = self._require_mapping(firm_id, tuple(wanted))
        context = self.context_for(firm_id, claim_date)
        describe = f"Claim {claim_number} on the principal"
        lines = [
            JournalLineData(
                ledger_account_id=accounts[receivable],
                debit_amount=scheme + loss,
                credit_amount=ZERO,
                description=describe,
            )
        ]
        for purpose, value in ((promotion, scheme), (stock, loss)):
            if value > ZERO:
                lines.append(
                    JournalLineData(
                        ledger_account_id=accounts[purpose],
                        debit_amount=ZERO,
                        credit_amount=value,
                        description=describe,
                    )
                )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=claim_date,
            reference_number=f"CLAIM-{claim_number}",
            description=describe,
            lines=lines,
            source_module="principal_claims",
            source_id=claim_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_landed_cost(
        self,
        *,
        firm_id: UUID,
        voucher_id: UUID,
        reference_number: str,
        voucher_date: date,
        inventory_amount: Decimal,
        cogs_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Move a freight or clearing charge into the cost of goods (BUY-16).

        Dr inventory for the share still on hand, Dr cost of goods sold for
        the share already sold, Cr expenses included in valuation -- where
        the charge's own bill was booked -- for the whole.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        clearing = ControlAccountPurpose.LANDED_COST_CLEARING
        stock = ControlAccountPurpose.INVENTORY
        sold = ControlAccountPurpose.COST_OF_GOODS_SOLD
        held = quantize_ledger(quantize_money(inventory_amount))
        gone = quantize_ledger(quantize_money(cogs_amount))
        wanted = [clearing]
        if held > ZERO:
            wanted.append(stock)
        if gone > ZERO:
            wanted.append(sold)
        accounts = self._require_mapping(firm_id, tuple(wanted))
        context = self.context_for(firm_id, voucher_date)
        describe = f"Landed cost {reference_number}"
        lines = [
            JournalLineData(
                ledger_account_id=accounts[purpose],
                debit_amount=value,
                credit_amount=ZERO,
                description=describe,
            )
            for purpose, value in ((stock, held), (sold, gone))
            if value > ZERO
        ]
        lines.append(
            JournalLineData(
                ledger_account_id=accounts[clearing],
                debit_amount=ZERO,
                credit_amount=held + gone,
                description=describe,
            )
        )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=voucher_date,
            reference_number=prefixed_reference("LCV", reference_number),
            description=describe,
            lines=lines,
            source_module="landed_costs",
            source_id=voucher_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_bill_of_entry(
        self,
        *,
        firm_id: UUID,
        bill_of_entry_id: UUID,
        reference_number: str,
        boe_date: date,
        inventory_amount: Decimal,
        cogs_amount: Decimal,
        expense_amount: Decimal,
        igst_amount: Decimal,
        cess_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Book the duty a Bill of Entry assessed (PG-12 part B).

        Basic customs duty and surcharge are a cost of the goods with no
        credit: Dr inventory for the share on stock still held, Dr cost of
        goods sold for the share already sold, Dr *Customs Duty* for a line no
        linked receipt carries. The IGST on import is input tax, Dr the IGST
        input account the purchase side claims through; cess Dr input tax.
        Cr *Customs Duty Payable* for the whole, which an ordinary payment or
        journal clears. Each leg is rounded on its own and the credit is
        their sum, so the entry balances.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        legs = (
            (ControlAccountPurpose.INVENTORY, inventory_amount),
            (ControlAccountPurpose.COST_OF_GOODS_SOLD, cogs_amount),
            (ControlAccountPurpose.CUSTOMS_DUTY, expense_amount),
            (input_tax_purpose("IGST"), igst_amount),
            (input_tax_purpose("CESS"), cess_amount),
        )
        debits = [
            (purpose, quantize_ledger(quantize_money(value))) for purpose, value in legs
        ]
        debits = [(purpose, value) for purpose, value in debits if value > ZERO]
        payable = ControlAccountPurpose.CUSTOMS_PAYABLE
        accounts = self._require_mapping(
            firm_id, (payable, *dict.fromkeys(purpose for purpose, _ in debits))
        )
        context = self.context_for(firm_id, boe_date)
        describe = f"Bill of Entry {reference_number}"
        lines = [
            JournalLineData(
                ledger_account_id=accounts[purpose],
                debit_amount=value,
                credit_amount=ZERO,
                description=describe,
            )
            for purpose, value in debits
        ]
        lines.append(
            JournalLineData(
                ledger_account_id=accounts[payable],
                debit_amount=ZERO,
                credit_amount=sum((value for _, value in debits), ZERO),
                description=describe,
            )
        )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=boe_date,
            reference_number=prefixed_reference("BOE", reference_number),
            description=describe,
            lines=lines,
            source_module="bill_of_entry",
            source_id=bill_of_entry_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_depreciation(
        self,
        *,
        firm_id: UUID,
        run_id: UUID,
        reference_number: str,
        on: date,
        legs: list[tuple[UUID, UUID, Decimal]],
        actor_id: UUID,
    ) -> JournalEntry:
        """Book a depreciation run (PG-13): Dr expense, Cr accumulated.

        ``legs`` is one (expense account, accumulated depreciation account,
        amount) per pair of accounts the run's asset classes post to, each
        amount already the sum of per-asset charges rounded to the paisa. The
        accounts are the class's own or the firm's ``DEPRECIATION_EXPENSE``
        and ``ACCUMULATED_DEPRECIATION`` control accounts, resolved by the
        caller.

        Raises:
            ValidationError: If no open period covers ``on``.

        """
        context = self.context_for(firm_id, on)
        describe = f"Depreciation {reference_number}"
        lines: list[JournalLineData] = []
        for expense_account, accumulated_account, amount in legs:
            value = quantize_ledger(amount)
            if value <= ZERO:
                continue
            lines.append(
                JournalLineData(
                    ledger_account_id=expense_account,
                    debit_amount=value,
                    credit_amount=ZERO,
                    description=describe,
                )
            )
            lines.append(
                JournalLineData(
                    ledger_account_id=accumulated_account,
                    debit_amount=ZERO,
                    credit_amount=value,
                    description=describe,
                )
            )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=on,
            reference_number=reference_number,
            description=describe,
            lines=lines,
            source_module="depreciation_run",
            source_id=run_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_asset_disposal(
        self,
        *,
        firm_id: UUID,
        asset_id: UUID,
        reference_number: str,
        on: date,
        asset_account_id: UUID,
        accumulated_account_id: UUID,
        money_account_id: UUID,
        cost: Decimal,
        accumulated: Decimal,
        sale_amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Take a sold or scrapped asset off the books (PG-13).

        Dr accumulated depreciation for all that was charged, Dr the cash or
        bank account for the sale money, Cr the asset account for its cost;
        the difference -- sale money less book value -- is a gain (Cr) or a
        loss (Dr) on ``ASSET_DISPOSAL_GAIN_LOSS``. Each leg is rounded on its
        own and the gain is what balances them.

        Raises:
            ValidationError: If the gain/loss account or an open period is
                missing.

        """
        gain_purpose = ControlAccountPurpose.ASSET_DISPOSAL_GAIN_LOSS
        accounts = self._require_mapping(firm_id, (gain_purpose,))
        context = self.context_for(firm_id, on)
        describe = f"Disposal of {reference_number}"
        ledger_cost = quantize_ledger(cost)
        ledger_accumulated = quantize_ledger(accumulated)
        ledger_sale = quantize_ledger(sale_amount)
        gain = ledger_sale - (ledger_cost - ledger_accumulated)
        lines: list[JournalLineData] = []
        if ledger_accumulated > ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accumulated_account_id,
                    debit_amount=ledger_accumulated,
                    credit_amount=ZERO,
                    description=describe,
                )
            )
        if ledger_sale > ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=money_account_id,
                    debit_amount=ledger_sale,
                    credit_amount=ZERO,
                    description=describe,
                )
            )
        lines.append(
            JournalLineData(
                ledger_account_id=asset_account_id,
                debit_amount=ZERO,
                credit_amount=ledger_cost,
                description=describe,
            )
        )
        if gain != ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[gain_purpose],
                    debit_amount=-gain if gain < ZERO else ZERO,
                    credit_amount=gain if gain > ZERO else ZERO,
                    description=(
                        f"Gain on {describe.lower()}"
                        if gain > ZERO
                        else f"Loss on {describe.lower()}"
                    ),
                )
            )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=on,
            reference_number=f"{reference_number}-DISPOSAL",
            description=describe,
            lines=lines,
            source_module="fixed_asset",
            source_id=asset_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_principal_claim_receipt(
        self,
        *,
        firm_id: UUID,
        settlement_id: UUID,
        reference_number: str,
        received_on: date,
        amount: Decimal,
        money_account_id: UUID,
        actor_id: UUID,
    ) -> JournalEntry:
        """Book money a principal paid against a claim (SEL-11).

        Dr the cash or bank account it arrived in, Cr claims receivable. No
        party ledger moves: the claim was never on the principal's account.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        receivable = ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE
        accounts = self._require_mapping(firm_id, (receivable,))
        context = self.context_for(firm_id, received_on)
        value = quantize_ledger(quantize_money(amount))
        describe = f"Claim payment {reference_number}"
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=received_on,
            reference_number=reference_number,
            description=describe,
            lines=[
                JournalLineData(
                    ledger_account_id=money_account_id,
                    debit_amount=value,
                    credit_amount=ZERO,
                    description=describe,
                ),
                JournalLineData(
                    ledger_account_id=accounts[receivable],
                    debit_amount=ZERO,
                    credit_amount=value,
                    description=describe,
                ),
            ],
            source_module="principal_claims",
            source_id=settlement_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_contra_voucher(
        self,
        *,
        firm_id: UUID,
        voucher_id: UUID,
        voucher_number: str,
        voucher_date: date,
        from_account_id: UUID,
        to_account_id: UUID,
        amount: Decimal,
        description: str,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post money moved between two of the firm's own accounts (74 row 3).

        Dr the account the money arrived in, Cr the one it left. Two legs,
        both cash or bank, so no party and no tax: the firm is no richer or
        poorer, only its money is somewhere else. The caller has already
        checked both are money accounts.

        Args:
            firm_id: The owning firm.
            voucher_id: The source document.
            voucher_number: Its number, used as the journal reference.
            voucher_date: The day the money moved.
            from_account_id: The cash or bank account credited.
            to_account_id: The cash or bank account debited.
            amount: How much moved.
            description: The narration both legs carry.
            actor_id: The user recording it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If no open period covers the date.

        """
        context = self.context_for(firm_id, voucher_date)
        value = quantize_ledger(quantize_money(amount))
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=voucher_date,
            reference_number=voucher_number,
            description=description,
            lines=[
                JournalLineData(
                    ledger_account_id=to_account_id,
                    debit_amount=value,
                    credit_amount=ZERO,
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=from_account_id,
                    debit_amount=ZERO,
                    credit_amount=value,
                    description=description,
                ),
            ],
            source_module="contra",
            source_id=voucher_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_cash_short_and_over(
        self,
        *,
        firm_id: UUID,
        shift_id: UUID,
        shift_number: str,
        closed_on: date,
        cash_account_id: UUID,
        difference: Decimal,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Post what a till was short or over by when it was counted (SG-7).

        Short, the drawer holds less than the books say: Dr *Cash short and
        over* / Cr the shift's cash account, so cash reads what was counted.
        Over is the mirror: Dr cash / Cr *Cash short and over*. One account
        for both, as Tally keeps it -- a credit balance on it is a gain.

        Args:
            firm_id: The owning firm.
            shift_id: The shift, as the journal's source.
            shift_number: Its number, which is the journal reference: a shift
                closes once, so the reference is its own.
            closed_on: The day the drawer was counted.
            cash_account_id: The cash account the shift's money is booked to.
            difference: Counted less expected: negative short, positive over.
            actor_id: Who closed the shift.

        Returns:
            The posted entry, or None when the drawer was exact.

        Raises:
            ValidationError: If the firm has mapped no *Cash short and over*
                account, or no open period covers the day.

        """
        amount = quantize_ledger(abs(quantize_money(difference)))
        if amount == ZERO:
            return None
        accounts = self._require_mapping(
            firm_id, (ControlAccountPurpose.CASH_SHORT_AND_OVER,)
        )
        variance = accounts[ControlAccountPurpose.CASH_SHORT_AND_OVER]
        short = difference < ZERO
        debit, credit = (
            (variance, cash_account_id) if short else (cash_account_id, variance)
        )
        description = (
            f"Cash {'short' if short else 'over'} at the close of {shift_number}"
        )
        context = self.context_for(firm_id, closed_on)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=closed_on,
            reference_number=shift_number,
            description=description,
            lines=[
                JournalLineData(
                    ledger_account_id=debit,
                    debit_amount=amount,
                    credit_amount=ZERO,
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=credit,
                    debit_amount=ZERO,
                    credit_amount=amount,
                    description=description,
                ),
            ],
            source_module="counter_shift",
            source_id=shift_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_tds_challan(
        self,
        *,
        firm_id: UUID,
        challan_id: UUID,
        challan_number: str,
        deposited_on: date,
        bank_account_id: UUID,
        tax_amount: Decimal,
        charges_amount: Decimal,
        description: str,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post a TDS deposit (ACC-7): Dr TDS payable, Cr the bank.

        Interest and the late fee paid on the same challan are a cost of
        their own, debited to ``TDS_INTEREST_AND_FEES`` -- never to TDS
        payable, which holds only what was deducted from somebody.

        Args:
            firm_id: The owning firm.
            challan_id: The source challan.
            challan_number: Its number, used as the journal reference.
            deposited_on: The day the bank received it.
            bank_account_id: The money account credited.
            tax_amount: The tax deposited.
            charges_amount: Interest and late fee together; may be zero.
            description: The narration every leg carries.
            actor_id: The user recording it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If an account is unmapped or no period is open.

        """
        purposes: tuple[ControlAccountPurpose, ...] = (
            ControlAccountPurpose.TDS_PAYABLE,
        )
        if charges_amount > ZERO:
            purposes = (*purposes, ControlAccountPurpose.TDS_INTEREST_AND_FEES)
        accounts = self._require_mapping(firm_id, purposes)
        context = self.context_for(firm_id, deposited_on)
        tax = quantize_ledger(quantize_money(tax_amount))
        charges = quantize_ledger(quantize_money(charges_amount))
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.TDS_PAYABLE],
                debit_amount=tax,
                credit_amount=ZERO,
                description=description,
            )
        ]
        if charges > ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.TDS_INTEREST_AND_FEES
                    ],
                    debit_amount=charges,
                    credit_amount=ZERO,
                    description=description,
                )
            )
        lines.append(
            JournalLineData(
                ledger_account_id=bank_account_id,
                debit_amount=ZERO,
                credit_amount=tax + charges,
                description=description,
            )
        )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=deposited_on,
            reference_number=challan_number,
            description=description,
            lines=lines,
            source_module="tds_challan",
            source_id=challan_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_cheque_return_charges(
        self,
        *,
        firm_id: UUID,
        cheque_id: UUID,
        reference: str,
        bounced_on: date,
        bank_account_id: UUID,
        bank_charges_amount: Decimal,
        customer_charge_amount: Decimal,
        description: str,
        actor_id: UUID,
    ) -> JournalEntry:
        """Post what a bounced cheque cost (ACC-2), in one entry.

        Two independent pairs, either of which may be absent:

        * what the firm's bank took for the return -- Dr bank charges, Cr
          the bank the cheque was paid into;
        * what the firm charges the customer for it -- Dr receivable, Cr
          cheque return charges, other income outside GST: a penalty for
          dishonour is not consideration for a supply.

        The reversal of the receipt itself is the settlement's own, posted
        separately, so this entry never touches the money the cheque was for.

        Args:
            firm_id: The owning firm.
            cheque_id: The source post-dated cheque.
            reference: The journal reference.
            bounced_on: The day the bank returned it.
            bank_account_id: The bank the cheque was deposited into.
            bank_charges_amount: The firm's bank's fee; may be zero.
            customer_charge_amount: The charge to the customer; may be zero.
            description: The narration every leg carries.
            actor_id: The user recording it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If an account is unmapped or no period is open.

        """
        bank_charges = quantize_ledger(quantize_money(bank_charges_amount))
        customer_charge = quantize_ledger(quantize_money(customer_charge_amount))
        purposes: tuple[ControlAccountPurpose, ...] = ()
        if bank_charges > ZERO:
            purposes = (*purposes, ControlAccountPurpose.BANK_CHARGES)
        if customer_charge > ZERO:
            purposes = (
                *purposes,
                ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
                ControlAccountPurpose.CHEQUE_RETURN_CHARGES,
            )
        accounts = self._require_mapping(firm_id, purposes)
        context = self.context_for(firm_id, bounced_on)
        lines: list[JournalLineData] = []
        if bank_charges > ZERO:
            lines += [
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.BANK_CHARGES],
                    debit_amount=bank_charges,
                    credit_amount=ZERO,
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=bank_account_id,
                    debit_amount=ZERO,
                    credit_amount=bank_charges,
                    description=description,
                ),
            ]
        if customer_charge > ZERO:
            lines += [
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.ACCOUNTS_RECEIVABLE
                    ],
                    debit_amount=customer_charge,
                    credit_amount=ZERO,
                    description=description,
                ),
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.CHEQUE_RETURN_CHARGES
                    ],
                    debit_amount=ZERO,
                    credit_amount=customer_charge,
                    description=description,
                ),
            ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=bounced_on,
            reference_number=reference,
            description=description,
            lines=lines,
            source_module="post_dated_cheque",
            source_id=cheque_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_commission_accrual(
        self,
        *,
        firm_id: UUID,
        payout_id: UUID,
        reference: str,
        accrued_on: date,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Recognise what a salesman has earned but not yet been paid.

        Two legs: the cost the firm has incurred, and the debt it now owes.
        Booking the expense straight against cash instead would say the firm
        owes nobody the moment it recognises the cost, which is wrong for
        every period that closes before the money goes out -- and that is most
        of them.

        Args:
            firm_id: The owning firm.
            payout_id: The source payout.
            reference: The payout's reference, used as the journal reference.
            accrued_on: The date the accrual is booked on.
            amount: What is owed.
            actor_id: The user approving it.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, COMMISSION_ACCRUAL_PURPOSES)
        context = self.context_for(firm_id, accrued_on)
        total = quantize_ledger(quantize_money(amount))
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.COMMISSION_EXPENSE],
                debit_amount=total,
                credit_amount=ZERO,
                description=f"Commission {reference}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.COMMISSION_PAYABLE],
                debit_amount=ZERO,
                credit_amount=total,
                description=f"Commission {reference}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=accrued_on,
            reference_number=reference,
            description=f"Commission accrual {reference}",
            lines=lines,
            source_module="commission",
            source_id=payout_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_commission_payment(
        self,
        *,
        firm_id: UUID,
        payout_id: UUID,
        reference: str,
        paid_on: date,
        amount: Decimal,
        money_account_id: UUID,
        actor_id: UUID,
    ) -> JournalEntry:
        """Settle a commission debt against the account the money left.

        The mirror image of the accrual: the payable falls and the cash or
        bank account falls with it. The expense is not touched -- it was
        recognised when the payout was approved, and recognising it again here
        would double the cost in whichever period the money happened to move.

        Args:
            firm_id: The owning firm.
            payout_id: The source payout.
            reference: The payout's reference.
            paid_on: The date the money moved.
            amount: How much moved.
            money_account_id: The cash or bank account it left.
            actor_id: The user recording the payment.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, COMMISSION_PAYMENT_PURPOSES)
        context = self.context_for(firm_id, paid_on)
        total = quantize_ledger(quantize_money(amount))
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.COMMISSION_PAYABLE],
                debit_amount=total,
                credit_amount=ZERO,
                description=f"Commission paid {reference}",
            ),
            JournalLineData(
                ledger_account_id=money_account_id,
                debit_amount=ZERO,
                credit_amount=total,
                description=f"Commission paid {reference}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=paid_on,
            reference_number=reference,
            description=f"Commission payment {reference}",
            lines=lines,
            source_module="commission",
            source_id=payout_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_expense(
        self,
        *,
        firm_id: UUID,
        expense_id: UUID,
        expense_number: str,
        expense_date: date,
        amount: Decimal,
        expense_account_id: UUID,
        paid_from_account_id: UUID,
        description: str,
        actor_id: UUID,
        tds_amount: Decimal = ZERO,
    ) -> JournalEntry:
        """Book money spent on running the firm: Dr the expense, Cr the money.

        Two legs and no control account: the caller has already chosen both
        accounts and checked that one is an expense and the other holds money.
        Nothing is flushed or committed here beyond what the journal engine
        stages, so the expense row and its journal land together or not at all.

        Args:
            firm_id: The owning firm.
            expense_id: The source expense.
            expense_number: Its number, used as the journal reference.
            expense_date: The day the money was spent.
            amount: How much was spent.
            expense_account_id: The expense account debited.
            paid_from_account_id: The cash or bank account credited.
            description: What the lines and the entry say it was for.
            actor_id: The user recording the expense.
            tds_amount: Tax deducted at source out of ``amount`` (53.1): the
                expense is the whole amount, the money leg the rest, and the
                deduction is credited to TDS Payable until the challan is paid.

        Returns:
            The posted journal entry.

        Raises:
            ValidationError: If no open period covers the date.

        """
        context = self.context_for(firm_id, expense_date)
        total = quantize_ledger(quantize_money(amount))
        deducted = quantize_ledger(quantize_money(tds_amount))
        lines = [
            JournalLineData(
                ledger_account_id=expense_account_id,
                debit_amount=total,
                credit_amount=ZERO,
                description=description,
            ),
            JournalLineData(
                ledger_account_id=paid_from_account_id,
                debit_amount=ZERO,
                credit_amount=total - deducted,
                description=description,
            ),
        ]
        if deducted > ZERO:
            tds_account = self._require_mapping(
                firm_id, (ControlAccountPurpose.TDS_PAYABLE,)
            )[ControlAccountPurpose.TDS_PAYABLE]
            lines.append(
                JournalLineData(
                    ledger_account_id=tds_account,
                    debit_amount=ZERO,
                    credit_amount=deducted,
                    description=f"TDS on {description}"[:500],
                )
            )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=expense_date,
            reference_number=expense_number,
            description=description,
            lines=lines,
            source_module="expenses",
            source_id=expense_id,
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
        tax_by_component: dict[str, Decimal] | None = None,
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
            tax_by_component: The tax per component as the return's lines
                recorded it, so each GST head is reversed through its own
                account (backlog 63.3). None reverses `OUTPUT_TAX` as a whole.

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
        accounts = self._require_mapping(
            firm_id,
            SALES_RETURN_PURPOSES + output_tax_purposes(tax, tax_by_component),
        )
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
        for offset, leg in enumerate(
            self._output_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_tax,
                tax_by_component=tax_by_component,
                describe=f"reversed on {return_number}",
                credit=False,
            ),
            start=1,
        ):
            lines.insert(offset, leg)
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

    def post_credit_note_document(
        self,
        *,
        firm_id: UUID,
        credit_note_id: UUID,
        credit_note_number: str,
        note_date: date,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        actor_id: UUID,
        tax_by_component: dict[str, Decimal] | None = None,
    ) -> JournalEntry | None:
        """Post a credit note that states the tax it reverses.

        Three legs, and the third is the whole point. The two-leg posting it
        replaced -- the receivable and sales returns, retired with its route
        (D-FIN-23) -- came from a bare receivable adjustment that carried one
        figure and no lines, so it had nothing to say what rate of tax to take
        off. A firm agreeing a rate
        difference after invoicing therefore credited the customer the gross
        amount and went on declaring output tax on a price nobody paid.

        The tax comes off at the rate the **invoice** charged, which the
        caller resolves from the line being credited rather than from today's
        profile: an edit to a tax profile in September must not change what
        was charged in March, exactly as it must not change a discount.

        Args:
            firm_id: The owning firm.
            credit_note_id: The source document.
            credit_note_number: Its number, used as the journal reference.
            note_date: The date the credit is booked on.
            taxable_amount: What is credited before tax.
            tax_amount: The tax reversed with it.
            actor_id: The user approving it.
            tax_by_component: The tax per GST head the way the invoice it
                credits was taxed (backlog 63.3); None reverses `OUTPUT_TAX`
                as a whole.

        Returns:
            The posted journal entry, or None where there is nothing to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        ledger_taxable = quantize_ledger(quantize_money(taxable_amount))
        ledger_tax = quantize_ledger(quantize_money(tax_amount))
        ledger_total = ledger_taxable + ledger_tax
        if ledger_total == ZERO:
            return None
        accounts = self._require_mapping(
            firm_id,
            CREDIT_NOTE_DOCUMENT_PURPOSES
            + output_tax_purposes(ledger_tax, tax_by_component),
        )
        context = self.context_for(firm_id, note_date)
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_RETURNS],
                debit_amount=ledger_taxable,
                description=f"Credit note {credit_note_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                credit_amount=ledger_total,
                description=f"Credit note {credit_note_number}",
            ),
        ]
        for offset, leg in enumerate(
            self._output_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_tax,
                tax_by_component=tax_by_component,
                describe=f"reversed on {credit_note_number}",
                credit=False,
            ),
            start=1,
        ):
            lines.insert(offset, leg)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=note_date,
            reference_number=credit_note_number,
            description=f"Credit note {credit_note_number}",
            lines=lines,
            source_module="credit_note",
            source_id=credit_note_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_customer_debit_note_document(
        self,
        *,
        firm_id: UUID,
        debit_note_id: UUID,
        debit_note_number: str,
        note_date: date,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        actor_id: UUID,
        tax_by_component: dict[str, Decimal] | None = None,
    ) -> JournalEntry | None:
        """Post a debit note to a customer: Dr receivable, Cr sales and output tax.

        The credit note turned the other way. The extra is more of the sale it
        names, so it is credited to sales revenue rather than to a contra
        account, and its tax is owed per GST head the way that invoice was
        taxed -- the caller resolves the split from the invoice, never from
        today's tax profile.

        Args:
            firm_id: The owning firm.
            debit_note_id: The source document.
            debit_note_number: Its number, used as the journal reference.
            note_date: The date the charge is booked on.
            taxable_amount: What is charged before tax.
            tax_amount: The tax charged with it.
            actor_id: The user approving it.
            tax_by_component: The tax per GST head; None credits `OUTPUT_TAX`
                as a whole.

        Returns:
            The posted journal entry, or None where there is nothing to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        ledger_taxable = quantize_ledger(quantize_money(taxable_amount))
        ledger_tax = quantize_ledger(quantize_money(tax_amount))
        ledger_total = ledger_taxable + ledger_tax
        if ledger_total == ZERO:
            return None
        accounts = self._require_mapping(
            firm_id,
            CUSTOMER_DEBIT_NOTE_PURPOSES
            + output_tax_purposes(ledger_tax, tax_by_component),
        )
        context = self.context_for(firm_id, note_date)
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE],
                debit_amount=ledger_total,
                description=f"Debit note {debit_note_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.SALES_REVENUE],
                credit_amount=ledger_taxable,
                description=f"Debit note {debit_note_number}",
            ),
            *self._output_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_tax,
                tax_by_component=tax_by_component,
                describe=f"charged on {debit_note_number}",
            ),
        ]
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=note_date,
            reference_number=debit_note_number,
            description=f"Debit note {debit_note_number}",
            lines=lines,
            source_module="customer_debit_note",
            source_id=debit_note_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_debit_note_document(
        self,
        *,
        firm_id: UUID,
        debit_note_id: UUID,
        debit_note_number: str,
        note_date: date,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        actor_id: UUID,
        tax_by_component: dict[str, Decimal] | None = None,
        reverse_charge_by_component: dict[str, Decimal] | None = None,
        blocked_tax_amount: Decimal = ZERO,
    ) -> JournalEntry | None:
        """Post a debit note to a supplier: Dr payable, Cr variance and input tax.

        The purchasing mirror of `post_credit_note_document`. The supplier owes
        the firm the whole claim, so **accounts payable is debited** with
        taxable plus tax. The taxable part is credited to purchase price
        variance -- the account a purchase return already puts the gap between
        a bill and what the goods cost through -- because no goods move: the
        firm simply paid, or was billed, more than it should have been. The
        input tax claimed on that part is reversed head by head, as the bill
        claimed it (D-CMP-20), through the same legs a purchase return uses.

        Args:
            firm_id: The owning firm.
            debit_note_id: The source document.
            debit_note_number: Its number, used as the journal reference.
            note_date: The date the claim is booked on.
            taxable_amount: What is claimed before tax.
            tax_amount: The input tax reversed with it.
            actor_id: The user approving it.
            tax_by_component: The tax per GST component, in the proportions
                the bill charged; None reverses `INPUT_TAX` as a whole.
            reverse_charge_by_component: The note's share of its bill's
                reverse charge, per component (backlog 68 row 8): the
                liability and the credit come off with the price.
            blocked_tax_amount: The note's share of tax its bill could not
                claim (backlog 78 row 1), credited back to
                `INELIGIBLE_INPUT_TAX` rather than off input tax.

        Returns:
            The posted journal entry, or None where there is nothing to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        # Each part rounded, then summed: what the payable is debited with is
        # exactly what the two credit legs carry.
        ledger_taxable = quantize_ledger(quantize_money(taxable_amount))
        ledger_tax = quantize_ledger(quantize_money(tax_amount))
        ledger_total = ledger_taxable + ledger_tax
        if ledger_total == ZERO:
            return None
        accounts = self._require_mapping(firm_id, DEBIT_NOTE_DOCUMENT_PURPOSES)
        context = self.context_for(firm_id, note_date)
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE],
                debit_amount=ledger_total,
                description=f"Debit note {debit_note_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[
                    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE
                ],
                credit_amount=ledger_taxable,
                description=f"Claimed on debit note {debit_note_number}",
            ),
        ]
        ledger_blocked = min(
            quantize_ledger(quantize_money(blocked_tax_amount)), ledger_tax
        )
        lines.extend(
            self._input_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_tax - ledger_blocked,
                tax_by_component=tax_by_component,
                describe=f"reversed on {debit_note_number}",
                credit=True,
            )
        )
        lines.extend(
            self._blocked_tax_legs(
                firm_id=firm_id,
                ledger_blocked=ledger_blocked,
                describe=f"reversed on {debit_note_number}",
                credit=True,
            )
        )
        lines.extend(
            self._reverse_charge_taken_off(
                firm_id=firm_id,
                reverse_charge_by_component=reverse_charge_by_component,
                describe=debit_note_number,
            )
        )
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=note_date,
            reference_number=debit_note_number,
            description=f"Debit note {debit_note_number}",
            lines=lines,
            source_module="debit_note",
            source_id=debit_note_id,
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

    def reverse_goods_return_to_stock(
        self,
        *,
        firm_id: UUID,
        entry_id: UUID,
        document_number: str,
        stock_value: Decimal,
        actor_id: UUID,
    ) -> JournalEntry:
        """Send returned goods back off the shelf at what they are worth now.

        The cost entry a completed return posted brought goods in at the
        average they were carried at that day. Cancelling sends them out again
        at the average of the day it is cancelled, and those differ the moment
        anything else has been received in between -- so mirroring the original
        credits inventory with a figure no movement removed. Measured on a
        seeded store: complete a return, receive twenty units at four times the
        price, cancel the return, and the books part company by 16.45.

        No third account is needed here, unlike a cancelled receipt or purchase
        return. Both legs of this entry are the same figure, so posting it at
        the movement value balances on its own and the difference against the
        original simply stays in cost of goods sold -- which is where the
        valuation of goods that were sold belongs.

        Args:
            firm_id: The owning firm.
            entry_id: The cost entry the return posted when it completed.
            document_number: The return's number, used as the reference.
            stock_value: What the reversing movements took back off the shelf.
            actor_id: The user cancelling the return.

        Returns:
            The posted reversal.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        accounts = self._require_mapping(firm_id, GOODS_ISSUE_PURPOSES)
        stock = quantize_ledger(quantize_money(stock_value))
        lines = [
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.INVENTORY],
                credit_amount=stock,
                description=f"Stock back off the shelf from {document_number}",
            ),
            JournalLineData(
                ledger_account_id=accounts[ControlAccountPurpose.COST_OF_GOODS_SOLD],
                debit_amount=stock,
                description=f"Cost of goods sold restored {document_number}",
            ),
        ]
        return self._journals.reverse_entry(
            entry_id,
            firm_id=firm_id,
            reference_number=f"{document_number}-COST-REV",
            actor_id=actor_id,
            lines=lines,
        )

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
        tax_by_component: dict[str, Decimal] | None = None,
        reverse_charge_by_component: dict[str, Decimal] | None = None,
        blocked_tax_amount: Decimal = ZERO,
        tds_amount: Decimal = ZERO,
        tcs_amount: Decimal = ZERO,
        capital_amounts: list[tuple[UUID, Decimal]] | None = None,
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
            tax_by_component: The tax per component code as the bill's lines
                recorded it, so each GST head is claimed through its own
                account (D-CMP-20). None posts the total to `INPUT_TAX`.
            reverse_charge_by_component: Tax the firm owes itself under
                reverse charge, per component (backlog 68 row 8). Never part
                of the payable: the supplier did not charge it. Each head is
                credited to its reverse-charge payable account -- paid in
                cash only -- and claimed back as input credit through the
                same input-tax account an ordinary bill uses.
            blocked_tax_amount: The part of ``tax_amount`` the firm may not
                claim (backlog 78 row 1), debited to `INELIGIBLE_INPUT_TAX`
                instead of input tax.
            tds_amount: Tax deducted at source on the bill (PG-5, 194C or
                194J): taken out of the payable and credited to TDS Payable,
                which the challan clears. The supplier is owed the rest.
            tcs_amount: TCS the supplier charged on the bill (PG-6, 206C(1H)):
                debited to TCS Receivable and added to the payable. Outside
                the goods and the tax, so it moves no stock and no GST.
            capital_amounts: The capital-goods lines (PG-13), one (asset
                account, rupee value) each: debited to the asset's cost
                account instead of being left to the accrual or the price
                variance, since such a line put nothing into stock. Their
                tax is claimed with the rest of the bill's.

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
        ledger_tds = quantize_ledger(quantize_money(tds_amount))
        if ledger_tds < ZERO or (ledger_tds > ZERO and ledger_tds >= ledger_total):
            raise ValidationError(
                f"TDS on invoice {invoice_number} must be less than what it owes."
            )

        ledger_tcs = quantize_ledger(quantize_money(tcs_amount))
        if ledger_tcs < ZERO:
            raise ValidationError(
                f"TCS on invoice {invoice_number} cannot be less than nothing."
            )

        accrued = (
            ledger_goods if accrued_amount is None else quantize_ledger(accrued_amount)
        )
        capital = [
            (account_id, quantize_ledger(amount))
            for account_id, amount in capital_amounts or []
            if quantize_ledger(amount) > ZERO
        ]
        variance = ledger_goods - accrued - sum((value for _, value in capital), ZERO)
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
                credit_amount=ledger_total + ledger_tcs - ledger_tds,
                description=f"Supplier invoice {invoice_number}",
            ),
        ]
        for account_id, value in capital:
            # Capital goods (PG-13): the asset's cost, never stock.
            lines.append(
                JournalLineData(
                    ledger_account_id=account_id,
                    debit_amount=value,
                    description=f"Capital goods on {invoice_number}",
                )
            )
        if ledger_tcs > ZERO:
            # Charged by the supplier on top of the bill (PG-6): the firm owes
            # it to the supplier and claims it back against its own tax.
            lines.append(
                JournalLineData(
                    ledger_account_id=self._require_mapping(
                        firm_id, (ControlAccountPurpose.TCS_RECEIVABLE,)
                    )[ControlAccountPurpose.TCS_RECEIVABLE],
                    debit_amount=ledger_tcs,
                    description=f"TCS charged on supplier invoice {invoice_number}",
                )
            )
        if ledger_tds > ZERO:
            # Deducted at the earlier of credit and payment (PG-5): the
            # supplier is owed the rest, the government this part.
            lines.append(
                JournalLineData(
                    ledger_account_id=self._require_mapping(
                        firm_id, (ControlAccountPurpose.TDS_PAYABLE,)
                    )[ControlAccountPurpose.TDS_PAYABLE],
                    credit_amount=ledger_tds,
                    description=f"TDS on supplier invoice {invoice_number}",
                )
            )
        # What the bill may not claim is a cost, not input tax (78 row 1).
        ledger_blocked = min(
            quantize_ledger(quantize_money(blocked_tax_amount)), ledger_tax
        )
        for offset, leg in enumerate(
            [
                *self._input_tax_legs(
                    firm_id=firm_id,
                    ledger_tax=ledger_tax - ledger_blocked,
                    tax_by_component=tax_by_component,
                    describe=f"on {invoice_number}",
                ),
                *self._blocked_tax_legs(
                    firm_id=firm_id,
                    ledger_blocked=ledger_blocked,
                    describe=f"on {invoice_number}",
                ),
            ],
            start=1,
        ):
            lines.insert(offset, leg)
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
        ledger_rcm = sum(
            (
                quantize_ledger(quantize_money(amount))
                for amount in (reverse_charge_by_component or {}).values()
            ),
            ZERO,
        )
        if ledger_rcm > ZERO:
            lines.extend(
                self._input_tax_legs(
                    firm_id=firm_id,
                    ledger_tax=ledger_rcm,
                    tax_by_component=reverse_charge_by_component,
                    describe=f"under reverse charge on {invoice_number}",
                )
            )
            lines.extend(
                self._tax_legs(
                    firm_id=firm_id,
                    ledger_tax=ledger_rcm,
                    tax_by_component=reverse_charge_by_component,
                    describe=f"on {invoice_number}",
                    purpose_of=rcm_payable_purpose,
                    fallback=ControlAccountPurpose.RCM_PAYABLE,
                    credit=True,
                )
            )

        # A bill of capital goods alone clears no accrual, and a leg of 0.00
        # says nothing: it is left off the journal (D-BUY-52).
        lines = [
            line
            for line in lines
            if line.debit_amount != ZERO or line.credit_amount != ZERO
        ]
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

    def _reverse_charge_taken_off(
        self,
        *,
        firm_id: UUID,
        reverse_charge_by_component: dict[str, Decimal] | None,
        describe: str,
    ) -> list[JournalLineData]:
        """Return the legs taking reverse charge off: the bill's, mirrored.

        The bill credited each head's reverse-charge payable and debited its
        input credit (backlog 68 row 8); goods going back, or a price coming
        down, owe that much less and claim that much less. Empty where the
        bill carried no reverse charge.
        """
        ledger_rcm = sum(
            (
                quantize_ledger(quantize_money(amount))
                for amount in (reverse_charge_by_component or {}).values()
            ),
            ZERO,
        )
        if ledger_rcm <= ZERO:
            return []
        return [
            *self._tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_rcm,
                tax_by_component=reverse_charge_by_component,
                describe=f"reverse charge taken off on {describe}",
                purpose_of=rcm_payable_purpose,
                fallback=ControlAccountPurpose.RCM_PAYABLE,
                credit=False,
            ),
            *self._input_tax_legs(
                firm_id=firm_id,
                ledger_tax=ledger_rcm,
                tax_by_component=reverse_charge_by_component,
                describe=f"under reverse charge reversed on {describe}",
                credit=True,
            ),
        ]

    def post_tcs_collection(
        self,
        *,
        firm_id: UUID,
        collection_id: UUID,
        reference: str,
        collected_on: date,
        amount: Decimal,
        actor_id: UUID,
    ) -> JournalEntry | None:
        """Post tax collected at source on a receipt.

        `Dr Accounts Receivable / Cr TCS Payable`. The buyer owes this **on
        top of** what they have just paid, so it raises a receivable rather
        than reducing one -- charging it against the money received would make
        the firm short by the tax on every collection, and would say the buyer
        had settled something they have not been billed for yet.

        Args:
            firm_id: The owning firm.
            collection_id: The TCS collection row this posts for.
            reference: The journal reference, unique per entry.
            collected_on: The date the receipt was recorded.
            amount: The tax collected.
            actor_id: The user recording it.

        Returns:
            The posted entry, or None where there is nothing to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        total = quantize_ledger(quantize_money(amount))
        if total == ZERO:
            return None
        accounts = self._require_mapping(firm_id, TCS_PURPOSES)
        context = self.context_for(firm_id, collected_on)
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=collected_on,
            reference_number=reference,
            description=f"Tax collected at source {reference}",
            lines=[
                JournalLineData(
                    ledger_account_id=accounts[
                        ControlAccountPurpose.ACCOUNTS_RECEIVABLE
                    ],
                    debit_amount=total,
                    description=f"TCS receivable {reference}",
                ),
                JournalLineData(
                    ledger_account_id=accounts[ControlAccountPurpose.TCS_PAYABLE],
                    credit_amount=total,
                    description=f"TCS payable {reference}",
                ),
            ],
            source_module="tcs",
            source_id=collection_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

    def post_loyalty(
        self,
        *,
        firm_id: UUID,
        entry_id: UUID,
        reference: str,
        on: date,
        amount: Decimal,
        earning: bool,
        actor_id: UUID,
        expiring: bool = False,
        description: str | None = None,
    ) -> JournalEntry | None:
        """Post points being earned, spent, or run out of time.

        Earning is `Dr Loyalty Expense / Cr Loyalty Payable`: a scheme costs
        the firm money the moment it promises the credit, not whenever the
        customer gets round to spending it, so the cost lands in the month it
        was incurred.

        Redeeming is `Dr Loyalty Payable / Cr Accounts Receivable`: the
        customer settles part of a bill with credit the firm already owed
        them. **No tax moves either way** -- the supply is worth what it is
        worth and the full tax was charged on it. Treating a redemption as a
        discount instead would reduce the taxable value and so the GST the
        firm collects, which is a decision about tax rather than about
        loyalty.

        Args:
            firm_id: The owning firm.
            entry_id: The ledger entry this posts for.
            reference: The journal reference, unique per entry.
            on: The date it happened.
            amount: What the points are worth.
            earning: True for points earned, False for points spent.
            actor_id: The user recording it.
            expiring: True for points that lapsed. Reverses the accrual --
                `Dr Loyalty Payable / Cr Loyalty Expense` -- because nothing
                was settled and the credit can never be claimed. Not the
                mirror of a redemption, which takes a receivable down.
            description: What to call it in place of the default -- a goodwill
                grant posts as an earning and a correction down as a lapse,
                but neither should read as one.

        Returns:
            The posted entry, or None where there is nothing to post.

        Raises:
            ValidationError: If accounts or an open period are missing.

        """
        total = quantize_ledger(quantize_money(amount))
        if total == ZERO:
            return None
        if expiring:
            purposes = LOYALTY_EXPIRY_PURPOSES
        elif earning:
            purposes = LOYALTY_EARN_PURPOSES
        else:
            purposes = LOYALTY_REDEEM_PURPOSES
        accounts = self._require_mapping(firm_id, purposes)
        context = self.context_for(firm_id, on)
        if expiring:
            # The accrual, run backwards: the debt goes and the cost with it.
            debit = accounts[ControlAccountPurpose.LOYALTY_PAYABLE]
            credit = accounts[ControlAccountPurpose.LOYALTY_EXPENSE]
            what = "Loyalty lapsed"
        elif earning:
            debit = accounts[ControlAccountPurpose.LOYALTY_EXPENSE]
            credit = accounts[ControlAccountPurpose.LOYALTY_PAYABLE]
            what = "Loyalty earned"
        else:
            debit = accounts[ControlAccountPurpose.LOYALTY_PAYABLE]
            credit = accounts[ControlAccountPurpose.ACCOUNTS_RECEIVABLE]
            what = "Loyalty redeemed"
        if description is not None:
            what = description
        entry = self._journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=on,
            reference_number=reference,
            description=f"{what} {reference}",
            lines=[
                JournalLineData(
                    ledger_account_id=debit,
                    debit_amount=total,
                    description=f"{what} {reference}",
                ),
                JournalLineData(
                    ledger_account_id=credit,
                    credit_amount=total,
                    description=f"{what} {reference}",
                ),
            ],
            source_module="loyalty",
            source_id=entry_id,
            actor_id=actor_id,
        )
        return self._journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
