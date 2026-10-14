"""A firm chooses the layout of its full-page bill (backlog 143).

* ``document_print_templates.bill_layout``: ``STANDARD`` (the bill every firm
  printed until now) or ``TRADE`` (the boxed bill the trade prints, laid out
  after the customer's own sample). NOT NULL with ``STANDARD`` as the server
  default, so every saved template keeps printing as it did.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so the column is added only
where it is missing.

Revision ID: 20261014_0381
Revises: 20261014_0380
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261014_0381"
down_revision: str | Sequence[str] | None = "20261014_0380"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_print_templates"
_COLUMN = "bill_layout"


def _has_column() -> bool:
    """Say whether this store's templates already carry the layout."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return True
    return any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE))


def upgrade() -> None:
    """Add the layout, STANDARD for every template already saved."""
    if _has_column():
        return
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.String(20),
            nullable=False,
            server_default="STANDARD",
        ),
    )


def downgrade() -> None:
    """Drop the layout; every bill prints in the standard layout again."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and any(
        column["name"] == _COLUMN for column in inspector.get_columns(_TABLE)
    ):
        op.drop_column(_TABLE, _COLUMN)
