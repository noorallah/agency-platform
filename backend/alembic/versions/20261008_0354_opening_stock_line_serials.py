"""Serial numbers typed on an opening stock line (D-STK-40, backlog 90 gap 1).

``opening_stock_line_serials``: the serials typed or scanned on an opening
stock line, held while the document is a draft. Posting turns them into
``serial_numbers`` rows in the document's warehouse, linked to the line
through ``document_line_serials`` -- the shape ``goods_receipt_line_serials``
has for a receipt.

The serials a transfer names need no table of their own: they are
``document_line_serials`` rows, and the two statuses a transfer gives a unit
(``IN_TRANSIT``, ``DAMAGED``) are values of a plain text column.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only in a firm store (one holding ``opening_stock_lines``) that lacks
it. No ``firm_id`` foreign key: ``firms`` lives only in the platform store.

Revision ID: 20261008_0354
Revises: 20261008_0353
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261008_0354"
down_revision: str | Sequence[str] | None = "20261008_0353"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "opening_stock_line_serials"


def _base_columns() -> list[sa.Column[object]]:
    """Return the columns every ``BaseEntity`` table carries."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def upgrade() -> None:
    """Create the table where a firm store lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("opening_stock_lines") or inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("opening_stock_batch_id", UUIDType(), nullable=False),
        sa.Column("opening_stock_line_id", UUIDType(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("serial_number", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"PK_{_TABLE}"),
        sa.UniqueConstraint(
            "opening_stock_line_id",
            "position",
            name="UQ_opening_stock_line_serials_line_position",
        ),
        sa.ForeignKeyConstraint(
            ["opening_stock_batch_id"],
            ["opening_stock_batches.id"],
            name=f"FK_{_TABLE}_opening_stock_batch_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opening_stock_line_id"],
            ["opening_stock_lines.id"],
            name=f"FK_{_TABLE}_opening_stock_line_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(f"IX_{_TABLE}_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        f"IX_{_TABLE}_opening_stock_line_id", _TABLE, ["opening_stock_line_id"]
    )
    op.create_index(
        "IX_opening_stock_line_serials_firm_batch",
        _TABLE,
        ["firm_id", "opening_stock_batch_id"],
    )


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
