"""Double-entry journal engine.

The engine owns the transition of a journal entry from draft to posted: it
validates that an entry balances, that its period accepts postings, and that
every referenced account belongs to the firm, then writes the ledger balances
and the immutable posting trail that reporting reads.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import (
    DEBIT_BALANCE_ACCOUNT_TYPES,
    AccountingPeriod,
    CostCenter,
    FinancialYear,
    GLPosting,
    JournalEntry,
    JournalLine,
    JournalStatus,
    JournalType,
    LedgerAccount,
    LedgerBalance,
    PeriodStatus,
    PostingStatus,
    ProfitCenter,
    VoucherType,
)

ZERO = Decimal("0")
MONEY = Decimal("0.01")

#: Which open period a date posts into when more than one covers it (D-FIN-6).
#: New periods can no longer overlap, but stores created before that rule may
#: hold some, and an unordered ``scalar()`` let the database pick. The most
#: specific one wins -- the latest start, then the earliest end -- and the code
#: settles a tie. Every column is NOT NULL, so no NULL ordering can decide it.
COVERING_PERIOD_ORDER = (
    AccountingPeriod.starts_on.desc(),
    AccountingPeriod.ends_on.asc(),
    AccountingPeriod.code.asc(),
)
#: What each posting module is called in a refusal, by ``source_module``. A
#: module missing here is still refused -- by its own name with the
#: underscores taken out -- so this is wording, not the rule.
SOURCE_DOCUMENT_NAMES = {
    "sales_invoice": "sales invoice",
    "sales_return": "sales return",
    "credit_note": "credit note",
    "delivery_note": "delivery note",
    "goods_receipt": "goods receipt",
    "purchase_invoice": "purchase invoice",
    "purchase_return": "purchase return",
    "settlements": "receipt, payment or refund",
    "customers": "customer's opening balance or credit note",
    "inventory": "stock adjustment or transfer",
    "physical_count": "physical count",
    "commission": "commission payout",
    "tcs": "TCS collection",
    "loyalty": "loyalty entry",
}

#: The namespace every hand-written journal's reference lives in (D-FIN-9).
#: References are unique per firm across every journal, and documents post
#: under their own numbers -- SI-, RC-, GRN-, LOY-, COMM-, a customer's -OB
#: and so on. A hand entry typed "SI-2026-2027-000004" took that invoice's
#: reference for good, and its approval then failed every time. Rather than a
#: list of every shape a document reference can take, which rots, hand
#: entries keep to "JV-" (journal voucher), and no numbering rule may use it.
MANUAL_REFERENCE_PREFIX = "JV-"


def assert_manual_reference(reference_number: str) -> None:
    """Refuse a hand journal reference outside the manual namespace."""
    if not reference_number.strip().upper().startswith(MANUAL_REFERENCE_PREFIX):
        raise ValidationError(
            f"A journal written by hand is referenced "
            f"{MANUAL_REFERENCE_PREFIX}<something> -- for example "
            f"{MANUAL_REFERENCE_PREFIX}{reference_number.strip() or '0001'}. "
            "Other references belong to the documents that post them, and one "
            "taken by hand would stop that document from ever posting."
        )


def quantize_money(value: Decimal | None) -> Decimal:
    """Round a monetary value to two decimal places."""
    if value is None:
        return ZERO
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class JournalLineData:
    """Carry one debit or credit leg into the engine."""

    ledger_account_id: UUID
    debit_amount: Decimal = field(default=ZERO)
    credit_amount: Decimal = field(default=ZERO)
    cost_center_id: UUID | None = None
    profit_center_id: UUID | None = None
    description: str | None = None


class JournalEntryEngine:
    """Create, post, and reverse double-entry journal entries."""

    def __init__(self, session: Session) -> None:
        """Bind the engine to one request unit of work."""
        self._session = session

    def create_entry(
        self,
        *,
        firm_id: UUID,
        journal_type_id: UUID,
        voucher_type_id: UUID,
        accounting_period_id: UUID,
        journal_date: date,
        reference_number: str,
        description: str | None,
        remarks: str | None = None,
        lines: list[JournalLineData],
        source_module: str | None = None,
        source_id: UUID | None = None,
        actor_id: UUID,
        inactive_centres_allowed: bool = False,
    ) -> JournalEntry:
        """Create one balanced draft journal entry.

        ``inactive_centres_allowed`` is for a reversal only: it repeats the
        centres the original carried, and undoing an entry must not depend on
        a centre still being in use.
        """
        period = self._require_open_period(accounting_period_id, firm_id=firm_id)
        if not (period.starts_on <= journal_date <= period.ends_on):
            raise ValidationError(
                "The journal date must fall inside the accounting period."
            )
        self._require_reference(
            journal_type_id, JournalType, firm_id, "Journal type not found."
        )
        self._require_reference(
            voucher_type_id, VoucherType, firm_id, "Voucher type not found."
        )
        total_debit, built = self._build_lines(
            lines,
            firm_id=firm_id,
            actor_id=actor_id,
            require_active_centres=not inactive_centres_allowed,
        )
        # Asked before the insert rather than learnt from the unique key
        # (D-FIN-9): the IntegrityError path below has to roll the session
        # back, which threw away everything else the request had done -- a
        # receipt's reserved number included, so every retry was handed the
        # same number and failed the same way.
        if self.reference_taken(reference_number, firm_id=firm_id):
            raise ConflictError(
                f"A journal entry with reference {reference_number} already " "exists."
            )
        entry = JournalEntry(
            firm_id=firm_id,
            journal_type_id=journal_type_id,
            voucher_type_id=voucher_type_id,
            accounting_period_id=accounting_period_id,
            journal_date=journal_date,
            reference_number=reference_number,
            description=description,
            remarks=remarks,
            status=JournalStatus.DRAFT.value,
            total_debit=total_debit,
            total_credit=total_debit,
            is_balanced=True,
            source_module=source_module,
            source_id=source_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        entry.lines.extend(built)
        self._session.add(entry)
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(
                "A journal entry with this reference number already exists."
            ) from error

        record_audit(
            self._session,
            action="finance.journal_entry.created",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "reference_number": entry.reference_number,
                "total_debit": str(entry.total_debit),
                "total_credit": str(entry.total_credit),
            },
        )
        return entry

    def post_entry(
        self, journal_entry_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> JournalEntry:
        """Post a draft entry to the general ledger."""
        entry = self.get_entry(journal_entry_id, firm_id=firm_id)
        if entry.status != JournalStatus.DRAFT.value:
            raise ValidationError(
                f"Only draft entries can be posted; this entry is "
                f"{entry.status.lower()}."
            )
        if not entry.is_balanced:
            raise ValidationError("An unbalanced entry cannot be posted.")
        # Re-check at posting time: the period may have closed since creation.
        self._require_open_period(entry.accounting_period_id, firm_id=firm_id)

        posted_at = utc_now()
        for line in entry.lines:
            self._post_line(
                entry, line, firm_id=firm_id, actor_id=actor_id, posted_at=posted_at
            )
        entry.status = JournalStatus.POSTED.value
        entry.posted_at = posted_at
        entry.updated_by = actor_id
        self._session.flush()

        record_audit(
            self._session,
            action="finance.journal_entry.posted",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": JournalStatus.DRAFT.value},
            after_data={"status": entry.status},
        )
        return entry

    def _hand_draft(
        self, journal_entry_id: UUID, *, firm_id: UUID, action: str
    ) -> JournalEntry:
        """Return a hand-written draft, or refuse the action by name (D-FIN-15).

        A posted entry is reversed, never edited; one a document raised
        belongs to that document.
        """
        entry = self.get_entry(journal_entry_id, firm_id=firm_id)
        if entry.status != JournalStatus.DRAFT.value:
            raise ValidationError(
                f"Only a draft can be {action}; {entry.reference_number} is "
                f"{entry.status.lower()}."
            )
        if entry.source_module is not None:
            owner = SOURCE_DOCUMENT_NAMES.get(
                entry.source_module, entry.source_module.replace("_", " ")
            )
            raise ValidationError(
                f"{entry.reference_number} was raised by a {owner} and can "
                f"only be {action} with it."
            )
        return entry

    def update_draft(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        changes: dict[str, object],
        lines: list[JournalLineData] | None = None,
    ) -> JournalEntry:
        """Edit a hand-written draft before it is posted (D-FIN-15).

        ``changes`` holds only the header fields the caller sent; ``lines``,
        when given, replaces every line. The edited draft is asked everything
        a new one is: an open period covering its date, live types, a
        balanced set of lines on accounts that accept them, and a reference
        in the manual namespace that nothing else holds.
        """
        entry = self._hand_draft(journal_entry_id, firm_id=firm_id, action="edited")
        before = self._draft_snapshot(entry)
        period_id = changes.get("accounting_period_id", entry.accounting_period_id)
        journal_date = changes.get("journal_date", entry.journal_date)
        assert isinstance(period_id, UUID)
        assert isinstance(journal_date, date)
        period = self._require_open_period(period_id, firm_id=firm_id)
        if not (period.starts_on <= journal_date <= period.ends_on):
            raise ValidationError(
                "The journal date must fall inside the accounting period."
            )
        if "journal_type_id" in changes:
            self._require_reference(
                changes["journal_type_id"],  # type: ignore[arg-type]
                JournalType,
                firm_id,
                "Journal type not found.",
            )
        if "voucher_type_id" in changes:
            self._require_reference(
                changes["voucher_type_id"],  # type: ignore[arg-type]
                VoucherType,
                firm_id,
                "Voucher type not found.",
            )
        reference = changes.get("reference_number")
        if isinstance(reference, str) and reference != entry.reference_number:
            assert_manual_reference(reference)
            if self.reference_taken(reference, firm_id=firm_id):
                raise ConflictError(
                    f"A journal entry with reference {reference} already exists."
                )
        if lines is not None:
            total, built = self._build_lines(
                lines, firm_id=firm_id, actor_id=actor_id, require_active_centres=True
            )
            # Cleared and flushed before the new lines go in: the unit of work
            # inserts before it deletes, and line numbers are unique per entry.
            entry.lines.clear()
            self._session.flush()
            entry.lines.extend(built)
            entry.total_debit = total
            entry.total_credit = total
            entry.is_balanced = True
        for name, value in changes.items():
            setattr(entry, name, value)
        entry.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="finance.journal_entry.updated",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._draft_snapshot(entry),
        )
        return entry

    def delete_draft(
        self, journal_entry_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Soft delete a hand-written draft (D-FIN-15).

        Its reference stays taken: the unique key counts deleted rows, and a
        number once issued is not handed out twice.
        """
        entry = self._hand_draft(journal_entry_id, firm_id=firm_id, action="deleted")
        entry.is_deleted = True
        entry.deleted_at = utc_now()
        entry.deleted_by = actor_id
        entry.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="finance.journal_entry.deleted",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=self._draft_snapshot(entry),
        )

    def reject_draft(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> JournalEntry:
        """Refuse a hand-written draft at review, keeping it on record (D-FIN-15).

        REJECTED was declared and never written. A rejected draft is final --
        it cannot be posted, edited or deleted -- and the reason is kept on
        the audit row and appended to its remarks.
        """
        entry = self._hand_draft(journal_entry_id, firm_id=firm_id, action="rejected")
        entry.status = JournalStatus.REJECTED.value
        if reason and reason.strip():
            note = f"Rejected: {reason.strip()}"
            entry.remarks = f"{entry.remarks}\n{note}" if entry.remarks else note
        entry.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="finance.journal_entry.rejected",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": JournalStatus.DRAFT.value},
            after_data={"status": entry.status, "reason": reason},
        )
        return entry

    @staticmethod
    def _draft_snapshot(entry: JournalEntry) -> dict[str, object]:
        """Return what an audit row says about a draft, lines included."""
        return {
            "reference_number": entry.reference_number,
            "journal_type_id": str(entry.journal_type_id),
            "voucher_type_id": str(entry.voucher_type_id),
            "accounting_period_id": str(entry.accounting_period_id),
            "journal_date": entry.journal_date.isoformat(),
            "description": entry.description,
            "remarks": entry.remarks,
            "total_debit": str(entry.total_debit),
            "total_credit": str(entry.total_credit),
            "lines": [
                {
                    "ledger_account_id": str(line.ledger_account_id),
                    "debit_amount": str(line.debit_amount),
                    "credit_amount": str(line.credit_amount),
                }
                for line in entry.lines
            ],
        }

    def reference_taken(self, reference_number: str, *, firm_id: UUID) -> bool:
        """Say whether any journal of the firm already carries a reference.

        Deleted rows count: the unique key does not exclude them.
        """
        return (
            self._session.scalar(
                select(JournalEntry.id)
                .where(
                    JournalEntry.firm_id == firm_id,
                    JournalEntry.reference_number == reference_number,
                )
                .limit(1)
            )
            is not None
        )

    def reverse_by_hand(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        reference_number: str,
        accounting_period_id: UUID | None = None,
        journal_date: date | None = None,
        actor_id: UUID,
    ) -> JournalEntry:
        """Reverse a hand-made journal from the journal screen (D-FIN-2).

        Only a journal somebody keyed in can be undone here. One a document
        posted belongs to that document: reversing it by hand left the
        invoice, receipt or return APPROVED/POSTED with its receivable and its
        stock while the ledger said it never happened, and the document's own
        cancel then found the hand mirror -- same source, POSTED -- and either
        reversed it back or collided with the ``-REV`` reference it had taken.
        The document's cancel or return is what takes its journal off, with
        everything else it moved; it calls :meth:`reverse_entry` directly.

        Raises:
            ValidationError: If the entry was posted by a document.

        """
        original = self.get_entry(journal_entry_id, firm_id=firm_id)
        if original.source_module is not None:
            owner = SOURCE_DOCUMENT_NAMES.get(
                original.source_module, original.source_module.replace("_", " ")
            )
            raise ValidationError(
                f"{original.reference_number} was posted by a {owner} and can "
                f"only be undone with it. Cancel or return the {owner} instead; "
                "that reverses this journal together with everything else the "
                "document moved."
            )
        assert_manual_reference(reference_number)
        return self.reverse_entry(
            journal_entry_id,
            firm_id=firm_id,
            reference_number=reference_number,
            accounting_period_id=accounting_period_id,
            journal_date=journal_date,
            actor_id=actor_id,
        )

    def reverse_entry(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        reference_number: str,
        accounting_period_id: UUID | None = None,
        journal_date: date | None = None,
        actor_id: UUID,
        lines: list[JournalLineData] | None = None,
    ) -> JournalEntry:
        """Create and post an entry that cancels a posted entry.

        A mirror by default: every line flipped, which is right whenever what
        is being undone is worth exactly what it was worth when it happened.

        ``lines`` is for when it is not. Cancelling a goods receipt gives the
        stock back at today's moving average, not at the price it arrived at,
        and mirroring the original there credits inventory with a number no
        movement ever removed -- which put a store 2,287.42 out in a single
        request. The caller supplies the entry it wants and keeps the rest of
        what a reversal is: the link back, the original marked REVERSED, and
        one audit row saying so.
        """
        original = self.get_entry(journal_entry_id, firm_id=firm_id)
        if original.status != JournalStatus.POSTED.value:
            raise ValidationError("Only posted entries can be reversed.")

        if accounting_period_id is not None:
            # The caller chose the period; keep the date inside it.
            target_period_id = accounting_period_id
            period = self._require_open_period(target_period_id, firm_id=firm_id)
            target_date = journal_date or period.starts_on
            if not (period.starts_on <= target_date <= period.ends_on):
                # D-FIN-15: the date was quietly moved to the period's first
                # day, so the reversal carried a date nobody chose.
                raise ValidationError(
                    f"A reversal dated {target_date.isoformat()} does not fall "
                    f"in {period.code} ({period.starts_on.isoformat()} to "
                    f"{period.ends_on.isoformat()})."
                )
        else:
            # D-BUY-4, decided by the owner on 2026-09-18: a reversal carries
            # the day it happened, in the period open on that day. It used to
            # take the first day of the *original's* period -- a receipt from
            # the 16th cancelled on the 20th reversed on the 1st, which is
            # neither date and sorts the reversal before what it undoes.
            #
            # D-FIN-5: never before the original, though. Documents carry the
            # user's local date, which runs ahead of UTC until 05:30 in India,
            # so a bill raised and cancelled in those hours reversed on the
            # day before it was raised -- on the 1st, in the previous period.
            if journal_date is not None and journal_date < original.journal_date:
                raise ValidationError(
                    f"A reversal cannot be dated {journal_date.isoformat()}, "
                    f"before {original.reference_number} itself "
                    f"({original.journal_date.isoformat()})."
                )
            target_date = journal_date or max(utc_now().date(), original.journal_date)
            open_period = self._open_period_covering(target_date, firm_id=firm_id)
            if open_period is None:
                # Nothing is open on that day -- typically a new year not yet
                # opened. Undo it on the original's own day rather than refuse
                # a cancellation the firm cannot otherwise make; a closed
                # original period is still refused below.
                target_date = original.journal_date
                open_period = self._require_open_period(
                    original.accounting_period_id, firm_id=firm_id
                )
            period = open_period
            target_period_id = period.id

        reversal_lines = lines or [
            JournalLineData(
                ledger_account_id=line.ledger_account_id,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount,
                description=f"Reversal of {original.reference_number}",
            )
            for line in original.lines
        ]
        reversal = self.create_entry(
            firm_id=firm_id,
            journal_type_id=original.journal_type_id,
            voucher_type_id=original.voucher_type_id,
            accounting_period_id=target_period_id,
            journal_date=target_date,
            reference_number=reference_number,
            description=f"Reversal of {original.reference_number}",
            lines=reversal_lines,
            source_module=original.source_module,
            source_id=original.source_id,
            actor_id=actor_id,
            inactive_centres_allowed=True,
        )
        reversal.reversal_of_id = original.id
        self.post_entry(reversal.id, firm_id=firm_id, actor_id=actor_id)

        original.status = JournalStatus.REVERSED.value
        original.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.journal_entry.reversed",
            entity_type="journal_entry",
            entity_id=original.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "status": original.status,
                "reversal_entry_id": str(reversal.id),
            },
        )
        return reversal

    def list_entries(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str | None = None,
        accounting_period_id: UUID | None = None,
        status: str | None = None,
        journal_type_id: UUID | None = None,
        source_module: str | None = None,
        descending: bool = True,
    ) -> tuple[list[JournalEntry], int]:
        """Return a page of journal entries, newest first by default.

        The module could create an entry and read one back by id, and had no
        way to find one -- so every posting the documents made was unfindable
        unless somebody already knew its id. Ordering is by journal date and
        then reference number, which is how an accountant looks for one, and
        the reference breaks the tie so two entries on one date keep a stable
        order across pages.

        Returns:
            The page and the total count, the shape `PaginatedResponse` wants.

        """
        conditions = [
            JournalEntry.firm_id == firm_id,
            JournalEntry.is_deleted.is_(False),
        ]
        if accounting_period_id is not None:
            conditions.append(JournalEntry.accounting_period_id == accounting_period_id)
        if status:
            conditions.append(JournalEntry.status == status)
        if journal_type_id is not None:
            conditions.append(JournalEntry.journal_type_id == journal_type_id)
        # The module that posted it, matched exactly -- the page could show
        # "Posted by <module>" on each row and had no way to ask for one
        # module's entries (BL-31.15).
        if source_module:
            conditions.append(JournalEntry.source_module == source_module)
        if search:
            term = f"%{search.strip()}%"
            conditions.append(
                or_(
                    JournalEntry.reference_number.ilike(term),
                    JournalEntry.description.ilike(term),
                )
            )
        # Within a date, the order entries were posted in -- not their
        # reference text. Sorting on the reference put every TCS-, SR- and
        # SO- entry of the day above an invoice's SI- entry, so the journal
        # an approval had just posted was buried (plan item 9.16, 2026-09-13).
        order = (
            (
                JournalEntry.journal_date.desc(),
                JournalEntry.created_at.desc(),
                JournalEntry.id.desc(),
            )
            if descending
            else (
                JournalEntry.journal_date.asc(),
                JournalEntry.created_at.asc(),
                JournalEntry.id.asc(),
            )
        )
        rows = list(
            self._session.scalars(
                select(JournalEntry)
                .where(*conditions)
                .order_by(*order)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = int(
            self._session.scalar(
                select(func.count()).select_from(JournalEntry).where(*conditions)
            )
            or 0
        )
        return rows, total

    def get_entry(self, journal_entry_id: UUID, *, firm_id: UUID) -> JournalEntry:
        """Return one journal entry or raise when it is unavailable."""
        entry = self._session.scalar(
            select(JournalEntry).where(
                JournalEntry.id == journal_entry_id,
                JournalEntry.firm_id == firm_id,
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry is None:
            raise ResourceNotFoundError("Journal entry not found.")
        return entry

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_lines(
        self,
        lines: list[JournalLineData],
        *,
        firm_id: UUID,
        actor_id: UUID,
        require_active_centres: bool,
    ) -> tuple[Decimal, list[JournalLine]]:
        """Validate the legs of an entry and build its lines.

        Shared by the create and the draft edit, so an edited draft is asked
        exactly what a new one is.

        Returns:
            The entry's total (debit, which equals credit) and its lines.

        """
        if len(lines) < 2:
            raise ValidationError(
                "A journal entry needs at least one debit and one credit line."
            )
        # Round each leg to the ledger's scale *before* checking the balance,
        # because these are the values that get stored. Summing first and
        # rounding after is not the same operation: a document balanced at its
        # own four decimals -- 100.0100 = 100.0050 + 0.0050 -- rounds to legs of
        # 100.01 against 100.01 + 0.01, and the old check compared the rounded
        # sums, saw 100.01 both sides, and wrote an entry whose lines were a
        # cent apart with ``is_balanced`` set to true. ``_post_line`` copies the
        # line amounts straight into the general ledger, so that cent stayed in
        # the trial balance with nothing reporting it.
        legs = [
            (
                data,
                quantize_money(data.debit_amount),
                quantize_money(data.credit_amount),
            )
            for data in lines
        ]
        total_debit = sum((debit for _, debit, _ in legs), ZERO)
        total_credit = sum((credit for _, _, credit in legs), ZERO)
        if total_debit != total_credit:
            raise ValidationError(
                f"Journal entry is not balanced: debit {total_debit}, "
                f"credit {total_credit}."
            )
        if total_debit == ZERO:
            raise ValidationError("A journal entry must carry a non-zero amount.")

        accounts = self._load_accounts(lines, firm_id=firm_id)
        self._check_centres(
            lines, firm_id=firm_id, require_active=require_active_centres
        )
        built: list[JournalLine] = []
        for index, (data, debit, credit) in enumerate(legs, start=1):
            self._validate_line_dimensions(accounts[data.ledger_account_id], data)
            built.append(
                JournalLine(
                    ledger_account_id=data.ledger_account_id,
                    cost_center_id=data.cost_center_id,
                    profit_center_id=data.profit_center_id,
                    line_number=index,
                    debit_amount=debit,
                    credit_amount=credit,
                    description=data.description,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        return total_debit, built

    def _post_line(
        self,
        entry: JournalEntry,
        line: JournalLine,
        *,
        firm_id: UUID,
        actor_id: UUID,
        posted_at: object,
    ) -> None:
        """Apply one journal line to its ledger balance and posting trail."""
        balance = self._session.scalar(
            select(LedgerBalance).where(
                LedgerBalance.ledger_account_id == line.ledger_account_id,
                LedgerBalance.accounting_period_id == entry.accounting_period_id,
            )
        )
        if balance is None:
            opening = self._opening_balance(
                line.ledger_account_id, entry.accounting_period_id, firm_id=firm_id
            )
            balance = LedgerBalance(
                firm_id=firm_id,
                ledger_account_id=line.ledger_account_id,
                accounting_period_id=entry.accounting_period_id,
                opening_balance=opening,
                period_debit=ZERO,
                period_credit=ZERO,
                closing_balance=opening,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(balance)
            self._session.flush()

        balance.period_debit = quantize_money(balance.period_debit + line.debit_amount)
        balance.period_credit = quantize_money(
            balance.period_credit + line.credit_amount
        )
        balance.closing_balance = self._closing_balance(
            line.ledger_account.account_type, balance
        )
        balance.updated_by = actor_id
        self._carry_into_later_periods(
            entry,
            line,
            firm_id=firm_id,
            actor_id=actor_id,
        )

        self._session.add(
            GLPosting(
                firm_id=firm_id,
                journal_entry_id=entry.id,
                journal_line_id=line.id,
                ledger_account_id=line.ledger_account_id,
                accounting_period_id=entry.accounting_period_id,
                posting_date=posted_at,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                status=PostingStatus.POSTED.value,
                posted_by=actor_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    def _carry_into_later_periods(
        self,
        entry: JournalEntry,
        line: JournalLine,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Move every later period's stored balance by what this line changed.

        A period's opening is copied from the previous closing once, when the
        account is first posted to in that period, and never looked at again.
        So a line dated into August after September already held a balance
        for the account moved August and left September opening where August
        used to close: every trial balance and balance sheet from September on
        disagreed with itself by that line. It happens routinely -- a bill
        dated last month cancelled today, a commission payout for an old
        month, two years of back-dated history -- and WHOLE01's September
        trial balance read 612,368.97 against 671,088.58 (manual plan item
        13.2, 2026-09-14) with every posting correct and 42 openings wrong.
        A later period's movement is its own; only its opening and closing
        move.
        """
        movement = (
            line.debit_amount - line.credit_amount
            if line.ledger_account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES
            else line.credit_amount - line.debit_amount
        )
        if movement == ZERO:
            return
        period = self._session.get(AccountingPeriod, entry.accounting_period_id)
        if period is None:
            return
        later = self._session.scalars(
            select(LedgerBalance)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.ledger_account_id == line.ledger_account_id,
                LedgerBalance.firm_id == firm_id,
                AccountingPeriod.starts_on > period.ends_on,
            )
        ).all()
        for balance in later:
            balance.opening_balance = quantize_money(balance.opening_balance + movement)
            balance.closing_balance = quantize_money(balance.closing_balance + movement)
            balance.updated_by = actor_id

    def _opening_balance(
        self, ledger_account_id: UUID, accounting_period_id: UUID, *, firm_id: UUID
    ) -> Decimal:
        """Carry the previous period's closing balance into a new period."""
        period = self._session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.id == accounting_period_id,
                AccountingPeriod.firm_id == firm_id,
            )
        )
        if period is None:
            return ZERO
        previous = self._session.scalar(
            select(LedgerBalance)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.ledger_account_id == ledger_account_id,
                LedgerBalance.firm_id == firm_id,
                AccountingPeriod.ends_on < period.starts_on,
            )
            .order_by(AccountingPeriod.ends_on.desc())
            .limit(1)
        )
        return previous.closing_balance if previous is not None else ZERO

    def _closing_balance(self, account_type: str, balance: LedgerBalance) -> Decimal:
        """Compute a closing balance using the account's normal balance side."""
        if account_type in DEBIT_BALANCE_ACCOUNT_TYPES:
            movement = balance.period_debit - balance.period_credit
        else:
            movement = balance.period_credit - balance.period_debit
        return quantize_money(balance.opening_balance + movement)

    def _open_period_covering(
        self, on: date, *, firm_id: UUID
    ) -> AccountingPeriod | None:
        """Return the open period that covers a date, if there is one."""
        return self._session.scalar(
            select(AccountingPeriod)
            .where(
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.starts_on <= on,
                AccountingPeriod.ends_on >= on,
                AccountingPeriod.status == PeriodStatus.OPEN.value,
                AccountingPeriod.is_deleted.is_(False),
            )
            .order_by(*COVERING_PERIOD_ORDER)
            .limit(1)
        )

    def _require_open_period(
        self, accounting_period_id: UUID, *, firm_id: UUID
    ) -> AccountingPeriod:
        """Return the period only when it still accepts postings."""
        period = self._session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.id == accounting_period_id,
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.is_deleted.is_(False),
            )
        )
        if period is None:
            raise ValidationError("Accounting period not found for the active firm.")
        if period.status != PeriodStatus.OPEN.value:
            raise ValidationError(
                f"Accounting period {period.code} is {period.status.lower()} "
                f"and cannot accept postings."
            )
        # An open period inside a locked year is still closed to postings: the
        # lock is the year-end close, and it was read only by the year's own
        # edit and delete, so documents went on posting into it (D-FIN-3).
        locked_year = self._session.scalar(
            select(FinancialYear.code).where(
                FinancialYear.id == period.financial_year_id,
                FinancialYear.is_locked.is_(True),
            )
        )
        if locked_year is not None:
            raise ValidationError(
                f"Accounting period {period.code} belongs to financial year "
                f"{locked_year}, which is locked, and cannot accept postings."
            )
        return period

    def _require_reference(
        self,
        entity_id: UUID,
        model: type[JournalType] | type[VoucherType],
        firm_id: UUID,
        message: str,
    ) -> None:
        """Confirm a supporting master record is the firm's and still in use.

        ``is_active`` was never read (D-FIN-15), so a type switched off went
        on taking entries.
        """
        found = self._session.execute(
            select(model.code, model.is_active).where(
                model.id == entity_id,
                model.firm_id == firm_id,
                model.is_deleted.is_(False),
            )
        ).first()
        if found is None:
            raise ValidationError(message)
        code, active = found
        if not active:
            label = "Journal type" if model is JournalType else "Voucher type"
            raise ValidationError(f"{label} {code} is inactive.")

    def _load_accounts(
        self, lines: list[JournalLineData], *, firm_id: UUID
    ) -> dict[UUID, LedgerAccount]:
        """Load and validate every ledger account referenced by the lines."""
        requested = {line.ledger_account_id for line in lines}
        accounts = {
            account.id: account
            for account in self._session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.id.in_(requested),
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.is_deleted.is_(False),
                )
            ).all()
        }
        missing = requested - accounts.keys()
        if missing:
            raise ValidationError(
                "One or more ledger accounts are unavailable for the active firm."
            )
        inactive = [a.code for a in accounts.values() if not a.is_active]
        if inactive:
            raise ValidationError(
                f"Ledger accounts are inactive: {', '.join(sorted(inactive))}."
            )
        return accounts

    def _check_centres(
        self,
        lines: list[JournalLineData],
        *,
        firm_id: UUID,
        require_active: bool,
    ) -> None:
        """Refuse a centre that is not the firm's, is deleted, or is inactive.

        D-FIN-12: only presence was checked. In the shared store another
        firm's centre was accepted onto this firm's line; in a store of its
        own an unknown id failed the foreign key, and that failure was
        reported as "A journal entry with this reference number already
        exists." -- the one message the unique key's handler knows.
        """
        costs = self._live_centres(
            CostCenter,
            {line.cost_center_id for line in lines if line.cost_center_id},
            firm_id=firm_id,
        )
        profits = self._live_centres(
            ProfitCenter,
            {line.profit_center_id for line in lines if line.profit_center_id},
            firm_id=firm_id,
        )
        for number, line in enumerate(lines, start=1):
            for centre_id, found, label in (
                (line.cost_center_id, costs, "cost centre"),
                (line.profit_center_id, profits, "profit centre"),
            ):
                if centre_id is None:
                    continue
                known = found.get(centre_id)
                if known is None:
                    raise ValidationError(f"Unknown {label} on line {number}.")
                code, active = known
                if require_active and not active:
                    raise ValidationError(
                        f"The {label} {code} on line {number} is inactive."
                    )

    def _live_centres(
        self,
        model: type[CostCenter] | type[ProfitCenter],
        wanted: set[UUID],
        *,
        firm_id: UUID,
    ) -> dict[UUID, tuple[str, bool]]:
        """Return the firm's live centres among ``wanted``: code and active."""
        if not wanted:
            return {}
        return {
            centre_id: (code, bool(active))
            for centre_id, code, active in self._session.execute(
                select(model.id, model.code, model.is_active).where(
                    model.id.in_(wanted),
                    model.firm_id == firm_id,
                    model.is_deleted.is_(False),
                )
            ).all()
        }

    def _validate_line_dimensions(
        self, account: LedgerAccount, data: JournalLineData
    ) -> None:
        """Enforce the cost and profit centre requirements of an account."""
        if account.requires_cost_center and data.cost_center_id is None:
            raise ValidationError(
                f"Ledger account {account.code} requires a cost centre."
            )
        if account.requires_profit_center and data.profit_center_id is None:
            raise ValidationError(
                f"Ledger account {account.code} requires a profit centre."
            )
