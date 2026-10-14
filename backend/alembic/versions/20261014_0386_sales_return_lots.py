"""Which lots a sales return line put its goods back into (L2 step 6).

* ``sales_return_line_batches``: one row per lot a completed return line
  refilled, with the quantity in stock units, what the movement carried and
  the movement itself (a bare id). Keyed to ``sales_return_lines`` (CASCADE)
  and ``batches`` (RESTRICT), both firm-owned and in every firm store, so no
  key crosses a schema (``docs/design/LOT_COST_DESIGN.md``, section 3.2).

Returns completed before this revision name no lot rows and are not gone
back over.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so the table is created only
where it is missing.

Revision ID: 20261014_0386
Revises: 20261014_0385
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0386"
down_revision: str | Sequence[str] | None = "20261014_0385"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_return_line_batches"


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails (`20260903_0114`).
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def upgrade() -> None:
    """Create the table where the store holds return lines and batches."""
    inspector = sa.inspect(op.get_bind())
    # The platform store holds neither, and the keys below would point at
    # tables it does not have.
    if (
        not inspector.has_table("sales_return_lines")
        or not inspector.has_table("batches")
        or inspector.has_table(_TABLE)
    ):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column(
            "sales_return_line_id",
            UUIDType(),
            sa.ForeignKey(
                "sales_return_lines.id",
                ondelete="CASCADE",
                name="FK_sales_return_line_batches_sales_return_line_id",
            ),
            nullable=False,
        ),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "batch_id",
            UUIDType(),
            sa.ForeignKey(
                "batches.id",
                ondelete="RESTRICT",
                name="FK_sales_return_line_batches_batch_id",
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("cost_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
    )
    op.create_index(
        "IX_sales_return_line_batches_line", _TABLE, ["sales_return_line_id"]
    )
    op.create_index(
        "IX_sales_return_line_batches_firm_batch", _TABLE, ["firm_id", "batch_id"]
    )


def downgrade() -> None:
    """Drop the table: a return line names one batch again."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
