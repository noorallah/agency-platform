"""A deposit can name the order it came in against.

`settlements.sales_order_id` records *why* the money arrived. It is a note, not
a ring-fence: the cash is the customer's balance either way, and if the order is
cancelled the deposit does not vanish -- it stays on account. What the link buys
is an answer to "what has this customer paid us for order X", and a way for the
bill raised against that order to find the deposit.

Nullable and unset on every existing row, so nothing changes for a firm that
never names one.

The other half of the feature needs no schema at all: `ADVANCE_APPLY` has been a
declared receivable transaction type since the settlements module shipped and
**nothing could reach it**, so a deposit taken before the bill existed sat on
the account with no way to say which bill it settled.
`POST /api/v1/receipts/{id}/allocate` is that missing action, and it writes only
rows these tables already had.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0123
Revises: 20260903_0122
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260903_0123"
down_revision: str | Sequence[str] | None = "20260903_0122"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "settlements"
_COLUMN = "sales_order_id"
_INDEX = "IX_settlements_firm_order"
_FK = "FK_settlements_sales_order_id"


def upgrade() -> None:
    """Add the order link where a firm store lacks it.

    The foreign key is declared only where `sales_orders` is present, the way
    every cross-table reference in a firm store has to be: `settlements` and
    `sales_orders` live together in a firm schema, but the platform store has
    neither and a firm store part-built by `Base.metadata.create_all` may have
    one without the other.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
    op.create_index(_INDEX, _TABLE, ["firm_id", _COLUMN])
    if inspector.has_table("sales_orders"):
        op.create_foreign_key(
            _FK, _TABLE, "sales_orders", [_COLUMN], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    """Drop the link, losing which order each deposit came in against."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    names = {constraint["name"] for constraint in inspector.get_foreign_keys(_TABLE)}
    if _FK in names:
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    if _INDEX in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
