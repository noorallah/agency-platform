"""Agree, follow and accrue a customer's turnover rebate (SG-9, backlog 87 #9).

The mirror of ``app/supplier_rebates`` (BUY-13). The turnover is derived on
every read -- the approved bills of the customer, or of the group's
customers, dated in the period, at taxable value, less the completed sales
returns and approved credit notes of the period, plus its approved debit
notes -- so an agreement can never disagree with the bills. They are the
documents and the statuses GSTR-1 counts. The highest slab reached sets the
rate on the whole turnover. Accrual snapshots the turnover, the rate and the
amount with the journal that booked them, and nothing re-reads the bills
after that. What has been settled is the sum of approved ``CUSTOMER_REBATE``
party adjustments naming the agreement.

No tax is computed or posted here (CGST Act s.15(3)): the agreement only
records whether it was made before the sales it rewards.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.pagination.reports import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.credit_note.models import CreditNote, CreditNoteStatus
from app.customer_debit_note.models import (
    CustomerDebitNote,
    CustomerDebitNoteStatus,
)
from app.customer_rebates.models import (
    CustomerRebateAgreement,
    CustomerRebateSlab,
    CustomerRebateStatus,
)
from app.customer_rebates.schemas import (
    CustomerRebateCreate,
    CustomerRebateResponse,
    CustomerRebateStatement,
    CustomerRebateStatementRow,
    CustomerRebateUpdate,
    RebateSettlementRow,
    RebateSlabResponse,
    RebateSlabWrite,
    RebateTurnoverRow,
)
from app.customers.models import Customer, CustomerGroup
from app.finance.models import JournalEntry
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.gst_returns.services.gstr_service import (
    _CREDITED_RETURN_STATUSES,
    _LIVE_INVOICE_STATUSES,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_return.billing import unbilled_taxable
from app.sales_return.models import SalesReturn

#: Bills that count towards the turnover and returns that come off it: the
#: statuses GSTR-1 declares, so the two cannot disagree about a document.
BILLED = _LIVE_INVOICE_STATUSES
RETURNED = _CREDITED_RETURN_STATUSES

#: What an accrual's journal is filed under, and found again by.
SOURCE_MODULE = "customer_rebates"

#: An agreement that still occupies its period: only a cancelled one frees it.
_LIVE = (CustomerRebateStatus.ACTIVE.value, CustomerRebateStatus.ACCRUED.value)

_GST_AGREED_BEFORE = (
    "Recorded as agreed before the sales it rewards. Under CGST Act "
    "s.15(3)(b) the firm's CA may reduce the taxable value with a GST credit "
    "note linked to the invoices, if the buyer reverses the input credit. "
    "The rebate settled here carries no tax."
)
_GST_AGREED_AFTER = (
    "Not recorded as agreed before the sales it rewards, so under CGST Act "
    "s.15(3) it is a financial credit: the taxable value and the tax charged "
    "on the invoices stand, and the rebate settled here carries no tax."
)


def rate_for(turnover: Decimal, slabs: Sequence[CustomerRebateSlab]) -> Decimal:
    """Return the rate of the highest slab the turnover reaches, or zero."""
    if turnover <= ZERO:
        return ZERO
    reached = [slab for slab in slabs if turnover >= slab.threshold]
    if not reached:
        return ZERO
    return max(reached, key=lambda slab: slab.threshold).rate_percent


@dataclass
class _Parts:
    """One customer's share of a turnover, by the kind of document."""

    invoiced: Decimal = ZERO
    returned: Decimal = ZERO
    credit_notes: Decimal = ZERO
    debit_notes: Decimal = ZERO

    @property
    def turnover(self) -> Decimal:
        """Return bills less returns and credit notes, plus debit notes."""
        return self.invoiced - self.returned - self.credit_notes + self.debit_notes


@dataclass
class _Turnover:
    """An agreement's turnover: each customer's parts."""

    by_customer: dict[UUID, _Parts] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        """Return the turnover of every customer the agreement covers."""
        return sum((parts.turnover for parts in self.by_customer.values()), ZERO)


def _number(value: Any) -> Decimal:  # noqa: ANN401
    """Read a summed column, which SQLite hands back as a float or an int."""
    return Decimal(str(value or 0))


class CustomerRebateService:
    """Keep one firm's customer rebate agreements."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_agreements(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID | None = None,
        customer_group_id: UUID | None = None,
        status: str | None = None,
        search: str | None = None,
        withdrawn: bool = True,
        window: ReportWindow = WHOLE_HISTORY,
    ) -> list[CustomerRebateAgreement]:
        """Return the firm's agreements, newest period first.

        ``window`` bounds the agreements to those whose period touches its
        dates, and pages them when it names a page. ``withdrawn`` is whether
        cancelled agreements are among them.
        """
        agreement = CustomerRebateAgreement
        statement = select(agreement).where(
            agreement.firm_id == firm_id, agreement.is_deleted.is_(False)
        )
        if customer_id is not None:
            statement = statement.where(agreement.customer_id == customer_id)
        if customer_group_id is not None:
            statement = statement.where(
                agreement.customer_group_id == customer_group_id
            )
        if status is not None:
            statement = statement.where(agreement.status == status)
        if not withdrawn:
            statement = statement.where(
                agreement.status != CustomerRebateStatus.CANCELLED.value
            )
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(
                or_(agreement.code.ilike(term), agreement.name.ilike(term))
            )
        if window.from_date is not None:
            statement = statement.where(agreement.period_to >= window.from_date)
        if window.to_date is not None:
            statement = statement.where(agreement.period_from <= window.to_date)
        return window.fetch(
            self._session,
            statement.order_by(
                agreement.period_from.desc(), agreement.code.asc(), agreement.id.asc()
            ),
        )

    def get(self, agreement_id: UUID, *, firm_id: UUID) -> CustomerRebateAgreement:
        """Return one agreement.

        Raises:
            ResourceNotFoundError: If the firm has no such agreement.

        """
        row = self._session.get(CustomerRebateAgreement, agreement_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Rebate agreement not found.")
        return row

    def responses(
        self, rows: Sequence[CustomerRebateAgreement]
    ) -> list[CustomerRebateResponse]:
        """Build the responses for a page, each table read once."""
        if not rows:
            return []
        return self._build(rows, self._turnovers([row.id for row in rows]))

    def statement(
        self, agreement_id: UUID, *, firm_id: UUID
    ) -> CustomerRebateStatement:
        """Return where one agreement stands and what it was built from."""
        # Imported here: party adjustments read this service.
        from app.party_adjustments.models import PartyAdjustment

        row = self.get(agreement_id, firm_id=firm_id)
        turnover = self._turnovers([row.id]).get(row.id, _Turnover())
        settlements = list(
            self._session.scalars(
                select(PartyAdjustment)
                .where(
                    PartyAdjustment.customer_rebate_agreement_id == row.id,
                    PartyAdjustment.is_deleted.is_(False),
                    PartyAdjustment.status.in_(("APPROVED", "CANCELLED")),
                )
                .order_by(
                    PartyAdjustment.adjustment_date.desc(),
                    PartyAdjustment.adjustment_number.desc(),
                )
            ).all()
        )
        wanted = {
            *turnover.by_customer,
            *(item.customer_id for item in settlements if item.customer_id),
        }
        names = self._customer_names(wanted)
        parts = list(turnover.by_customer.values())
        return CustomerRebateStatement(
            agreement=self._build([row], {row.id: turnover})[0],
            customers=sorted(
                (
                    RebateTurnoverRow(
                        customer_id=customer_id,
                        customer_name=names.get(customer_id),
                        invoiced=quantize_ledger(own.invoiced),
                        returned=quantize_ledger(own.returned),
                        credit_notes=quantize_ledger(own.credit_notes),
                        debit_notes=quantize_ledger(own.debit_notes),
                        turnover=quantize_ledger(own.turnover),
                    )
                    for customer_id, own in turnover.by_customer.items()
                ),
                key=lambda item: (item.customer_name or "", str(item.customer_id)),
            ),
            invoiced=quantize_ledger(sum((own.invoiced for own in parts), ZERO)),
            returned=quantize_ledger(sum((own.returned for own in parts), ZERO)),
            credit_notes=quantize_ledger(
                sum((own.credit_notes for own in parts), ZERO)
            ),
            debit_notes=quantize_ledger(sum((own.debit_notes for own in parts), ZERO)),
            turnover_today=quantize_ledger(turnover.total),
            settlements=[
                RebateSettlementRow(
                    id=item.id,
                    adjustment_number=item.adjustment_number,
                    adjustment_date=item.adjustment_date,
                    customer_id=item.customer_id,
                    customer_name=(
                        None
                        if item.customer_id is None
                        else names.get(item.customer_id)
                    ),
                    amount=quantize_ledger(item.amount),
                    status=item.status,
                )
                for item in settlements
            ],
            gst_note=(
                _GST_AGREED_BEFORE if row.agreed_before_sale else _GST_AGREED_AFTER
            ),
        )

    def statement_report(
        self, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[CustomerRebateStatementRow]:
        """Return accrued and settled per agreement whose period is in the window.

        Withdrawn agreements are left out: they owe and are owed nothing.
        """
        rows = self.list_agreements(firm_id=firm_id, withdrawn=False, window=window)
        return mapped_like(
            rows,
            [
                CustomerRebateStatementRow(
                    id=view.id,
                    code=view.code,
                    name=view.name,
                    party_name=view.customer_name or view.customer_group_name,
                    is_group=view.customer_group_id is not None,
                    period_from=view.period_from,
                    period_to=view.period_to,
                    status=view.status,
                    agreed_before_sale=view.agreed_before_sale,
                    agreed_label=(
                        "Before the sale"
                        if view.agreed_before_sale
                        else "After the sale"
                    ),
                    turnover=view.turnover,
                    rate_percent=view.rate_percent,
                    earned=view.earned,
                    accrued=view.accrued_amount or ZERO,
                    settled=view.settled,
                    balance=view.to_settle,
                )
                for view in self.responses(rows)
            ],
        )

    def settled(self, agreement_ids: Sequence[UUID]) -> dict[UUID, Decimal]:
        """Sum the approved rebate settlements naming each agreement."""
        # Imported here: party adjustments read this service.
        from app.party_adjustments.models import PartyAdjustment

        if not agreement_ids:
            return {}
        return {
            agreement_id: quantize_ledger(_number(total))
            for agreement_id, total in self._session.execute(
                select(
                    PartyAdjustment.customer_rebate_agreement_id,
                    func.coalesce(func.sum(PartyAdjustment.amount), 0),
                )
                .where(
                    PartyAdjustment.customer_rebate_agreement_id.in_(
                        list(agreement_ids)
                    ),
                    PartyAdjustment.is_deleted.is_(False),
                    PartyAdjustment.status == "APPROVED",
                )
                .group_by(PartyAdjustment.customer_rebate_agreement_id)
            ).all()
            if agreement_id is not None
        }

    def to_settle(
        self, agreement_id: UUID, *, firm_id: UUID, customer_id: UUID
    ) -> Decimal:
        """Return what an accrued rebate still has to settle.

        Raises:
            ValidationError: If it is not accrued, or does not cover the
                customer.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        if row.customer_id is not None and row.customer_id != customer_id:
            raise ValidationError("That rebate agreement is another customer's.")
        if row.customer_group_id is not None:
            customer = self._session.get(Customer, customer_id)
            if customer is None or customer.customer_group_id != row.customer_group_id:
                raise ValidationError(
                    "That rebate agreement is for a customer group this "
                    "customer is not in."
                )
        if (
            row.status != CustomerRebateStatus.ACCRUED.value
            or row.accrued_amount is None
        ):
            raise ValidationError(
                "Only an accrued rebate can be settled: accrue it once its "
                "period is over."
            )
        done = self.settled([row.id]).get(row.id, ZERO)
        return quantize_ledger(Decimal(str(row.accrued_amount)) - done)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self, data: CustomerRebateCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CustomerRebateAgreement:
        """Agree a rebate; commit.

        Raises:
            ConflictError: If the code is taken.
            ValidationError: If the customer or group is not the firm's, or a
                live agreement already covers the party in the period.

        """
        self._assert_party(data.customer_id, data.customer_group_id, firm_id=firm_id)
        self._assert_code_free(data.code, firm_id=firm_id)
        self._assert_no_overlap(
            firm_id=firm_id,
            customer_id=data.customer_id,
            customer_group_id=data.customer_group_id,
            period_from=data.period_from,
            period_to=data.period_to,
            except_id=None,
        )
        row = CustomerRebateAgreement(
            firm_id=firm_id,
            customer_id=data.customer_id,
            customer_group_id=data.customer_group_id,
            code=data.code,
            name=data.name.strip(),
            period_from=data.period_from,
            period_to=data.period_to,
            agreed_before_sale=data.agreed_before_sale,
            notes=data.notes,
            status=CustomerRebateStatus.ACTIVE.value,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_slabs(row, data.slabs, actor_id=actor_id)
        self._audit("customer_rebate.created", row, actor_id)
        self._session.commit()
        return row

    def update(
        self,
        agreement_id: UUID,
        data: CustomerRebateUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CustomerRebateAgreement:
        """Change an agreement still counting; commit.

        Raises:
            ValidationError: If it is accrued or cancelled, the period would
                run backwards, or the new period meets another live agreement.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        self._assert_counting(row, doing="changed")
        values = data.model_dump(exclude_unset=True, exclude={"slabs"})
        period_from = values.get("period_from") or row.period_from
        period_to = values.get("period_to") or row.period_to
        if period_to < period_from:
            raise ValidationError("The period must not end before it starts.")
        if (period_from, period_to) != (row.period_from, row.period_to):
            self._assert_no_overlap(
                firm_id=firm_id,
                customer_id=row.customer_id,
                customer_group_id=row.customer_group_id,
                period_from=period_from,
                period_to=period_to,
                except_id=row.id,
            )
        for name, value in values.items():
            if value is None and name != "notes":
                # A null where the column cannot hold one says nothing.
                continue
            setattr(row, name, value)
        if "slabs" in data.model_fields_set and data.slabs is not None:
            self._replace_slabs(row, data.slabs, actor_id=actor_id)
        row.updated_by = actor_id
        self._audit("customer_rebate.updated", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self,
        agreement_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CustomerRebateAgreement:
        """Withdraw an agreement nothing was accrued on; commit."""
        row = self.get(agreement_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        self._assert_counting(row, doing="cancelled")
        row.status = CustomerRebateStatus.CANCELLED.value
        row.updated_by = actor_id
        self._audit("customer_rebate.cancelled", row, actor_id)
        self._session.commit()
        return row

    def accrue(
        self,
        agreement_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        accrual_date: date | None = None,
        expected_version: int | None = None,
    ) -> CustomerRebateAgreement:
        """Book what the period earned, once, after it is over; commit.

        Dated on the period's last day unless the caller names another (that
        month may be closed). The turnover, rate and amount are kept with the
        journal and never re-read.

        Raises:
            ValidationError: If the period is not over, it earned nothing, or
                it is not still counting.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        self._assert_counting(row, doing="accrued")
        today = firm_today(self._session, firm_id)
        if today <= row.period_to:
            raise ValidationError(
                f"The period runs to {row.period_to:%d %b %Y}; accrue it after "
                "that, once every bill of the period is in."
            )
        on = accrual_date or row.period_to
        if on < row.period_to:
            raise ValidationError("Accrue on or after the period's last day.")
        turnover = self._turnovers([row.id]).get(row.id, _Turnover()).total
        rate = rate_for(turnover, self._slabs([row.id]).get(row.id, []))
        amount = quantize_ledger(turnover * rate / 100)
        if amount <= ZERO:
            raise ValidationError(
                f"Sales of {quantize_ledger(turnover)} reached no slab, so "
                "there is nothing to accrue. Cancel the agreement instead."
            )
        entry = DocumentPostingService(self._session).post_customer_rebate_accrual(
            firm_id=firm_id,
            agreement_id=row.id,
            reference_number=self._accrual_reference(row),
            agreement_code=row.code,
            accrual_date=on,
            amount=amount,
            actor_id=actor_id,
        )
        row.accrued_turnover = quantize_ledger(turnover)
        row.accrued_rate = rate
        row.accrued_amount = amount
        row.accrual_journal_id = entry.id
        row.accrued_at = utc_now()
        row.accrued_by = actor_id
        row.status = CustomerRebateStatus.ACCRUED.value
        row.updated_by = actor_id
        self._audit("customer_rebate.accrued", row, actor_id)
        self._session.commit()
        return row

    def reverse_accrual(
        self,
        agreement_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CustomerRebateAgreement:
        """Take an accrual back off the books while nothing is settled; commit.

        The journal is mirrored, never deleted, and the agreement counts again
        -- a bill booked late into the period can then be counted, and the
        next accrual takes a reference of its own.

        Raises:
            ValidationError: If it is not accrued or part of it is settled.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if (
            row.status != CustomerRebateStatus.ACCRUED.value
            or row.accrual_journal_id is None
        ):
            raise ValidationError("Only an accrued rebate can be reversed.")
        if self.settled([row.id]).get(row.id, ZERO) > ZERO:
            raise ValidationError(
                "Part of this rebate is already set against the customer's "
                "account; cancel those settlements first."
            )
        journals = JournalEntryEngine(self._session)
        booked = journals.get_entry(row.accrual_journal_id, firm_id=firm_id)
        journals.reverse_entry(
            booked.id,
            firm_id=firm_id,
            reference_number=f"{booked.reference_number}-REV",
            actor_id=actor_id,
        )
        row.accrued_turnover = None
        row.accrued_rate = None
        row.accrued_amount = None
        row.accrual_journal_id = None
        row.accrued_at = None
        row.accrued_by = None
        row.status = CustomerRebateStatus.ACTIVE.value
        row.updated_by = actor_id
        self._audit("customer_rebate.accrual_reversed", row, actor_id)
        self._session.commit()
        return row

    # ------------------------------------------------------------------

    def _build(
        self,
        rows: Sequence[CustomerRebateAgreement],
        turnovers: dict[UUID, _Turnover],
    ) -> list[CustomerRebateResponse]:
        """Build each agreement's response from turnovers already read."""
        ids = [row.id for row in rows]
        slabs = self._slabs(ids)
        settled = self.settled(ids)
        names = self._customer_names(
            {row.customer_id for row in rows if row.customer_id is not None}
        )
        groups = self._group_names(
            {row.customer_group_id for row in rows if row.customer_group_id is not None}
        )
        answer: list[CustomerRebateResponse] = []
        for row in rows:
            own = slabs.get(row.id, [])
            accrued = row.status == CustomerRebateStatus.ACCRUED.value
            turnover = (
                Decimal(str(row.accrued_turnover))
                if accrued and row.accrued_turnover is not None
                else turnovers.get(row.id, _Turnover()).total
            )
            rate = (
                Decimal(str(row.accrued_rate))
                if accrued and row.accrued_rate is not None
                else rate_for(turnover, own)
            )
            earned = (
                Decimal(str(row.accrued_amount))
                if accrued and row.accrued_amount is not None
                else quantize_ledger(turnover * rate / 100)
            )
            ahead = [slab for slab in own if slab.threshold > turnover]
            following = min(ahead, key=lambda slab: slab.threshold) if ahead else None
            done = settled.get(row.id, ZERO)
            answer.append(
                CustomerRebateResponse(
                    id=row.id,
                    version=row.version,
                    customer_id=row.customer_id,
                    customer_name=(
                        None if row.customer_id is None else names.get(row.customer_id)
                    ),
                    customer_group_id=row.customer_group_id,
                    customer_group_name=(
                        None
                        if row.customer_group_id is None
                        else groups.get(row.customer_group_id)
                    ),
                    code=row.code,
                    name=row.name,
                    period_from=row.period_from,
                    period_to=row.period_to,
                    status=row.status,
                    agreed_before_sale=row.agreed_before_sale,
                    notes=row.notes,
                    slabs=[RebateSlabResponse.model_validate(slab) for slab in own],
                    turnover=quantize_ledger(turnover),
                    rate_percent=rate,
                    earned=earned,
                    next_threshold=None if following is None else following.threshold,
                    next_rate_percent=(
                        None if following is None else following.rate_percent
                    ),
                    to_next=(
                        None
                        if following is None
                        else quantize_ledger(following.threshold - turnover)
                    ),
                    accrued_amount=row.accrued_amount,
                    accrual_journal_id=row.accrual_journal_id,
                    accrued_at=row.accrued_at,
                    settled=done,
                    to_settle=(
                        quantize_ledger(Decimal(str(row.accrued_amount)) - done)
                        if accrued and row.accrued_amount is not None
                        else ZERO
                    ),
                )
            )
        return answer

    def _turnovers(self, agreement_ids: Sequence[UUID]) -> dict[UUID, _Turnover]:
        """Sum each agreement's documents by customer, one statement a kind.

        Four statements whatever the page or the period holds. A document is
        the agreement's when its customer is the one named, or is in the
        group named, and its own date falls in the period. Header figures:
        what a bill charged before tax and before rounding -- the lines, the
        freight and the charges beside them.
        """
        found: dict[UUID, _Turnover] = {}
        kinds: tuple[tuple[str, Any, Any, Any, ColumnElement[bool]], ...] = (
            (
                "invoiced",
                SalesInvoice,
                SalesInvoice.invoice_date,
                SalesInvoice.grand_total
                - SalesInvoice.tax_total
                - SalesInvoice.round_off,
                SalesInvoice.status.in_(BILLED),
            ),
            (
                "returned",
                SalesReturn,
                SalesReturn.return_date,
                # Less what came back before billing: it was never in the
                # turnover a bill made (D-SELL-55).
                SalesReturn.grand_total
                - SalesReturn.tax_total
                - SalesReturn.round_off
                - unbilled_taxable(),
                SalesReturn.status.in_(RETURNED),
            ),
            (
                "credit_notes",
                CreditNote,
                CreditNote.credit_note_date,
                CreditNote.taxable_amount,
                CreditNote.status == CreditNoteStatus.APPROVED.value,
            ),
            (
                "debit_notes",
                CustomerDebitNote,
                CustomerDebitNote.debit_note_date,
                CustomerDebitNote.taxable_amount,
                CustomerDebitNote.status == CustomerDebitNoteStatus.APPROVED.value,
            ),
        )
        for name, document, dated, amount, counted in kinds:
            for agreement_id, customer_id, total in self._summed(
                agreement_ids, document, dated, amount, counted
            ):
                parts = found.setdefault(agreement_id, _Turnover()).by_customer
                setattr(parts.setdefault(customer_id, _Parts()), name, _number(total))
        return found

    def _summed(
        self,
        agreement_ids: Sequence[UUID],
        document: Any,  # noqa: ANN401
        dated: InstrumentedAttribute[date],
        amount: ColumnElement[Decimal],
        counted: ColumnElement[bool],
    ) -> Sequence[Any]:
        """Return (agreement, customer, total) for one kind of document."""
        agreement = CustomerRebateAgreement
        return self._session.execute(
            select(agreement.id, Customer.id, func.coalesce(func.sum(amount), 0))
            .select_from(agreement)
            .join(
                Customer,
                and_(
                    Customer.firm_id == agreement.firm_id,
                    or_(
                        Customer.id == agreement.customer_id,
                        Customer.customer_group_id == agreement.customer_group_id,
                    ),
                ),
            )
            .join(
                document,
                and_(
                    document.firm_id == agreement.firm_id,
                    document.customer_id == Customer.id,
                    dated >= agreement.period_from,
                    dated <= agreement.period_to,
                    document.is_deleted.is_(False),
                    counted,
                ),
            )
            .where(agreement.id.in_(list(agreement_ids)))
            .group_by(agreement.id, Customer.id)
        ).all()

    def _slabs(
        self, agreement_ids: Sequence[UUID]
    ) -> dict[UUID, list[CustomerRebateSlab]]:
        """Return each agreement's slabs, lowest threshold first."""
        found: dict[UUID, list[CustomerRebateSlab]] = {}
        for slab in self._session.scalars(
            select(CustomerRebateSlab)
            .where(
                CustomerRebateSlab.agreement_id.in_(list(agreement_ids)),
                CustomerRebateSlab.is_deleted.is_(False),
            )
            .order_by(CustomerRebateSlab.threshold.asc())
        ).all():
            found.setdefault(slab.agreement_id, []).append(slab)
        return found

    def _replace_slabs(
        self,
        row: CustomerRebateAgreement,
        slabs: Sequence[RebateSlabWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Put a new ladder in place of the old one."""
        for old in self._slabs([row.id]).get(row.id, []):
            self._session.delete(old)
        self._session.flush()
        for number, slab in enumerate(
            sorted(slabs, key=lambda item: item.threshold), start=1
        ):
            self._session.add(
                CustomerRebateSlab(
                    agreement_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    threshold=slab.threshold,
                    rate_percent=slab.rate_percent,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def _customer_names(self, customer_ids: set[UUID]) -> dict[UUID, str]:
        """Return the name of each customer, read once."""
        if not customer_ids:
            return {}
        return {
            customer_id: name
            for customer_id, name in self._session.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
            ).all()
        }

    def _group_names(self, group_ids: set[UUID]) -> dict[UUID, str]:
        """Return the name of each customer group, read once."""
        if not group_ids:
            return {}
        return {
            group_id: name
            for group_id, name in self._session.execute(
                select(CustomerGroup.id, CustomerGroup.name).where(
                    CustomerGroup.id.in_(group_ids)
                )
            ).all()
        }

    def _assert_party(
        self,
        customer_id: UUID | None,
        customer_group_id: UUID | None,
        *,
        firm_id: UUID,
    ) -> None:
        """Refuse a customer or a group that is not one of the firm's."""
        if customer_id is not None:
            customer = self._session.get(Customer, customer_id)
            if customer is None or customer.is_deleted or customer.firm_id != firm_id:
                raise ValidationError("That customer is not one of this firm's.")
        if customer_group_id is not None:
            group = self._session.get(CustomerGroup, customer_group_id)
            if group is None or group.is_deleted or group.firm_id != firm_id:
                raise ValidationError("That customer group is not one of this firm's.")

    def _assert_code_free(self, code: str, *, firm_id: UUID) -> None:
        """Refuse a code another live agreement holds."""
        taken = self._session.scalar(
            select(CustomerRebateAgreement.id).where(
                CustomerRebateAgreement.firm_id == firm_id,
                CustomerRebateAgreement.code == code,
                CustomerRebateAgreement.is_deleted.is_(False),
            )
        )
        if taken is not None:
            raise ConflictError(f"A rebate agreement {code} already exists.")

    def _assert_no_overlap(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        customer_group_id: UUID | None,
        period_from: date,
        period_to: date,
        except_id: UUID | None,
    ) -> None:
        """Refuse a second live agreement over the same sales.

        A customer takes one rebate on a bill: not two of its own whose
        periods meet, and not one of its own beside its group's. Asked both
        ways -- a customer's agreement against its group's, and a group's
        against each member's -- on who is in the group today. An overlap is
        not a key, so this read is the guard.

        Raises:
            ValidationError: Naming the agreement, and the customer, in the way.

        """
        agreement = CustomerRebateAgreement
        meeting = (
            select(agreement)
            .where(
                agreement.firm_id == firm_id,
                agreement.is_deleted.is_(False),
                agreement.status.in_(_LIVE),
                agreement.period_from <= period_to,
                agreement.period_to >= period_from,
            )
            .order_by(agreement.period_from.asc(), agreement.code.asc())
        )
        if except_id is not None:
            meeting = meeting.where(agreement.id != except_id)
        if customer_id is not None:
            customer = self._session.get(Customer, customer_id)
            group_id = None if customer is None else customer.customer_group_id
            same = agreement.customer_id == customer_id
            clash = self._session.scalars(
                meeting.where(
                    same
                    if group_id is None
                    else or_(same, agreement.customer_group_id == group_id)
                )
            ).first()
            if clash is None:
                return
            who = "this customer" if customer is None else customer.name
            if clash.customer_group_id is not None:
                group = self._group_names({clash.customer_group_id}).get(
                    clash.customer_group_id, "its group"
                )
                raise ValidationError(
                    f"{who} is in the customer group {group}, which rebate "
                    f"agreement {clash.code} already covers from "
                    f"{clash.period_from:%d %b %Y} to {clash.period_to:%d %b %Y}."
                )
            raise ValidationError(
                f"{who} already has rebate agreement {clash.code} from "
                f"{clash.period_from:%d %b %Y} to {clash.period_to:%d %b %Y}; "
                "two cannot cover the same sales."
            )
        if customer_group_id is None:  # pragma: no cover - one party is named
            return
        named = self._group_names({customer_group_id}).get(customer_group_id, "named")
        clash = self._session.scalars(
            meeting.where(agreement.customer_group_id == customer_group_id)
        ).first()
        if clash is not None:
            raise ValidationError(
                f"The customer group {named} already has rebate agreement "
                f"{clash.code} from {clash.period_from:%d %b %Y} to "
                f"{clash.period_to:%d %b %Y}; two cannot cover the same sales."
            )
        member = self._session.execute(
            meeting.join(Customer, Customer.id == agreement.customer_id)
            .where(
                Customer.customer_group_id == customer_group_id,
                Customer.is_deleted.is_(False),
            )
            .with_only_columns(agreement.code, Customer.name)
        ).first()
        if member is not None:
            raise ValidationError(
                f"{member[1]} is in the customer group {named} and already has "
                f"rebate agreement {member[0]} of its own over these dates; "
                "cancel that one or leave the customer out of the group."
            )

    def _accrual_reference(self, row: CustomerRebateAgreement) -> str:
        """Return a journal reference no earlier accrual of this agreement took.

        A reference is unique in a firm, and an accrual that was reversed
        keeps the one it posted under, so the second accrual of an agreement
        is numbered.
        """
        earlier = self._session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.firm_id == row.firm_id,
                JournalEntry.source_module == SOURCE_MODULE,
                JournalEntry.source_id == row.id,
                JournalEntry.reversal_of_id.is_(None),
            )
        )
        base = f"CREBATE-{row.code}"
        return base if not earlier else f"{base}-{int(earlier) + 1}"

    @staticmethod
    def _assert_counting(row: CustomerRebateAgreement, *, doing: str) -> None:
        """Refuse a change to an agreement that is accrued or withdrawn."""
        if row.status != CustomerRebateStatus.ACTIVE.value:
            raise ValidationError(
                f"A rebate agreement that is {row.status.lower()} cannot be {doing}."
            )

    def _audit(self, action: str, row: CustomerRebateAgreement, actor_id: UUID) -> None:
        """Write one audit row for a change to an agreement."""
        record_audit(
            self._session,
            action=action,
            entity_type="customer_rebate_agreement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "code": row.code,
                "status": row.status,
                "period_from": row.period_from.isoformat(),
                "period_to": row.period_to.isoformat(),
                "agreed_before_sale": row.agreed_before_sale,
                "accrued_amount": (
                    None if row.accrued_amount is None else str(row.accrued_amount)
                ),
            },
        )


__all__ = ["CustomerRebateService", "rate_for"]
