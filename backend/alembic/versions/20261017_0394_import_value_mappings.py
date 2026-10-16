"""A saved import mapping also maps values (Swathi plan, gap G6 part 2).

``import_mappings.value_mapping``: nullable JSON, ``{column: {source value:
our value}}``, so a firm moving from Tally, Marg, Busy or Swathi keeps how its
old program's head names read as our account groups beside the heading
mapping it already keeps. Null means no value is translated.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column is
added only where the table exists and lacks it.

Revision ID: 20261017_0394
Revises: 20261017_0393
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261017_0394"
down_revision: str | Sequence[str] | None = "20261017_0393"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "import_mappings"
_COLUMN = "value_mapping"


def _has_column() -> bool:
    """Say whether the table exists and already holds the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return False
    return any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE))


def upgrade() -> None:
    """Add the column in a store whose table lacks it."""
    if not sa.inspect(op.get_bind()).has_table(_TABLE) or _has_column():
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop the column; saved value mappings are lost."""
    if _has_column():
        op.drop_column(_TABLE, _COLUMN)
