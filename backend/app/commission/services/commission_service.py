"""Commission rules, and what a period of collections earned.

The report is built from `settlement_allocations`, not from invoices: an
allocation is the only record of an invoice actually being paid, and its
settlement is the only place that says the payment was later taken back.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.commission.models import (
    CommissionBasis,
    CommissionMeasure,
    CommissionRateType,
    CommissionRule,
    CommissionRuleSlab,
    CommissionRuleStatus,
    CommissionSlabMode,
)
from app.commission.schemas import (
    CommissionBasisEnum,
    CommissionRateTypeEnum,
    CommissionReport,
    CommissionRuleCreate,
    CommissionRuleResponse,
    CommissionRuleStatusEnum,
    CommissionRuleUpdate,
    CommissionSlabModeEnum,
    CommissionSlabResponse,
    CommissionSlabWrite,
    SalesmanCommissionRecord,
)
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.core.utils.pricing import apportion
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.products.models import Product, ProductCategory
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_targets.services import SalesTargetService
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementStatus,
)

#: What the report calls money that belongs to nobody.
UNASSIGNED_LABEL = "Unassigned"

#: What it calls a salesman who is no longer an active member of the firm.
#: Their collections still happened and still have to appear; blanking the name
#: would leave a row nobody can identify.
FORMER_MEMBER_LABEL = "Former member"

#: A hundred, as the divisor a percentage is.
HUNDRED = Decimal("100")

#: What the report calls a person whose arrangement changed mid-period.
MIXED_BASIS_LABEL = "MIXED"

#: Stands in for an absent id when reading a name out of a mapping, so an
#: optional key does not need a branch at every call site.
_NOBODY = UUID(int=0)


def _whole_document(amount: Decimal) -> "_BilledLine":
    """Stand in for an invoice whose lines cannot be read.

    A rule about the whole document should still measure money that exists,
    so an invoice with no readable lines contributes as a single unscoped
    line. Only a rule naming a product fails to match it, which is right:
    nothing here says what was sold.
    """
    return _BilledLine(
        product_id=_NOBODY, category_id=None, quantity=ZERO, share=amount
    )


@dataclass(frozen=True)
class _BilledLine:
    """One line of an invoice, as commission needs to see it.

    `share` is this line's part of the invoice's own total, not its net
    amount: the shares of an invoice sum to the invoice exactly, which is what
    keeps a scoped and an unscoped rule measuring the same money.
    """

    product_id: UUID
    category_id: UUID | None
    quantity: Decimal
    share: Decimal
    #: What the goods cost, or None where nothing recorded it. None is not
    #: zero: an invoice with no dispatch behind it costed nothing because
    #: nothing moved, and zero would say the goods were free -- which on a
    #: margin rule pays commission on the whole sale price.
    cost: Decimal | None = None
    #: What the line was billed at, before the invoice's total was
    #: apportioned onto it. The margin is measured against this rather than
    #: against `share`, which carries the header's rounding and charges and
    #: would make a margin drift by whatever those come to.
    net: Decimal = ZERO


class CommissionService:
    """Maintain commission rules and report what collections earned."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._members = FirmMetadataReader(session)
        self._names_cache: dict[UUID, str] | None = None

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[CommissionRule]], firm_id: UUID
    ) -> Select[tuple[CommissionRule]]:
        """Restrict a rule query to one firm's live rows."""
        return statement.where(
            CommissionRule.firm_id == firm_id,
            CommissionRule.is_deleted.is_(False),
        )

    def list_rules(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        salesman_id: UUID | None = None,
        status: CommissionRuleStatusEnum | None = None,
    ) -> tuple[Sequence[CommissionRule], int]:
        """Return one page of rules, newest effective window first.

        Args:
            firm_id: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            salesman_id: Restrict to one person's own rules.
            status: Restrict to rules in this state.

        Returns:
            The page of rules and the total matching count.

        """
        statement = self._scoped(select(CommissionRule), firm_id)
        if salesman_id is not None:
            statement = statement.where(CommissionRule.salesman_id == salesman_id)
        if status is not None:
            statement = statement.where(CommissionRule.status == status.value)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                CommissionRule.effective_from.desc(),
                CommissionRule.created_at.desc(),
                CommissionRule.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get_rule(self, rule_id: UUID, *, firm_id: UUID) -> CommissionRule:
        """Return one rule.

        Args:
            rule_id: The rule to read.
            firm_id: The owning firm.

        Returns:
            The rule.

        Raises:
            ResourceNotFoundError: If the firm has no such live rule.

        """
        row = self._session.scalar(
            self._scoped(select(CommissionRule), firm_id).where(
                CommissionRule.id == rule_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Commission rule not found.")
        return row

    def create_rule(
        self, data: CommissionRuleCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CommissionRule:
        """Record one commission rate.

        Args:
            data: The rate, its scope and its window.
            firm_id: The owning firm.
            actor_id: The user recording it.

        Returns:
            The stored rule.

        """
        row = CommissionRule(
            firm_id=firm_id,
            salesman_id=data.salesman_id,
            percentage=data.percentage,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            status=data.status.value,
            basis=data.basis.value,
            slab_mode=data.slab_mode.value,
            max_commission_amount=data.max_commission_amount,
            product_id=data.product_id,
            product_category_id=data.product_category_id,
            rate_type=data.rate_type.value,
            per_unit_amount=data.per_unit_amount,
            minimum_amount=data.minimum_amount,
            bonus_percentage=data.bonus_percentage,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._assert_rate_shape(row)
        self._assert_window_is_free(row)
        self._session.add(row)
        self._session.flush()
        self._replace_slabs(row, data.slabs, actor_id=actor_id)
        record_audit(
            self._session,
            action="commission.rule.created",
            entity_type="commission_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        return row

    def update_rule(
        self,
        rule_id: UUID,
        data: CommissionRuleUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CommissionRule:
        """Change part of a rule.

        The payload is dumped with ``exclude_unset``, so a field the caller did
        not mention keeps the stored value while an explicit null still clears
        `effective_to` or moves the rule to the firm-wide scope.

        Args:
            rule_id: The rule to change.
            data: The fields to change.
            firm_id: The owning firm.
            actor_id: The user making the change.
            expected_version: The version the caller last read, if any.

        Returns:
            The changed rule.

        Raises:
            ValidationError: If the resulting window closes before it opens.

        """
        row = self.get_rule(rule_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        if "salesman_id" in values:
            row.salesman_id = values["salesman_id"]
        if values.get("percentage") is not None:
            row.percentage = values["percentage"]
        if values.get("effective_from") is not None:
            row.effective_from = values["effective_from"]
        if "effective_to" in values:
            row.effective_to = values["effective_to"]
        if values.get("status") is not None:
            row.status = CommissionRuleStatusEnum(values["status"]).value
        if values.get("basis") is not None:
            row.basis = CommissionBasisEnum(values["basis"]).value
        if values.get("slab_mode") is not None:
            row.slab_mode = CommissionSlabModeEnum(values["slab_mode"]).value
        if "max_commission_amount" in values:
            row.max_commission_amount = values["max_commission_amount"]
        if "product_id" in values:
            row.product_id = values["product_id"]
        if "product_category_id" in values:
            row.product_category_id = values["product_category_id"]
        if values.get("rate_type") is not None:
            row.rate_type = CommissionRateTypeEnum(values["rate_type"]).value
        if values.get("per_unit_amount") is not None:
            row.per_unit_amount = values["per_unit_amount"]
        if "minimum_amount" in values:
            row.minimum_amount = values["minimum_amount"]
        if values.get("bonus_percentage") is not None:
            row.bonus_percentage = values["bonus_percentage"]
        if data.slabs is not None:
            self._replace_slabs(row, data.slabs, actor_id=actor_id)
        if row.effective_to is not None and row.effective_to < row.effective_from:
            raise ValidationError("effective_to cannot be before effective_from.")
        self._assert_rate_shape(row)
        self._assert_window_is_free(row)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="commission.rule.updated",
            entity_type="commission_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def delete_rule(self, rule_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Retire a rule.

        Soft, like everything else here: the rule still has to explain the
        payouts it produced while it was in force.

        Args:
            rule_id: The rule to retire.
            firm_id: The owning firm.
            actor_id: The user retiring it.

        """
        row = self.get_rule(rule_id, firm_id=firm_id)
        before = self._snapshot(row)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="commission.rule.deleted",
            entity_type="commission_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
        )

    @staticmethod
    def _assert_rate_shape(candidate: CommissionRule) -> None:
        """Refuse a rule whose rate and basis cannot mean anything together.

        A per-unit rate multiplies **quantity**, so it can only be paid on
        what was invoiced: money collected has no cases in it, and inventing a
        conversion would pay a number nobody agreed. A rule naming both a
        product and a category is two answers to one question -- the product
        is the narrower of the two, so say that and drop the other.

        Args:
            candidate: The rule about to be written.

        Raises:
            ValidationError: If the combination has no meaning.

        """
        if (
            candidate.rate_type == CommissionRateType.PER_UNIT.value
            and candidate.basis != CommissionBasis.INVOICED.value
        ):
            raise ValidationError(
                "A per-unit rate can only be paid on invoiced value: money "
                "collected has no units in it."
            )
        if (
            candidate.rate_type == CommissionRateType.PER_UNIT.value
            and candidate.product_id is None
            and candidate.product_category_id is None
        ):
            raise ValidationError(
                "Say which product or category a per-unit rate is for. A rate "
                "per unit across everything a firm sells would add cases of "
                "biscuits to litres of oil."
            )
        if candidate.product_id is not None and (
            candidate.product_category_id is not None
        ):
            raise ValidationError(
                "Name a product or a category, not both -- the product is the "
                "narrower of the two."
            )

    def _assert_window_is_free(self, candidate: CommissionRule) -> None:
        """Refuse a second live rule covering the same scope and dates.

        Two rules in force for one salesman on one day would leave the rate to
        whichever row a query happened to return first, which is the shape of
        defect that only surfaces once somebody has been underpaid. An INACTIVE
        rule resolves to nothing, so it is free to overlap.

        Args:
            candidate: The rule about to be written.

        Raises:
            ConflictError: If a live rule already covers part of the window.

        """
        if candidate.status != CommissionRuleStatus.ACTIVE.value:
            return
        # `date.max` stands in for "until further notice" on both sides, so an
        # open-ended rule is compared the same way a closed one is.
        statement = self._scoped(select(CommissionRule), candidate.firm_id).where(
            CommissionRule.status == CommissionRuleStatus.ACTIVE.value,
            CommissionRule.effective_from <= (candidate.effective_to or date.max),
            func.coalesce(CommissionRule.effective_to, date.max)
            >= candidate.effective_from,
            (
                CommissionRule.salesman_id.is_(None)
                if candidate.salesman_id is None
                else CommissionRule.salesman_id == candidate.salesman_id
            ),
            # Two rules over one person's days are fine when they are about
            # different goods: "3% on everything, 5% on the cold chain" is an
            # ordinary arrangement, and the resolution below prefers the
            # narrower of the two per line.
            (
                CommissionRule.product_id.is_(None)
                if candidate.product_id is None
                else CommissionRule.product_id == candidate.product_id
            ),
            (
                CommissionRule.product_category_id.is_(None)
                if candidate.product_category_id is None
                else CommissionRule.product_category_id == candidate.product_category_id
            ),
        )
        if candidate.id is not None:
            statement = statement.where(CommissionRule.id != candidate.id)
        clash = self._session.scalar(statement)
        if clash is not None:
            raise ConflictError(
                "Another active rule already covers part of that period for "
                "the same scope "
                f"(from {clash.effective_from.isoformat()})."
            )

    # ------------------------------------------------------------------
    # The ladder
    # ------------------------------------------------------------------

    def slabs_of(self, rule: CommissionRule) -> list[CommissionRuleSlab]:
        """Return one rule's rungs, lowest band first.

        Ordered by `from_amount` rather than by `sequence`: the bands are what
        decide which rung an amount falls in, and a sequence that disagreed
        with them would be the thing believed while the money went elsewhere.
        """
        rows = self._session.scalars(
            select(CommissionRuleSlab).where(
                CommissionRuleSlab.commission_rule_id == rule.id,
                CommissionRuleSlab.is_deleted.is_(False),
            )
        ).all()
        return sorted(rows, key=lambda slab: (slab.from_amount, slab.sequence))

    def _replace_slabs(
        self,
        rule: CommissionRule,
        slabs: Sequence[CommissionSlabWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Write a rule's ladder, replacing whatever it had.

        Replaced rather than merged, because a ladder is one arrangement: a
        rung reconciled against an old one by position would let an edit that
        removes the top band leave it in force.

        Args:
            rule: The rule the ladder belongs to.
            slabs: The rungs, in the order the caller gave them.
            actor_id: The user writing them.

        Raises:
            ValidationError: If the rungs do not form a ladder.

        """
        ordered = sorted(slabs, key=lambda slab: slab.from_amount)
        self._assert_ladder_is_whole(ordered)
        for existing in self._session.scalars(
            select(CommissionRuleSlab).where(
                CommissionRuleSlab.commission_rule_id == rule.id,
                CommissionRuleSlab.is_deleted.is_(False),
            )
        ).all():
            existing.is_deleted = True
            existing.deleted_at = utc_now()
            existing.deleted_by = actor_id
            existing.updated_by = actor_id
        for position, slab in enumerate(ordered, start=1):
            self._session.add(
                CommissionRuleSlab(
                    commission_rule_id=rule.id,
                    sequence=position,
                    from_amount=slab.from_amount,
                    to_amount=slab.to_amount,
                    percentage=slab.percentage,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    @staticmethod
    def _assert_ladder_is_whole(ordered: Sequence[CommissionSlabWrite]) -> None:
        """Refuse a ladder with a gap, an overlap or a hole at the bottom.

        A gap is an amount the rule cannot answer for and an overlap is two
        answers to one question; either turns a payout into whichever rung a
        query returned first. A ladder that does not start at zero leaves the
        first rupee uncovered, which reads as a rule that pays nothing until a
        threshold -- so if that is the arrangement, say it with a rung of zero
        percent rather than by omission.

        Args:
            ordered: The rungs, lowest band first.

        Raises:
            ValidationError: If the rungs do not meet exactly.

        """
        if not ordered:
            return
        if ordered[0].from_amount != ZERO:
            raise ValidationError(
                "The first slab must start at 0; use a 0% slab if the "
                "arrangement pays nothing below a threshold."
            )
        for lower, higher in zip(ordered, ordered[1:], strict=False):
            if lower.to_amount is None:
                raise ValidationError("Only the highest slab may be open-ended.")
            if lower.to_amount != higher.from_amount:
                raise ValidationError(
                    "Slabs must meet exactly: "
                    f"{lower.to_amount} does not continue at {higher.from_amount}."
                )

    def _earned(
        self,
        rule: CommissionRule,
        amount: Decimal,
        *,
        quantity: Decimal = ZERO,
        target_met: bool | None = None,
    ) -> Decimal:
        """Return what one rule pays on one subtotal.

        A rule with a `minimum_amount` pays **nothing at all** until the
        subtotal reaches it. That is a threshold on the arrangement, not a rung
        of a ladder: a zero-percent bottom slab would start paying from the
        first rupee once the threshold was crossed, which is a different deal
        from "no commission below ten lakh".

        A `bonus_percentage` is added only when the period's targets were met.
        `target_met` is None where the person had no target, which is not a
        failure -- it is somebody nobody set a number for -- and a bonus for
        beating a target that does not exist would pay everybody.

        A PER_UNIT rule pays its rate for every unit sold and ignores the
        money entirely -- that is what "two rupees a case" means, and it is
        why the quantity is carried here rather than folded into the amount.
        Slabs do not apply to it: a ladder of bands is a statement about
        value, and a per-unit rate is deliberately not one.

        A rule with no ladder pays its flat percentage, which is every rule
        written before slabs existed. A rule *with* one ignores that column
        entirely -- there is one answer to what a rule pays.

        MARGINAL charges each portion at its own rate; WHOLE_AMOUNT charges the
        whole subtotal at the rate of the highest rung it reaches. Both are in
        ordinary use and they pay very differently, which is why the mode is
        the firm's to declare.

        The cap is applied last, so it limits what was earned rather than what
        was sold: capping the subtotal first would push the amount down a rung
        and pay less than the ceiling the firm agreed.

        Args:
            rule: The arrangement.
            amount: What was collected or invoiced under it.
            quantity: How many units were sold under it, which is what a
                PER_UNIT rate multiplies and what a PERCENT rule ignores.
            target_met: Whether this person's targets over the period were met,
                or None if they had none.

        Returns:
            The commission, before rounding to the ledger's two places.

        """
        # The threshold is judged on what was sold, before any rate is
        # applied -- "below ten lakh" is a statement about trading, not about
        # a payout.
        if rule.minimum_amount is not None and amount < Decimal(
            str(rule.minimum_amount)
        ):
            return ZERO
        if rule.rate_type == CommissionRateType.PER_UNIT.value:
            earned = quantity * Decimal(str(rule.per_unit_amount))
            earned += self._bonus(rule, amount, target_met)
            if rule.max_commission_amount is not None:
                earned = min(earned, Decimal(str(rule.max_commission_amount)))
            return earned
        slabs = self.slabs_of(rule)
        if not slabs:
            earned = amount * Decimal(str(rule.percentage)) / HUNDRED
        elif rule.slab_mode == CommissionSlabMode.WHOLE_AMOUNT.value:
            earned = amount * self._rung_reached(slabs, amount) / HUNDRED
        else:
            earned = ZERO
            for slab in slabs:
                floor = Decimal(str(slab.from_amount))
                if amount <= floor:
                    break
                ceiling = (
                    amount
                    if slab.to_amount is None
                    else min(amount, Decimal(str(slab.to_amount)))
                )
                earned += (ceiling - floor) * Decimal(str(slab.percentage)) / HUNDRED
        earned += self._bonus(rule, amount, target_met)
        if rule.max_commission_amount is not None:
            earned = min(earned, Decimal(str(rule.max_commission_amount)))
        return earned

    @staticmethod
    def _bonus(
        rule: CommissionRule, amount: Decimal, target_met: bool | None
    ) -> Decimal:
        """Return the target bonus this rule pays on this subtotal.

        Only on a target actually met. A person with no target has nothing to
        beat, so `target_met` is None and the bonus is zero -- paying it there
        would hand a bonus to everybody the firm never set a number for, which
        is the opposite of what a target bonus is.

        The bonus is added before the cap, so a firm's ceiling still holds.
        """
        if target_met is not True or rule.bonus_percentage == ZERO:
            return ZERO
        return amount * Decimal(str(rule.bonus_percentage)) / HUNDRED

    @staticmethod
    def _rung_reached(slabs: Sequence[CommissionRuleSlab], amount: Decimal) -> Decimal:
        """Return the rate of the highest rung an amount reaches.

        The bands are half-open -- `from_amount` inclusive, `to_amount`
        exclusive -- so a subtotal landing exactly on a boundary belongs to the
        rung above it, which is the reading a firm means when it says "3% from
        100,000".
        """
        rate = ZERO
        for slab in slabs:
            if amount >= Decimal(str(slab.from_amount)):
                rate = Decimal(str(slab.percentage))
        return rate

    def _snapshot(self, row: CommissionRule) -> dict[str, object]:
        """Describe a rule for the audit trail."""
        return {
            "salesman_id": str(row.salesman_id) if row.salesman_id else None,
            "percentage": str(row.percentage),
            "effective_from": row.effective_from.isoformat(),
            "effective_to": (
                row.effective_to.isoformat() if row.effective_to else None
            ),
            "status": row.status,
            "basis": row.basis,
            "slab_mode": row.slab_mode,
            "product_id": str(row.product_id) if row.product_id else None,
            "product_category_id": (
                str(row.product_category_id) if row.product_category_id else None
            ),
            "rate_type": row.rate_type,
            "per_unit_amount": str(row.per_unit_amount),
            "minimum_amount": (
                str(row.minimum_amount) if row.minimum_amount is not None else None
            ),
            "bonus_percentage": str(row.bonus_percentage),
            "max_commission_amount": (
                str(row.max_commission_amount)
                if row.max_commission_amount is not None
                else None
            ),
            "slabs": [
                {
                    "from_amount": str(slab.from_amount),
                    "to_amount": (
                        str(slab.to_amount) if slab.to_amount is not None else None
                    ),
                    "percentage": str(slab.percentage),
                }
                for slab in self.slabs_of(row)
            ],
        }

    # ------------------------------------------------------------------
    # Responses
    # ------------------------------------------------------------------

    def names_for(self, firm_id: UUID) -> dict[UUID, str]:
        """Return the firm's people by id.

        `users` and `user_firms` are platform tables, so this goes through
        ``FirmMetadataReader``, which opens the platform store when the request
        session cannot see them.

        Args:
            firm_id: The firm whose members to name.

        Returns:
            A mapping of user id to display name.

        """
        return {
            member.user_id: member.full_name or member.email
            for member in self._members.active_members(firm_id)
        }

    def rule_response(
        self, row: CommissionRule, names: dict[UUID, str]
    ) -> CommissionRuleResponse:
        """Build the response for one rule.

        Args:
            row: The stored rule.
            names: The firm's people by id.

        Returns:
            The response model.

        """
        return CommissionRuleResponse(
            id=row.id,
            salesman_id=row.salesman_id,
            salesman_name=(
                "" if row.salesman_id is None else self._name_of(row.salesman_id, names)
            ),
            percentage=row.percentage,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            status=CommissionRuleStatusEnum(row.status),
            basis=CommissionBasisEnum(row.basis),
            slab_mode=CommissionSlabModeEnum(row.slab_mode),
            product_id=row.product_id,
            product_name=self._goods_names().get(row.product_id or _NOBODY, ""),
            product_category_id=row.product_category_id,
            product_category_name=self._goods_names().get(
                row.product_category_id or _NOBODY, ""
            ),
            rate_type=CommissionRateTypeEnum(row.rate_type),
            per_unit_amount=row.per_unit_amount,
            minimum_amount=row.minimum_amount,
            bonus_percentage=row.bonus_percentage,
            max_commission_amount=row.max_commission_amount,
            slabs=[
                CommissionSlabResponse(
                    sequence=slab.sequence,
                    from_amount=slab.from_amount,
                    to_amount=slab.to_amount,
                    percentage=slab.percentage,
                )
                for slab in self.slabs_of(row)
            ],
            version=row.version,
        )

    @staticmethod
    def _name_of(salesman_id: UUID, names: dict[UUID, str]) -> str:
        """Name a salesman, tolerating one who has left the firm."""
        return names.get(salesman_id) or FORMER_MEMBER_LABEL

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(
        self,
        *,
        firm_id: UUID,
        from_date: date,
        to_date: date,
        salesman_id: UUID | None = None,
    ) -> CommissionReport:
        """Report money collected and commission earned, by salesman.

        Collections are read from the allocations that cleared sales invoices,
        joined to the settlement that made them, so a **reversed** settlement
        contributes nothing: its allocations stay on the record to show what it
        had cleared, and `Settlement.status` is the only thing that says the
        money went back.

        Args:
            firm_id: The owning firm.
            from_date: First settlement date to include, inclusive.
            to_date: Last settlement date to include, inclusive.
            salesman_id: Report one person rather than everybody.

        Returns:
            One row per salesman, plus the Unassigned bucket when anything
            landed in it.

        Raises:
            ValidationError: If the period runs backwards.

        """
        if to_date < from_date:
            raise ValidationError("to_date cannot be before from_date.")
        rules = self._active_rules(firm_id)
        by_id = {rule.id: rule for rule in rules}
        collected: dict[UUID | None, Decimal] = {}
        invoiced: dict[UUID | None, Decimal] = {}
        invoices: dict[UUID | None, set[UUID]] = {}
        # Subtotals per person *per governing rule*, because a slab is a
        # function of the value earned under one arrangement. Resolving the
        # rule row by row keeps the existing behaviour that a rate change
        # mid-period applies from the day it took effect; grouping by it then
        # runs each window's ladder on its own subtotal, which is the only
        # reading that does not either double-count a threshold or credit one
        # arrangement with the other's volume.
        under_rule: dict[tuple[UUID | None, UUID], Decimal] = {}
        bases: dict[UUID | None, set[str]] = {}

        measured: list[tuple[UUID | None, UUID, date, Decimal, str]] = [
            (owner, invoice_id, when, amount, CommissionBasis.COLLECTED.value)
            for owner, invoice_id, when, amount in self._collections(
                firm_id=firm_id,
                from_date=from_date,
                to_date=to_date,
                salesman_id=salesman_id,
            )
        ] + [
            (owner, invoice_id, when, amount, CommissionBasis.INVOICED.value)
            for owner, invoice_id, when, amount in self._invoiced(
                firm_id=firm_id,
                from_date=from_date,
                to_date=to_date,
                salesman_id=salesman_id,
            )
        ]
        # What each invoice is made of, so a rule that names a product can be
        # resolved against the lines rather than against the whole bill.
        goods = self._lines_of({invoice_id for _, invoice_id, _, _, _ in measured})
        # Quantities are accumulated separately from money: a per-unit rate
        # multiplies cases, not rupees, and mixing the two into one subtotal
        # would make the ladder unreadable.
        under_rule_quantity: dict[tuple[UUID | None, UUID], Decimal] = {}

        for owner, invoice_id, when, amount, kind in measured:
            invoices.setdefault(owner, set()).add(invoice_id)
            if kind == CommissionBasis.COLLECTED.value:
                collected[owner] = collected.get(owner, ZERO) + amount
            else:
                invoiced[owner] = invoiced.get(owner, ZERO) + amount
            lines = goods.get(invoice_id) or [_whole_document(amount)]
            billed = sum((line.share for line in lines), ZERO)
            for line in lines:
                rule = self._rule_for(owner, when, line, rules)
                # A rule pays on one basis. Money measured the other way is
                # reported and earns nothing, so a firm that moves from paying
                # on collections to paying on invoiced value pays once, not
                # twice.
                if rule is None or rule.basis != kind:
                    continue
                key = (owner, rule.id)
                # An unscoped rule matches every line and the shares sum to
                # the invoice exactly, so it measures precisely what it
                # measured before scoping existed. A scoped one takes only
                # its lines' share -- of the bill on the invoiced basis, and
                # of each receipt in the same proportion on the collected one,
                # because a payment clears a share of every line it settles.
                portion = (
                    line.share
                    if kind == CommissionBasis.INVOICED.value
                    else (amount * line.share / billed if billed > ZERO else ZERO)
                )
                if rule.measure == CommissionMeasure.MARGIN.value:
                    margin = self._margin_of(line, portion)
                    if margin is None:
                        # Nothing recorded what these goods cost, so the
                        # margin cannot be measured. Skipped rather than
                        # treated as costing nothing, which would pay on the
                        # whole sale price as though the goods were free.
                        continue
                    portion = margin
                under_rule[key] = under_rule.get(key, ZERO) + portion
                under_rule_quantity[key] = (
                    under_rule_quantity.get(key, ZERO) + line.quantity
                )
                bases.setdefault(owner, set()).add(kind)

        # Whether each person's targets over the period were met, asked once
        # rather than per rule: a target is about the person and the window,
        # not about the arrangement they are paid under.
        met = self._targets_met(firm_id, from_date, to_date)

        earned: dict[UUID | None, Decimal] = {}
        for (owner, rule_id), subtotal in under_rule.items():
            earned[owner] = earned.get(owner, ZERO) + self._earned(
                by_id[rule_id],
                subtotal,
                quantity=under_rule_quantity.get((owner, rule_id), ZERO),
                target_met=met.get(owner),
            )

        names = self.names_for(firm_id)
        rows = [
            SalesmanCommissionRecord(
                salesman_id=owner,
                salesman_name=(
                    UNASSIGNED_LABEL if owner is None else self._name_of(owner, names)
                ),
                target_met=met.get(owner),
                collected_amount=quantize_ledger(collected.get(owner, ZERO)),
                invoiced_amount=quantize_ledger(invoiced.get(owner, ZERO)),
                basis=self._basis_label(bases.get(owner, set())),
                commission_amount=quantize_ledger(earned.get(owner, ZERO)),
                invoice_count=len(invoices[owner]),
            )
            for owner in set(collected) | set(invoiced)
        ]
        # Biggest earner first, and the bucket that belongs to nobody last
        # whatever it holds -- it is a reconciliation line, not a performer.
        rows.sort(
            key=lambda row: (
                row.salesman_id is None,
                -row.commission_amount,
                row.salesman_name,
            )
        )
        return CommissionReport(
            from_date=from_date,
            to_date=to_date,
            total_collected_amount=quantize_ledger(sum(collected.values(), ZERO)),
            total_invoiced_amount=quantize_ledger(sum(invoiced.values(), ZERO)),
            total_commission_amount=quantize_ledger(sum(earned.values(), ZERO)),
            rows=rows,
        )

    def _collections(
        self,
        *,
        firm_id: UUID,
        from_date: date,
        to_date: date,
        salesman_id: UUID | None,
    ) -> list[tuple[UUID | None, UUID, date, Decimal]]:
        """Return (salesman, invoice, settlement date, amount) for the period.

        Row-grained rather than summed in SQL because the rate depends on the
        day the money arrived: two receipts against one invoice can fall either
        side of a rate change, and a sum taken first would have to pick one of
        the two rates for both.
        """
        statement = (
            select(
                SalesInvoice.salesman_id,
                SalesInvoice.id,
                Settlement.settlement_date,
                SettlementAllocation.amount,
            )
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .join(
                SalesInvoice, SalesInvoice.id == SettlementAllocation.sales_invoice_id
            )
            .where(
                SettlementAllocation.firm_id == firm_id,
                SettlementAllocation.is_deleted.is_(False),
                SettlementAllocation.sales_invoice_id.is_not(None),
                Settlement.is_deleted.is_(False),
                Settlement.status == SettlementStatus.POSTED.value,
                Settlement.direction == SettlementDirection.RECEIPT.value,
                Settlement.settlement_date >= from_date,
                Settlement.settlement_date <= to_date,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if salesman_id is not None:
            statement = statement.where(SalesInvoice.salesman_id == salesman_id)
        return [
            (owner, invoice_id, when, Decimal(str(amount)))
            for owner, invoice_id, when, amount in self._session.execute(statement)
        ]

    def _active_rules(self, firm_id: UUID) -> list[CommissionRule]:
        """Return the firm's live rules, most recently effective first.

        Read once and resolved in Python rather than queried per allocation:
        there are a handful of rules and thousands of receipts, and ranking in
        memory also keeps the firm-wide default -- whose `salesman_id` is NULL
        -- from being chosen by a NULL sort, which orders one way on PostgreSQL
        and the other on SQLite.
        """
        rows = self._session.scalars(
            self._scoped(select(CommissionRule), firm_id).where(
                CommissionRule.status == CommissionRuleStatus.ACTIVE.value
            )
        ).all()
        return sorted(
            rows,
            key=lambda rule: (rule.effective_from, rule.created_at),
            reverse=True,
        )

    @staticmethod
    def _basis_label(seen: set[str]) -> str:
        """Name the arrangement a row was paid under.

        Empty when no rule governed anything -- the Unassigned bucket, and a
        person whose firm has declared no rate. MIXED when a rate change moved
        the arrangement mid-period, which is honest rather than picking one of
        the two and printing it over the other.
        """
        if not seen:
            return ""
        if len(seen) == 1:
            return next(iter(seen))
        return MIXED_BASIS_LABEL

    @staticmethod
    def _rule_for(
        salesman_id: UUID | None,
        when: date,
        line: "_BilledLine",
        rules: Sequence[CommissionRule],
    ) -> CommissionRule | None:
        """Resolve the arrangement in force for one person, day and line.

        Six rungs of specificity, narrowest first: the person's own rule for
        this product, then for its category, then their unscoped rule, then
        the same three firm-wide. "3% on everything, 5% on the cold chain" is
        an ordinary arrangement, and it only works if the narrower rule wins
        for the lines it names while the broader one still covers the rest.

        The person's own rule beats the firm-wide default, which beats nothing
        at all -- a firm that has declared no rate has not agreed to pay one,
        so the answer is None rather than a refusal, and the report still shows
        what was collected and what was billed.

        **Money that belongs to nobody earns nothing.** The firm-wide default
        is what a salesman with no rule of their own is paid; it is not a rate
        on collections that named no salesman, because there is nobody to pay
        it to. Reading the default there put 30.00 of commission against the
        Unassigned bucket on a seeded store where no invoice carries a
        salesman -- every rupee collected, inflating what the firm believes it
        owes by the whole default rate. The bucket keeps its collected figure
        so the collections still reconcile against the cash book; only the
        payout is zero.
        """
        if salesman_id is None:
            return None
        # Six buckets, indexed by how specific a match is. Collected in one
        # pass and chosen at the end, because the rules are already ordered by
        # date and re-sorting them per line would be the expensive way to ask
        # a cheap question.
        best: dict[int, CommissionRule] = {}
        for rule in rules:
            if rule.effective_from > when:
                continue
            if rule.effective_to is not None and rule.effective_to < when:
                continue
            if rule.salesman_id is not None and rule.salesman_id != salesman_id:
                continue
            if rule.product_id is not None and rule.product_id != line.product_id:
                continue
            if (
                rule.product_category_id is not None
                and rule.product_category_id != line.category_id
            ):
                continue
            mine = 0 if rule.salesman_id is not None else 3
            goods = (
                0
                if rule.product_id is not None
                else (1 if rule.product_category_id is not None else 2)
            )
            best.setdefault(mine + goods, rule)
        for rank in range(6):
            found = best.get(rank)
            if found is not None:
                return found
        return None

    def _targets_met(
        self, firm_id: UUID, from_date: date, to_date: date
    ) -> dict[UUID | None, bool]:
        """Say, per salesman, whether their targets over the window were met.

        **Taken together**, not one by one: a year holding twelve monthly
        targets is met when the twelve achievements add up to the twelve
        numbers. Requiring every single month would make an annual bonus
        almost impossible to earn, and requiring only one would make it
        almost impossible to miss.

        Each target is still measured over its own period and on its own
        basis -- that is `SalesTargetService`'s rule and this does not
        second-guess it; it only adds the two columns up.

        A person with no target is absent from the answer rather than False.
        Nobody set them a number, so there is nothing they failed.

        Args:
            firm_id: The owning firm.
            from_date: First day of the report window.
            to_date: Last day of it.

        Returns:
            True or False per salesman who had a target in the window.

        """
        targeted: dict[UUID | None, Decimal] = {}
        achieved: dict[UUID | None, Decimal] = {}
        for row in SalesTargetService(self._session).achievement(
            firm_scope=firm_id, from_date=from_date, to_date=to_date
        ):
            # A target naming a round rather than a person belongs to nobody
            # in particular, so it cannot decide anybody's bonus.
            if row.salesman_id is None:
                continue
            targeted[row.salesman_id] = (
                targeted.get(row.salesman_id, ZERO) + row.target_amount
            )
            achieved[row.salesman_id] = (
                achieved.get(row.salesman_id, ZERO) + row.achieved_amount
            )
        return {
            owner: achieved.get(owner, ZERO) >= total
            for owner, total in targeted.items()
        }

    @staticmethod
    def _margin_of(line: "_BilledLine", portion: Decimal) -> Decimal | None:
        """Return the margin in this portion of the line, or None if unknown.

        The cost belongs to the whole line, and `portion` may be only part of
        it -- a receipt clears a share of every line it settles. So the cost
        is scaled by the same share of the line's own value, which keeps the
        margin proportional to whatever is being measured.

        Args:
            line: The billed line, with what it cost and what it billed at.
            portion: The part of it this rule is measuring.

        Returns:
            The margin, never below zero, or None where the cost is unknown.

        Note:
            A negative margin is floored at zero rather than clawed back. A
            sale below cost earns no commission, which is what a firm means by
            paying on margin; taking money off other sales to cover it is a
            different arrangement and not one anybody asked for.

        """
        if line.cost is None:
            return None
        if line.net <= ZERO:
            return ZERO
        share = portion / line.net
        margin = portion - (line.cost * share)
        return margin if margin > ZERO else ZERO

    def _lines_of(self, invoice_ids: set[UUID]) -> dict[UUID, list["_BilledLine"]]:
        """Return what each invoice was made of, with each line's share of it.

        The share is the invoice's own `grand_total` apportioned across its
        lines in proportion to their net amounts, so **the shares of an
        invoice sum to the invoice exactly**. That is what lets an unscoped
        rule measure precisely what it measured before scoping existed: it
        matches every line, and the parts add up to the whole. Deriving the
        share from the line's net amount instead would drift from the total by
        whatever the header carries -- rounding, a bill-level charge -- and a
        commission report that does not reconcile against the invoices behind
        it is one nobody can sign off.

        `apportion` is the same helper a bill discount is split with, so the
        rounding residual lands on the largest line rather than being dropped.
        """
        if not invoice_ids:
            return {}
        rows = self._session.execute(
            select(
                SalesInvoiceLine.sales_invoice_id,
                SalesInvoiceLine.product_id,
                SalesInvoiceLine.current_invoice_quantity,
                SalesInvoiceLine.net_amount,
                Product.category_id,
                SalesInvoiceLine.cost_amount,
            )
            .join(Product, Product.id == SalesInvoiceLine.product_id, isouter=True)
            .where(
                SalesInvoiceLine.sales_invoice_id.in_(invoice_ids),
                SalesInvoiceLine.is_deleted.is_(False),
            )
        ).all()
        totals = {
            invoice_id: Decimal(str(total))
            for invoice_id, total in self._session.execute(
                select(SalesInvoice.id, SalesInvoice.grand_total).where(
                    SalesInvoice.id.in_(invoice_ids)
                )
            ).all()
        }
        grouped: dict[
            UUID, list[tuple[UUID, Decimal, Decimal, UUID | None, Decimal | None]]
        ] = {}
        for invoice_id, product_id, quantity, net, category_id, cost in rows:
            grouped.setdefault(invoice_id, []).append(
                (
                    product_id,
                    Decimal(str(quantity)),
                    Decimal(str(net)),
                    category_id,
                    None if cost is None else Decimal(str(cost)),
                )
            )
        answer: dict[UUID, list[_BilledLine]] = {}
        for invoice_id, lines in grouped.items():
            shares = apportion(
                totals.get(invoice_id, ZERO), [net for _, _, net, _, _ in lines]
            )
            answer[invoice_id] = [
                _BilledLine(
                    product_id=product_id,
                    category_id=category_id,
                    quantity=quantity,
                    share=share,
                    cost=cost,
                    net=net,
                )
                for (product_id, quantity, net, category_id, cost), share in zip(
                    lines, shares, strict=True
                )
            ]
        return answer

    def _goods_names(self) -> dict[UUID, str]:
        """Name the products and categories any rule refers to.

        Read once per service instance and cached, because a page of rules
        would otherwise ask the same two questions twenty times.
        """
        if self._names_cache is None:
            self._names_cache = {
                row_id: name
                for row_id, name in self._session.execute(
                    select(Product.id, Product.name)
                ).all()
            }
            self._names_cache.update(
                {
                    row_id: name
                    for row_id, name in self._session.execute(
                        select(ProductCategory.id, ProductCategory.name)
                    ).all()
                }
            )
        return self._names_cache

    def _invoiced(
        self,
        *,
        firm_id: UUID,
        from_date: date,
        to_date: date,
        salesman_id: UUID | None,
    ) -> list[tuple[UUID | None, UUID, date, Decimal]]:
        """Return (salesman, invoice, invoice date, value) for the period.

        Approved and closed invoices only: a draft is not a sale and a
        cancelled one is not either, which is the same test
        `app/sales_targets` applies to the same question. Row-grained for the
        reason the collections are -- the rule is resolved on the document's
        own date, so a rate change mid-period splits the period rather than
        pricing all of it one way.
        """
        statement = select(
            SalesInvoice.salesman_id,
            SalesInvoice.id,
            SalesInvoice.invoice_date,
            SalesInvoice.grand_total,
        ).where(
            SalesInvoice.firm_id == firm_id,
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_(("APPROVED", "CLOSED")),
            SalesInvoice.invoice_date >= from_date,
            SalesInvoice.invoice_date <= to_date,
        )
        if salesman_id is not None:
            statement = statement.where(SalesInvoice.salesman_id == salesman_id)
        return [
            (owner, invoice_id, when, Decimal(str(amount)))
            for owner, invoice_id, when, amount in self._session.execute(statement)
        ]
