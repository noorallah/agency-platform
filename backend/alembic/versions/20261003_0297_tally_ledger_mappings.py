"""The firm's ledger names in its CA's Tally (MSG-5, decision A135).

``tally_ledger_mappings``: what one of our accounts is called, and grouped
under, in Tally.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0297
Revises: 20261003_0296
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0297"
down_revision: str | Sequence[str] | None = "20261003_0296"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the mapping table where a store keeps ledger accounts."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("ledger_accounts") or inspector.has_table(
        "tally_ledger_mappings"
    ):
        return
    op.create_table(
        "tally_ledger_mappings",
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
        sa.Column("ledger_account_id", UUIDType(), nullable=False),
        sa.Column("tally_name", sa.String(200), nullable=False),
        sa.Column("tally_parent", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_tally_ledger_mappings"),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            ["ledger_accounts.id"],
            name="FK_tally_ledger_mappings_ledger_account_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "IX_tally_ledger_mappings_firm_id", "tally_ledger_mappings", ["firm_id"]
    )
    op.create_index(
        "UQ_tally_ledger_mappings_account_active",
        "tally_ledger_mappings",
        ["firm_id", "ledger_account_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the mapping table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("tally_ledger_mappings"):
        op.drop_table("tally_ledger_mappings")
