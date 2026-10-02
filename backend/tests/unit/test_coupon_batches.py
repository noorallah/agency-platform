"""A campaign's single-use coupon codes minted at once (SEL-5, decision A70).

Codes are random, readable off paper, single-use in all and per customer,
never clash with a code the firm ever minted, and come back as a CSV.
"""

# ruff: noqa: D103

import csv
import io
import re
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.promotions.models import PromotionCoupon
from app.promotions.schemas import PromotionActionType
from app.promotions.services.coupon_batches import ALPHABET, CouponBatchService
from tests.unit.test_promotions import _firm, _promotion, _session_factory


def _offer() -> tuple[object, object, object]:
    session = _session_factory()()
    firm = _firm(session)
    promotion = _promotion(
        session,
        firm_id=firm.id,
        code="DIWALI",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )
    return session, firm, promotion


def test_a_batch_mints_single_use_readable_codes() -> None:
    session, firm, promotion = _offer()
    actor = uuid4()
    codes = CouponBatchService(session).generate(  # type: ignore[arg-type]
        promotion.id,  # type: ignore[attr-defined]
        count=500,
        prefix="diwali26",
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
        effective_from=date(2026, 10, 20),
        effective_to=date(2026, 11, 5),
    )
    assert len(codes) == len(set(codes)) == 500
    pattern = re.compile(rf"^DIWALI26-[{ALPHABET}]{{8}}$")
    assert all(pattern.match(code) for code in codes)
    rows = session.scalars(select(PromotionCoupon)).all()  # type: ignore[attr-defined]
    assert len(rows) == 500
    assert {(r.max_redemptions, r.max_redemptions_per_customer) for r in rows} == {
        (1, 1)
    }
    assert {r.effective_to for r in rows} == {date(2026, 11, 5)}
    trail = session.scalars(  # type: ignore[attr-defined]
        select(AuditLog).where(AuditLog.action == "promotion.coupons.generated")
    ).all()
    assert len(trail) == 1 and trail[0].after_data["count"] == 500


def test_the_export_lists_every_code_with_its_use() -> None:
    session, firm, promotion = _offer()
    service = CouponBatchService(session)  # type: ignore[arg-type]
    codes = service.generate(
        promotion.id,  # type: ignore[attr-defined]
        count=3,
        prefix="",
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=uuid4(),
    )
    text, filename = service.export_csv(
        promotion.id, firm_id=firm.id  # type: ignore[attr-defined]
    )
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][:4] == ["Code", "Status", "Uses allowed", "Used"]
    assert [row[0] for row in rows[1:]] == codes
    assert {row[3] for row in rows[1:]} == {"0"}
    assert filename == "coupons-DIWALI.csv"


def test_bad_counts_prefixes_windows_and_offers_are_refused() -> None:
    session, firm, promotion = _offer()
    service = CouponBatchService(session)  # type: ignore[arg-type]
    base = {"firm_id": firm.id, "actor_id": uuid4()}  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="between 1 and 5000"):
        service.generate(promotion.id, count=5001, prefix="X", **base)  # type: ignore[attr-defined, arg-type]
    with pytest.raises(ValidationError, match="prefix"):
        service.generate(promotion.id, count=1, prefix="DI-WALI", **base)  # type: ignore[attr-defined, arg-type]
    with pytest.raises(ValidationError, match="end before"):
        service.generate(
            promotion.id,  # type: ignore[attr-defined]
            count=1,
            prefix="X",
            effective_from=date(2026, 11, 5),
            effective_to=date(2026, 10, 1),
            **base,  # type: ignore[arg-type]
        )
    with pytest.raises(ResourceNotFoundError):
        service.generate(uuid4(), count=1, prefix="X", **base)  # type: ignore[arg-type]
