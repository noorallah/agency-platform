"""A person's usual branch and warehouse in a firm (backlog 44).

``user_work_defaults``: one live row per firm and person, naming the branch
and warehouse their new documents open with. Kept in the firm's own store
beside the branches it names; ``users`` lives in the platform store, so the
person is a plain UUID with no key.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261001_0177
Revises: 20261001_0176
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0177"
down_revision: str | Sequence[str] | None = "20261001_0176"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_work_defaults"


def upgrade() -> None:
    """Create the table where a firm store with branches lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("branches") or not inspector.has_table("warehouses"):
        return
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
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
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=True),
        sa.Column("warehouse_id", UUIDType(), nullable=True),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name="FK_user_work_defaults_branch_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="FK_user_work_defaults_warehouse_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_user_work_defaults_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_user_work_defaults_firm_user_active",
        _TABLE,
        ["firm_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )


def downgrade() -> None:
    """Drop the table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
