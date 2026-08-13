"""Give stock movements a clock that advances within a request.

``created_at`` defaults to ``func.now()``, which in PostgreSQL is
``transaction_timestamp()``: every statement in a transaction reads the same
instant. For a business record that is honest -- the rows a purchase order
writes were created together. For a ledger it is a problem, because rows written
in one request are then **unorderable by time**.

Posting a delivery note writes UNRESERVE and then DISPATCH. Both carried the
same ``created_at`` to the microsecond, so ``GET /inventory/ledger``, which
sorts on it, could return them either way round -- and a running balance read
90, then 72, then 90 again. A tiebreaker on ``id`` already made paging safe
(the same row could otherwise appear on two pages), but ``id`` is a UUID4 and
carries no order, so the sequence stayed arbitrary.

``clock_timestamp()`` reads the wall clock per statement. It is still a value
the *database* evaluates, so the rule against reading the application server's
clock is untouched, and the column is still UTC.

Only the two movement tables change. Everywhere else, one instant for one
request is the better answer.

Existing rows keep the timestamps they were written with: no ordering can be
invented for movements that genuinely share an instant, and the id tiebreaker
keeps their order stable. New movements order correctly.

Both tables are firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0069"
down_revision: str | Sequence[str] | None = "20260812_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("inventory_transactions", "stock_ledger_entries")


def upgrade() -> None:
    """Point the movement tables at the statement clock."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table in _TABLES:
        # Firm-owned: the platform schema has neither.
        if not inspector.has_table(table):
            continue
        op.alter_column(
            table,
            "created_at",
            server_default=sa.text("clock_timestamp()"),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Put the transaction clock back."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        op.alter_column(
            table,
            "created_at",
            server_default=sa.text("now()"),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
