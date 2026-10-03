"""Purchase budgets (BUY-14, decision A106).

August's budget is 1,000 across all branches and categories. An approved
order of 600 uses 600 of it. A second order of 600 would take it to 1,200:
by default the approval goes ahead and the timeline says so; a firm that
needs approval refuses it unless the approver may approve over budget. A
budget for one category ignores products outside it.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import AuthorizationError, ConflictError
from app.products.models import ProductCategory
from app.purchase.models import PurchaseOrder
from app.purchase.schemas import (
    PurchaseBudgetWrite,
    PurchaseOrderCreate,
    PurchaseWorkflowSettingsWrite,
)
from app.purchase.services import PurchaseService
from app.purchase.services.budgets import PurchaseBudgetService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with a budget of 1,000 for August."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="BUDGT")
    PurchaseBudgetService(built.session).create(
        PurchaseBudgetWrite(budget_month=date(2026, 8, 15), amount=D("1000")),
        firm_id=built.firm.id,
        actor_id=built.actor_id,
    )
    return built


def _submitted(firm: _Firm, quantity: str) -> PurchaseOrder:
    service = PurchaseService(firm.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": [
                    {
                        "product_id": firm.product.id,
                        "ordered_quantity": quantity,
                        "unit_price": "100",
                        "discount_percent": "0",
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    return service.submit_order(
        order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _approve(firm: _Firm, order: PurchaseOrder, *, may: bool) -> PurchaseOrder:
    return PurchaseService(firm.session).approve_order(
        order.id,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        may_exceed_budget=may,
    )


def test_usage_and_a_warning_past_the_budget(firm: _Firm) -> None:
    budgets = PurchaseBudgetService(firm.session)
    _approve(firm, _submitted(firm, "6"), may=False)
    (august,) = budgets.list_budgets(firm.firm.id, date(2026, 8, 1))
    assert (august.used, august.available) == (D("600"), D("400"))

    second = _submitted(firm, "6")
    (check,) = budgets.check_order(second)
    assert (check.used, check.this_order, check.exceeded) == (D("600"), D("600"), True)
    approved = _approve(firm, second, may=False)
    assert approved.status == "APPROVED"
    with pytest.raises(ConflictError, match="already has a budget"):
        budgets.create(
            PurchaseBudgetWrite(budget_month=date(2026, 8, 1), amount=D("5")),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_firm_that_needs_approval_refuses_without_it(firm: _Firm) -> None:
    PurchaseWorkflowService(firm.session).update_settings(
        PurchaseWorkflowSettingsWrite(
            purchase_order_stage=True,
            goods_receipt_stage=True,
            budget_policy="NEEDS_APPROVAL",
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    order = _submitted(firm, "12")
    with pytest.raises(AuthorizationError, match="PURCHASE_APPROVE_OVER_BUDGET"):
        _approve(firm, order, may=False)
    firm.session.rollback()
    assert _approve(firm, order, may=True).status == "APPROVED"


def test_a_category_budget_ignores_other_products(firm: _Firm) -> None:
    category = ProductCategory(
        firm_id=firm.firm.id, code="OTHER", name="Other", level=0, path="OTHER"
    )
    firm.session.add(category)
    firm.session.commit()
    budgets = PurchaseBudgetService(firm.session)
    budgets.create(
        PurchaseBudgetWrite(
            budget_month=date(2026, 8, 1),
            product_category_id=category.id,
            amount=D("10"),
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    checks = budgets.check_order(_submitted(firm, "6"))
    assert [check.label.endswith("all categories") for check in checks] == [True]
