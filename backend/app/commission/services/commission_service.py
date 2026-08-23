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

from app.commission.models import CommissionRule, CommissionRuleStatus
from app.commission.schemas import (
    CommissionReport,
    CommissionRuleCreate,
    CommissionRuleResponse,
    CommissionRuleStatusEnum,
    CommissionRuleUpdate,
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
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._assert_window_is_free(row)
        self._session.add(row)
        self._session.flush()
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

    @staticmethod
    def _snapshot(row: CommissionRule) -> dict[str, object]:
        """Describe a rule for the audit trail."""
        return {
            "salesman_id": str(row.salesman_id) if row.salesman_id else None,
            "percentage": str(row.percentage),
            "effective_from": row.effective_from.isoformat(),
            "effective_to": (
                row.effective_to.isoformat() if row.effective_to else None
            ),
            "status": row.status,
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
        collected: dict[UUID | None, Decimal] = {}
        earned: dict[UUID | None, Decimal] = {}
        invoices: dict[UUID | None, set[UUID]] = {}
        for owner, invoice_id, when, amount in self._collections(
            firm_id=firm_id,
            from_date=from_date,
            to_date=to_date,
            salesman_id=salesman_id,
        ):
            rate = self._rate_for(owner, when, rules)
            collected[owner] = collected.get(owner, ZERO) + amount
            earned[owner] = earned.get(owner, ZERO) + amount * rate / HUNDRED
            invoices.setdefault(owner, set()).add(invoice_id)

        names = self.names_for(firm_id)
        rows = [
            SalesmanCommissionRecord(
                salesman_id=owner,
                salesman_name=(
                    UNASSIGNED_LABEL if owner is None else self._name_of(owner, names)
                ),
                collected_amount=quantize_ledger(collected[owner]),
                commission_amount=quantize_ledger(earned[owner]),
                invoice_count=len(invoices[owner]),
            )
            for owner in collected
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
    def _rate_for(
        salesman_id: UUID | None, when: date, rules: Sequence[CommissionRule]
    ) -> Decimal:
        """Resolve the percentage in force for one person on one day.

        The person's own rule beats the firm-wide default, which beats nothing
        at all -- a firm that has declared no rate has not agreed to pay one,
        so the answer is zero rather than a refusal, and the report still shows
        what was collected.
        """
        default: Decimal | None = None
        for rule in rules:
            if rule.effective_from > when:
                continue
            if rule.effective_to is not None and rule.effective_to < when:
                continue
            if salesman_id is not None and rule.salesman_id == salesman_id:
                return Decimal(str(rule.percentage))
            if rule.salesman_id is None and default is None:
                default = Decimal(str(rule.percentage))
        return default if default is not None else ZERO
