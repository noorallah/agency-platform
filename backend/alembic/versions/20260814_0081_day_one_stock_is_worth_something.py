"""Let opening stock carry what it was worth.

`opening_stock_lines` recorded a quantity and no cost, so day-one stock entered
the valuation at zero: a firm's entire starting inventory was worth nothing in
the stock valuation and nothing in the ledger. The two agreed, and agreed with
nothing real.

That is also what made posting opening stock pointless -- there was never a
value to post. `unit_cost` is nullable, because a firm that does not know what
its opening stock cost is better served recording the quantity than recording
nothing; such stock stays worth zero and posts no journal, as before.

Firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0081"
down_revision: str | Sequence[str] | None = "20260814_0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "opening_stock_lines"
_COLUMN = "unit_cost"


def _columns() -> set[str]:
    """Return the table's column names, asked for now."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the per-unit cost to opening stock lines."""
    present = _columns()
    if present and _COLUMN not in present:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    """Drop the per-unit cost."""
    if _COLUMN in _columns():
        op.drop_column(_TABLE, _COLUMN)
