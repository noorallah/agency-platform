"""Two firms in one store keep their own custom fields (MST-8), on PostgreSQL.

The code is unique per firm among live rows and among the shared rows, which
takes two partial unique indexes. SQLite honours ``sqlite_where`` but the
deployed stores are built by migration ``20261003_0283``'s ``postgresql_where``,
so only a real server shows that two firms may hold the same code while one
firm may not hold it twice.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
)
from app.business.services import AttributeService


def _field(firm_id: object, code: str = "ROUTE_DAY") -> AttributeDefinition:
    """Return an unsaved TEXT field on customers."""
    return AttributeDefinition(
        firm_id=firm_id,
        code=code,
        name=code.title(),
        entity_type=AttributeEntityType.CUSTOMER,
        data_type=AttributeDataType.TEXT,
    )


def test_two_firms_hold_one_code_and_see_only_their_own(
    temp_session: Session,
) -> None:
    """Each firm's form offers the shared field and its own, never the other's."""
    acme, beta = uuid4(), uuid4()
    temp_session.add_all([_field(None, "FSSAI"), _field(acme), _field(beta)])
    temp_session.flush()
    service = AttributeService(temp_session)

    acme_rows = service.definitions_for(AttributeEntityType.CUSTOMER, firm_id=acme)

    assert sorted((row.code, row.firm_id) for row in acme_rows) == [
        ("FSSAI", None),
        ("ROUTE_DAY", acme),
    ]


@pytest.mark.parametrize("owner", ["firm", "shared"])
def test_one_owner_cannot_hold_a_live_code_twice(
    temp_session: Session, owner: str
) -> None:
    """The partial unique indexes refuse a second live row of one code."""
    firm_id = uuid4() if owner == "firm" else None
    temp_session.add(_field(firm_id))
    temp_session.flush()
    temp_session.add(_field(firm_id))

    with pytest.raises(IntegrityError):
        temp_session.flush()
