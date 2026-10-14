"""The order lots leave in, on PostgreSQL (L2 step 4).

PostgreSQL sorts NULLs first in ascending order and SQLite last, so a lot with
no expiry or no received date could leave first on one and last on the other.
The ranking is explicit; this proves it on the database the firms run on.
"""

from datetime import date

from sqlalchemy.orm import Session

from tests.unit.test_lot_choosing import _Shop


def test_lots_leave_by_expiry_then_received_then_reference(
    temp_session: Session,
) -> None:
    """Dated expiry first, then oldest received, undated lots last."""
    shop = _Shop(by_lot=True, session=temp_session)
    undated = shop.lot("LOT-0001", received_on=None)
    later = shop.lot("LOT-0002", received_on=date(2026, 9, 1))
    no_expiry = shop.lot("LOT-0003", received_on=date(2026, 8, 1))
    expiring = shop.lot(
        "LOT-0004",
        received_on=date(2026, 9, 5),
        number="B1",
        expiry=date(2027, 1, 1),
    )
    tie_b = shop.lot("LOT-0006", received_on=date(2026, 7, 1))
    tie_a = shop.lot("LOT-0005", received_on=date(2026, 7, 1))

    order = [lot for lot, _ in shop.split("60")]

    assert order == [expiring, tie_a, tie_b, no_expiry, later, undated]
    assert [row.batch_id for row in shop.picker()] == order
