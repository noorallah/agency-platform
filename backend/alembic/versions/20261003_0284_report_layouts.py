"""A person's saved layouts of the analysis screens (RPT-1, decision A121).

* ``report_layouts``: firm, person, report, name and the screen's settings;
  one live layout per name.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0284
Revises: 20261003_0283
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0284"
down_revision: str | Sequence[str] | None = "20261003_0283"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the layouts table where a firm's documents live."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no sales invoices.
    if not inspector.has_table("sales_invoices"):
        return
    if inspector.has_table("report_layouts"):
        return
    op.create_table(
        "report_layouts",
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
        sa.Column("report_code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_report_layouts"),
    )
    op.create_index("IX_report_layouts_firm_id", "report_layouts", ["firm_id"])
    op.create_index(
        "UQ_report_layouts_name_active",
        "report_layouts",
        ["firm_id", "user_id", "report_code", "name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the layouts table."""
    if sa.inspect(op.get_bind()).has_table("report_layouts"):
        op.drop_table("report_layouts")
