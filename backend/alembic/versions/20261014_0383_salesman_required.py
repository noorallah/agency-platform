"""A firm may require a salesman on every order, delivery note and bill (P2).

* ``sales_workflow_settings.salesman_required``: NOT NULL, ``false`` as the
  server default, so every firm saves as it did until it switches the rule on
  (``docs/design/SALESMAN_LIST_DESIGN.md``, section 6).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so the column is added only
where it is missing.

Revision ID: 20261014_0383
Revises: 20261014_0382
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261014_0383"
down_revision: str | Sequence[str] | None = "20261014_0382"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_workflow_settings"
_COLUMN = "salesman_required"


def _has_column() -> bool:
    """Say whether this store's sales settings already carry the switch."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return True
    return any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE))


def upgrade() -> None:
    """Add the switch, off for every firm."""
    if _has_column():
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
    """Drop the switch; no firm requires a salesman again."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and any(
        column["name"] == _COLUMN for column in inspector.get_columns(_TABLE)
    ):
        op.drop_column(_TABLE, _COLUMN)
