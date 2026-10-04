"""Restate open foreign-currency payables at a period end (PG-12 part A).

A bill from a supplier abroad is carried in rupees at the rate it was booked
at. At a period end the firm may restate what is still owed at the day's
rate, so the balance sheet shows today's rupees: the difference is an
**unrealised** gain or loss, posted against payables and reversed the next
day -- the convention Tally and ERPNext both follow. Nothing is stored on the
bills or the allocations, so the payment still settles against the bill's own
rate and realises the whole difference then.

Minimal by design: what each bill owes is read as it stands now, among bills
dated on or before the period end, and one net journal is posted for all of
them. A revaluation is refused for a day that already has one.
"""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO
from app.finance.currency import to_base
from app.finance.models import JournalEntry
from app.finance.schemas.fx_revaluation import (
    FxRevaluationLine,
    FxRevaluationRequest,
    FxRevaluationResponse,
)
from app.finance.services.document_posting import DocumentPostingService


class FxRevaluationService:
    """Restate open foreign-currency payables and post the difference."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session

    def revalue(
        self, data: FxRevaluationRequest, *, firm_id: UUID, actor_id: UUID
    ) -> FxRevaluationResponse:
        """Restate every open bill in a named currency and post the net.

        Raises:
            ValidationError: If the day was already revalued, or the posting
                is refused (accounts, open periods).

        """
        # Imported here: the settlements services read the finance services.
        from app.settlements.services import PaymentService

        reference = f"FXREV-{data.as_of:%Y%m%d}"
        taken = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.reference_number == reference,
                JournalEntry.is_deleted.is_(False),
            )
        )
        if taken is not None:
            raise ValidationError(
                f"Payables in other currencies were already revalued on "
                f"{data.as_of.isoformat()} ({reference})."
            )
        lines: list[FxRevaluationLine] = []
        for record in PaymentService(self._session).outstanding_invoices(
            firm_id=firm_id, party_id=None
        ):
            if (
                record.currency_code is None
                or record.currency_code not in data.rates
                or record.invoice_date > data.as_of
                or record.currency_outstanding is None
                or record.currency_outstanding <= ZERO
            ):
                continue
            revalued = to_base(
                record.currency_outstanding, data.rates[record.currency_code]
            )
            lines.append(
                FxRevaluationLine(
                    invoice_id=record.invoice_id,
                    invoice_number=record.invoice_number,
                    vendor_id=record.party_id,
                    currency_code=record.currency_code,
                    currency_outstanding=record.currency_outstanding,
                    carried_amount=record.outstanding_amount,
                    revalued_amount=revalued,
                    difference=revalued - record.outstanding_amount,
                )
            )
        total = sum((line.difference for line in lines), ZERO)
        response = FxRevaluationResponse(
            as_of=data.as_of,
            reference=reference,
            lines=lines,
            total_difference=total,
        )
        if total == ZERO:
            return response
        revaluation_id = uuid4()
        entry, reversal = DocumentPostingService(self._session).post_fx_revaluation(
            firm_id=firm_id,
            revaluation_id=revaluation_id,
            reference=reference,
            as_of=data.as_of,
            difference=total,
            actor_id=actor_id,
        )
        response.journal_entry_id = entry.id
        response.reversal_journal_entry_id = reversal.id
        record_audit(
            self._session,
            action="finance.fx_revaluation.posted",
            entity_type="fx_revaluation",
            entity_id=revaluation_id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "as_of": data.as_of.isoformat(),
                "rates": {code: str(rate) for code, rate in data.rates.items()},
                "bills": len(lines),
                "total_difference": str(total),
                "journal_entry_id": str(entry.id),
                "reversal_journal_entry_id": str(reversal.id),
            },
        )
        self._session.flush()
        return response
