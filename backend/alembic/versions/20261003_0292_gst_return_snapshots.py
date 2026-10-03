"""Filed GSTR-1 snapshots (GST-6, decision A130).

``gst_return_snapshots``: the GSTR-1 a filing reported, as it stood when
marked filed; later changes are amendments read against it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0292
Revises: 20261003_0291
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0292"
down_revision: str | Sequence[str] | None = "20261003_0291"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the snapshot table where a store keeps filings."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("gst_return_filings"):
        return
    if inspector.has_table("gst_return_snapshots"):
        return
    op.create_table(
        "gst_return_snapshots",
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
        sa.Column("filing_id", UUIDType(), nullable=False),
        sa.Column("return_type", sa.String(10), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_gst_return_snapshots"),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["gst_return_filings.id"],
            name="FK_gst_return_snapshots_filing_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "IX_gst_return_snapshots_firm_id", "gst_return_snapshots", ["firm_id"]
    )
    op.create_index(
        "IX_gst_return_snapshots_filing_id", "gst_return_snapshots", ["filing_id"]
    )
    op.create_index(
        "IX_gst_return_snapshots_firm_period",
        "gst_return_snapshots",
        ["firm_id", "from_date"],
    )


def downgrade() -> None:
    """Drop the snapshot table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("gst_return_snapshots"):
        op.drop_table("gst_return_snapshots")
