"""Offers on certain weekdays or hours (SEL-7, decision A72).

"Weekends only" reads the document date's weekday; "4 to 6 pm" reads when the
document was raised, in India time, inclusive at both ends of the window.
Values outside a week or a day, and a window across midnight, are refused.
"""

# ruff: noqa: D103

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionConditionWrite,
    PromotionField,
)
from app.promotions.services import PromotionService
from app.promotions.services.promotion_service import minutes_of_day_in_india
from tests.unit.test_promotions import (
    _firm,
    _product,
    _promotion,
    _request,
    _session_factory,
)

SATURDAY, MONDAY = date(2026, 8, 8), date(2026, 8, 10)


def _priced(
    condition: tuple[PromotionField, PromotionConditionOperator, dict],
    *,
    on: date = MONDAY,
    at: datetime | None = None,
) -> list[str]:
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="WINDOW",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
        conditions=[condition],
    )
    request = _request(lines=[(1, product.id, "1", "100")], on=on)
    request = request.model_copy(update={"transaction_time": at})
    return (
        PromotionService(session)
        .evaluate(request, firm_scope=firm.id)
        .applied_promotion_codes
    )


WEEKENDS = (
    PromotionField.WEEKDAY,
    PromotionConditionOperator.IN,
    {"value_json": ["6", "7"]},
)
FOUR_TO_SIX = (
    PromotionField.TIME_OF_DAY,
    PromotionConditionOperator.BETWEEN,
    {"value_json": [960, 1079]},
)


def test_weekends_only_reads_the_document_date() -> None:
    assert _priced(WEEKENDS, on=SATURDAY) == ["WINDOW"]
    assert _priced(WEEKENDS, on=MONDAY) == []


@pytest.mark.parametrize(
    ("utc", "applies"),
    [
        # 16:00 IST is 10:30 UTC -- the first minute of the window.
        (datetime(2026, 8, 10, 10, 30, tzinfo=UTC), True),
        # 17:59 IST, the last minute.
        (datetime(2026, 8, 10, 12, 29, tzinfo=UTC), True),
        # 15:59 and 18:00 IST, one minute either side.
        (datetime(2026, 8, 10, 10, 29, tzinfo=UTC), False),
        (datetime(2026, 8, 10, 12, 30, tzinfo=UTC), False),
        # A naive stored timestamp is UTC, as SQLite hands them back.
        (datetime(2026, 8, 10, 11, 0), True),
    ],
)
def test_four_to_six_reads_india_time_inclusive(utc: datetime, applies: bool) -> None:
    assert (_priced(FOUR_TO_SIX, at=utc) == ["WINDOW"]) is applies


def test_minutes_cross_the_utc_date_line() -> None:
    # 20:00 UTC is 01:30 the next day in India.
    assert minutes_of_day_in_india(datetime(2026, 8, 10, 20, 0, tzinfo=UTC)) == 90


@pytest.mark.parametrize(
    ("field", "operator", "values", "message"),
    [
        (
            PromotionField.WEEKDAY,
            PromotionConditionOperator.IN,
            ["0", "6"],
            "1 \\(Monday\\)",
        ),
        (
            PromotionField.WEEKDAY,
            PromotionConditionOperator.IN,
            ["8"],
            "1 \\(Monday\\)",
        ),
        (
            PromotionField.TIME_OF_DAY,
            PromotionConditionOperator.BETWEEN,
            [0, 1440],
            "1439",
        ),
        (
            PromotionField.TIME_OF_DAY,
            PromotionConditionOperator.BETWEEN,
            [1320, 120],
            "midnight",
        ),
    ],
)
def test_days_and_times_out_of_range_are_refused(
    field: PromotionField,
    operator: PromotionConditionOperator,
    values: list[object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        PromotionConditionWrite(field_key=field, operator=operator, value_json=values)


def test_a_valid_window_is_accepted() -> None:
    written = PromotionConditionWrite(
        field_key=PromotionField.TIME_OF_DAY,
        operator=PromotionConditionOperator.BETWEEN,
        value_json=[960, 1079],
    )
    assert written.value_json == [960, 1079]
