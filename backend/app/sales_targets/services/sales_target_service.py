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

A target on a territory covers the node **and every live descendant**. A
document carries the node its customer is assigned to -- the route, at the
bottom of the tree -- so a target matched on that column alone achieved
nothing on any level above it (D-TER-12). The descendants are walked down
`parent_id` rather than matched on a `path LIKE` prefix, which also took a
sibling whose code merely started the same way and read `_` as a wildcard.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.money import quantize_money
from app.sales.models import SalesTerritoryNode
from app.sales_targets.models import SalesTarget
from app.sales_targets.schemas import (
    SalesTargetAchievement,
    SalesTargetBasis,
    SalesTargetResponse,
    SalesTargetUpdate,
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
#: What a target naming neither a person nor a territory is for.
WHOLE_FIRM = "Whole firm"


@dataclass(frozen=True)
class TerritoryLabel:
    """A territory's code and name, as the reports print them."""

    code: str
    name: str

    def __str__(self) -> str:
        """Print as ``CODE · Name``."""
        return f"{self.code} · {self.name}"


def scope_label(salesman_name: str | None, territory: TerritoryLabel | None) -> str:
    """Say who a target is for, ready to print.

    The person, the territory, both, or the firm. A client deriving this
    from the salesman alone called every territory target "Whole firm".
    """
    parts = [part for part in (salesman_name, str(territory or "")) if part]
    return " · ".join(parts) or WHOLE_FIRM


#: Every column an update may touch, in the order the audit row lists them.
_COLUMNS: tuple[str, ...] = (
    "salesman_id",
    "territory_id",
    "period_start",
    "period_end",
    "period_type",
    "basis",
    "target_amount",
    "notes",
    "status",
)
#: The ones that cannot be emptied: a target with no period, basis, amount
#: or status is not a target. The other three -- the person, the round and
#: the notes -- are cleared by an explicit ``null``.
_REQUIRED: frozenset[str] = frozenset(
    {"period_start", "period_end", "period_type", "basis", "target_amount", "status"}
)


def _audit_value(value: object) -> object:
    """Render one column for the audit row: JSON-safe, and ``None`` as itself."""
    return None if value is None else str(value)


def _optional_uuid(value: object) -> UUID | None:
    """Narrow a merged column back to the id it is, for the type checker."""
    assert value is None or isinstance(value, UUID)
    return value


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
        self._assert_free(
            firm_id=firm_id,
            basis=data.basis.value,
            period_start=data.period_start,
            period_end=data.period_end,
            salesman_id=data.salesman_id,
            territory_id=data.territory_id,
        )
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
        data: SalesTargetUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> SalesTarget:
        """Change some of one target, leaving the rest as it was.

        Only the fields the body actually set are written -- **absent means
        leave alone, and an explicit ``null`` still clears** -- because the
        write model's defaults used to be applied to every omission: a PUT
        naming only the dates and the amount cleared the person, made the
        target the firm's own, and stopped their bonus (D-TER-8). The overlap
        check runs on the merged row rather than the body, since the body may
        name none of what decides it, and the audit row records the before
        and after of every column that moved.

        Raises:
            ValidationError: If a column that cannot be empty is set to
                ``null``, or the merged period ends before it starts.
            ConflictError: If the merged target overlaps another on the same
                scope and basis.

        """
        row = self.get_target(target_id, firm_scope=firm_scope)
        changes = data.model_dump(exclude_unset=True)
        emptied = sorted(
            field for field in changes if field in _REQUIRED and changes[field] is None
        )
        if emptied:
            raise ValidationError(
                "A target cannot have these cleared: " + ", ".join(emptied) + "."
            )
        merged: dict[str, object] = {
            field: changes.get(field, getattr(row, field)) for field in _COLUMNS
        }
        for field in ("period_type", "basis"):
            label = merged[field]
            if isinstance(label, StrEnum):
                merged[field] = label.value
        period_start, period_end = merged["period_start"], merged["period_end"]
        assert isinstance(period_start, date) and isinstance(period_end, date)
        if period_end < period_start:
            raise ValidationError("A target cannot end before it starts.")
        self._assert_free(
            firm_id=firm_scope,
            basis=str(merged["basis"]),
            period_start=period_start,
            period_end=period_end,
            salesman_id=_optional_uuid(merged["salesman_id"]),
            territory_id=_optional_uuid(merged["territory_id"]),
            excluding=row.id,
        )
        before: dict[str, object] = {}
        after: dict[str, object] = {}
        for field in _COLUMNS:
            current = getattr(row, field)
            if merged[field] == current:
                continue
            before[field] = _audit_value(current)
            after[field] = _audit_value(merged[field])
            setattr(row, field, merged[field])
        if not after:
            # Nothing moved: no write, no audit row, and the version stays.
            return row
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_target.updated",
            entity_type="sales_target",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=after,
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
        territory_ids = {row.territory_id for row in targets if row.territory_id}
        labels = self.territory_labels(territory_ids, firm_scope)
        covered = {
            territory_id: self._covered_by(territory_id, firm_scope)
            for territory_id in territory_ids
        }
        answers: list[SalesTargetAchievement] = []
        for row in targets:
            achieved = quantize_money(
                self._achieved(
                    row,
                    firm_scope=firm_scope,
                    covered=covered.get(row.territory_id) if row.territory_id else None,
                )
            )
            target = quantize_money(row.target_amount)
            person = names.get(row.salesman_id, UNASSIGNED) if row.salesman_id else None
            territory = labels.get(row.territory_id) if row.territory_id else None
            label = scope_label(person, territory)
            answers.append(
                SalesTargetAchievement(
                    target_id=row.id,
                    salesman_id=row.salesman_id,
                    salesman_name=person or label,
                    territory_id=row.territory_id,
                    territory_code=territory.code if territory else None,
                    territory_name=territory.name if territory else None,
                    scope_label=label,
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

    def _achieved(
        self,
        target: SalesTarget,
        *,
        firm_scope: UUID,
        covered: frozenset[UUID] | None = None,
    ) -> Decimal:
        """Return what this target actually took, on its own basis.

        Args:
            target: The target being measured.
            firm_scope: The owning firm.
            covered: The territory ids the target reaches -- its own node
                and every live descendant -- resolved by the caller once per
                territory rather than once per target. Resolved here when
                not given; ``None`` for a target naming no territory.

        """
        if target.territory_id is not None and covered is None:
            covered = self._covered_by(target.territory_id, firm_scope)
        if target.basis == SalesTargetBasis.COLLECTED.value:
            return self._collected(target, firm_scope=firm_scope, covered=covered)
        return self._invoiced(target, firm_scope=firm_scope, covered=covered)

    def _invoiced(
        self,
        target: SalesTarget,
        *,
        firm_scope: UUID,
        covered: frozenset[UUID] | None,
    ) -> Decimal:
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
        return sum_of([row for row in rows if self._in_scope(target, row, covered)])

    def _collected(
        self,
        target: SalesTarget,
        *,
        firm_scope: UUID,
        covered: frozenset[UUID] | None,
    ) -> Decimal:
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
        return sum_of([row for row in rows if self._in_scope(target, row, covered)])

    @staticmethod
    def _in_scope(
        target: SalesTarget, row: NetSale, covered: frozenset[UUID] | None
    ) -> bool:
        """Say whether one sale counts towards whoever the target is for.

        A target naming neither a salesman nor a territory is the firm's own
        number, and takes everything. One naming a territory takes the sales
        tagged to that node **or any live node beneath it** -- a document
        carries the route its customer is on, and a region is its routes
        (D-TER-12).

        Args:
            target: The target being measured.
            row: One measured sale.
            covered: The territory ids the target reaches, or ``None`` when
                it names no territory.

        """
        if target.salesman_id is not None and row.salesman_id != target.salesman_id:
            return False
        if target.territory_id is None:
            return True
        return row.territory_id is not None and row.territory_id in (
            covered or frozenset({target.territory_id})
        )

    def _covered_by(self, territory_id: UUID, firm_scope: UUID) -> frozenset[UUID]:
        """Return the territory and every live descendant, as ids.

        Breadth-first down `parent_id`, which is the relation the tree is
        built on, bounded by the ids seen so a cycle in a plain column cannot
        walk for ever. Not a `path LIKE '<prefix>%'`: that also took a
        sibling whose code merely started the same way (`T-N` and `T-N2`)
        and read `_` in a code as a wildcard. Only rows that are not deleted
        count as live; a node the target names is always its own.
        """
        covered = {territory_id}
        frontier = [territory_id]
        while frontier:
            children = [
                child
                for child in self._session.scalars(
                    select(SalesTerritoryNode.id).where(
                        SalesTerritoryNode.firm_id == firm_scope,
                        SalesTerritoryNode.parent_id.in_(frontier),
                        SalesTerritoryNode.is_deleted.is_(False),
                    )
                ).all()
                if child not in covered
            ]
            covered.update(children)
            frontier = children
        return frozenset(covered)

    def territory_labels(
        self, territory_ids: set[UUID], firm_scope: UUID
    ) -> dict[UUID, TerritoryLabel]:
        """Resolve territory codes and names, from the firm's own store.

        Deleted nodes are answered too: a target set on a territory since
        retired should still say which one, not fall back to "Whole firm".
        """
        if not territory_ids:
            return {}
        rows = self._session.execute(
            select(
                SalesTerritoryNode.id, SalesTerritoryNode.code, SalesTerritoryNode.name
            ).where(
                SalesTerritoryNode.firm_id == firm_scope,
                SalesTerritoryNode.id.in_(list(territory_ids)),
            )
        ).all()
        return {row_id: TerritoryLabel(code, name) for row_id, code, name in rows}

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
        self,
        row: SalesTarget,
        names: dict[UUID, str] | None = None,
        territories: dict[UUID, TerritoryLabel] | None = None,
    ) -> SalesTargetResponse:
        """Build the API response for one target.

        Args:
            row: The target.
            names: Salesman names already resolved, keyed by user id. Looked
                up for this row when not given.
            territories: Territory labels already resolved, keyed by node
                id. Looked up for this row when not given.

        """
        lookup = names
        if lookup is None:
            lookup = self._names_for(
                {row.salesman_id} if row.salesman_id else set(), row.firm_id
            )
        labels = territories
        if labels is None:
            labels = self.territory_labels(
                {row.territory_id} if row.territory_id else set(), row.firm_id
            )
        person = lookup.get(row.salesman_id) if row.salesman_id else None
        territory = labels.get(row.territory_id) if row.territory_id else None
        return SalesTargetResponse(
            id=row.id,
            salesman_id=row.salesman_id,
            salesman_name=person,
            territory_id=row.territory_id,
            territory_code=territory.code if territory else None,
            territory_name=territory.name if territory else None,
            scope_label=scope_label(person, territory),
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
        *,
        firm_id: UUID,
        basis: str,
        period_start: date,
        period_end: date,
        salesman_id: UUID | None,
        territory_id: UUID | None,
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

        Takes the values rather than a body, because an update's body may
        name none of them: the check has to run on what the row will hold
        once the body is merged into it (D-TER-8).

        Args:
            firm_id: The owning firm.
            basis: INVOICED or COLLECTED.
            period_start: First day of the target about to be written.
            period_end: Last day of it.
            salesman_id: The person it is for, if anyone.
            territory_id: The round it is for, if any.
            excluding: The row being updated, which may of course overlap
                itself.

        Raises:
            ConflictError: If a live target of the same scope and basis
                already covers any of those days.

        """
        statement = select(SalesTarget).where(
            SalesTarget.firm_id == firm_id,
            SalesTarget.is_deleted.is_(False),
            SalesTarget.basis == basis,
            SalesTarget.period_start <= period_end,
            SalesTarget.period_end >= period_start,
            (
                SalesTarget.salesman_id.is_(None)
                if salesman_id is None
                else SalesTarget.salesman_id == salesman_id
            ),
            (
                SalesTarget.territory_id.is_(None)
                if territory_id is None
                else SalesTarget.territory_id == territory_id
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
