"""Movements need a clock that advances inside a request.

``func.now()`` is PostgreSQL's ``transaction_timestamp()``: every statement in a
transaction reads the same instant, so every row one request writes carries the
same ``created_at`` to the microsecond. That is the right answer for a business
record and the wrong one for a ledger, which is read as a chronology.

Posting a delivery note writes UNRESERVE and then DISPATCH. Sharing an instant
made them unorderable, and ``GET /inventory/ledger`` -- which sorts on
``created_at`` -- could return them either way round, so a running balance read
90, then 72, then 90 again. A tiebreaker on ``id`` already kept paging safe, but
a UUID4 carries no order, so the sequence stayed arbitrary.
"""

from sqlalchemy import func
from sqlalchemy.dialects import postgresql, sqlite

from app.core.database.clock import statement_now
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.products.models import Product


def test_the_statement_clock_advances_on_postgresql() -> None:
    """``clock_timestamp()`` is the one PostgreSQL function that moves."""
    compiled = str(statement_now().compile(dialect=postgresql.dialect()))
    assert compiled == "clock_timestamp()"
    assert compiled != "now()", "transaction_timestamp cannot order one request"


def test_the_statement_clock_still_compiles_on_sqlite() -> None:
    """The unit suite builds its schema on SQLite, which has no such function."""
    compiled = str(statement_now().compile(dialect=sqlite.dialect()))
    assert compiled == "CURRENT_TIMESTAMP"


def test_both_movement_tables_use_the_statement_clock() -> None:
    """The ledger and the transactions behind it must agree on their clock."""
    for model in (InventoryTransaction, StockLedgerEntry):
        default = model.__table__.c.created_at.server_default
        assert default is not None, f"{model.__name__} lost its created_at default"
        rendered = str(default.arg.compile(dialect=postgresql.dialect()))
        assert rendered == "clock_timestamp()", (
            f"{model.__name__}.created_at is on {rendered}, which gives every row "
            "in a request the same instant and leaves the ledger unorderable."
        )


def test_ordinary_records_keep_the_transaction_clock() -> None:
    """Ordinary records keep one instant per request, deliberately.

    One instant for one request is the better answer for a business record: the
    rows a purchase order writes were created together, and saying so is
    honest. Only the tables read as a chronology need the wall clock.
    """
    default = Product.__table__.c.created_at.server_default
    assert default is not None
    assert str(default.arg.compile(dialect=postgresql.dialect())) == str(
        func.now().compile(dialect=postgresql.dialect())
    )
