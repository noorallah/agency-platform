"""Let a settlement be taken back.

A receipt keyed against the wrong customer, or for the wrong amount, could not
be corrected: settlements shipped without a reversal because undoing one has to
unwind the customer's outstanding *and* advance balances by the exact amounts
it moved them, and a wrong reversal is worse than none.

`customer_receivable_transactions` already stores `outstanding_delta` and
`advance_delta` per row, which is what makes an exact undo possible -- a receipt
of 500 against an outstanding 300 became 300 off the balance and 200 of advance,
and only the row itself remembers that split.

The settlement gains what it needs to show the correction: the mirror journal
that cancelled it, when, by whom, and why. Nothing is deleted -- money recorded
and then unrecorded is a fact about the day.

``settlements`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260814_0077"
down_revision: str | Sequence[str] | None = "20260814_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "settlements"
_COLUMNS = {
    "reversal_journal_entry_id": sa.Column(
        "reversal_journal_entry_id", UUIDType(), nullable=True
    ),
    "reversed_at": sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
    "reversed_by": sa.Column("reversed_by", UUIDType(), nullable=True),
    "reversal_reason": sa.Column("reversal_reason", sa.Text(), nullable=True),
}


def _existing() -> set[str]:
    """Return the column names the table already has, asked for now.

    A single ``Inspector`` caches what it has seen, which silently skipped a
    table in `20260814_0076`; this asks the database each time.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the reversal columns where the settlements table exists."""
    present = _existing()
    if not present:
        return
    for name, column in _COLUMNS.items():
        if name not in present:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    """Drop the reversal columns."""
    present = _existing()
    for name in _COLUMNS:
        if name in present:
            op.drop_column(_TABLE, name)
