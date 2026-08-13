"""Let a receipt and a dispatch name a real batch, not a string.

``goods_receipt_lines.batch_number`` and ``delivery_note_lines.batch_number``
are free text -- what the storeman read off the carton. ``batches`` is a keyed
register. Nothing joined them, so the goods on the shelf and the batch record
of the same delivery were two unrelated facts, and the ledger carried neither.

Stage two of making the batch the grain of stock:

* ``goods_receipt_lines.batch_id`` -- what the typed number resolved to.
  Receiving now creates the batch when the number is new, because goods that
  have physically arrived have to be receivable; a mistyped number is
  recoverable afterwards, a blocked receipt stops a warehouse.
* ``delivery_note_lines.batch_id`` -- the batch a line shipped from, chosen by
  earliest expiry. A line spanning two batches posts one movement per batch and
  records the first here; the movements carry the whole split.

The text columns stay. They are what was written on the paperwork, and a batch
record created later must not silently rewrite the history of a receipt.

Both tables are firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260813_0071"
down_revision: str | Sequence[str] | None = "20260813_0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("goods_receipt_lines", "delivery_note_lines")


def upgrade() -> None:
    """Point both document lines at the batch register."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in _TABLES:
        if not inspector.has_table(table):
            continue  # platform schema: firm-owned tables are not there.
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "batch_id" in columns:
            continue
        op.add_column(table, sa.Column("batch_id", UUIDType(), nullable=True))
        op.create_foreign_key(
            f"FK_{table}_batch_id",
            table,
            "batches",
            ["batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"IX_{table}_batch_id", table, ["batch_id"])


def downgrade() -> None:
    """Return both lines to carrying only the typed number."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "batch_id" not in columns:
            continue
        if f"IX_{table}_batch_id" in {
            index["name"] for index in inspector.get_indexes(table)
        }:
            op.drop_index(f"IX_{table}_batch_id", table_name=table)
        op.drop_constraint(f"FK_{table}_batch_id", table, type_="foreignkey")
        op.drop_column(table, "batch_id")
