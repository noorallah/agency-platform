"""A settlement allocation remembers the day the money met the bill (D-TER-6).

Commission and sales targets counted a collection in the period of the
receipt's ``settlement_date``, and ``POST /receipts/{id}/allocate`` adds a
later application to that same receipt -- so an advance taken in August and
applied to a September bill was August's collection, in a period whose payout
might already be paid. The allocation now carries its own date: the
settlement's for an allocation made with the money, the bill's for an advance
applied to a bill raised since. ``net_sales.collected_net`` reads it, so the
commission report, the clawback re-read and the target achievement all move
together.

One nullable column on ``settlement_allocations``, backfilled from the
settlement's date where NULL -- which is exactly what every existing row
meant, because until now nothing could be applied on any other day. Readers
fall back to the settlement date for any row still NULL, so the column being
nullable changes no answer.

Idempotent: the column is added only where the table exists (the platform
schema holds no firm data once pruned) and is missing, and the backfill
touches only rows still NULL, so a replay overwrites nothing. Firm-owned, so
run it through ``scripts/migrate_all_stores.py``.

Revision ID: 20260920_0152
Revises: 20260920_0150
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0152"
down_revision: str | Sequence[str] | None = "20260920_0150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "settlement_allocations"
_COLUMN = "allocated_on"


def upgrade() -> None:
    """Add the column where it is missing and date the rows that have none."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Date(), nullable=True))
    # Only rows still undated: a replay must not move a date that was set by
    # the service after the column arrived.
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = ("
            "SELECT settlements.settlement_date FROM settlements "
            f"WHERE settlements.id = {_TABLE}.settlement_id"
            f") WHERE {_COLUMN} IS NULL"
        )
    )


def downgrade() -> None:
    """Drop the column; readers fall back to the settlement's date."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
