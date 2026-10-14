"""Each lot a delivery line takes keeps its movement and its cost (L2 step 5).

* ``delivery_note_line_batches.inventory_transaction_id``: the stock movement
  that carried the lot out, a bare UUID as every downstream document records
  its source.
* ``delivery_note_line_batches.cost_amount``: what the lot's units cost when
  they left, read off the stock ledger at dispatch. Null on rows written
  before this revision and on picks not yet dispatched; the bill then reads
  the note's cost by product, as it did
  (``docs/design/LOT_COST_DESIGN.md``, sections 3.2 and 3.5).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so each column is added only
where it is missing. Nothing is backfilled.

Revision ID: 20261014_0385
Revises: 20261014_0384
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0385"
down_revision: str | Sequence[str] | None = "20261014_0384"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "delivery_note_line_batches"


def _columns() -> set[str] | None:
    """Return the table's column names, or None where the store has no table."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return None
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the movement and the cost, null on every row that exists."""
    present = _columns()
    if present is None:
        return
    if "inventory_transaction_id" not in present:
        op.add_column(
            _TABLE, sa.Column("inventory_transaction_id", UUIDType(), nullable=True)
        )
    if "cost_amount" not in present:
        op.add_column(
            _TABLE, sa.Column("cost_amount", sa.Numeric(18, 4), nullable=True)
        )


def downgrade() -> None:
    """Drop both columns; the bill reads the note's cost by product again."""
    present = _columns()
    if present is None:
        return
    for name in ("cost_amount", "inventory_transaction_id"):
        if name in present:
            op.drop_column(_TABLE, name)
