"""Record what a movement changed about ownership.

Found by ``scripts/verify_sample_data.py`` while verifying sales returns:
cancelling one left the stock value 203.16 above the inventory control account.
The movement had said the firm owned two units more -- one sellable, one
damaged -- while the sellable bucket moved by one, and ``reverse_transaction``
mirrors the six bucket deltas and nothing else. It backed the quantity out and
left the value behind.

The figure lived only on the in-memory movement, so the reversal had no way to
know it. Persisting it also closes the same hole for the quarantine write-off,
which has carried an owned delta since it was written and had never been
reversed in anger.

NULL keeps its meaning -- ownership moved by exactly ``current_quantity_delta``
-- which is true of every movement written before now, so nothing is
backfilled.

``inventory_transactions`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0085"
down_revision: str | Sequence[str] | None = "20260814_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "inventory_transactions"
_COLUMN = "owned_quantity_delta"


def _has_column() -> bool:
    """Return whether the column is already there, asked for now."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return True
    return any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE))


def upgrade() -> None:
    """Add the nullable owned delta."""
    if not _has_column():
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    """Drop it again."""
    if _has_column() and sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_column(_TABLE, _COLUMN)
