"""A bill remembers whether its discount was typed as an amount or a rate.

``sales_invoices.bill_discount_typed_as`` -- ``amount`` or ``percent``, as the
bill discount was last stated on the bill; NULL where it was never stated. A
bill keeps both figures, and an edit that left the discount out carried it as
the four-place **rate**, so a typed 25.00 came back as 25.0001 (D-PRC-35).
An amount is now carried as the amount.

Every typed bill discount stored before this revision was carried as its
rate, so those rows are backfilled ``percent`` -- what they already do --
and only rows still at NULL, so a replay cannot overwrite a later save.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0341
Revises: 20261006_0340
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0341"
down_revision: str | Sequence[str] | None = "20261006_0340"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_invoices"
_COLUMN = "bill_discount_typed_as"


def upgrade() -> None:
    """Add the column where the store keeps bills, and mark the typed ones."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(10), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = 'percent' "
            f"WHERE {_COLUMN} IS NULL AND bill_discount_source = 'typed'"
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
