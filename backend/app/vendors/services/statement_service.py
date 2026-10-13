"""What a supplier's account looks like over a period (backlog 74 row 4).

The customer statement reads `customer_receivable_transactions`, the
customer's own sub-ledger. A supplier has none: what the firm owes a supplier
is not a column but the bills still owing, derived from the documents
(`app/vendors/models/opening_bill.py`). So this reads the one place every
document that moves a supplier's balance already writes to, and writes in
date order: **the payables lines of the general ledger**, each traced back to
its supplier through the document that posted it.

Seven documents post to accounts payable, and each names its supplier:

==========================  ==========================  =====================
``source_module``           Document                    Side
==========================  ==========================  =====================
``purchase_invoice``        Supplier bill               Cr: owed more
``vendor_opening_bills``    Bill from the old books     Cr
``settlements``             Payment                     Dr: owed less
``purchase_return``         Goods sent back             Dr
``debit_note``              Debit note                  Dr
``party_adjustments``       Write-back or set-off       Dr
``supplier_credit_refund``  Money the supplier paid     Cr: the credit a
                            back for a return or note   return left is used
==========================  ==========================  =====================

The refund was left out when it was built (D-BUY-48): the statement, the
balance confirmation and the per-supplier books check all closed wrong by
every refund a supplier had paid.

A cancelled document's mirror carries the same source (`reverse_entry` copies
it), so a cancellation appears on the statement on the day it happened, as a
``*_REVERSAL`` line, and the two net to nothing. Hand journals are refused on
payables (D-FIN-11), so nothing else can move the account.

**A payment to a main office that clears a branch's bill** (backlog 127)
posts one journal, in the main office's name. The branch's account comes down
all the same: each such allocation is read as a pair of ``PAYMENT_TRANSFER``
lines, a debit on the branch and a credit on the main office for the same
amount on the day the money met the bill. The pair nets to nothing on the
payables account, so the property below still holds, and it is derived from
the allocation rather than stored, as the rest of this statement is. A
reversed payment keeps its pair and gains the opposite one on the day it was
reversed (``PAYMENT_TRANSFER_REVERSAL``).

Two properties follow and are what the tests hold it to. The supplier's
closing balance **is** the payables ledger's balance for that supplier, by
construction -- every supplier's closing balance sums to the account. And the
running balance is **recomputed in date order**, never read off a stored
snapshot: a payment keyed today for a bill dated last month sits where its
date puts it.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CompoundSelect,
    String,
    and_,
    cast,
    func,
    literal,
    null,
    select,
    union_all,
)
from sqlalchemy.orm import Session

from app.core.database.types import UUIDType
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.debit_note.models import DebitNote
from app.finance.models import JournalEntry, JournalLine, JournalStatus
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.party_adjustments.models import PartyAdjustment
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_return.models import PurchaseReturn
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementStatus,
    SupplierCreditRefund,
)
from app.vendors.models import Vendor, VendorOpeningBill
from app.vendors.schemas.statement import SupplierStatement, SupplierStatementLine

#: Every document that posts to payables, by the ``source_module`` its
#: journals carry, with its table and the line type the statement shows.
SUPPLIER_SOURCES: tuple[tuple[str, Any, str], ...] = (
    ("purchase_invoice", PurchaseInvoice, "BILL"),
    ("vendor_opening_bills", VendorOpeningBill, "OPENING_BILL"),
    ("settlements", Settlement, "PAYMENT"),
    ("purchase_return", PurchaseReturn, "PURCHASE_RETURN"),
    ("debit_note", DebitNote, "DEBIT_NOTE"),
    ("party_adjustments", PartyAdjustment, "ADJUSTMENT"),
    ("supplier_credit_refund", SupplierCreditRefund, "REFUND"),
)

#: What a main office's payment cleared on a branch (backlog 127): not a
#: journal, but read as one line on each of the two accounts.
_TRANSFER = "payment_transfer"

_LINE_TYPES = {module: label for module, _, label in SUPPLIER_SOURCES} | {
    _TRANSFER: "PAYMENT_TRANSFER"
}

#: A posted journal counts; so does one later reversed, because its mirror
#: (POSTED) is what takes it back and both belong on the statement.
_COUNTED = (JournalStatus.POSTED.value, JournalStatus.REVERSED.value)


class SupplierStatementService:
    """Build a supplier's statement of account and supplier balances."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def _payables_account(self, firm_id: UUID) -> UUID | None:
        """Return the account the firm's payables post to, if it has one."""
        return (
            ControlAccountService(self._session)
            .mapping(firm_id)
            .get(ControlAccountPurpose.ACCOUNTS_PAYABLE.value)
        )

    def _movements(
        self, firm_id: UUID, account_id: UUID, vendor_id: UUID | None
    ) -> CompoundSelect[Any]:
        """Select every payables line with the supplier its document names.

        One branch per posting document, joined to its table on the source
        id, so the supplier comes from the document and never from the
        narration.
        """
        branches = []
        for module, model, _ in SUPPLIER_SOURCES:
            branch = (
                select(
                    model.vendor_id.label("vendor_id"),
                    JournalEntry.journal_date.label("journal_date"),
                    JournalEntry.created_at.label("created_at"),
                    JournalEntry.id.label("entry_id"),
                    JournalEntry.reference_number.label("reference_number"),
                    JournalEntry.description.label("description"),
                    literal(module).label("source_module"),
                    JournalEntry.reversal_of_id.label("reversal_of_id"),
                    JournalLine.debit_amount.label("debit"),
                    JournalLine.credit_amount.label("credit"),
                    # The supplier's own credit note a debit note records
                    # (backlog 68 row 10), so the statement names it.
                    (
                        DebitNote.supplier_credit_note_number
                        if model is DebitNote
                        else cast(null(), String(80))
                    ).label("party_reference"),
                )
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                .join(
                    model,
                    and_(
                        model.id == JournalEntry.source_id,
                        JournalEntry.source_module == module,
                    ),
                )
                .where(
                    JournalLine.ledger_account_id == account_id,
                    JournalLine.is_deleted.is_(False),
                    JournalEntry.firm_id == firm_id,
                    JournalEntry.is_deleted.is_(False),
                    JournalEntry.status.in_(_COUNTED),
                    model.firm_id == firm_id,
                )
            )
            if vendor_id is not None:
                branch = branch.where(model.vendor_id == vendor_id)
            branches.append(branch)
        branches.extend(self._transfers(firm_id, vendor_id))
        return union_all(*branches)

    @staticmethod
    def _transfers(firm_id: UUID, vendor_id: UUID | None) -> list[Any]:
        """Select what a main office's payments cleared on its branches.

        One allocation of a payment to a bill of another supplier -- which
        only a main office's payment to a branch's bill can be -- is two
        lines: the branch owes less, and the main office's payment counts
        for less on its own account. A reversed payment adds the opposite
        pair, dated by the journal that reversed it.
        """
        selects: list[Any] = []
        mirror = JournalEntry.__table__.alias("reversal_journal")
        for bill, bill_column, numbered in (
            (
                PurchaseInvoice,
                SettlementAllocation.purchase_invoice_id,
                PurchaseInvoice.invoice_number,
            ),
            (
                VendorOpeningBill,
                SettlementAllocation.vendor_opening_bill_id,
                VendorOpeningBill.bill_number,
            ),
        ):
            for undone in (False, True):
                for on_branch in (True, False):
                    owner = bill.vendor_id if on_branch else Settlement.vendor_id
                    # The branch is debited and the main office credited;
                    # the pair that undoes it is the other way round.
                    debit_side = on_branch != undone
                    amount = SettlementAllocation.amount
                    nothing = literal(0)
                    statement = (
                        select(
                            owner.label("vendor_id"),
                            (
                                mirror.c.journal_date
                                if undone
                                else func.coalesce(
                                    SettlementAllocation.allocated_on,
                                    Settlement.settlement_date,
                                )
                            ).label("journal_date"),
                            (
                                mirror.c.created_at
                                if undone
                                else SettlementAllocation.created_at
                            ).label("created_at"),
                            (
                                mirror.c.id if undone else Settlement.journal_entry_id
                            ).label("entry_id"),
                            cast(Settlement.settlement_number, String(80)).label(
                                "reference_number"
                            ),
                            (
                                literal(
                                    "Paid by the main office, bill "
                                    if on_branch
                                    else "Paid for a branch, bill "
                                )
                                + cast(numbered, String(120))
                            ).label("description"),
                            literal(_TRANSFER).label("source_module"),
                            (mirror.c.id if undone else cast(null(), UUIDType())).label(
                                "reversal_of_id"
                            ),
                            (amount if debit_side else nothing).label("debit"),
                            (nothing if debit_side else amount).label("credit"),
                            cast(null(), String(80)).label("party_reference"),
                        )
                        .select_from(SettlementAllocation)
                        .join(
                            Settlement,
                            Settlement.id == SettlementAllocation.settlement_id,
                        )
                        .join(bill, bill.id == bill_column)
                        .where(
                            SettlementAllocation.firm_id == firm_id,
                            SettlementAllocation.is_deleted.is_(False),
                            Settlement.direction == SettlementDirection.PAYMENT.value,
                            Settlement.vendor_id.is_not(None),
                            bill.vendor_id != Settlement.vendor_id,
                        )
                    )
                    if undone:
                        statement = statement.join(
                            mirror, mirror.c.id == Settlement.reversal_journal_entry_id
                        ).where(Settlement.status == SettlementStatus.REVERSED.value)
                    if vendor_id is not None:
                        statement = statement.where(owner == vendor_id)
                    selects.append(statement)
        return selects

    def statement(
        self,
        vendor_id: UUID,
        *,
        firm_scope: UUID,
        from_date: date,
        to_date: date,
    ) -> SupplierStatement:
        """Return one supplier's account movement over a period.

        The opening balance is **summed from every payables line before the
        period**, the same arithmetic as the closing one, so the two cannot
        drift; the lines are then read in the order they are dated.

        Raises:
            ValidationError: If the period runs backwards.
            ResourceNotFoundError: If the supplier is not this firm's.

        """
        if to_date < from_date:
            raise ValidationError("to_date cannot be before from_date.")
        vendor = self._vendor(vendor_id, firm_scope=firm_scope)
        account_id = self._payables_account(firm_scope)
        opening = ZERO
        rows: list[Any] = []
        if account_id is not None:
            movements = self._movements(firm_scope, account_id, vendor_id).subquery()
            opening = quantize_ledger(
                Decimal(
                    str(
                        self._session.scalar(
                            select(
                                func.coalesce(
                                    func.sum(movements.c.credit - movements.c.debit), 0
                                )
                            ).where(movements.c.journal_date < from_date)
                        )
                        or 0
                    )
                )
            )
            rows = list(
                self._session.execute(
                    select(movements).where(
                        movements.c.journal_date >= from_date,
                        movements.c.journal_date <= to_date,
                    )
                    # Date first, then the order they were written: two
                    # things on one day have no other order, and the id is
                    # stable where a timestamp would tie.
                    .order_by(
                        movements.c.journal_date.asc(),
                        movements.c.created_at.asc(),
                        movements.c.entry_id.asc(),
                    )
                ).all()
            )
        running = opening
        total_debit = ZERO
        total_credit = ZERO
        lines: list[SupplierStatementLine] = []
        for row in rows:
            debit = quantize_ledger(Decimal(str(row.debit)))
            credit = quantize_ledger(Decimal(str(row.credit)))
            running += credit - debit
            total_debit += debit
            total_credit += credit
            label = _LINE_TYPES.get(row.source_module, "OTHER")
            if row.reversal_of_id is not None:
                label = f"{label}_REVERSAL"
            lines.append(
                SupplierStatementLine(
                    transaction_date=row.journal_date,
                    transaction_type=label,
                    reference_number=row.reference_number,
                    remarks=(
                        f"{row.description} -- supplier's credit note "
                        f"{row.party_reference}"
                        if row.party_reference
                        else row.description
                    ),
                    debit=debit,
                    credit=credit,
                    balance=quantize_ledger(running),
                )
            )
        return SupplierStatement(
            vendor_id=vendor.id,
            vendor_code=vendor.code,
            vendor_name=vendor.display_name or vendor.name,
            from_date=from_date,
            to_date=to_date,
            opening_balance=opening,
            closing_balance=quantize_ledger(running),
            total_debit=total_debit,
            total_credit=total_credit,
            lines=lines,
        )

    def balances(
        self, *, firm_scope: UUID, as_of: date, vendor_id: UUID | None = None
    ) -> dict[UUID, Decimal]:
        """Return what the firm owed each supplier at the end of a day.

        Grouped in SQL across every supplier at once. A supplier whose
        account nets to nothing is left out.
        """
        account_id = self._payables_account(firm_scope)
        if account_id is None:
            return {}
        movements = self._movements(firm_scope, account_id, vendor_id).subquery()
        answer: dict[UUID, Decimal] = {}
        for owner, total in self._session.execute(
            select(
                movements.c.vendor_id,
                func.sum(movements.c.credit - movements.c.debit),
            )
            .where(movements.c.journal_date <= as_of)
            .group_by(movements.c.vendor_id)
        ).all():
            value = quantize_ledger(Decimal(str(total or 0)))
            if value != ZERO:
                answer[owner] = value
        return answer

    def _vendor(self, vendor_id: UUID, *, firm_scope: UUID) -> Vendor:
        """Return one of this firm's suppliers."""
        row = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_scope,
                Vendor.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Supplier not found.")
        return row


__all__ = ["SUPPLIER_SOURCES", "SupplierStatementService"]
