"""Purchase budgets by month, branch and category (BUY-14, decision A106).

A budget names a month and, optionally, one branch and one product
category; a blank branch or category covers them all. What it has used is
the value before tax of the approved orders dated in that month whose lines
it covers -- derived on every read, never stored. Approving an order that
takes a budget past its amount warns, or, where the firm says so, needs
PURCHASE_APPROVE_OVER_BUDGET.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.products.models import Product, ProductCategory
from app.purchase.models import PurchaseBudget, PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import (
    PurchaseBudgetCheckRow,
    PurchaseBudgetResponse,
    PurchaseBudgetWrite,
)

ZERO = Decimal("0")

#: Orders that count against a budget: approved, and on through receiving.
_COUNTED = ("APPROVED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED")


def month_of(day: date) -> date:
    """Return the first day of the day's month."""
    return day.replace(day=1)


def _next_month(first: date) -> date:
    """Return the first day of the following month."""
    return (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    )


@dataclass(frozen=True)
class _Spend:
    """Value before tax spent in one month, by branch and category."""

    by_place: dict[tuple[UUID, UUID | None], Decimal]

    def covered_by(self, budget: PurchaseBudget) -> Decimal:
        """Return what the budget's branch and category cover."""
        return sum(
            (
                amount
                for (branch, category), amount in self.by_place.items()
                if (budget.branch_id is None or budget.branch_id == branch)
                and (
                    budget.product_category_id is None
                    or budget.product_category_id == category
                )
            ),
            ZERO,
        )


class PurchaseBudgetService:
    """Keep a firm's purchase budgets and check orders against them."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    def list_budgets(self, firm_id: UUID, month: date) -> list[PurchaseBudgetResponse]:
        """Return the month's budgets with what each has used."""
        first = month_of(month)
        budgets = self._budgets(firm_id, first)
        spend = self._spend(firm_id, first)
        return self._responses(budgets, spend)

    def create(
        self, data: PurchaseBudgetWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseBudgetResponse:
        """Add one budget.

        Raises:
            ConflictError: If the month already has one for that branch and
                category.

        """
        first = month_of(data.budget_month)
        self._assert_free(firm_id, first, data.branch_id, data.product_category_id)
        row = PurchaseBudget(
            firm_id=firm_id,
            budget_month=first,
            branch_id=data.branch_id,
            product_category_id=data.product_category_id,
            amount=data.amount,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit("purchase_budget.created", row, actor_id)
        self._session.commit()
        return self._responses([row], self._spend(firm_id, first))[0]

    def update(
        self,
        budget_id: UUID,
        data: PurchaseBudgetWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PurchaseBudgetResponse:
        """Change one budget's amount, month, branch or category."""
        row = self._get(budget_id, firm_id)
        first = month_of(data.budget_month)
        if (first, data.branch_id, data.product_category_id) != (
            row.budget_month,
            row.branch_id,
            row.product_category_id,
        ):
            self._assert_free(firm_id, first, data.branch_id, data.product_category_id)
        row.budget_month = first
        row.branch_id = data.branch_id
        row.product_category_id = data.product_category_id
        row.amount = data.amount
        row.updated_by = actor_id
        self._session.flush()
        self._audit("purchase_budget.updated", row, actor_id)
        self._session.commit()
        return self._responses([row], self._spend(firm_id, first))[0]

    def delete(self, budget_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove one budget."""
        row = self._get(budget_id, firm_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        self._audit("purchase_budget.deleted", row, actor_id)
        self._session.commit()

    def check_order(self, order: PurchaseOrder) -> list[PurchaseBudgetCheckRow]:
        """Return every budget the order touches, before and after it counts.

        An order already counted (approved) is not added a second time.
        """
        first = month_of(order.purchase_date)
        budgets = [
            budget
            for budget in self._budgets(order.firm_id, first)
            if budget.branch_id is None or budget.branch_id == order.branch_id
        ]
        if not budgets:
            return []
        own = self._order_spend(order)
        spend = self._spend(order.firm_id, first)
        counted = order.status in _COUNTED
        names = self._names(budgets)
        rows: list[PurchaseBudgetCheckRow] = []
        for budget in budgets:
            this = _Spend(own).covered_by(budget)
            if this <= ZERO:
                continue
            used = spend.covered_by(budget) - (this if counted else ZERO)
            after = used + this
            amount = Decimal(str(budget.amount))
            rows.append(
                PurchaseBudgetCheckRow(
                    budget_id=budget.id,
                    label=names[budget.id],
                    amount=amount,
                    used=used,
                    this_order=this,
                    available=amount - used,
                    exceeded=after > amount,
                )
            )
        return rows

    def _spend(self, firm_id: UUID, first: date) -> _Spend:
        """Return the month's counted value before tax, grouped in SQL."""
        value = func.sum(PurchaseOrderLine.net_amount - PurchaseOrderLine.tax_amount)
        found: dict[tuple[UUID, UUID | None], Decimal] = defaultdict(lambda: ZERO)
        for branch, category, amount in self._session.execute(
            select(PurchaseOrder.branch_id, Product.category_id, value)
            .join(
                PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
            )
            .join(Product, Product.id == PurchaseOrderLine.product_id)
            .where(
                PurchaseOrder.firm_id == firm_id,
                PurchaseOrder.status.in_(_COUNTED),
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrderLine.is_deleted.is_(False),
                PurchaseOrder.purchase_date >= first,
                PurchaseOrder.purchase_date < _next_month(first),
            )
            .group_by(PurchaseOrder.branch_id, Product.category_id)
        ).all():
            found[(branch, category)] += Decimal(str(amount or 0))
        return _Spend(dict(found))

    def _order_spend(
        self, order: PurchaseOrder
    ) -> dict[tuple[UUID, UUID | None], Decimal]:
        """Return one order's value before tax by category."""
        found: dict[tuple[UUID, UUID | None], Decimal] = defaultdict(lambda: ZERO)
        for category, net, tax in self._session.execute(
            select(
                Product.category_id,
                PurchaseOrderLine.net_amount,
                PurchaseOrderLine.tax_amount,
            )
            .join(Product, Product.id == PurchaseOrderLine.product_id)
            .where(
                PurchaseOrderLine.purchase_order_id == order.id,
                PurchaseOrderLine.is_deleted.is_(False),
            )
        ).all():
            found[(order.branch_id, category)] += Decimal(str(net)) - Decimal(str(tax))
        return dict(found)

    def _budgets(self, firm_id: UUID, first: date) -> list[PurchaseBudget]:
        """Return the month's live budgets."""
        return list(
            self._session.scalars(
                select(PurchaseBudget).where(
                    PurchaseBudget.firm_id == firm_id,
                    PurchaseBudget.budget_month == first,
                    PurchaseBudget.is_deleted.is_(False),
                )
            ).all()
        )

    def _get(self, budget_id: UUID, firm_id: UUID) -> PurchaseBudget:
        """Return one of the firm's budgets."""
        row = self._session.get(PurchaseBudget, budget_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Purchase budget not found.")
        return row

    def _assert_free(
        self,
        firm_id: UUID,
        first: date,
        branch_id: UUID | None,
        category_id: UUID | None,
    ) -> None:
        """Refuse a second budget for the same month, branch and category."""
        for row in self._budgets(firm_id, first):
            if row.branch_id == branch_id and row.product_category_id == category_id:
                raise ConflictError(
                    f"{first:%B %Y} already has a budget for that branch and "
                    "category; change it instead."
                )

    def _names(self, budgets: list[PurchaseBudget]) -> dict[UUID, str]:
        """Describe each budget: its branch and category, or "all"."""
        from app.branches.models import Branch

        branch_ids = {b.branch_id for b in budgets if b.branch_id}
        category_ids = {b.product_category_id for b in budgets if b.product_category_id}
        branches: dict[UUID, str] = {}
        if branch_ids:
            for row_id, name in self._session.execute(
                select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids))
            ).all():
                branches[row_id] = name
        categories: dict[UUID, str] = {}
        if category_ids:
            for row_id, name in self._session.execute(
                select(ProductCategory.id, ProductCategory.name).where(
                    ProductCategory.id.in_(category_ids)
                )
            ).all():
                categories[row_id] = name
        labels: dict[UUID, str] = {}
        for budget in budgets:
            branch = (
                branches.get(budget.branch_id, "")
                if budget.branch_id
                else "all branches"
            )
            category = (
                categories.get(budget.product_category_id, "")
                if budget.product_category_id
                else "all categories"
            )
            labels[budget.id] = (
                f"{budgets_label(budget.budget_month)}: {branch}, {category}"
            )
        return labels

    def _responses(
        self, budgets: list[PurchaseBudget], spend: _Spend
    ) -> list[PurchaseBudgetResponse]:
        """Shape budgets with what they have used."""
        names = self._names(budgets)
        return [
            PurchaseBudgetResponse(
                id=budget.id,
                budget_month=budget.budget_month,
                branch_id=budget.branch_id,
                product_category_id=budget.product_category_id,
                label=names[budget.id],
                amount=Decimal(str(budget.amount)),
                used=spend.covered_by(budget),
                available=Decimal(str(budget.amount)) - spend.covered_by(budget),
                version=budget.version,
            )
            for budget in budgets
        ]

    def _audit(self, action: str, row: PurchaseBudget, actor_id: UUID) -> None:
        """Write one audit row for a change to a budget."""
        record_audit(
            self._session,
            action=action,
            entity_type="purchase_budget",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "budget_month": row.budget_month.isoformat(),
                "branch_id": None if row.branch_id is None else str(row.branch_id),
                "product_category_id": (
                    None
                    if row.product_category_id is None
                    else str(row.product_category_id)
                ),
                "amount": str(row.amount),
            },
        )


def budgets_label(first: date) -> str:
    """Name a budget month, "Aug 2026"."""
    return f"{first:%b %Y}"
