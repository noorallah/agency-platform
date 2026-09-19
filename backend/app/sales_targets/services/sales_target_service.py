"""Set what a firm expects to sell, and report how it went.

Achievement is measured on the target's **own** basis and over the target's
**own** dates, never over a window somebody types into a report. A target for
April measured across May is not that target's achievement, and a firm running
monthly and yearly targets together would otherwise see one of them answered
against the wrong period.

Attribution is the document's own `salesman_id` -- the tag it carried when it
was raised, not the customer's current territory assignment. The same rule
`app/commission` follows, and for the same reason: what was true when the sale
happened is what it counts towards.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.money import quantize_money
from app.sales_targets.models import SalesTarget
from app.sales_targets.schemas import (
    SalesTargetAchievement,
    SalesTargetBasis,
    SalesTargetResponse,
    SalesTargetWrite,
)
from app.settlements.services.net_sales import (
    NetSale,
    collected_net,
    invoiced_net,
    sum_of,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
#: The bucket a document with nobody named falls into. Reported rather than
#: dropped, for the reason the commission report names its own: a total that
#: silently omits untagged sales cannot be reconciled against the day book.
UNASSIGNED = "Unassigned"


class SalesTargetService:
    """Manage targets and answer what was achieved against them."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def list_targets(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        salesman_id: UUID | None = None,
    ) -> tuple[list[SalesTarget], int]:
        """List a firm's targets, newest period first."""
        statement = select(SalesTarget).where(
            SalesTarget.firm_id == firm_scope, SalesTarget.is_deleted.is_(False)
        )
        count = (
            select(func.count())
            .select_from(SalesTarget)
            .where(SalesTarget.firm_id == firm_scope, SalesTarget.is_deleted.is_(False))
        )
        if salesman_id is not None:
            statement = statement.where(SalesTarget.salesman_id == salesman_id)
            count = count.where(SalesTarget.salesman_id == salesman_id)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    SalesTarget.period_start.desc(), SalesTarget.id.desc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def get_target(self, target_id: UUID, *, firm_scope: UUID) -> SalesTarget:
        """Fetch one target, scoped to the firm."""
        row = self._session.scalar(
            select(SalesTarget).where(
                SalesTarget.id == target_id,
                SalesTarget.firm_id == firm_scope,
                SalesTarget.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales target not found.")
        return row

    def create_target(
        self, data: SalesTargetWrite, *, firm_id: UUID, actor_id: UUID
    ) -> SalesTarget:
        """Set one target."""
        self._assert_free(data, firm_id=firm_id)
        row = SalesTarget(
            firm_id=firm_id,
            salesman_id=data.salesman_id,
            territory_id=data.territory_id,
            period_start=data.period_start,
            period_end=data.period_end,
            period_type=data.period_type.value,
            basis=data.basis.value,
            target_amount=data.target_amount,
            notes=data.notes,
            status=data.status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="sales_target.created",
            entity_type="sales_target",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "period_start": str(row.period_start),
                "target_amount": str(row.target_amount),
            },
        )
        self._session.commit()
        return row

    def update_target(
        self,
        target_id: UUID,
        data: SalesTargetWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> SalesTarget:
        """Replace one target's numbers."""
        row = self.get_target(target_id, firm_scope=firm_scope)
        self._assert_free(data, firm_id=firm_scope, excluding=row.id)
        before: dict[str, object] = {"target_amount": str(row.target_amount)}
        row.salesman_id = data.salesman_id
        row.territory_id = data.territory_id
        row.period_start = data.period_start
        row.period_end = data.period_end
        row.period_type = data.period_type.value
        row.basis = data.basis.value
        row.target_amount = data.target_amount
        row.notes = data.notes
        row.status = data.status
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_target.updated",
            entity_type="sales_target",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"target_amount": str(row.target_amount)},
        )
        self._session.commit()
        return row

    def delete_target(
        self, target_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Withdraw one target without forgetting it was set."""
        row = self.get_target(target_id, firm_scope=firm_scope)
        row.is_deleted = True
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_target.deleted",
            entity_type="sales_target",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"target_amount": str(row.target_amount)},
        )
        self._session.commit()

    def achievement(
        self,
        *,
        firm_scope: UUID,
        from_date: date,
        to_date: date,
        salesman_id: UUID | None = None,
    ) -> list[SalesTargetAchievement]:
        """Report every target whose period overlaps the window asked for.

        Each is measured over **its own** dates and on **its own** basis, not
        over the window: a target for April is April's achievement whether the
        report asks for the quarter or the year. The window only chooses which
        targets are worth reporting.
        """
        targets = list(
            self._session.scalars(
                select(SalesTarget)
                .where(
                    SalesTarget.firm_id == firm_scope,
                    SalesTarget.is_deleted.is_(False),
                    SalesTarget.status == "ACTIVE",
                    SalesTarget.period_start <= to_date,
                    SalesTarget.period_end >= from_date,
                    *(
                        [SalesTarget.salesman_id == salesman_id]
                        if salesman_id is not None
                        else []
                    ),
                )
                .order_by(SalesTarget.period_start.asc(), SalesTarget.id.asc())
            ).all()
        )
        names = self._names_for(
            {row.salesman_id for row in targets if row.salesman_id}, firm_scope
        )
        answers: list[SalesTargetAchievement] = []
        for row in targets:
            achieved = quantize_money(self._achieved(row, firm_scope=firm_scope))
            target = quantize_money(row.target_amount)
            answers.append(
                SalesTargetAchievement(
                    target_id=row.id,
                    salesman_id=row.salesman_id,
                    salesman_name=(
                        names.get(row.salesman_id, UNASSIGNED)
                        if row.salesman_id
                        else "Whole firm"
                    ),
                    territory_id=row.territory_id,
                    period_start=row.period_start,
                    period_end=row.period_end,
                    period_type=row.period_type,
                    basis=row.basis,
                    target_amount=target,
                    achieved_amount=achieved,
                    # Floored at zero: a target beaten is not a shortfall of a
                    # negative amount, and a report saying so reads wrong.
                    shortfall_amount=max(ZERO, quantize_money(target - achieved)),
                    achieved_percent=(
                        quantize_money(achieved * HUNDRED / target)
                        if target > ZERO
                        else ZERO
                    ),
                )
            )
        return answers

    def _achieved(self, target: SalesTarget, *, firm_scope: UUID) -> Decimal:
        """Return what this target actually took, on its own basis."""
        if target.basis == SalesTargetBasis.COLLECTED.value:
            return self._collected(target, firm_scope=firm_scope)
        return self._invoiced(target, firm_scope=firm_scope)

    def _invoiced(self, target: SalesTarget, *, firm_scope: UUID) -> Decimal:
        """Sum what was billed in the period, net of what came back.

        Only approved invoices: a draft is not a sale, and a cancelled one is
        not one either. Each bill counts for its total less what a credit
        note or a completed return has since taken off it -- `invoiced_net`
        is the one walk, shared with `app/commission`, so a target and a
        payout cannot disagree about the same money.
        """
        rows = invoiced_net(
            self._session,
            firm_id=firm_scope,
            from_date=target.period_start,
            to_date=target.period_end,
        )
        return sum_of([row for row in rows if self._in_scope(target, row)])

    def _collected(self, target: SalesTarget, *, firm_scope: UUID) -> Decimal:
        """Sum the money that actually arrived in the period.

        Walks the allocations rather than the invoices, and counts only POSTED
        receipts -- a reversed settlement collected nothing -- net of what has
        been credited against the bill since. The same walk `app/commission`
        makes, and it must stay the same one: two numbers describing the same
        money computed two ways will disagree.
        """
        rows = collected_net(
            self._session,
            firm_id=firm_scope,
            from_date=target.period_start,
            to_date=target.period_end,
        )
        return sum_of([row for row in rows if self._in_scope(target, row)])

    @staticmethod
    def _in_scope(target: SalesTarget, row: NetSale) -> bool:
        """Say whether one sale counts towards whoever the target is for.

        A target naming neither a salesman nor a territory is the firm's own
        number, and takes everything.
        """
        if target.salesman_id is not None and row.salesman_id != target.salesman_id:
            return False
        return target.territory_id is None or row.territory_id == target.territory_id

    def _names_for(self, salesman_ids: set[UUID], firm_scope: UUID) -> dict[UUID, str]:
        """Resolve salesman names through the platform store.

        `users` and `user_firms` exist only in the platform schema, so a tenant
        session cannot see them -- reading them here would answer 503 for every
        firm outside the platform store, which this codebase has recorded seven
        separate times.
        """
        if not salesman_ids:
            return {}
        return {
            member.user_id: member.full_name or member.email
            for member in FirmMetadataReader(self._session).active_members(firm_scope)
            if member.user_id in salesman_ids
        }

    def target_response(
        self, row: SalesTarget, names: dict[UUID, str] | None = None
    ) -> SalesTargetResponse:
        """Build the API response for one target."""
        lookup = names or {}
        return SalesTargetResponse(
            id=row.id,
            salesman_id=row.salesman_id,
            salesman_name=(lookup.get(row.salesman_id) if row.salesman_id else None),
            territory_id=row.territory_id,
            period_start=row.period_start,
            period_end=row.period_end,
            period_type=row.period_type,
            basis=row.basis,
            target_amount=row.target_amount,
            notes=row.notes,
            status=row.status,
            version=row.version,
        )

    def _assert_free(
        self,
        data: SalesTargetWrite,
        *,
        firm_id: UUID,
        excluding: UUID | None = None,
    ) -> None:
        """Refuse a second target for the same scope and basis over any of the days.

        Overlap, not a shared start date: two targets over the same days on
        the same basis count the same sales twice, and `_targets_met` then
        adds both amounts up and pays the bonus on the total. A quarterly
        target from the 1st used to be refused because the monthly one
        started that day, while one from the 2nd -- overlapping it entirely
        -- was accepted (D-TER-2). A target on the *other* basis is free to
        overlap: what was invoiced and what was collected are different
        numbers, and a firm may set both.

        Args:
            data: The target about to be written.
            firm_id: The owning firm.
            excluding: The row being updated, which may of course overlap
                itself.

        Raises:
            ConflictError: If a live target of the same scope and basis
                already covers any of those days.

        """
        statement = select(SalesTarget).where(
            SalesTarget.firm_id == firm_id,
            SalesTarget.is_deleted.is_(False),
            SalesTarget.basis == data.basis.value,
            SalesTarget.period_start <= data.period_end,
            SalesTarget.period_end >= data.period_start,
            (
                SalesTarget.salesman_id.is_(None)
                if data.salesman_id is None
                else SalesTarget.salesman_id == data.salesman_id
            ),
            (
                SalesTarget.territory_id.is_(None)
                if data.territory_id is None
                else SalesTarget.territory_id == data.territory_id
            ),
        )
        if excluding is not None:
            statement = statement.where(SalesTarget.id != excluding)
        clash = self._session.scalar(statement)
        if clash is not None:
            raise ConflictError(
                "A target for this scope on the same basis already covers "
                f"part of that period ({clash.period_start.isoformat()} to "
                f"{clash.period_end.isoformat()}). Two would count the same "
                "sales twice."
            )
