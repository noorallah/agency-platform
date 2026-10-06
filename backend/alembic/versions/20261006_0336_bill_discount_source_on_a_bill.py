"""A bill says whether its bill discount was typed or inherited (D-PRC-1).

``sales_invoices.bill_discount_source`` -- ``typed`` when the bill itself
stated the discount on the whole document, ``inherited`` when it is the share
agreed on the order the bill continues, NULL when it carries none. A bill now
inherits its order's, and the two must stay apart afterwards: only a typed one
is judged against the approver's discount limit, and only a typed one is
carried across an edit that leaves it out.

Every bill discount stored before this revision was typed on its bill, because
nothing was inherited, so those rows are backfilled ``typed`` -- only rows
still at NULL, so a replay cannot overwrite what a later save recorded.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0336
Revises: 20261006_0335
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0336"
down_revision: str | Sequence[str] | None = "20261006_0335"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_invoices"
_COLUMN = "bill_discount_source"


def upgrade() -> None:
    """Add the column where the store keeps bills, and mark the typed ones."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(20), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = 'typed' "
            f"WHERE {_COLUMN} IS NULL AND bill_discount_amount > 0"
        )
    )


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
