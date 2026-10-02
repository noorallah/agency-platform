"""Festival bonus loyalty points (SEL-4, decision A73).

A bonus-points offer multiplies what a bill earns while it runs, judged on the
bill's own date and conditions; the largest of several wins; the pricing
engine passes over it; cancelling the bill takes the doubled points back; and
the offer carries nothing but the multiplier.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.loyalty.services import LoyaltyService
from app.promotions.models import Promotion, PromotionAction, PromotionCondition
from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionEvaluationRequest,
    PromotionField,
    PromotionWrite,
)
from app.promotions.services import PromotionService
from tests.unit.test_loyalty import WHEN, _Books, _session_factory


def _festival(
    books: _Books,
    multiplier: str,
    *,
    code: str = "DIWALI2X",
    starts: date = WHEN,
    ends: date = WHEN,
    customer: bool = False,
) -> Promotion:
    row = Promotion(
        firm_id=books.firm.id,
        code=code,
        name=code,
        priority=100,
        status="ACTIVE",
        allow_stacking=True,
        effective_from=starts,
        effective_to=ends,
        version_group_id=uuid4(),
        version_number=1,
    )
    books.session.add(row)
    books.session.flush()
    books.session.add(
        PromotionAction(
            firm_id=books.firm.id,
            promotion_id=row.id,
            sequence=1,
            action_type=PromotionActionType.LOYALTY_MULTIPLIER.value,
            parameters={"multiplier": multiplier},
        )
    )
    if customer:
        books.session.add(
            PromotionCondition(
                firm_id=books.firm.id,
                promotion_id=row.id,
                sequence=1,
                field_key=PromotionField.CUSTOMER_ID.value,
                operator=PromotionConditionOperator.EQUALS.value,
                value_text=str(uuid4()),
            )
        )
    books.session.commit()
    books.session.refresh(row)
    return row


def test_points_are_doubled_inside_the_offer_and_audited() -> None:
    books = _Books(_session_factory()())
    _festival(books, "2")
    entry = books.earn(books.invoice("SI-1", total="1000"))
    assert books.points() == Decimal("40.0000")
    trail = books.session.scalar(
        select(AuditLog).where(
            AuditLog.action == "loyalty.earned", AuditLog.entity_id == entry.id  # type: ignore[union-attr]
        )
    )
    assert trail is not None
    assert trail.after_data["bonus_offer"] == "DIWALI2X"
    assert trail.after_data["multiplier"] == "2"


def test_outside_the_dates_or_conditions_points_are_as_usual() -> None:
    books = _Books(_session_factory()())
    _festival(
        books, "3", starts=WHEN + timedelta(days=1), ends=WHEN + timedelta(days=5)
    )
    _festival(books, "4", code="ONECUSTOMER", customer=True)
    books.earn(books.invoice("SI-1", total="1000"))
    assert books.points() == Decimal("20.0000")


def test_the_largest_of_two_running_offers_wins() -> None:
    books = _Books(_session_factory()())
    _festival(books, "2", code="DOUBLE")
    _festival(books, "3", code="TRIPLE")
    books.earn(books.invoice("SI-1", total="1000"))
    assert books.points() == Decimal("60.0000")


def test_cancelling_the_bill_takes_the_doubled_points_back() -> None:
    books = _Books(_session_factory()())
    _festival(books, "2")
    invoice = books.invoice("SI-1", total="1000")
    books.earn(invoice)
    LoyaltyService(books.session).stage_reversal(
        invoice, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert books.points() == Decimal("0.0000")


def test_pricing_passes_over_a_points_offer() -> None:
    books = _Books(_session_factory()())
    _festival(books, "2")
    result = PromotionService(books.session).evaluate(
        PromotionEvaluationRequest(
            transaction_type="SALES_ORDER", transaction_date=WHEN, lines=[]
        ),
        firm_scope=books.firm.id,
    )
    assert result.applied_promotion_codes == []
    assert any("bonus-points" in d.reason for d in result.decisions)


def test_a_points_offer_carries_nothing_else_and_needs_a_multiplier() -> None:
    base = {"code": "X", "name": "X"}
    with pytest.raises(ValidationError, match="gives nothing else"):
        PromotionWrite.model_validate(
            {
                **base,
                "actions": [
                    {"action_type": "LOYALTY_MULTIPLIER", "multiplier": "2"},
                    {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "5"},
                ],
            }
        )
    with pytest.raises(ValidationError, match="how many times"):
        PromotionWrite.model_validate(
            {**base, "actions": [{"action_type": "LOYALTY_MULTIPLIER"}]}
        )
    with pytest.raises(ValidationError):
        PromotionWrite.model_validate(
            {
                **base,
                "actions": [{"action_type": "LOYALTY_MULTIPLIER", "multiplier": "1"}],
            }
        )
