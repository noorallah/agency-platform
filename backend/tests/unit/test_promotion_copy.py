"""Copy last season's offers with new dates (SEL-8, decision A71).

Copies are drafts with the new window, a suffixed code and their own version
history; their conditions and benefits match; the originals are untouched;
and one clashing code refuses the whole copy.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.promotions.models import Promotion
from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
    PromotionStatus,
)
from app.promotions.services.promotion_copy import PromotionCopyService
from tests.unit.test_promotions import _firm, _promotion, _session_factory

NEW_FROM, NEW_TO = date(2026, 10, 20), date(2026, 11, 5)


def _season() -> tuple[object, object, list[Promotion]]:
    session = _session_factory()()
    firm = _firm(session)
    offers = [
        _promotion(
            session,
            firm_id=firm.id,
            code="DIWALI",
            effective_from=date(2025, 10, 10),
            effective_to=date(2025, 10, 25),
            actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
            conditions=[
                (
                    PromotionField.LINE_QUANTITY,
                    PromotionConditionOperator.GREATER_OR_EQUAL,
                    {"value_number": Decimal("5")},
                )
            ],
        ),
        _promotion(
            session,
            firm_id=firm.id,
            code="SWEETS",
            actions=[(PromotionActionType.BILL_DISCOUNT_AMOUNT, {"amount": "50"})],
        ),
    ]
    return session, firm, offers


def test_copies_are_drafts_with_new_dates_and_the_same_rules() -> None:
    session, firm, offers = _season()
    copies = PromotionCopyService(session).copy(  # type: ignore[arg-type]
        [offer.id for offer in offers],
        effective_from=NEW_FROM,
        effective_to=NEW_TO,
        code_suffix="-26",
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=uuid4(),
    )
    assert [c.code for c in copies] == ["DIWALI-26", "SWEETS-26"]
    assert {c.status for c in copies} == {PromotionStatus.DRAFT.value}
    assert {(c.effective_from, c.effective_to) for c in copies} == {(NEW_FROM, NEW_TO)}
    assert {c.version_number for c in copies} == {1}
    assert copies[0].version_group_id != offers[0].version_group_id
    diwali = copies[0]
    assert [a.parameters for a in diwali.actions] == [
        a.parameters for a in offers[0].actions
    ]
    assert [(c.field_key, c.value_number) for c in diwali.conditions] == [
        (c.field_key, c.value_number) for c in offers[0].conditions
    ]
    original = session.get(Promotion, offers[0].id)  # type: ignore[attr-defined]
    assert original.code == "DIWALI"
    assert original.effective_from == date(2025, 10, 10)
    trail = session.scalars(  # type: ignore[attr-defined]
        select(AuditLog).where(AuditLog.action == "promotion.copied")
    ).all()
    assert len(trail) == 2 and trail[0].after_data["copied_from"] in {
        "DIWALI",
        "SWEETS",
    }


def test_one_clashing_code_refuses_the_whole_copy() -> None:
    session, firm, offers = _season()
    _promotion(
        session,  # type: ignore[arg-type]
        firm_id=firm.id,  # type: ignore[attr-defined]
        code="SWEETS-26",
        actions=[(PromotionActionType.BILL_DISCOUNT_AMOUNT, {"amount": "1"})],
    )
    with pytest.raises(ConflictError, match="SWEETS-26"):
        PromotionCopyService(session).copy(  # type: ignore[arg-type]
            [offer.id for offer in offers],
            effective_from=NEW_FROM,
            effective_to=NEW_TO,
            code_suffix="-26",
            firm_id=firm.id,  # type: ignore[attr-defined]
            actor_id=uuid4(),
        )
    assert (
        session.scalar(  # type: ignore[attr-defined]
            select(Promotion).where(Promotion.code == "DIWALI-26")
        )
        is None
    )


def test_bad_windows_suffixes_and_offers_are_refused() -> None:
    session, firm, offers = _season()
    service = PromotionCopyService(session)  # type: ignore[arg-type]
    ids = [offers[0].id]

    def attempt(
        chosen: list, start: date, end: date, suffix: str = "-26"  # type: ignore[type-arg]
    ) -> None:
        service.copy(
            chosen,
            effective_from=start,
            effective_to=end,
            code_suffix=suffix,
            firm_id=firm.id,  # type: ignore[attr-defined]
            actor_id=uuid4(),
        )

    with pytest.raises(ValidationError, match="end before"):
        attempt(ids, NEW_TO, NEW_FROM)
    with pytest.raises(ValidationError, match="suffix"):
        attempt(ids, NEW_FROM, NEW_TO, " ")
    with pytest.raises(ValidationError, match="twice"):
        attempt(ids * 2, NEW_FROM, NEW_TO)
    with pytest.raises(ResourceNotFoundError):
        attempt([uuid4()], NEW_FROM, NEW_TO)
