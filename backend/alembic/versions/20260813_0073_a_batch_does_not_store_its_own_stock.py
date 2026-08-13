"""Stop `batches` keeping its own copy of the stock it holds.

Six columns -- ``quantity``, ``available_quantity``, ``reserved_quantity``,
``blocked_quantity``, ``damaged_quantity``, ``quarantine_quantity`` -- were
written by the batch API and reconciled against `inventories` by nothing. A
batch could claim ten on the shelf while no stock row anywhere held any of it,
and every movement that went through a document rather than the batch endpoint
widened the gap. The seeded demo store had exactly that: one batch claiming ten
units, and zero batch-tracked stock rows.

They survived stage two of batch-grained stock because ``create_batch`` took
quantity as an input and nothing could derive it yet. Since `inventories` is
keyed by batch, it can: ``InventoryService.stock_by_batch`` sums the stock rows
carrying a batch, and the API reports that instead. A batch is a register entry
-- number, supplier, expiry, status -- and how much of it is on the shelf is a
consequence of the movements that put it there.

The numbers are not migrated anywhere. There is nowhere to put them: a quantity
with no movement behind it is exactly what the stock ledger exists to refuse,
and writing one now would invent history. A batch whose stored figure was right
already has the stock rows that say so.

``downgrade`` restores the columns at zero. The stored figures are gone and
cannot be recovered -- reversing this migration gives back the shape, not the
data.

``batches`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0073"
down_revision: str | Sequence[str] | None = "20260813_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "batches"
_COLUMNS = (
    "quantity",
    "available_quantity",
    "reserved_quantity",
    "blocked_quantity",
    "damaged_quantity",
    "quarantine_quantity",
)


def upgrade() -> None:
    """Drop the stored quantities, leaving the stock rows as the one answer."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return  # platform schema: firm-owned tables are not there.
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _COLUMNS:
        if column in present:
            op.drop_column(_TABLE, column)


def downgrade() -> None:
    """Put the columns back, at zero. The figures they held are gone."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _COLUMNS:
        if column not in present:
            op.add_column(
                _TABLE,
                sa.Column(
                    column,
                    sa.Numeric(18, 4),
                    nullable=False,
                    server_default="0",
                ),
            )
