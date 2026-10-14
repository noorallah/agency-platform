"""Boxes and pieces on one line: the columns (L5, step 1).

Row L5 of ``docs/CUSTOMER_BUILD_TASKS.md``, step 1 of
``docs/design/BOX_AND_PIECE_LINE_DESIGN.md`` (section 3.8):

* ``pack_uom_id`` (FK ``uoms.id`` RESTRICT, ``FK_<table>_pack_uom_id``) and
  ``pack_size`` (Numeric(18,4)) on the nine selling and buying line tables:
  the pack a line's quantity is shown in, as it was when the line was written.
* ``box_and_piece_entry`` (Boolean, not null, default false) on the nine
  document headers (the layout a document was saved in), on
  ``sales_workflow_settings`` and ``purchase_workflow_settings`` (the firm's
  switch for each side), and on ``customers`` and ``vendors`` (the party's
  documents open with the box cells).

Nothing is backfilled: every existing line has no pack and every switch is
off, so a firm behaves exactly as before. Nothing reads the columns yet.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and the column does not, and the foreign
key only where ``uoms`` is in the same store.

Revision ID: 20261015_0389
Revises: 20261015_0388
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261015_0389"
down_revision: str | Sequence[str] | None = "20261015_0388"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINE_TABLES = (
    "sales_quotation_lines",
    "sales_order_lines",
    "delivery_note_lines",
    "sales_invoice_lines",
    "sales_return_lines",
    "purchase_order_lines",
    "goods_receipt_lines",
    "purchase_invoice_lines",
    "purchase_return_lines",
)
_ENTRY_TABLES = (
    "sales_quotations",
    "sales_orders",
    "delivery_notes",
    "sales_invoices",
    "sales_returns",
    "purchase_orders",
    "goods_receipts",
    "purchase_invoices",
    "purchase_returns",
    "sales_workflow_settings",
    "purchase_workflow_settings",
    "customers",
    "vendors",
)


def _present(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the names of the columns ``table`` already has."""
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the pack columns, the switches and the marks where missing."""
    inspector = sa.inspect(op.get_bind())
    has_uoms = inspector.has_table("uoms")
    for table in _LINE_TABLES:
        if not inspector.has_table(table):
            continue
        present = _present(inspector, table)
        if "pack_uom_id" not in present:
            op.add_column(table, sa.Column("pack_uom_id", UUIDType(), nullable=True))
        held = any(
            key["constrained_columns"] == ["pack_uom_id"]
            for key in inspector.get_foreign_keys(table)
        )
        if has_uoms and not held:
            op.create_foreign_key(
                op.f(f"FK_{table}_pack_uom_id"),
                table,
                "uoms",
                ["pack_uom_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if "pack_size" not in present:
            op.add_column(
                table, sa.Column("pack_size", sa.Numeric(18, 4), nullable=True)
            )
    for table in _ENTRY_TABLES:
        if not inspector.has_table(table):
            continue
        if "box_and_piece_entry" not in _present(inspector, table):
            op.add_column(
                table,
                sa.Column(
                    "box_and_piece_entry",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )


def downgrade() -> None:
    """Drop the pack columns, the switches and the marks where present."""
    inspector = sa.inspect(op.get_bind())
    for table in _ENTRY_TABLES:
        if inspector.has_table(table) and "box_and_piece_entry" in _present(
            inspector, table
        ):
            op.drop_column(table, "box_and_piece_entry")
    for table in _LINE_TABLES:
        if not inspector.has_table(table):
            continue
        present = _present(inspector, table)
        if "pack_size" in present:
            op.drop_column(table, "pack_size")
        if "pack_uom_id" in present:
            keys = {key["name"] for key in inspector.get_foreign_keys(table)}
            if f"FK_{table}_pack_uom_id" in keys:
                op.drop_constraint(f"FK_{table}_pack_uom_id", table, type_="foreignkey")
            op.drop_column(table, "pack_uom_id")
