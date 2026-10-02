"""A shelf life on the product (STK-18, decision A59).

`products.shelf_life_days` is how long the product keeps from manufacture. A
goods receipt typed with only a manufacturing date gets its expiry from it.
Nullable: a product with none fills nothing, as before.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0242
Revises: 20261003_0241
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0242"
down_revision: str | Sequence[str] | None = "20261003_0241"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "products"
_COLUMN = "shelf_life_days"


def upgrade() -> None:
    """Add the shelf life, where the products table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    """Drop the shelf life."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
