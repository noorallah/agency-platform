"""A product names the supplier it is normally bought from (decision A18).

``products.preferred_vendor_id``: reorder raises its draft orders with this
supplier, and falls back to the one last billed where none is set or the one
set is no longer live and active.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent; the foreign key
is declared only where ``vendors`` lives.

Revision ID: 20261002_0221
Revises: 20261002_0220
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0221"
down_revision: str | Sequence[str] | None = "20261002_0220"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "products"
_COLUMN = "preferred_vendor_id"


def upgrade() -> None:
    """Add the column, its index and, where vendors live, its foreign key."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
        if inspector.has_table("vendors"):
            op.create_foreign_key(
                f"FK_{_TABLE}_{_COLUMN}",
                _TABLE,
                "vendors",
                [_COLUMN],
                ["id"],
                ondelete="RESTRICT",
            )
    if f"IX_{_TABLE}_{_COLUMN}" not in {
        index["name"] for index in inspector.get_indexes(_TABLE)
    }:
        op.create_index(f"IX_{_TABLE}_{_COLUMN}", _TABLE, [_COLUMN])


def downgrade() -> None:
    """Drop the column; reorder goes back to the supplier last billed."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and _COLUMN in {
        column["name"] for column in inspector.get_columns(_TABLE)
    }:
        op.drop_column(_TABLE, _COLUMN)
