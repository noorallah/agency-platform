"""Commission rules, and what a period of collections earned.

The report is built from `settlement_allocations`, not from invoices: an
allocation is the only record of an invoice actually being paid, and its
settlement is the only place that says the payment was later taken back.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.commission.models import (
    CommissionBasis,
    CommissionRule,
    CommissionRuleSlab,
    CommissionRuleStatus,
    CommissionSlabMode,
)
from app.commission.schemas import (
    CommissionBasisEnum,
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
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.sales_invoice.models import SalesInvoice
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


class CommissionService:
    """Maintain commission rules and report what collections earned."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._members = FirmMetadataReader(session)

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
            created_by=actor_id,
            updated_by=actor_id,
        )
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
        if data.slabs is not None:
            self._replace_slabs(row, data.slabs, actor_id=actor_id)
        if row.effective_to is not None and row.effective_to < row.effective_from:
            raise ValidationError("effective_to cannot be before effective_from.")
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
        )
        if candidate.id is not None:
            statement = statement.where(CommissionRule.id != candidate.id)
        clash = self._session.scalar(statement)
        if clash is not None:
            raise ConflictError(
                "Another active rule already covers part of that period "
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

    def _earned(self, rule: CommissionRule, amount: Decimal) -> Decimal:
        """Return what one rule pays on one subtotal.

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

        Returns:
            The commission, before rounding to the ledger's two places.

        """
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
        if rule.max_commission_amount is not None:
            earned = min(earned, Decimal(str(rule.max_commission_amount)))
        return earned

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
        for owner, invoice_id, when, amount, kind in measured:
            invoices.setdefault(owner, set()).add(invoice_id)
            if kind == CommissionBasis.COLLECTED.value:
                collected[owner] = collected.get(owner, ZERO) + amount
            else:
                invoiced[owner] = invoiced.get(owner, ZERO) + amount
            rule = self._rule_for(owner, when, rules)
            # A rule pays on one basis. Money measured the other way is
            # reported and earns nothing, so a firm that moves from paying on
            # collections to paying on invoiced value pays once, not twice.
            if rule is None or rule.basis != kind:
                continue
            key = (owner, rule.id)
            under_rule[key] = under_rule.get(key, ZERO) + amount
            bases.setdefault(owner, set()).add(kind)

        earned: dict[UUID | None, Decimal] = {}
        for (owner, rule_id), subtotal in under_rule.items():
            earned[owner] = earned.get(owner, ZERO) + self._earned(
                by_id[rule_id], subtotal
            )

        names = self.names_for(firm_id)
        rows = [
            SalesmanCommissionRecord(
                salesman_id=owner,
                salesman_name=(
                    UNASSIGNED_LABEL if owner is None else self._name_of(owner, names)
                ),
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
        salesman_id: UUID | None, when: date, rules: Sequence[CommissionRule]
    ) -> CommissionRule | None:
        """Resolve the arrangement in force for one person on one day.

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
        default: CommissionRule | None = None
        for rule in rules:
            if rule.effective_from > when:
                continue
            if rule.effective_to is not None and rule.effective_to < when:
                continue
            if rule.salesman_id == salesman_id:
                return rule
            if rule.salesman_id is None and default is None:
                default = rule
        return default

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
