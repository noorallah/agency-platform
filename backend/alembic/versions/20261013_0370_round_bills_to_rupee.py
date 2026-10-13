"""Round every bill to the nearest rupee, a firm setting (backlog 134).

``sales_workflow_settings`` gains ``round_bills_to_rupee``: whether the server
works the round-off out on every sales bill and credit note. NOT NULL and
false, which is how every firm already behaves, so there is nothing to
backfill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column is
added only where the store holds the table and lacks it, because a firm store
is partly built by ``Base.metadata.create_all`` and can already have it.

Revision ID: 20261013_0370
Revises: 20261013_0369
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0370"
down_revision: str | Sequence[str] | None = "20261013_0369"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_workflow_settings"
_COLUMN = "round_bills_to_rupee"


def _has_column(inspector: sa.Inspector) -> bool:
    """Say whether the store's table already has the column."""
    return _COLUMN in {item["name"] for item in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the column where a store holds the table and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE) or _has_column(inspector):
        return
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Drop the column where a store has it."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and _has_column(inspector):
        op.drop_column(_TABLE, _COLUMN)
