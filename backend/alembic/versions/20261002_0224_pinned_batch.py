"""A sales order line may pin the batch the customer asked for (79 row 4).

``sales_order_lines.pinned_batch_id``: approval holds that batch and no other,
and a delivery note raised from the line starts with it picked.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent; the foreign key
is declared only where ``batches`` lives.

Revision ID: 20261002_0224
Revises: 20261002_0223
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0224"
down_revision: str | Sequence[str] | None = "20261002_0223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_order_lines"
_COLUMN = "pinned_batch_id"


def upgrade() -> None:
    """Add the column and, where batches live, its foreign key."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
    if inspector.has_table("batches"):
        op.create_foreign_key(
            f"FK_{_TABLE}_{_COLUMN}",
            _TABLE,
            "batches",
            [_COLUMN],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Drop the column; orders take earliest expiry again."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and _COLUMN in {
        column["name"] for column in inspector.get_columns(_TABLE)
    }:
        op.drop_column(_TABLE, _COLUMN)
