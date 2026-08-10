"""Decide whether a customer's credit limit permits one more document.

``credit_limit`` was recorded on every customer and enforced nowhere: sales
orders snapshotted it and no code ever compared it with what the customer owed.
This is the comparison, and the policy that decides what to do about it.

Exposure is what the customer owes net of money already received:

    outstanding - unapplied advance + the document being saved

A customer who has paid in advance is not consuming their limit with it, and
the document under consideration counts because the point is to catch the
breach before it happens rather than to report it afterwards. Approved orders
that have not been invoiced are deliberately **not** counted: that number is
truer commercially but does not match the balance the customer screen shows,
and a warning nobody can reconcile against the screen is a warning nobody
trusts.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import quantize_money
from app.customers.models import CreditControlSettings, Customer
from app.customers.schemas import (
    CreditControlSettingsResponse,
    CreditControlSettingsWrite,
    CreditEnforcement,
    CreditStatus,
    CreditStatusResponse,
)

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class CreditAssessment:
    """The numbers behind a credit decision, and the decision itself."""

    status: CreditStatus
    limit: Decimal
    exposure: Decimal
    available: Decimal
    used_percent: Decimal
    message: str | None

    @property
    def blocks(self) -> bool:
        """Whether this assessment should stop the document."""
        return self.status is CreditStatus.BREACH


DEFAULT_SETTINGS = CreditControlSettings(
    enforcement=CreditEnforcement.WARN.value,
    warn_at_percent=Decimal("80"),
    block_at_percent=Decimal("100"),
)


class CreditControlService:
    """Evaluate a customer against their firm's credit policy."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def _stored_settings(self, firm_id: UUID) -> CreditControlSettings | None:
        """Return the firm's own policy row, or nothing if it never set one."""
        return self._session.scalar(
            select(CreditControlSettings).where(
                CreditControlSettings.firm_id == firm_id,
                CreditControlSettings.is_deleted.is_(False),
            )
        )

    def settings_for(self, firm_id: UUID) -> CreditControlSettings:
        """Return the firm's policy, or the platform default.

        A firm that has never configured credit control still warns at 80%.
        Shipping this switched off would leave the field exactly as unused as
        it was before.
        """
        stored = self._stored_settings(firm_id)
        return stored if stored is not None else DEFAULT_SETTINGS

    def assess(
        self,
        customer: Customer,
        *,
        additional_amount: Decimal = _ZERO,
        settings: CreditControlSettings | None = None,
    ) -> CreditAssessment:
        """Return where this customer stands once the document is added."""
        policy = settings or self.settings_for(customer.firm_id)
        limit = quantize_money(customer.credit_limit)
        exposure = quantize_money(
            customer.current_outstanding
            - customer.unapplied_advance_balance
            + additional_amount
        )
        available = quantize_money(limit - exposure)

        # A limit of zero means "no limit set", not "no credit". Treating it as
        # a hard zero would block every customer the moment this ships.
        if limit <= _ZERO or policy.enforcement == CreditEnforcement.OFF.value:
            return CreditAssessment(
                status=CreditStatus.OK,
                limit=limit,
                exposure=exposure,
                available=available,
                used_percent=_ZERO,
                message=None,
            )

        used_percent = quantize_money(exposure / limit * Decimal("100"))
        # The numeric fields keep full money scale for the caller to compute
        # with; the message is read by a person, and "88.5664% of a 250000.0000
        # limit" is not how anyone states a credit position.
        shown_percent = used_percent.quantize(Decimal("0.1"))
        shown_limit = limit.quantize(Decimal("0.01"))
        shown_available = available.quantize(Decimal("0.01"))
        blocking = policy.enforcement == CreditEnforcement.BLOCK.value
        if blocking and used_percent >= policy.block_at_percent:
            return CreditAssessment(
                status=CreditStatus.BREACH,
                limit=limit,
                exposure=exposure,
                available=available,
                used_percent=used_percent,
                message=(
                    f"{customer.display_name} would be at {shown_percent}% of a "
                    f"{shown_limit} credit limit. Collect payment or raise the "
                    "limit before continuing."
                ),
            )
        if used_percent >= policy.warn_at_percent:
            return CreditAssessment(
                status=CreditStatus.WARNING,
                limit=limit,
                exposure=exposure,
                available=available,
                used_percent=used_percent,
                message=(
                    f"{customer.display_name} would be at {shown_percent}% of a "
                    f"{shown_limit} credit limit, leaving {shown_available} "
                    "available."
                ),
            )
        return CreditAssessment(
            status=CreditStatus.OK,
            limit=limit,
            exposure=exposure,
            available=available,
            used_percent=used_percent,
            message=None,
        )

    def settings_response(self, firm_id: UUID) -> CreditControlSettingsResponse:
        """Report the firm's policy and whether the firm actually chose it."""
        stored = self._stored_settings(firm_id)
        policy = stored if stored is not None else DEFAULT_SETTINGS
        return CreditControlSettingsResponse(
            enforcement=CreditEnforcement(policy.enforcement),
            warn_at_percent=policy.warn_at_percent,
            block_at_percent=policy.block_at_percent,
            is_configured=stored is not None,
        )

    def update_settings(
        self,
        data: CreditControlSettingsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> CreditControlSettingsResponse:
        """Replace the firm's policy, creating the row on first write.

        The policy decides whether trading stops, so the change is audited with
        the thresholds on both sides -- ``DEFAULT_SETTINGS`` is never mutated,
        it is the fallback every unconfigured firm shares.
        """
        row = self._stored_settings(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = CreditControlSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = {
                "enforcement": row.enforcement,
                "warn_at_percent": str(row.warn_at_percent),
                "block_at_percent": str(row.block_at_percent),
            }
        row.enforcement = data.enforcement.value
        row.warn_at_percent = data.warn_at_percent
        row.block_at_percent = data.block_at_percent
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="UPDATE" if before is not None else "CREATE",
            entity_type="CreditControlSettings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "enforcement": row.enforcement,
                "warn_at_percent": str(row.warn_at_percent),
                "block_at_percent": str(row.block_at_percent),
            },
        )
        self._session.commit()
        return CreditControlSettingsResponse(
            enforcement=CreditEnforcement(row.enforcement),
            warn_at_percent=row.warn_at_percent,
            block_at_percent=row.block_at_percent,
            is_configured=True,
        )

    def status_for(
        self, customer: Customer, *, additional_amount: Decimal = _ZERO
    ) -> CreditStatusResponse:
        """Answer "can this customer take one more document?" for a client.

        Reporting the thresholds alongside the verdict lets a desktop form show
        why it is warning without a second call for the policy.
        """
        policy = self.settings_for(customer.firm_id)
        assessment = self.assess(
            customer, additional_amount=additional_amount, settings=policy
        )
        return CreditStatusResponse(
            customer_id=customer.id,
            customer_name=customer.display_name,
            enforcement=CreditEnforcement(policy.enforcement),
            status=assessment.status,
            limit=assessment.limit,
            exposure=assessment.exposure,
            available=assessment.available,
            used_percent=assessment.used_percent,
            warn_at_percent=policy.warn_at_percent,
            block_at_percent=policy.block_at_percent,
            would_block=assessment.blocks,
            message=assessment.message,
        )

    def assert_within_limit(
        self, customer: Customer, *, additional_amount: Decimal = _ZERO
    ) -> CreditAssessment:
        """Raise when the firm's policy refuses the document, else report.

        The returned assessment carries the warning when there is one, so a
        caller can surface it on the document it just saved.
        """
        assessment = self.assess(customer, additional_amount=additional_amount)
        if assessment.blocks:
            raise ValidationError(assessment.message or "Credit limit exceeded.")
        return assessment
