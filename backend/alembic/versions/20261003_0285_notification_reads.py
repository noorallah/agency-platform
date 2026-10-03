"""What a person has seen on the bell (PLT-2, decision A123).

* ``notification_reads``: firm, person, notification key, when seen; one
  live mark per key. The notifications themselves are derived, not stored.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0285
Revises: 20261003_0284
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0285"
down_revision: str | Sequence[str] | None = "20261003_0284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the read marks where a firm's documents live."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no purchase orders.
    if not inspector.has_table("purchase_orders"):
        return
    if inspector.has_table("notification_reads"):
        return
    op.create_table(
        "notification_reads",
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
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("notification_key", sa.String(200), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_notification_reads"),
    )
    op.create_index("IX_notification_reads_firm_id", "notification_reads", ["firm_id"])
    op.create_index(
        "UQ_notification_reads_key_active",
        "notification_reads",
        ["firm_id", "user_id", "notification_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the read marks."""
    if sa.inspect(op.get_bind()).has_table("notification_reads"):
        op.drop_table("notification_reads")
