"""Give a numbering rule a year format (BILL_SERIES design section 15, part b).

``document_numbering_rules.year_format`` says how the year prints: ``NONE``,
``TWO_DIGIT`` (``26``), ``SHORT`` (``26-27``) or ``FULL`` (``2026-2027``).
The two older flags, ``include_financial_year`` and ``short_financial_year``,
are kept and stay in step with it.

The column is added NOT NULL with a ``NONE`` server default, then every row
is backfilled from its flags, so each existing firm prints exactly as it did:
a year, short -> ``SHORT``; a year, not short -> ``FULL``; no year ->
``NONE``. The ``UPDATE`` touches only rows still at the default whose flags
say they print a year, so a replay changes nothing -- a rule an administrator
set to ``NONE`` has its year flag off and is never matched.

``document_numbering_rules`` is firm-owned and lives in every firm store: run
``scripts/migrate_all_stores.py``.

Revision ID: 20261017_0397
Revises: 20261017_0396
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261017_0397"
down_revision: str | Sequence[str] | None = "20261017_0396"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_numbering_rules"
_COLUMN = "year_format"


def _has_table(table: str) -> bool:
    """Say whether ``table`` exists in this store."""
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    """Say whether ``table`` exists and already holds ``column``."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(row["name"] == column for row in inspector.get_columns(table))


def upgrade() -> None:
    """Add the column where the table is, and backfill it from the flags."""
    if not _has_table(_TABLE):
        return
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(length=20),
                server_default=sa.text("'NONE'"),
                nullable=False,
            ),
        )
    op.get_bind().execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = CASE "
            "WHEN short_financial_year = true THEN 'SHORT' ELSE 'FULL' END "
            f"WHERE {_COLUMN} = 'NONE' AND include_financial_year = true"
        )
    )


def downgrade() -> None:
    """Drop the column; the two flags carry the layout alone again."""
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
