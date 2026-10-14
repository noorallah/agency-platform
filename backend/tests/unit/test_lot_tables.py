"""The tables cost per purchase lot is built on (L2 step 1).

`docs/design/LOT_COST_DESIGN.md`, section 3.2. Nothing reads these tables
yet, so what is pinned here is their shape: the keys that say what may repeat
and what may not, and that a firm with nothing set is on Average.
"""

from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import BatchRecord
from app.core.database.base import Base
from app.inventory.models import BatchValuation, StockLotSettings

_FIRM = uuid4()
_PRODUCT = uuid4()


@pytest.fixture
def session() -> Iterator[Session]:
    """Yield a session on an empty in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as opened:
        yield opened
    engine.dispose()


def _batch(
    number: str,
    reference: str | None,
    *,
    lot: bool = False,
    firm_id: UUID = _FIRM,
) -> BatchRecord:
    """Build one batch of the one product."""
    return BatchRecord(
        firm_id=firm_id,
        product_id=_PRODUCT,
        batch_number=number,
        lot_reference=reference,
        per_purchase_line=lot,
    )


def test_a_batch_is_an_ordinary_printed_batch_unless_told(session: Session) -> None:
    """Every batch written today keeps today's meaning."""
    row = _batch("BN-1", "B000001")
    session.add(row)
    session.commit()

    assert row.per_purchase_line is False
    assert row.has_printed_batch is True
    assert row.lot_reference == "B000001"
    assert row.received_on is None
    assert row.source_document_type is None


def test_the_same_number_is_still_the_same_batch(session: Session) -> None:
    """Two ordinary batches of one product cannot share a number."""
    session.add(_batch("BN-1", "B000001"))
    session.commit()
    session.add(_batch("BN-1", "B000002"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_lot_of_one_purchase_line_may_repeat_the_number(session: Session) -> None:
    """A second delivery of a printed batch is a second lot."""
    session.add(_batch("BN-1", "B000001"))
    session.add(_batch("BN-1", "L-1", lot=True))
    session.add(_batch("BN-1", "L-2", lot=True))
    session.commit()

    assert session.query(BatchRecord).count() == 3


def test_a_lot_reference_is_one_lot_per_firm(session: Session) -> None:
    """A reference repeats across firms and after a delete, never beside itself."""
    first = _batch("BN-1", "L-1", lot=True)
    session.add(first)
    session.add(_batch("BN-1", "L-1", lot=True, firm_id=uuid4()))
    session.commit()

    session.add(_batch("BN-2", "L-1", lot=True))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    first.is_deleted = True
    session.add(_batch("BN-2", "L-1", lot=True))
    session.commit()


def test_a_batch_without_a_reference_is_refused(session: Session) -> None:
    """Every creator issues a reference, so a batch with none is a mistake."""
    session.add(_batch("BN-1", None))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_lot_has_one_valuation(session: Session) -> None:
    """One row says what a lot is worth, starting at nothing."""
    batch = _batch("BN-1", "L-1", lot=True)
    session.add(batch)
    session.flush()
    row = BatchValuation(firm_id=_FIRM, batch_id=batch.id, product_id=_PRODUCT)
    session.add(row)
    session.commit()

    assert row.quantity_on_hand == Decimal("0")
    assert row.unit_cost == Decimal("0")
    assert row.total_value == Decimal("0")

    session.add(BatchValuation(firm_id=_FIRM, batch_id=batch.id, product_id=_PRODUCT))
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_firm_has_one_setting_and_starts_on_average(session: Session) -> None:
    """A row with nothing chosen is Average, and refuses a bill without stock."""
    row = StockLotSettings(firm_id=_FIRM)
    session.add(row)
    session.commit()

    assert row.costing_method == "AVERAGE"
    assert row.switched_on is None
    assert row.allow_billing_without_stock is False

    session.add(StockLotSettings(firm_id=_FIRM))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    row.is_deleted = True
    session.add(StockLotSettings(firm_id=_FIRM))
    session.commit()


def test_the_reset_clears_lot_values_with_the_product_values() -> None:
    """What a lot is worth goes with the movements that valued it."""
    from scripts.generate_transaction_history import RESET_ORDER

    assert "batch_valuations" in RESET_ORDER
    assert "batches" not in RESET_ORDER
