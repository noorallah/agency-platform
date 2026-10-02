"""What is still unfinished in a month about to close (backlog ACC-5).

Closing a month says its books are done. Before that is true, a checklist
answers what is not:

* **Draft journals** dated in the month -- written and never posted.
* **Draft documents** dated in the month -- bills, invoices, notes and
  returns raised and never approved, so nothing of them is in the books.
* **Documents with no journal** -- approved (a return: completed) with a
  value, yet no journal names them. Every posting module writes one, so a
  document without is a posting that failed or was skipped.
* **Money on account** -- receipts in the month not set against any bill.
  Often a deliberate advance, so listed and never a reason to refuse.
* **GST returns not recorded as filed** -- for each month the period covers
  that the firm traded in, a GSTR-1 not marked filed and a GSTR-3B neither
  marked filed nor settled by a GST payment. Listed and never refusing: a
  month is usually closed before its returns fall due.

A firm chooses what happens (`period_close_settings.close_check`): WARN, the
default, lists and lets the month close; BLOCK refuses while any of the first
three stands. Tally and Zoho close a period with no such list; ERPNext's
period closing voucher refuses on drafts -- which is the BLOCK choice, kept
optional because a one-person firm closing late should not be stopped by a
draft it has decided to leave.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry, JournalStatus, PeriodCloseSettings

#: The two policies a firm may choose.
CLOSE_CHECKS = ("WARN", "BLOCK")
#: What a firm with no row gets.
DEFAULT_CLOSE_CHECK = "WARN"
#: How many document numbers an item names before saying "and N more".
EXAMPLES = 5


@dataclass(frozen=True)
class CloseCheckItem:
    """One kind of unfinished work, with how much of it there is."""

    code: str
    label: str
    count: int
    #: Whether this item refuses the close under BLOCK.
    blocks: bool
    examples: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CloseCheckResult:
    """The checklist for one period."""

    close_check: str
    items: list[CloseCheckItem]

    @property
    def blocking(self) -> list[CloseCheckItem]:
        """Return the items that refuse the close under BLOCK."""
        return [item for item in self.items if item.blocks]

    @property
    def refuses(self) -> bool:
        """Whether closing is refused under the firm's policy."""
        return self.close_check == "BLOCK" and bool(self.blocking)


def _documents() -> list[tuple[str, Any, Any, Any, tuple[str, ...], Any, str]]:
    """Return each posting document: label, model, number, date, posted, total.

    Imported here: these are domains finance otherwise does not depend on.
    """
    from app.credit_note.models import CreditNote
    from app.customer_debit_note.models import CustomerDebitNote
    from app.debit_note.models import DebitNote
    from app.purchase_invoice.models import PurchaseInvoice
    from app.purchase_return.models import PurchaseReturn
    from app.sales_invoice.models import SalesInvoice
    from app.sales_return.models import SalesReturn

    return [
        (
            "Sales invoice",
            SalesInvoice,
            SalesInvoice.invoice_number,
            SalesInvoice.invoice_date,
            ("APPROVED", "CLOSED"),
            SalesInvoice.grand_total,
            "sales_invoice",
        ),
        (
            "Purchase invoice",
            PurchaseInvoice,
            PurchaseInvoice.invoice_number,
            PurchaseInvoice.invoice_date,
            ("APPROVED", "CLOSED"),
            PurchaseInvoice.grand_total,
            "purchase_invoice",
        ),
        (
            "Credit note",
            CreditNote,
            CreditNote.credit_note_number,
            CreditNote.credit_note_date,
            ("APPROVED",),
            CreditNote.total_amount,
            "credit_note",
        ),
        (
            "Debit note to a customer",
            CustomerDebitNote,
            CustomerDebitNote.debit_note_number,
            CustomerDebitNote.debit_note_date,
            ("APPROVED",),
            CustomerDebitNote.total_amount,
            "customer_debit_note",
        ),
        (
            "Debit note to a supplier",
            DebitNote,
            DebitNote.debit_note_number,
            DebitNote.debit_note_date,
            ("APPROVED",),
            DebitNote.total_amount,
            "debit_note",
        ),
        (
            "Sales return",
            SalesReturn,
            SalesReturn.return_number,
            SalesReturn.return_date,
            ("COMPLETED", "CLOSED"),
            SalesReturn.grand_total,
            "sales_return",
        ),
        (
            "Purchase return",
            PurchaseReturn,
            PurchaseReturn.return_number,
            PurchaseReturn.return_date,
            ("COMPLETED", "CLOSED"),
            PurchaseReturn.grand_total,
            "purchase_return",
        ),
    ]


class PeriodCloseChecks:
    """Answer what is unfinished in a firm's month, and its policy on it."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    # ---- policy ---------------------------------------------------------

    def close_check(self, firm_id: UUID) -> str:
        """Return the firm's policy, WARN when it has never said."""
        row = self._settings(firm_id)
        return DEFAULT_CLOSE_CHECK if row is None else row.close_check

    def set_close_check(self, firm_id: UUID, value: str, *, actor_id: UUID) -> str:
        """Record the firm's policy, with the change on its audit trail.

        Raises:
            ValidationError: If ``value`` is not WARN or BLOCK.

        """
        value = value.strip().upper()
        if value not in CLOSE_CHECKS:
            raise ValidationError("Choose WARN or BLOCK.")
        row = self._settings(firm_id)
        before = None if row is None else row.close_check
        if row is None:
            row = PeriodCloseSettings(
                firm_id=firm_id, created_by=actor_id, updated_by=actor_id
            )
            self._session.add(row)
        row.close_check = value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="finance.period_close_settings.updated",
            entity_type="period_close_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"close_check": before},
            after_data={"close_check": value},
        )
        return value

    def _settings(self, firm_id: UUID) -> PeriodCloseSettings | None:
        """Return the firm's live settings row, if it has one."""
        return self._session.scalar(
            select(PeriodCloseSettings).where(
                PeriodCloseSettings.firm_id == firm_id,
                PeriodCloseSettings.is_deleted.is_(False),
            )
        )

    # ---- the checklist --------------------------------------------------

    def run(self, firm_id: UUID, starts_on: date, ends_on: date) -> CloseCheckResult:
        """Return everything unfinished between the two dates, inclusive."""
        items = [
            self._draft_journals(firm_id, starts_on, ends_on),
            self._draft_documents(firm_id, starts_on, ends_on),
            self._unposted_documents(firm_id, starts_on, ends_on),
            self._money_on_account(firm_id, starts_on, ends_on),
            self._returns_not_filed(firm_id, starts_on, ends_on),
        ]
        return CloseCheckResult(
            close_check=self.close_check(firm_id),
            items=[item for item in items if item.count],
        )

    def _draft_journals(
        self, firm_id: UUID, starts_on: date, ends_on: date
    ) -> CloseCheckItem:
        """Count journals written in the month and never posted."""
        rows = self._session.execute(
            select(JournalEntry.reference_number).where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.is_deleted.is_(False),
                JournalEntry.status == JournalStatus.DRAFT.value,
                JournalEntry.journal_date.between(starts_on, ends_on),
            )
        ).all()
        return CloseCheckItem(
            code="DRAFT_JOURNALS",
            label="Draft journals dated in the month",
            count=len(rows),
            blocks=True,
            examples=[str(row[0]) for row in rows[:EXAMPLES]],
        )

    def _draft_documents(
        self, firm_id: UUID, starts_on: date, ends_on: date
    ) -> CloseCheckItem:
        """Count documents dated in the month still in draft."""
        count = 0
        examples: list[str] = []
        for label, model, number, on, _posted, _total, _module in _documents():
            rows = self._session.execute(
                select(number).where(
                    model.firm_id == firm_id,
                    model.is_deleted.is_(False),
                    model.status == "DRAFT",
                    on.between(starts_on, ends_on),
                )
            ).all()
            count += len(rows)
            examples += [f"{label} {row[0]}" for row in rows]
        return CloseCheckItem(
            code="DRAFT_DOCUMENTS",
            label="Documents dated in the month still in draft",
            count=count,
            blocks=True,
            examples=examples[:EXAMPLES],
        )

    def _unposted_documents(
        self, firm_id: UUID, starts_on: date, ends_on: date
    ) -> CloseCheckItem:
        """Count approved documents with a value that no journal names."""
        count = 0
        examples: list[str] = []
        for label, model, number, on, posted, total, module in _documents():
            journal = exists().where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.source_module == module,
                JournalEntry.source_id == model.id,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
            )
            rows = self._session.execute(
                select(number).where(
                    model.firm_id == firm_id,
                    model.is_deleted.is_(False),
                    model.status.in_(posted),
                    total > 0,
                    on.between(starts_on, ends_on),
                    ~journal,
                )
            ).all()
            count += len(rows)
            examples += [f"{label} {row[0]}" for row in rows]
        return CloseCheckItem(
            code="UNPOSTED_DOCUMENTS",
            label="Approved documents with no journal",
            count=count,
            blocks=True,
            examples=examples[:EXAMPLES],
        )

    def _money_on_account(
        self, firm_id: UUID, starts_on: date, ends_on: date
    ) -> CloseCheckItem:
        """Count receipts of the month not set against any bill."""
        from app.settlements.models import Settlement

        rows = self._session.execute(
            select(Settlement.settlement_number, Settlement.unallocated_amount).where(
                Settlement.firm_id == firm_id,
                Settlement.is_deleted.is_(False),
                Settlement.direction == "RECEIPT",
                Settlement.status == "POSTED",
                Settlement.unallocated_amount > 0,
                Settlement.settlement_date.between(starts_on, ends_on),
            )
        ).all()
        return CloseCheckItem(
            code="MONEY_ON_ACCOUNT",
            label="Receipts held on account, not set against a bill",
            count=len(rows),
            blocks=False,
            examples=[
                f"{row[0]} ({Decimal(str(row[1])):.2f})" for row in rows[:EXAMPLES]
            ],
        )

    def _returns_not_filed(
        self, firm_id: UUID, starts_on: date, ends_on: date
    ) -> CloseCheckItem:
        """Name each traded month's GSTR-1 and GSTR-3B not recorded as done."""
        from app.gst_returns.models import (
            GstPayment,
            GstPaymentStatus,
            GstReturnFiling,
        )
        from app.purchase_invoice.models import PurchaseInvoice
        from app.sales_invoice.models import SalesInvoice

        months = sorted(
            {
                f"{day.year:04d}-{day.month:02d}"
                for model, on in (
                    (SalesInvoice, SalesInvoice.invoice_date),
                    (PurchaseInvoice, PurchaseInvoice.invoice_date),
                )
                for (day,) in self._session.execute(
                    select(on)
                    .where(
                        model.firm_id == firm_id,
                        model.is_deleted.is_(False),
                        on.between(starts_on, ends_on),
                    )
                    .distinct()
                ).all()
            }
        )
        if not months:
            return CloseCheckItem("GST_NOT_FILED", "", 0, False)
        filed = {
            (kind, period)
            for kind, period in self._session.execute(
                select(
                    GstReturnFiling.return_type, GstReturnFiling.return_period
                ).where(
                    GstReturnFiling.firm_id == firm_id,
                    GstReturnFiling.is_deleted.is_(False),
                    GstReturnFiling.return_period.in_(months),
                )
            ).all()
        }
        paid = set(
            self._session.scalars(
                select(GstPayment.return_period).where(
                    GstPayment.firm_id == firm_id,
                    GstPayment.is_deleted.is_(False),
                    GstPayment.status == GstPaymentStatus.POSTED.value,
                    GstPayment.return_period.in_(months),
                )
            ).all()
        )
        missing = [
            f"GSTR-1 {month}" for month in months if ("GSTR1", month) not in filed
        ] + [
            f"GSTR-3B {month}"
            for month in months
            if ("GSTR3B", month) not in filed and month not in paid
        ]
        return CloseCheckItem(
            code="GST_NOT_FILED",
            label="GST returns not recorded as filed",
            count=len(missing),
            blocks=False,
            examples=missing[:EXAMPLES],
        )


def refuse_if_blocked(result: CloseCheckResult, period_code: str) -> None:
    """Refuse a close the firm's BLOCK policy forbids, naming what stands.

    Raises:
        ValidationError: Listing each blocking item and its count.

    """
    if not result.refuses:
        return
    standing = "; ".join(
        f"{item.label.lower()}: {item.count}"
        + (f" ({', '.join(item.examples)})" if item.examples else "")
        for item in result.blocking
    )
    raise ValidationError(
        f"{period_code} cannot be closed yet -- the firm refuses a close while "
        f"work is unfinished. {standing}. Post or cancel them first, or set "
        "'Before closing a month' to warn."
    )


__all__ = [
    "CLOSE_CHECKS",
    "CloseCheckItem",
    "CloseCheckResult",
    "PeriodCloseChecks",
    "refuse_if_blocked",
]
