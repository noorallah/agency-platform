"""The largest purchase order a role may approve (backlog 68 row 4).

* ``role_purchase_approval_limits``, per firm and role code -- the buying
  sibling of ``role_discount_limits`` (``20261001_0181``).

No new permission: reading the limits takes ``PURCHASE_VIEW`` and replacing
them ``PURCHASE_MANAGE_SETTINGS``, both already seeded.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0205"
down_revision: str | Sequence[str] | None = "20261001_0202"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_limits(inspector: sa.Inspector) -> None:
    """Create the per-firm, per-role approval limit table in a firm store."""
    if not inspector.has_table("purchase_orders"):
        return
    if inspector.has_table("role_purchase_approval_limits"):
        return
    op.create_table(
        "role_purchase_approval_limits",
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
        sa.Column("role_code", sa.String(100), nullable=False),
        sa.Column("max_order_amount", sa.Numeric(18, 2), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_role_purchase_approval_limits"),
    )
    op.create_index(
        "IX_role_purchase_approval_limits_firm_id",
        "role_purchase_approval_limits",
        ["firm_id"],
    )
    op.create_index(
        "UQ_role_purchase_approval_limits_firm_role_active",
        "role_purchase_approval_limits",
        ["firm_id", "role_code"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def upgrade() -> None:
    """Add the limit table to a firm store."""
    _create_limits(sa.inspect(op.get_bind()))


def downgrade() -> None:
    """Drop it."""
    if sa.inspect(op.get_bind()).has_table("role_purchase_approval_limits"):
        op.drop_table("role_purchase_approval_limits")
