"""Record on a sales order the bill that raised it (D-SELL-54).

With the sales-order and delivery-note stages off, a bill typed straight in
raises an order and a note behind it, and the order's approval reserves the
stock. Cancelling the draft bill cancelled the note it raised and left the
order APPROVED with the quantity held -- no screen shows that order, so every
cancelled counter draft took its quantity out of available stock until later
sales of the product were refused.

``raised_by_sales_invoice_id`` names the bill that raised the order, and only
that bill's cancel withdraws it. A bare, nullable, indexed id, the same shape
as the one ``20260919_0146`` put on the delivery note: an order a person
raised, which a bill merely dispatched for a firm that types no notes, stays
NULL and is theirs to cancel.

Backfill, only where still NULL: an order is stamped with the bill that
stamped its note when order and bill were written in one transaction --
``created_at`` is the transaction's timestamp on PostgreSQL, so equal values
mean the chain raised the order in the bill's own save. A person's order was
written earlier and stays NULL. The backfill cancels nothing: an order left
approved by a draft cancelled before this revision is still cancelled by hand.

Idempotent: the column and index are added only where ``sales_orders`` exists
and lacks them, because firm stores are partly built by ``create_all``. The
table is firm-owned, so run this through ``scripts/migrate_all_stores.py``.

Revision ID: 20261005_0330
Revises: 20261005_0326
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0330"
down_revision: str | Sequence[str] | None = "20261005_0326"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_orders"
_COLUMN = "raised_by_sales_invoice_id"
_INDEX = "IX_sales_orders_raised_by_sales_invoice_id"

#: Pairs to stamp: the order, and the bill that raised it in its own save.
_RAISED_TOGETHER = sa.text(
    """
    SELECT DISTINCT o.id AS order_id, i.id AS invoice_id
    FROM sales_orders o
    JOIN delivery_notes n
      ON n.sales_order_id = o.id
     AND n.raised_by_sales_invoice_id IS NOT NULL
    JOIN sales_invoices i
      ON i.id = n.raised_by_sales_invoice_id
     AND i.created_at = o.created_at
    WHERE o.raised_by_sales_invoice_id IS NULL
    """
)


def upgrade() -> None:
    """Add the column and index where missing, then stamp the chain's orders."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        # The platform schema holds no firm-owned tables once pruned.
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN])
    if not (
        inspector.has_table("sales_invoices") and inspector.has_table("delivery_notes")
    ):
        return
    note_columns = {
        column["name"] for column in inspector.get_columns("delivery_notes")
    }
    if _COLUMN not in note_columns:
        return
    pairs = bind.execute(_RAISED_TOGETHER).mappings().all()
    for pair in pairs:
        bind.execute(
            sa.text(
                f"UPDATE {_TABLE} SET {_COLUMN} = :invoice_id "
                f"WHERE id = :order_id AND {_COLUMN} IS NULL"
            ),
            {"invoice_id": pair["invoice_id"], "order_id": pair["order_id"]},
        )


def downgrade() -> None:
    """Drop the index and the column where they exist."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
