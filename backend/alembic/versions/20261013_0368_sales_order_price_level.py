"""The price level a sales order names for itself (backlog 131, row M13).

* ``sales_orders.price_level_id``: the level this order is priced at where it
  is not the customer's usual one -- a retail customer buying at wholesale
  today. NULL is the customer's usual level, which is what every order
  already written means, so no row changes.

A bill typed directly raises an order, and the level it names is kept there,
so ``sales_invoices`` gains nothing.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column and
the foreign key are added only where ``sales_orders`` exists and lacks them,
because a firm store is partly built by ``Base.metadata.create_all``; the key
is declared only where the store holds ``price_levels``.

Revision ID: 20261013_0368
Revises: 20261013_0367
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0368"
down_revision: str | Sequence[str] | None = "20261013_0367"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_orders"
_COLUMN = "price_level_id"
_FK = "FK_sales_orders_price_level_id"


def upgrade() -> None:
    """Add the level an order names, and its key to the firm's levels."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
    keys = {key["name"] for key in inspector.get_foreign_keys(_TABLE)}
    if _FK not in keys and inspector.has_table("price_levels"):
        op.create_foreign_key(
            _FK, _TABLE, "price_levels", [_COLUMN], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    """Drop the key and the column; every order is the customer's usual again."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _FK in {key["name"] for key in inspector.get_foreign_keys(_TABLE)}:
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
