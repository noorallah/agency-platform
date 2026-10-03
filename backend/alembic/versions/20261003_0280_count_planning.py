"""Count planning: plans and blind sheets (STK-6, decision A117).

* ``count_plans``: warehouse, ABC class or bin, frequency, blind.
* ``physical_counts.count_plan_id`` and ``physical_counts.is_blind``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0280
Revises: 20261003_0279
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0280"
down_revision: str | Sequence[str] | None = "20261003_0279"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the plans and add the sheet columns where missing."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("physical_counts"):
        return
    have = {c["name"] for c in inspector.get_columns("physical_counts")}
    if "count_plan_id" not in have:
        op.add_column("physical_counts", sa.Column("count_plan_id", UUIDType()))
    if "is_blind" not in have:
        op.add_column(
            "physical_counts",
            sa.Column(
                "is_blind", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    if inspector.has_table("count_plans"):
        return
    op.create_table(
        "count_plans",
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
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("warehouse_id", UUIDType(), nullable=False),
        sa.Column("abc_class", sa.String(1), nullable=True),
        sa.Column("storage_node_id", UUIDType(), nullable=True),
        sa.Column("frequency_days", sa.Integer(), nullable=False),
        sa.Column(
            "blind", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_count_plans"),
    )
    op.create_index("IX_count_plans_firm_id", "count_plans", ["firm_id"])


def downgrade() -> None:
    """Drop the plans and the sheet columns."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("count_plans"):
        op.drop_table("count_plans")
    if inspector.has_table("physical_counts"):
        have = {c["name"] for c in inspector.get_columns("physical_counts")}
        for column in ("count_plan_id", "is_blind"):
            if column in have:
                op.drop_column("physical_counts", column)
