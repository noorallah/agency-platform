"""TDS on the purchase of goods, section 194Q: a firm's settings (ACC-8).

``tds_194q_settings``: one row per firm -- the switch (off), the fifty-lakh
threshold, 0.1% and 5% without a PAN. No row reads as those defaults.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: created only in
a store that holds vendors and lacks it.

Revision ID: 20261003_0251
Revises: 20261003_0250
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0251"
down_revision: str | Sequence[str] | None = "20261003_0250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "tds_194q_settings"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("vendors") or inspector.has_table(_TABLE):
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
            "is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "threshold_amount",
            sa.Numeric(18, 2),
            server_default=sa.text("5000000"),
            nullable=False,
        ),
        sa.Column(
            "rate_percent",
            sa.Numeric(6, 3),
            server_default=sa.text("0.1"),
            nullable=False,
        ),
        sa.Column(
            "rate_without_pan_percent",
            sa.Numeric(6, 3),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_tds_194q_settings"),
        sa.UniqueConstraint("firm_id", name="UQ_tds_194q_settings_firm"),
    )
    op.create_index("IX_tds_194q_settings_firm_id", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
