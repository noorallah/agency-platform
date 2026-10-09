"""Count planning (STK-6, decision A117).

The shop's one product, dispatched, is class A. A plan for class A draws a
blind sheet holding it; a plan for class C covers nothing. A plan never
counted is due today, and a week after its sheet is posted it is not. A
storekeeper allowed 250 cannot post a sheet 500 out; somebody allowed more
can.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.inventory.schemas import PhysicalCountLineWrite, PhysicalCountUpdate
from app.inventory.services.adjustment_approval import (
    StockAdjustmentApprovalService,
    StockAdjustmentLimitItem,
)
from app.inventory.services.count_planning import (
    CountPlanService,
    CountPlanWrite,
    abc_classes,
)
from app.inventory.services.physical_count_service import PhysicalCountService
from tests.unit.test_batch_picker import _Shop

D = Decimal


def _cost(shop: _Shop, cost: str) -> None:
    """Give the shop's product a moving average, so its movements have value."""
    from sqlalchemy import select

    from app.inventory.models import ProductValuation

    valuation = shop.session.scalar(
        select(ProductValuation).where(ProductValuation.product_id == shop.product.id)
    )
    assert valuation is not None
    valuation.average_cost = D(cost)
    shop.session.commit()
    from app.finance.services.opening_setup import seed_finance_setup

    seed_finance_setup(
        shop.session,
        firm_id=shop.firm_id,
        year_starts_on=date(2026, 4, 1),
        actor_id=shop.actor_id,
    )
    shop.session.commit()


def _person(shop: _Shop, code: str) -> UUID:
    """Create a user holding one role in the shop's firm."""
    from uuid import uuid4

    from sqlalchemy import select

    from app.identity.models import Role, User, UserRole

    user = User(
        email=f"{uuid4().hex[:8]}@count.test", full_name=code, password_hash="x"
    )
    shop.session.add(user)
    shop.session.flush()
    role = shop.session.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=code.title())
        shop.session.add(role)
        shop.session.flush()
    shop.session.add(UserRole(user_id=user.id, role_id=role.id, firm_id=shop.firm_id))
    shop.session.commit()
    return user.id


def _plan(shop: _Shop, abc: str | None, *, blind: bool = True) -> object:
    branch_id = shop.order.branch_id
    return CountPlanService(shop.session).create(
        CountPlanWrite(
            name=f"Class {abc}",
            branch_id=branch_id,
            warehouse_id=shop.warehouse_id,
            abc_class=abc,
            frequency_days=7,
            blind=blind,
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )


def test_abc_classes_plans_and_blind_sheets() -> None:
    shop = _Shop()
    _cost(shop, "100")
    shop.dispatch(shop.note(None))
    assert abc_classes(shop.session, shop.firm_id, on=date(2026, 9, 30)) == {
        shop.product.id: "A"
    }
    plans = CountPlanService(shop.session)
    plan_a = _plan(shop, "A")
    plan_c = _plan(shop, "C")
    listed = plans.list_plans(shop.firm_id, on=date(2026, 9, 30))
    (due,) = [p for p in listed if p.id == plan_a.id]  # type: ignore[attr-defined]
    assert due.is_due

    sheet = plans.draw_sheet(
        plan_a.id,  # type: ignore[attr-defined]
        count_date=date(2026, 9, 30),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    assert sheet.is_blind and sheet.count_plan_id == plan_a.id  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="covers no stock"):
        plans.draw_sheet(
            plan_c.id,  # type: ignore[attr-defined]
            count_date=date(2026, 9, 30),
            firm_id=shop.firm_id,
            actor_id=shop.actor_id,
        )


def test_a_sheet_beyond_the_posters_limit_waits() -> None:
    shop = _Shop()
    for batch in shop.batches.values():
        batch.expiry_date = date(2030, 1, 1)
    shop.session.commit()
    # A limit names a role the firm has (D-STK-67), so the role comes first.
    from app.identity.models import Role

    shop.session.add(Role(code="STOREKEEPER", name="Storekeeper"))
    shop.session.flush()
    StockAdjustmentApprovalService(shop.session).replace_limits(
        [StockAdjustmentLimitItem(role_code="STOREKEEPER", max_value=D("250"))],
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    _cost(shop, "100")

    counts = PhysicalCountService(shop.session)
    plan = _plan(shop, None, blind=False)
    sheet = CountPlanService(shop.session).draw_sheet(
        plan.id,  # type: ignore[attr-defined]
        count_date=date(2026, 9, 30),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    lines = counts.lines_for(sheet.id)
    counts.update(
        sheet.id,
        PhysicalCountUpdate(
            lines=[
                PhysicalCountLineWrite(
                    product_id=line.product_id,
                    batch_id=line.batch_id,
                    storage_node_id=line.storage_node_id,
                    counted_quantity=(
                        Decimal(str(line.expected_quantity)) - D("5")
                        if index == 0
                        else Decimal(str(line.expected_quantity))
                    ),
                )
                for index, line in enumerate(lines)
            ]
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    shop.session.commit()
    keeper = _person(shop, "STOREKEEPER")
    with pytest.raises(ValidationError, match="somebody allowed more"):
        counts.post(sheet.id, firm_id=shop.firm_id, actor_id=keeper)
    shop.session.rollback()
    posted = counts.post(sheet.id, firm_id=shop.firm_id, actor_id=shop.actor_id)
    assert posted.status == "POSTED"


def test_a_plan_switched_off_draws_no_sheet() -> None:
    """D-STK-64: a plan switched off went on handing out sheets."""
    shop = _Shop()
    _cost(shop, "100")
    shop.dispatch(shop.note(None))
    plans = CountPlanService(shop.session)
    plan = _plan(shop, None)
    plans.update(
        plan.id,  # type: ignore[attr-defined]
        CountPlanWrite(
            name="Class None",
            branch_id=shop.order.branch_id,
            warehouse_id=shop.warehouse_id,
            frequency_days=7,
            is_active=False,
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    with pytest.raises(ValidationError, match="switched off"):
        plans.draw_sheet(
            plan.id,  # type: ignore[attr-defined]
            count_date=date(2026, 9, 30),
            firm_id=shop.firm_id,
            actor_id=shop.actor_id,
        )


def test_a_plan_needs_a_name() -> None:
    """D-STK-63: a name of only spaces was kept as a blank row."""
    from uuid import uuid4

    import pydantic

    with pytest.raises(pydantic.ValidationError, match="Give the count plan a name"):
        CountPlanWrite(
            name="   ", branch_id=uuid4(), warehouse_id=uuid4(), frequency_days=7
        )
    kept = CountPlanWrite(
        name="  Fast movers ", branch_id=uuid4(), warehouse_id=uuid4(), frequency_days=7
    )
    assert kept.name == "Fast movers"
