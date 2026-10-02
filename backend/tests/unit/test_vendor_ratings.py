"""People rate suppliers, kept apart from the figures (BUY-15, decision A74).

One live rating per person per supplier; rating again replaces your own and
keeps the old one as history; averages per criterion; scores outside 1-5 are
refused; a withdrawn rating leaves the averages.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError
from app.vendors.models.vendor_rating import VendorRating
from app.vendors.schemas.rating import VendorRatingWrite
from app.vendors.services import VendorService
from app.vendors.services.vendor_ratings import VendorRatingService
from tests.unit.test_vendor_collections_survive_an_edit import (
    _create,
    _firm,
    _session_factory,
)


def _scores(value: int, **over: int) -> VendorRatingWrite:
    base = dict.fromkeys(
        ("quality", "delivery", "price", "communication", "paperwork"), value
    )
    base.update(over)
    return VendorRatingWrite(**base)


def _supplier() -> tuple[object, object, object]:
    session = _session_factory()()
    firm = _firm(session)
    vendor_id = _create(VendorService(session), firm.id, uuid4())
    return session, firm, vendor_id


def test_ratings_average_per_criterion_and_name_the_readers_own() -> None:
    session, firm, vendor_id = _supplier()
    service = VendorRatingService(session)  # type: ignore[arg-type]
    asha, ravi = uuid4(), uuid4()
    service.rate(vendor_id, _scores(4, paperwork=2), firm_id=firm.id, actor_id=asha)  # type: ignore[arg-type, attr-defined]
    service.rate(vendor_id, _scores(5, paperwork=3), firm_id=firm.id, actor_id=ravi)  # type: ignore[arg-type, attr-defined]

    summary = service.summary(vendor_id, firm_id=firm.id, reader_id=asha)  # type: ignore[arg-type, attr-defined]
    assert summary.count == 2
    assert summary.averages["quality"] == Decimal("4.5")
    assert summary.averages["paperwork"] == Decimal("2.5")
    assert summary.overall == Decimal("4.1")
    assert summary.mine is not None and summary.mine.paperwork == 2


def test_rating_again_replaces_your_own_and_keeps_history() -> None:
    session, firm, vendor_id = _supplier()
    service = VendorRatingService(session)  # type: ignore[arg-type]
    asha = uuid4()
    service.rate(vendor_id, _scores(2), firm_id=firm.id, actor_id=asha)  # type: ignore[arg-type, attr-defined]
    service.rate(vendor_id, _scores(5), firm_id=firm.id, actor_id=asha)  # type: ignore[arg-type, attr-defined]

    summary = service.summary(vendor_id, firm_id=firm.id, reader_id=asha)  # type: ignore[arg-type, attr-defined]
    assert summary.count == 1 and summary.overall == Decimal("5.0")
    every = session.scalars(select(VendorRating)).all()  # type: ignore[attr-defined]
    assert len(every) == 2 and sum(row.is_deleted for row in every) == 1
    trail = session.scalars(  # type: ignore[attr-defined]
        select(AuditLog).where(AuditLog.action == "vendor.rated")
    ).all()
    assert trail[-1].before_data == dict.fromkeys(
        ("quality", "delivery", "price", "communication", "paperwork"), 2
    )


def test_a_withdrawn_rating_leaves_the_averages() -> None:
    session, firm, vendor_id = _supplier()
    service = VendorRatingService(session)  # type: ignore[arg-type]
    asha = uuid4()
    service.rate(vendor_id, _scores(1), firm_id=firm.id, actor_id=asha)  # type: ignore[arg-type, attr-defined]
    service.withdraw(vendor_id, firm_id=firm.id, actor_id=asha)  # type: ignore[arg-type, attr-defined]
    summary = service.summary(vendor_id, firm_id=firm.id, reader_id=asha)  # type: ignore[arg-type, attr-defined]
    assert summary.count == 0 and summary.overall is None and summary.mine is None
    with pytest.raises(ResourceNotFoundError):
        service.withdraw(vendor_id, firm_id=firm.id, actor_id=asha)  # type: ignore[arg-type, attr-defined]


def test_scores_outside_one_to_five_and_unknown_suppliers_are_refused() -> None:
    with pytest.raises(ValidationError):
        _scores(6)
    with pytest.raises(ValidationError):
        _scores(3, price=0)
    session, firm, _ = _supplier()
    with pytest.raises(ResourceNotFoundError):
        VendorRatingService(session).rate(  # type: ignore[arg-type]
            uuid4(), _scores(3), firm_id=firm.id, actor_id=uuid4()  # type: ignore[attr-defined]
        )
