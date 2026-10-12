"""A TDS switch on each supplier and a TCS switch on each customer (backlog 113).

``vendors.tds_applicable`` and ``customers.tcs_applicable``, both NOT NULL and
both defaulting to true: every party already stored keeps being proposed and
charged exactly as it was, so there is nothing to backfill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where the store holds the table and lacks the column, because a
firm store is partly built by ``Base.metadata.create_all`` and can already
have it.

Revision ID: 20261013_0357
Revises: 20261013_0356
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0357"
down_revision: str | Sequence[str] | None = "20261013_0356"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SWITCHES = (("vendors", "tds_applicable"), ("customers", "tcs_applicable"))


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    """Say whether the table already has the column."""
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    """Add each switch where a store holds the table and lacks the column."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _SWITCHES:
        if not inspector.has_table(table):
            continue
        if not _has_column(inspector, table, column):
            op.add_column(
                table,
                sa.Column(
                    column,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                ),
            )


def downgrade() -> None:
    """Drop each switch where a store has it."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _SWITCHES:
        if inspector.has_table(table) and _has_column(inspector, table, column):
            op.drop_column(table, column)
