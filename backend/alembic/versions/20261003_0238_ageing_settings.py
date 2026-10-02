"""The ageing bands a firm reads its receivables and payables in (ACC-6).

``ageing_settings``: one row per firm, ``bucket_days`` the boundaries after
the first band, ascending and comma separated. ``30,60,90`` -- the default,
also what a firm with no row gets -- is the 0-29 / 30-59 / 60-89 / 90+ the
ageing has always used.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: created only in
a store that holds journals and lacks it.

Revision ID: 20261003_0238
Revises: 20261002_0237
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0238"
down_revision: str | Sequence[str] | None = "20261002_0237"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "ageing_settings"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("journal_entries") or inspector.has_table(_TABLE):
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
            "bucket_days",
            sa.String(40),
            server_default="30,60,90",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_ageing_settings"),
        sa.UniqueConstraint("firm_id", name="UQ_ageing_settings_firm"),
    )
    op.create_index("IX_ageing_settings_firm_id", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the table; every firm ages in 0-29 / 30-59 / 60-89 / 90+ again."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
