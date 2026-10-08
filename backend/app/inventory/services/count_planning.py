"""Count planning: ABC classes, cycle-count plans, blind sheets (STK-6).

Decision A117.

* **ABC class** is worked out, never stored: each product's dispatch value
  over the last year, ranked; the products making the first 80% of it are
  A, the next 15% B, the rest -- and anything not dispatched -- C.
* **A count plan** names a warehouse, an ABC class or a bin, and how often
  to count; its next count falls due that many days after the last sheet it
  drew was posted. Drawing the sheet counts exactly what the plan covers.
* **A blind sheet** hides what the system holds until it is posted.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.concurrency import assert_version
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryRecord, InventoryTransaction, StockLedgerEntry
from app.inventory.models.physical_count import CountPlan, PhysicalCount
from app.inventory.schemas import PhysicalCountCreate, PhysicalCountLineWrite

ZERO = Decimal("0")
#: Cumulative shares of the year's dispatch value that close class A and B.
A_SHARE = Decimal("0.80")
B_SHARE = Decimal("0.95")


def abc_classes(session: Session, firm_id: UUID, *, on: date) -> dict[UUID, str]:
    """Return each dispatched product's class; a product not listed is C."""
    since = on - timedelta(days=365)
    values = session.execute(
        select(
            InventoryTransaction.product_id,
            func.sum(func.abs(StockLedgerEntry.total_cost)),
        )
        .join(
            StockLedgerEntry, StockLedgerEntry.transaction_id == InventoryTransaction.id
        )
        .where(
            InventoryTransaction.firm_id == firm_id,
            InventoryTransaction.transaction_type == "DISPATCH",
            InventoryTransaction.is_deleted.is_(False),
            InventoryTransaction.transaction_date > since,
            InventoryTransaction.transaction_date <= on,
        )
        .group_by(InventoryTransaction.product_id)
    ).all()
    ranked = sorted(
        ((product_id, Decimal(str(value or 0))) for product_id, value in values),
        key=lambda item: (-item[1], str(item[0])),
    )
    total = sum((value for _, value in ranked), ZERO)
    classes: dict[UUID, str] = {}
    running = ZERO
    for product_id, value in ranked:
        if total <= ZERO or value <= ZERO:
            classes[product_id] = "C"
            continue
        share_before = running / total
        running += value
        classes[product_id] = (
            "A" if share_before < A_SHARE else "B" if share_before < B_SHARE else "C"
        )
    return classes


class CountPlanWrite(BaseModel):
    """Create or change one count plan."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    branch_id: UUID
    warehouse_id: UUID
    #: ``A``, ``B`` or ``C``; or blank with a bin; or both blank for everything.
    abc_class: str | None = Field(default=None, pattern="^[ABC]$")
    storage_node_id: UUID | None = None
    frequency_days: int = Field(ge=1, le=366)
    blind: bool = False
    is_active: bool = True


class CountPlanResponse(BaseModel):
    """One plan and when it next falls due."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    branch_id: UUID
    warehouse_id: UUID
    abc_class: str | None
    storage_node_id: UUID | None
    frequency_days: int
    blind: bool
    is_active: bool
    last_counted_on: date | None
    next_due_on: date
    is_due: bool
    version: int


class CountPlanService:
    """Keep count plans and draw their sheets."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    def list_plans(self, firm_id: UUID, *, on: date) -> list[CountPlanResponse]:
        """Return the firm's plans, the ones due first."""
        plans = list(
            self._session.scalars(
                select(CountPlan).where(
                    CountPlan.firm_id == firm_id, CountPlan.is_deleted.is_(False)
                )
            ).all()
        )
        last = self._last_counted([plan.id for plan in plans])
        responses = [self._response(plan, last.get(plan.id), on) for plan in plans]
        responses.sort(key=lambda plan: (not plan.is_due, plan.next_due_on, plan.name))
        return responses

    def create(
        self, data: CountPlanWrite, *, firm_id: UUID, actor_id: UUID
    ) -> CountPlanResponse:
        """Add one plan.

        Raises:
            ValidationError: If the branch, warehouse or bin is not the
                firm's own.

        """
        self._assert_place(data, firm_id)
        row = CountPlan(
            firm_id=firm_id,
            created_by=actor_id,
            updated_by=actor_id,
            **data.model_dump(),
        )
        self._session.add(row)
        self._session.flush()
        self._audit("count_plan.created", row, actor_id)
        self._session.commit()
        return self._response(row, None, firm_today(self._session, firm_id))

    def update(
        self,
        plan_id: UUID,
        data: CountPlanWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CountPlanResponse:
        """Change one plan.

        ``expected_version`` is the version the caller read; a save aimed at
        an older one is refused rather than laid over the newer (F15).

        Raises:
            ValidationError: If the branch, warehouse or bin is not the
                firm's own.

        """
        row = self._get(plan_id, firm_id)
        assert_version(row.version, expected_version)
        self._assert_place(data, firm_id)
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._audit("count_plan.updated", row, actor_id)
        self._session.commit()
        return self._response(
            row,
            self._last_counted([row.id]).get(row.id),
            firm_today(self._session, firm_id),
        )

    def delete(self, plan_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove one plan; its sheets stay."""
        row = self._get(plan_id, firm_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        self._audit("count_plan.deleted", row, actor_id)
        self._session.commit()

    def draw_sheet(
        self, plan_id: UUID, *, count_date: date, firm_id: UUID, actor_id: UUID
    ) -> PhysicalCount:
        """Open the sheet a plan covers, blind if the plan says so; commit.

        Raises:
            ValidationError: If the plan covers no stock.

        """
        from app.inventory.services.physical_count_service import (
            PhysicalCountService,
        )

        plan = self._get(plan_id, firm_id)
        rows = list(
            self._session.scalars(
                select(InventoryRecord).where(
                    InventoryRecord.firm_id == firm_id,
                    InventoryRecord.warehouse_id == plan.warehouse_id,
                    InventoryRecord.is_deleted.is_(False),
                    *(
                        [InventoryRecord.storage_node_id == plan.storage_node_id]
                        if plan.storage_node_id is not None
                        else []
                    ),
                )
            ).all()
        )
        if plan.abc_class is not None:
            classes = abc_classes(self._session, firm_id, on=count_date)
            rows = [
                row
                for row in rows
                if classes.get(row.product_id, "C") == plan.abc_class
            ]
        if not rows:
            raise ValidationError(f"{plan.name} covers no stock to count.")
        sheet = PhysicalCountService(self._session).create(
            PhysicalCountCreate(
                branch_id=plan.branch_id,
                warehouse_id=plan.warehouse_id,
                count_date=count_date,
                remarks=f"Count plan: {plan.name}",
                is_blind=plan.blind,
                lines=[
                    PhysicalCountLineWrite(
                        product_id=row.product_id,
                        batch_id=row.batch_id,
                        storage_node_id=row.storage_node_id,
                    )
                    for row in rows
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
            lines_from_stock=True,
        )
        sheet.count_plan_id = plan.id
        self._session.commit()
        return sheet

    def _assert_place(self, data: CountPlanWrite, firm_id: UUID) -> None:
        """Refuse a plan over a place that is not the firm's (F8).

        A plan was saved with another firm's warehouse id, and with a
        warehouse under a different branch than the one named; nothing said
        so until its sheet was drawn. Judged by the checks a count sheet
        makes, so a plan is never accepted that could not be counted.

        Raises:
            ValidationError: If the branch is not the firm's, the warehouse
                is not under it, or the bin is not in the warehouse.

        """
        from app.inventory.services.physical_count_service import (
            PhysicalCountService,
        )

        PhysicalCountService(self._session).require_place(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            storage_node_ids={data.storage_node_id},
        )

    def _last_counted(self, plan_ids: list[UUID]) -> dict[UUID, date]:
        """Return each plan's latest posted sheet date."""
        if not plan_ids:
            return {}
        found: dict[UUID, date] = {}
        for plan_id, last in self._session.execute(
            select(PhysicalCount.count_plan_id, func.max(PhysicalCount.count_date))
            .where(
                PhysicalCount.count_plan_id.in_(plan_ids),
                PhysicalCount.status == "POSTED",
                PhysicalCount.is_deleted.is_(False),
            )
            .group_by(PhysicalCount.count_plan_id)
        ).all():
            if plan_id is not None and last is not None:
                found[plan_id] = last
        return found

    @staticmethod
    def _response(plan: CountPlan, last: date | None, on: date) -> CountPlanResponse:
        """Shape one plan with its due date."""
        due = (last + timedelta(days=plan.frequency_days)) if last else on
        return CountPlanResponse(
            id=plan.id,
            name=plan.name,
            branch_id=plan.branch_id,
            warehouse_id=plan.warehouse_id,
            abc_class=plan.abc_class,
            storage_node_id=plan.storage_node_id,
            frequency_days=plan.frequency_days,
            blind=plan.blind,
            is_active=plan.is_active,
            last_counted_on=last,
            next_due_on=due,
            is_due=plan.is_active and due <= on,
            version=plan.version,
        )

    def _get(self, plan_id: UUID, firm_id: UUID) -> CountPlan:
        """Return one of the firm's plans."""
        row = self._session.get(CountPlan, plan_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Count plan not found.")
        return row

    def _audit(self, action: str, row: CountPlan, actor_id: UUID) -> None:
        """Write one audit row for a plan."""
        record_audit(
            self._session,
            action=action,
            entity_type="count_plan",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "name": row.name,
                "abc_class": row.abc_class,
                "frequency_days": row.frequency_days,
                "blind": row.blind,
            },
        )
