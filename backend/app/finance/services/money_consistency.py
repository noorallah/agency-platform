"""Do the firm's books agree with themselves, month by month (item 30, part 1).

Every figure a firm sees is read from somewhere, and the same money is kept
in more than one place: the general ledger, the customer sub-ledger
(``customer_receivable_transactions``), the documents and the settlements set
against them. Each pair has drifted apart at least once -- a balance moved
without a journal, a bill posted twice, a cancelled document whose journal was
never taken off. This answers, for each month, whether they still agree, and
names the document where they do not.

It is **read-only**: it reads and never writes, flushes or commits. The
figures are the ones the product already shows -- the trial balance, the
customer ageing, the supplier statement, Record Payment's open bills -- so a
difference here is a difference a user could find on two screens. No balance
is worked out a new way.

Checks, per month (an accounting period of the firm):

1. **The trial balance balances.** The posted journal lines dated in the
   month debit what they credit; no single journal is out of balance; and the
   stored trial balance (``GeneralLedgerService.trial_balance``) balances on
   its movement and closing columns.
2. **Receivables agree.** The receivables control account's balance at the
   month's end equals the customers' sub-ledger summed to that day, owing less
   advances held. And each customer's account, owing less advances, equals
   what their bills still owe -- the ageing's open invoices and opening bills
   less settlements, credits and adjustments
   (``CustomerStatementService.ageing``) -- less receipts held on account
   and less the credit returns and credit notes gave that no bill absorbed
   and nothing has used (``customer_credits``), and less an opening balance
   typed on the customer master in credit, held as an advance no receipt
   holds and no bill carries.
3. **Payables agree.** The payables control account's balance at the
   month's end equals the sum of the suppliers' statements to that day
   (``SupplierStatementService.balances``). And each supplier's statement
   equals their open bills (``PaymentService.outstanding_invoices``) less
   payments held on account and credit not yet used (``supplier_credits``).

   The account-against-bills halves of 2 and 3 are asked **as at today**
   only, under the current month: what a receipt or payment held unapplied
   on an earlier day is not something the settlements record.
4. **Every posting document has its journal, and every journal its
   document.** An approved document with a value and no journal naming it;
   a settlement naming a journal that does not stand; and a journal whose
   document is missing, deleted, or cancelled while the journal was never
   reversed.

``check_money_consistency`` returns one ``Difference`` per disagreement;
``scripts/check_money_consistency.py`` prints them for a firm or every firm.

TODO, later parts of item 30 (not built here):

* Stock value against the inventory control account, per month.
* GST: output and input tax accounts against GSTR-1 / GSTR-3B for the month.
* TCS collected against TCS payable; TDS deducted against TDS payable and
  the challans paid.
* Loyalty points held against loyalty payable; commission accrued against
  commission payable.
* Check 2 nets an opening balance in credit at its typed figure, so one
  later paid back by a refund that names no source reads as a difference;
  nothing yet records which opening credit a refund drew.
* Check 4 for the remaining posting modules (loyalty, tcs, commission,
  expenses, party adjustments, opening bills and the rest of
  ``source_module``), which have no single "has a value" column to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_today
from app.core.utils.money import quantize_ledger
from app.finance.models import (
    AccountingPeriod,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.general_ledger_service import GeneralLedgerService
from app.finance.services.period_close_checks import _documents

ZERO = Decimal("0.00")

#: A posted journal counts; so does one later reversed, because its mirror
#: (POSTED) is what takes it back.
COUNTED = (JournalStatus.POSTED.value, JournalStatus.REVERSED.value)
#: A document in one of these states has been undone.
UNDONE = ("CANCELLED", "REVERSED")

TRIAL_BALANCE = "TRIAL_BALANCE"
JOURNAL_UNBALANCED = "JOURNAL_UNBALANCED"
RECEIVABLES_LEDGER = "RECEIVABLES_LEDGER_VS_CUSTOMERS"
RECEIVABLES_BILLS = "RECEIVABLES_CUSTOMER_VS_BILLS"
PAYABLES_LEDGER = "PAYABLES_LEDGER_VS_SUPPLIERS"
PAYABLES_BILLS = "PAYABLES_SUPPLIER_VS_BILLS"
DOCUMENT_WITHOUT_JOURNAL = "DOCUMENT_WITHOUT_JOURNAL"
JOURNAL_WITHOUT_DOCUMENT = "JOURNAL_WITHOUT_DOCUMENT"


@dataclass(frozen=True)
class Difference:
    """One place two of the firm's books disagree."""

    #: Which check found it -- one of the constants above.
    check: str
    #: The month, ``YYYY-MM``.
    period: str
    #: The document, account or party it is about.
    document_ref: str
    #: What one book says.
    expected: Decimal
    #: What the other says.
    actual: Decimal
    #: Why, where the check can say.
    note: str = ""


def check_money_consistency(
    session: Session,
    firm_id: UUID,
    *,
    from_month: date | None = None,
    to_month: date | None = None,
) -> list[Difference]:
    """Return every disagreement in the firm's books, month by month.

    Args:
        session: The firm's store. Read from and never written to.
        firm_id: The firm.
        from_month: Any day of the first month to check; None from the first.
        to_month: Any day of the last month to check; None to the current.

    Returns:
        One ``Difference`` per disagreement, month by month; empty when the
        books agree.

    """
    months = _months(session, firm_id, from_month, to_month)
    if not months:
        return []
    found: list[Difference] = []
    controls = ControlAccountService(session).mapping(firm_id)
    receivable = controls.get(ControlAccountPurpose.ACCOUNTS_RECEIVABLE.value)
    payable = controls.get(ControlAccountPurpose.ACCOUNTS_PAYABLE.value)
    for period in months:
        label = f"{period.starts_on:%Y-%m}"
        found += _trial_balance(session, firm_id, period, label)
        if receivable is not None:
            found += _receivables(session, firm_id, receivable, period, label)
        if payable is not None:
            found += _payables(session, firm_id, payable, period, label)
    today = firm_today(session, firm_id)
    if months[-1].ends_on >= today:
        if receivable is not None:
            found += _receivables_against_bills(session, firm_id, today)
        if payable is not None:
            found += _payables_against_bills(session, firm_id, today)
    found += _documents_without_journals(session, firm_id, months)
    found += _journals_without_documents(session, firm_id, months)
    return found


def _months(
    session: Session,
    firm_id: UUID,
    from_month: date | None,
    to_month: date | None,
) -> list[AccountingPeriod]:
    """Return the firm's periods to check, oldest first, none in the future."""
    statement = select(AccountingPeriod).where(
        AccountingPeriod.firm_id == firm_id,
        AccountingPeriod.is_deleted.is_(False),
        AccountingPeriod.starts_on <= firm_today(session, firm_id),
    )
    if from_month is not None:
        statement = statement.where(
            AccountingPeriod.ends_on >= from_month.replace(day=1)
        )
    if to_month is not None:
        statement = statement.where(AccountingPeriod.starts_on <= to_month)
    return list(session.scalars(statement.order_by(AccountingPeriod.starts_on)))


def _money(value: object) -> Decimal:
    """Read a summed amount as money at the ledger's two places."""
    return quantize_ledger(Decimal(str(value or 0)))


# ---- 1. the trial balance --------------------------------------------------


def _trial_balance(
    session: Session, firm_id: UUID, period: AccountingPeriod, label: str
) -> list[Difference]:
    """Check the month's journals and its stored trial balance balance."""
    found: list[Difference] = []
    debit, credit = session.execute(
        select(
            func.coalesce(func.sum(JournalLine.debit_amount), 0),
            func.coalesce(func.sum(JournalLine.credit_amount), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(*_in_month(firm_id, period), JournalLine.is_deleted.is_(False))
    ).one()
    if _money(debit) != _money(credit):
        found.append(
            Difference(
                TRIAL_BALANCE,
                label,
                "posted journal lines",
                _money(debit),
                _money(credit),
                "debits against credits dated in the month",
            )
        )
    for reference, module, line_debit, line_credit in session.execute(
        select(
            JournalEntry.reference_number,
            JournalEntry.source_module,
            func.coalesce(func.sum(JournalLine.debit_amount), 0),
            func.coalesce(func.sum(JournalLine.credit_amount), 0),
        )
        .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
        .where(*_in_month(firm_id, period), JournalLine.is_deleted.is_(False))
        .group_by(
            JournalEntry.id, JournalEntry.reference_number, JournalEntry.source_module
        )
        .having(
            func.sum(JournalLine.debit_amount) != func.sum(JournalLine.credit_amount)
        )
        .order_by(JournalEntry.reference_number)
    ).all():
        found.append(
            Difference(
                JOURNAL_UNBALANCED,
                label,
                f"Journal {reference}" + (f" ({module})" if module else ""),
                _money(line_debit),
                _money(line_credit),
                "the journal's debits against its credits",
            )
        )
    report = GeneralLedgerService(session).trial_balance(
        firm_id=firm_id, accounting_period_id=period.id
    )
    for side, debits, credits in (
        ("movement", report.total_period_debit, report.total_period_credit),
        ("closing", report.total_closing_debit, report.total_closing_credit),
    ):
        if _money(debits) != _money(credits):
            found.append(
                Difference(
                    TRIAL_BALANCE,
                    label,
                    f"trial balance, {side} columns",
                    _money(debits),
                    _money(credits),
                    "the stored balances the trial balance reads",
                )
            )
    return found


def _in_month(firm_id: UUID, period: AccountingPeriod) -> tuple[Any, ...]:
    """Return the filter for counted journals dated in one period."""
    return (
        JournalEntry.firm_id == firm_id,
        JournalEntry.is_deleted.is_(False),
        JournalEntry.status.in_(COUNTED),
        JournalEntry.journal_date.between(period.starts_on, period.ends_on),
    )


def _account_balance(
    session: Session, firm_id: UUID, account_id: UUID, as_of: date
) -> tuple[str, Decimal]:
    """Return an account's code and its debit-less-credit balance at a day."""
    code = session.scalar(
        select(LedgerAccount.code).where(LedgerAccount.id == account_id)
    )
    balance = session.scalar(
        select(
            func.coalesce(
                func.sum(JournalLine.debit_amount - JournalLine.credit_amount), 0
            )
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalLine.ledger_account_id == account_id,
            JournalLine.is_deleted.is_(False),
            JournalEntry.firm_id == firm_id,
            JournalEntry.is_deleted.is_(False),
            JournalEntry.status.in_(COUNTED),
            JournalEntry.journal_date <= as_of,
        )
    )
    return str(code or account_id), _money(balance)


# ---- 2. receivables --------------------------------------------------------


def _customer_accounts(
    session: Session, firm_id: UUID, as_of: date
) -> dict[UUID, tuple[str, Decimal, Decimal]]:
    """Return each customer's code, outstanding and advance at a day's end.

    Summed from the dated movements, as the statement and the ageing sum them.
    """
    from app.customers.models import Customer, CustomerReceivableTransaction

    return {
        customer_id: (customer_code, _money(owed), _money(advance))
        for customer_id, customer_code, owed, advance in session.execute(
            select(
                CustomerReceivableTransaction.customer_id,
                Customer.code,
                func.coalesce(
                    func.sum(CustomerReceivableTransaction.outstanding_delta), 0
                ),
                func.coalesce(func.sum(CustomerReceivableTransaction.advance_delta), 0),
            )
            .join(Customer, Customer.id == CustomerReceivableTransaction.customer_id)
            .where(
                CustomerReceivableTransaction.firm_id == firm_id,
                CustomerReceivableTransaction.is_deleted.is_(False),
                CustomerReceivableTransaction.transaction_date <= as_of,
            )
            .group_by(CustomerReceivableTransaction.customer_id, Customer.code)
        ).all()
    }


def _receivables(
    session: Session,
    firm_id: UUID,
    account_id: UUID,
    period: AccountingPeriod,
    label: str,
) -> list[Difference]:
    """Check the receivables account against the customers at the month's end."""
    code, ledger = _account_balance(session, firm_id, account_id, period.ends_on)
    accounts = _customer_accounts(session, firm_id, period.ends_on)
    customers = sum((owed - advance for _, owed, advance in accounts.values()), ZERO)
    if ledger == customers:
        return []
    return [
        Difference(
            RECEIVABLES_LEDGER,
            label,
            f"Account {code}",
            ledger,
            customers,
            "receivables account against customers owing less advances held, "
            "at the month's end -- a balance moved without a journal, or the "
            "reverse",
        )
    ]


def _receivables_against_bills(
    session: Session, firm_id: UUID, today: date
) -> list[Difference]:
    """Check each customer's account against their open bills, today."""
    from app.customers.services.statement_service import CustomerStatementService
    from app.settlements.models import Settlement, SettlementDirection, SettlementStatus

    accounts = _customer_accounts(session, firm_id, today)
    ageing = CustomerStatementService(session).ageing(firm_scope=firm_id)
    owing = {row.customer_id: quantize_ledger(row.total_outstanding) for row in ageing}
    codes = {row.customer_id: row.customer_code for row in ageing}
    for customer_id, held in session.execute(
        select(Settlement.customer_id, func.sum(Settlement.unallocated_amount))
        .where(
            Settlement.firm_id == firm_id,
            Settlement.is_deleted.is_(False),
            Settlement.customer_id.is_not(None),
            Settlement.direction == SettlementDirection.RECEIPT.value,
            Settlement.status == SettlementStatus.POSTED.value,
            Settlement.unallocated_amount > 0,
        )
        .group_by(Settlement.customer_id)
    ).all():
        owing[customer_id] = owing.get(customer_id, ZERO) - _money(held)
    for customer_id, credit in _unused_customer_credit(session, firm_id).items():
        owing[customer_id] = owing.get(customer_id, ZERO) - credit
    for customer_id, opening in _opening_credits(session, firm_id, today).items():
        owing[customer_id] = owing.get(customer_id, ZERO) - opening
    found: list[Difference] = []
    for customer_id in sorted(set(accounts) | set(owing), key=str):
        code, owed, advance = accounts.get(customer_id, ("", ZERO, ZERO))
        account = owed - advance
        bills = owing.get(customer_id, ZERO)
        if account == bills:
            continue
        found.append(
            Difference(
                RECEIVABLES_BILLS,
                f"{today:%Y-%m}",
                f"Customer {code or codes.get(customer_id, customer_id)}",
                account,
                bills,
                "the customer's account less advances against open bills less "
                "receipts held on account and return or credit-note credit "
                "unused and opening balances in credit, as at "
                f"{today.isoformat()} -- "
                + (
                    "credit on the account that no receipt, return, credit "
                    "note or opening balance holds"
                    if bills > account
                    else "a charge on the account that no open bill carries"
                ),
            )
        )
    return found


def _unused_customer_credit(session: Session, firm_id: UUID) -> dict[UUID, Decimal]:
    """Return each customer's return and credit-note credit not yet used.

    What a completed return or an approved credit note gave that its own bill
    could not absorb -- the bill already paid -- and that has been neither set
    against another bill nor paid back. It is on the account (held as an
    advance, or off what was owed) and on no open bill, so the bills' side
    takes it off as it takes off a receipt held on account. Read through
    ``customer_credits``, the figure the Customer credits screen shows, one
    customer at a time and only for customers with a standing source.
    """
    from app.settlements.services.customer_credits import _sources, customer_credits

    customers = {
        source.customer_id
        for source in _sources(session, firm_id, None, standing_only=True).values()
    }
    unused: dict[UUID, Decimal] = {}
    for customer_id in sorted(customers, key=str):
        total = sum(
            (
                credit.available_amount
                for credit in customer_credits(
                    session, firm_id=firm_id, customer_id=customer_id
                )
            ),
            ZERO,
        )
        if total != ZERO:
            unused[customer_id] = _money(total)
    return unused


def _opening_credits(
    session: Session, firm_id: UUID, today: date
) -> dict[UUID, Decimal]:
    """Return each customer's opening balance in credit, from the master.

    The single day-one figure typed on the customer (``OPENING_BALANCE``),
    when the firm owed the customer at cutover: held for them as an advance
    that no receipt holds and no bill carries, so the bills' side takes it
    off. In debit it needs nothing here -- the ageing already carries it as
    an "Opening balance" row. A revised figure deletes the old rows, so only
    live rows count.
    """
    from app.customers.models import CustomerReceivableTransaction
    from app.customers.schemas.customer import CustomerReceivableTransactionType

    return {
        customer_id: _money(value)
        for customer_id, value in session.execute(
            select(
                CustomerReceivableTransaction.customer_id,
                func.sum(CustomerReceivableTransaction.advance_delta),
            )
            .where(
                CustomerReceivableTransaction.firm_id == firm_id,
                CustomerReceivableTransaction.is_deleted.is_(False),
                CustomerReceivableTransaction.transaction_type
                == CustomerReceivableTransactionType.OPENING_BALANCE.value,
                CustomerReceivableTransaction.transaction_date <= today,
            )
            .group_by(CustomerReceivableTransaction.customer_id)
        ).all()
        if _money(value) != ZERO
    }


# ---- 3. payables -----------------------------------------------------------


def _payables(
    session: Session,
    firm_id: UUID,
    account_id: UUID,
    period: AccountingPeriod,
    label: str,
) -> list[Difference]:
    """Check the payables account against the suppliers at the month's end."""
    from app.vendors.services.statement_service import SupplierStatementService

    code, balance = _account_balance(session, firm_id, account_id, period.ends_on)
    ledger = -balance
    suppliers = sum(
        SupplierStatementService(session)
        .balances(firm_scope=firm_id, as_of=period.ends_on)
        .values(),
        ZERO,
    )
    if ledger == suppliers:
        return []
    return [
        Difference(
            PAYABLES_LEDGER,
            label,
            f"Account {code}",
            ledger,
            quantize_ledger(suppliers),
            "payables account against the suppliers' statements, at the "
            "month's end -- a line on the account no supplier document names",
        )
    ]


def _payables_against_bills(
    session: Session, firm_id: UUID, today: date
) -> list[Difference]:
    """Check each supplier's statement against their open bills, today."""
    from app.settlements.models import Settlement, SettlementStatus
    from app.settlements.services import PaymentService
    from app.settlements.services.supplier_credits import supplier_credits
    from app.vendors.models import Vendor
    from app.vendors.services.statement_service import SupplierStatementService

    statements = SupplierStatementService(session).balances(
        firm_scope=firm_id, as_of=today
    )
    owing: dict[UUID, Decimal] = {}
    for record in PaymentService(session).outstanding_invoices(
        firm_id=firm_id, party_id=None
    ):
        if record.party_id is not None:
            owing[record.party_id] = (
                owing.get(record.party_id, ZERO) + record.outstanding_amount
            )
    for vendor_id, held in session.execute(
        select(Settlement.vendor_id, func.sum(Settlement.unallocated_amount))
        .where(
            Settlement.firm_id == firm_id,
            Settlement.is_deleted.is_(False),
            Settlement.vendor_id.is_not(None),
            Settlement.status == SettlementStatus.POSTED.value,
            Settlement.unallocated_amount > 0,
        )
        .group_by(Settlement.vendor_id)
    ).all():
        owing[vendor_id] = owing.get(vendor_id, ZERO) - _money(held)
    for credit in supplier_credits(session, firm_id=firm_id):
        owing[credit.vendor_id] = (
            owing.get(credit.vendor_id, ZERO) - credit.available_amount
        )
    codes: dict[UUID, str] = {
        vendor_id: code
        for vendor_id, code in session.execute(
            select(Vendor.id, Vendor.code).where(Vendor.firm_id == firm_id)
        ).all()
    }
    found: list[Difference] = []
    for vendor_id in sorted(set(statements) | set(owing), key=str):
        statement = quantize_ledger(statements.get(vendor_id, ZERO))
        bills = quantize_ledger(owing.get(vendor_id, ZERO))
        if statement == bills:
            continue
        found.append(
            Difference(
                PAYABLES_BILLS,
                f"{today:%Y-%m}",
                f"Supplier {codes.get(vendor_id, vendor_id)}",
                statement,
                bills,
                f"the supplier's statement against open bills less payments "
                f"on account and credit unused, as at {today.isoformat()}",
            )
        )
    return found


# ---- 4. documents and journals ---------------------------------------------


def _documents_without_journals(
    session: Session, firm_id: UUID, months: list[AccountingPeriod]
) -> list[Difference]:
    """Name each posted document with a value that no standing journal names."""
    from app.settlements.models import Settlement

    starts_on, ends_on = months[0].starts_on, months[-1].ends_on
    found: list[Difference] = []
    for label, model, number, on, posted, total, module in _documents():
        journal = (
            select(JournalEntry.id)
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.source_module == module,
                JournalEntry.source_id == model.id,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
                JournalEntry.status.in_(COUNTED),
            )
            .exists()
        )
        for document_number, day, value in session.execute(
            select(number, on, total)
            .where(
                model.firm_id == firm_id,
                model.is_deleted.is_(False),
                model.status.in_(posted),
                total > 0,
                on.between(starts_on, ends_on),
                ~journal,
            )
            .order_by(on, number)
        ).all():
            found.append(
                Difference(
                    DOCUMENT_WITHOUT_JOURNAL,
                    f"{day:%Y-%m}",
                    f"{label} {document_number}",
                    _money(value),
                    ZERO,
                    "approved with a value, and no journal names it",
                )
            )
    standing = (
        select(JournalEntry.id)
        .where(
            JournalEntry.id == Settlement.journal_entry_id,
            JournalEntry.is_deleted.is_(False),
            JournalEntry.status.in_(COUNTED),
        )
        .exists()
    )
    for document_number, day, value in session.execute(
        select(
            Settlement.settlement_number, Settlement.settlement_date, Settlement.amount
        )
        .where(
            Settlement.firm_id == firm_id,
            Settlement.is_deleted.is_(False),
            Settlement.settlement_date.between(starts_on, ends_on),
            ~standing,
        )
        .order_by(Settlement.settlement_date, Settlement.settlement_number)
    ).all():
        found.append(
            Difference(
                DOCUMENT_WITHOUT_JOURNAL,
                f"{day:%Y-%m}",
                f"Settlement {document_number}",
                _money(value),
                ZERO,
                "the journal the settlement names does not stand",
            )
        )
    return found


def _sources() -> list[tuple[str, str, Any, Any]]:
    """Return each posting module: its label, source module, table and number."""
    from app.delivery_note.models import DeliveryNote
    from app.goods_receipt.models import GoodsReceipt
    from app.settlements.models import Settlement

    return [
        (label, module, model, number)
        for label, model, number, _on, _posted, _total, module in _documents()
    ] + [
        (
            "Delivery note",
            "delivery_note",
            DeliveryNote,
            DeliveryNote.delivery_note_number,
        ),
        ("Goods receipt", "goods_receipt", GoodsReceipt, GoodsReceipt.grn_number),
        ("Settlement", "settlements", Settlement, Settlement.settlement_number),
    ]


def _journals_without_documents(
    session: Session, firm_id: UUID, months: list[AccountingPeriod]
) -> list[Difference]:
    """Name each journal whose document is missing, deleted or undone."""
    starts_on, ends_on = months[0].starts_on, months[-1].ends_on
    found: list[Difference] = []
    for label, module, model, number in _sources():
        for (
            reference,
            day,
            value,
            source_id,
            deleted,
            status,
            document,
        ) in session.execute(
            select(
                JournalEntry.reference_number,
                JournalEntry.journal_date,
                JournalEntry.total_debit,
                model.id,
                model.is_deleted,
                model.status,
                number,
            )
            .outerjoin(
                model,
                and_(model.id == JournalEntry.source_id, model.firm_id == firm_id),
            )
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.source_module == module,
                JournalEntry.is_deleted.is_(False),
                JournalEntry.status.in_(COUNTED),
                JournalEntry.journal_date.between(starts_on, ends_on),
                or_(
                    model.id.is_(None),
                    model.is_deleted.is_(True),
                    and_(
                        JournalEntry.status == JournalStatus.POSTED.value,
                        JournalEntry.reversal_of_id.is_(None),
                        model.status.in_(UNDONE),
                    ),
                ),
            )
            .order_by(JournalEntry.journal_date, JournalEntry.reference_number)
        ).all():
            if source_id is None:
                why = f"names a {label.lower()} that does not exist"
            elif deleted:
                why = f"names {label.lower()} {document}, which is deleted"
            else:
                why = (
                    f"{label.lower()} {document} is {status.lower()} and the "
                    "journal was never reversed"
                )
            found.append(
                Difference(
                    JOURNAL_WITHOUT_DOCUMENT,
                    f"{day:%Y-%m}",
                    f"Journal {reference}",
                    ZERO,
                    _money(value),
                    why,
                )
            )
    return found


__all__ = ["Difference", "check_money_consistency"]
