"""The switch-over to costing by lot, on PostgreSQL, store by store (L2 step 9).

A firm's switch runs on its own store's session. Two firm stores are two
schemas; switching one must leave the other on Average with nothing carried,
and the switched one's lots must add up to what it held, on the database the
firms run on -- including the row lock the switch takes on its settings row.
"""

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.base import Base
from app.inventory.models import BatchValuation, ProductValuation, StockLotSettings
from tests.unit.test_lot_switch_over import SWITCH_DAY, _Trader


@pytest.fixture
def other_session(engine: Engine) -> Iterator[Session]:
    """Yield a session on a second disposable firm store, then drop it."""
    name = f"it_{uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
    bind = engine.execution_options(schema_translate_map={None: name})
    session = sessionmaker(bind=bind, expire_on_commit=False)()
    try:
        Base.metadata.create_all(bind)
        session.execute(text(f'SET search_path TO "{name}"'))
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))


def _totals(session: Session) -> tuple[Decimal, Decimal]:
    """Return the store's stock quantity and value, from its valuations."""
    quantity, value = session.execute(
        select(
            func.coalesce(func.sum(ProductValuation.quantity_on_hand), 0),
            func.coalesce(func.sum(ProductValuation.total_value), 0),
        )
    ).one()
    return Decimal(quantity), Decimal(value)


def test_switching_one_store_leaves_the_other_untouched(
    temp_session: Session, other_session: Session
) -> None:
    """One firm by lot with exact lots; the other on Average, nothing carried."""
    switching = _Trader(temp_session)
    staying = _Trader(other_session)
    before = _totals(temp_session)
    untouched = _totals(other_session)

    switching.service.switch(switching.firm.id, SWITCH_DAY, switching.actor)

    temp_session.expire_all()
    lot_quantity, lot_value = temp_session.execute(
        select(
            func.sum(BatchValuation.quantity_on_hand),
            func.sum(BatchValuation.total_value),
        )
    ).one()
    assert (Decimal(lot_quantity), Decimal(lot_value)) == before
    assert _totals(temp_session) == before
    other_session.expire_all()
    assert _totals(other_session) == untouched
    assert other_session.scalar(select(func.count(BatchValuation.id))) == 0
    assert other_session.scalar(select(func.count(StockLotSettings.id))) == 0
    assert staying.service.settings(staying.firm.id).costing_method == "AVERAGE"
    assert {
        row.costing_method for row in other_session.scalars(select(ProductValuation))
    } == {"WEIGHTED_AVERAGE"}
