"""Give a physical count somewhere to live.

Counting a warehouse was the last inventory gap. It is a document rather than
an action: the sheet is drawn up from what the warehouse holds, walked over
hours by people with a clipboard, and posted once at the end -- so it has to
survive somebody closing a laptop, which an endpoint taking counted quantities
could not.

Posting turns each difference into a stock adjustment, and adjustments have
reached the general ledger since `20260814_0079`, so a count that finds twenty
missing cartons puts their value in the profit and loss without anybody keying
a journal.

Both tables are firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260814_0083"
down_revision: str | Sequence[str] | None = "20260814_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COUNTS = "physical_counts"
_LINES = "physical_count_lines"


def _has(table: str) -> bool:
    """Return whether a table exists in this store, asked for now."""
    return sa.inspect(op.get_bind()).has_table(table)


def _entity_columns() -> list[sa.Column]:
    """Return the columns every business entity carries.

    Checked against ``BaseEntity`` rather than written from memory: a list
    missing ``deleted_by`` and the timestamp server defaults shipped in
    `20260814_0076` and failed on the first real request.
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
    ]


def upgrade() -> None:
    """Create the count sheet and its lines."""
    if _has("inventories") and not _has(_COUNTS):
        op.create_table(
            _COUNTS,
            *_entity_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("warehouse_id", UUIDType(), nullable=False),
            sa.Column("count_number", sa.String(length=60), nullable=False),
            sa.Column("count_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("posted_by", UUIDType(), nullable=True),
            sa.UniqueConstraint(
                "firm_id", "count_number", name="UQ_physical_counts_firm_number"
            ),
        )
        op.create_index("IX_physical_counts_firm_id", _COUNTS, ["firm_id"])
        op.create_index(
            "IX_physical_counts_firm_status", _COUNTS, ["firm_id", "status"]
        )
        op.create_index(
            "IX_physical_counts_firm_date", _COUNTS, ["firm_id", "count_date"]
        )
        op.create_index(
            "IX_physical_counts_firm_warehouse", _COUNTS, ["firm_id", "warehouse_id"]
        )

    if _has(_COUNTS) and not _has(_LINES):
        op.create_table(
            _LINES,
            *_entity_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("physical_count_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=False),
            sa.Column("batch_id", UUIDType(), nullable=True),
            sa.Column(
                "expected_quantity",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
            sa.Column("counted_quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("variance_quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("transaction_id", UUIDType(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.UniqueConstraint(
                "physical_count_id",
                "line_number",
                name="UQ_physical_count_lines_line_number",
            ),
            sa.ForeignKeyConstraint(
                ["physical_count_id"],
                ["physical_counts.id"],
                name="FK_physical_count_lines_physical_count_id",
                ondelete="CASCADE",
            ),
        )
        op.create_index("IX_physical_count_lines_firm_id", _LINES, ["firm_id"])
        op.create_index("IX_physical_count_lines_count", _LINES, ["physical_count_id"])
        op.create_index(
            "IX_physical_count_lines_firm_product", _LINES, ["firm_id", "product_id"]
        )


def downgrade() -> None:
    """Drop the count sheet and its lines."""
    if _has(_LINES):
        op.drop_table(_LINES)
    if _has(_COUNTS):
        op.drop_table(_COUNTS)
