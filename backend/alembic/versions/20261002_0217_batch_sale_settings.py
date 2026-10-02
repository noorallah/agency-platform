"""A firm's rules for which batches go out on a sale (backlog 79 row 6).

``batch_sale_settings``, one row per firm: how many days before expiry a batch
counts as near expiry (30), whether a near-expiry batch leaving needs a reason
(WARN or REASON), whether drawing a later batch ahead of an earlier one needs
a reason (RECORD or REASON), and whether a line wholly from near-expiry
batches may be sold below its price floor (decision A2, on). A firm with no
row shares those defaults.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0217
Revises: 20261002_0216
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0217"
down_revision: str | Sequence[str] | None = "20261002_0216"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "batch_sale_settings"


def upgrade() -> None:
    """Create the per-firm rules table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    # A firm store holds batches; the platform store does not need the rules.
    if not inspector.has_table("batches") or inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
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
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "near_expiry_days", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column(
            "near_expiry_policy", sa.String(10), server_default="WARN", nullable=False
        ),
        sa.Column(
            "fefo_skip_policy", sa.String(10), server_default="RECORD", nullable=False
        ),
        sa.Column(
            "near_expiry_below_floor",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_batch_sale_settings"),
    )
    op.create_index("IX_batch_sale_settings_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_batch_sale_settings_firm_active",
        _TABLE,
        ["firm_id"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    """Drop the rules table; every firm falls back to the defaults."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
