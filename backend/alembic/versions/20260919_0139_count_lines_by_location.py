"""Give a physical count line the storage location it counts (D-STK-13).

A count line named a product and a batch and nothing about where in the
warehouse it was. The variance was measured against every location's stock
summed, and posted onto the warehouse's unlocated ROOT row -- so a warehouse
keeping stock in bins got the right total and the wrong rows: goods missing
from BIN-A came off ROOT, which could go negative, while BIN-A kept stock that
was not there.

A sheet now carries one line per stock row -- product, batch and storage
location, exactly as the stock is held -- and posts each difference back onto
that row. ``storage_node_id`` is nullable and additive: NULL is the ROOT row,
which is what every existing line counted, so no backfill is needed. No
foreign key, like ``batch_id`` beside it: the line records what was counted,
and a location retired later must not make the sheet unreadable.

The table is firm-owned, so run this through ``migrate-all`` on every store.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260919_0139"
#: Follows D-STK-4's ``20260919_0138`` (document_line_serials, PR #465), which
#: merges first; two revisions off 0137 would leave two heads.
down_revision: str | Sequence[str] | None = "20260919_0138"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "physical_count_lines"
_COLUMN = "storage_node_id"


def _has_column(inspector: sa.Inspector) -> bool:
    """Return whether the line table already carries the column."""
    return any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE))


def upgrade() -> None:
    """Add the nullable column where the table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        # The platform schema holds no firm-owned tables once pruned.
        return
    if _has_column(inspector):
        # A store built by ``create_all`` from the current models has it.
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))


def downgrade() -> None:
    """Drop the column where it exists."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and _has_column(inspector):
        op.drop_column(_TABLE, _COLUMN)
