"""Let a receivable movement point at the journal it posted.

An opening balance needs it. Changing one has to mirror the entry the old
figure wrote, and searching the ledger by source module would not tell an
opening balance apart from the credit notes and refunds the same customer
raises -- they all post from `customers`.

Nullable, and nothing is backfilled: the balances already recorded posted no
journal at all, which is the defect `post_opening_balance` closes going
forward. `docs/BACKLOG.md` §12 describes reconciling the ones already on the
books, which needs a firm to decide the date it wants them booked at.

``customer_receivable_transactions`` is firm-owned: run
``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260815_0088"
down_revision: str | Sequence[str] | None = "20260815_0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customer_receivable_transactions"
_COLUMN = "journal_entry_id"


def _has_column() -> bool:
    """Return whether the column is already there, asked for now."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return True
    return any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE))


def upgrade() -> None:
    """Add the nullable journal reference."""
    if not _has_column():
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))


def downgrade() -> None:
    """Drop it again."""
    if _has_column() and sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_column(_TABLE, _COLUMN)
