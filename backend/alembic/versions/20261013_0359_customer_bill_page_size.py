"""The paper a customer's bills print on (backlog 118).

``customers.bill_page_size``: ``HALF`` for half an A4 sheet, ``A4`` for a full
page. Nullable with no default -- blank takes the firm's own print setting,
which is how every customer already stored printed, so there is nothing to
backfill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column is
added only where the store holds the table and lacks it, because a firm store
is partly built by ``Base.metadata.create_all`` and can already have it.

Revision ID: 20261013_0359
Revises: 20261013_0358
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0359"
down_revision: str | Sequence[str] | None = "20261013_0358"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customers"
_COLUMN = "bill_page_size"


def _has_column(inspector: sa.Inspector) -> bool:
    """Say whether the store's table already has the column."""
    return _COLUMN in {item["name"] for item in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the column where a store holds the table and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if not _has_column(inspector):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=10), nullable=True))


def downgrade() -> None:
    """Drop the column where a store has it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _has_column(inspector):
        op.drop_column(_TABLE, _COLUMN)
