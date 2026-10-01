"""The batches a delivery line takes, as a person chose them (backlog 79).

* ``delivery_note_line_batches``: one row per batch a delivery note line draws
  from, with the quantity in stock units. None means earliest expiry first at
  dispatch, as before.

No permission codes: the picks are written with the note, and the batch
availability read takes ``BATCH_VIEW``, ``INVENTORY_VIEW`` or ``SALES_VIEW``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0214
Revises: 20261002_0213
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0214"
down_revision: str | Sequence[str] | None = "20261002_0213"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
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
    """Create the table where this store holds delivery notes and batches."""
    inspector = sa.inspect(op.get_bind())
    if not (
        inspector.has_table("delivery_note_lines") and inspector.has_table("batches")
    ):
        return
    if inspector.has_table("delivery_note_line_batches"):
        return
    op.create_table(
        "delivery_note_line_batches",
        *_base_columns(),
        sa.Column("delivery_note_line_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("batch_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_note_line_id"],
            ["delivery_note_lines.id"],
            name="FK_delivery_note_line_batches_delivery_note_line_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            name="FK_delivery_note_line_batches_batch_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "IX_delivery_note_line_batches_line",
        "delivery_note_line_batches",
        ["delivery_note_line_id"],
    )
    op.create_index(
        "IX_delivery_note_line_batches_firm_id",
        "delivery_note_line_batches",
        ["firm_id"],
    )


def downgrade() -> None:
    """Drop the table where it exists."""
    if sa.inspect(op.get_bind()).has_table("delivery_note_line_batches"):
        op.drop_table("delivery_note_line_batches")
