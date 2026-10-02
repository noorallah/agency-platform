"""Saved column mappings for file imports (decision B3).

``import_mappings``: one firm's named mapping of a source's headings onto one
import's template -- "Tally ledger export" for customers, say -- kept so the
next export from the same software maps itself.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0226
Revises: 20261002_0225
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0226"
down_revision: str | Sequence[str] | None = "20261002_0225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "import_mappings"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    # A firm store holds products; the platform store has no imports.
    if not inspector.has_table("products") or inspector.has_table(_TABLE):
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
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_import_mappings"),
    )
    op.create_index("IX_import_mappings_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_import_mappings_firm_kind_name_active",
        _TABLE,
        ["firm_id", "kind", "name"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    """Drop the table; saved mappings are lost, imports work as before."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
