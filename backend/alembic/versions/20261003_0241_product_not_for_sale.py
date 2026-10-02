"""Products marked not for sale (STK-17, decision A58).

`products.not_for_sale` holds packing material and consumables off every new
sales line. The DISCONTINUED status needs no migration: `products.status` is a
plain string. Every existing product stays for sale.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0241
Revises: 20261003_0240
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0241"
down_revision: str | Sequence[str] | None = "20261003_0240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "products"
_COLUMN = "not_for_sale"


def upgrade() -> None:
    """Add the flag, where the products table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    """Drop the flag."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
