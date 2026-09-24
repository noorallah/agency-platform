"""A cancelled sales invoice says when it was cancelled (D-FIN-21).

An ageing as of a past day left out an invoice cancelled after that day,
because a cancellation carried no timestamp: on that day the bill was owed,
and only its status said otherwise. ``sales_invoices.cancelled_at`` records
the moment; rows already CANCELLED are backfilled from ``updated_at``, which
is the last write -- the cancel itself for every invoice nothing touched
afterwards -- and only where the column is still empty, so a replay cannot
overwrite a real timestamp.

Firm-owned, so run it through ``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0158
Revises: 20260924_0157
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0158"
down_revision: str | Sequence[str] | None = "20260924_0157"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``cancelled_at`` where it is missing and backfill it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("sales_invoices"):
        return
    columns = {column["name"] for column in inspector.get_columns("sales_invoices")}
    if "cancelled_at" not in columns:
        op.add_column(
            "sales_invoices",
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(
        sa.text(
            "UPDATE sales_invoices SET cancelled_at = updated_at "
            "WHERE status = 'CANCELLED' AND cancelled_at IS NULL"
        )
    )


def downgrade() -> None:
    """Drop ``cancelled_at`` where it exists."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("sales_invoices"):
        return
    columns = {column["name"] for column in inspector.get_columns("sales_invoices")}
    if "cancelled_at" in columns:
        op.drop_column("sales_invoices", "cancelled_at")
