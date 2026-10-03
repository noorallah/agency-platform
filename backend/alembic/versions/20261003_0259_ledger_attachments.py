"""Files kept with journals, receipts and payments (ACC-10, decision A88).

``ledger_attachments``: one file reference backing a journal entry or a
settlement -- never both -- in the shape of ``stock_attachments`` (STK-9).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0259
Revises: 20261003_0258
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0259"
down_revision: str | Sequence[str] | None = "20261003_0258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "ledger_attachments"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if (
        inspector.has_table(_TABLE)
        or not inspector.has_table("journal_entries")
        or not inspector.has_table("settlements")
    ):
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
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("settlement_id", UUIDType(), nullable=True),
        sa.Column("file_name", sa.String(260), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("caption", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_ledger_attachments"),
        sa.CheckConstraint(
            "(journal_entry_id IS NULL) <> (settlement_id IS NULL)",
            name="CK_ledger_attachments_one_parent",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="FK_ledger_attachments_journal_entry_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["settlements.id"],
            name="FK_ledger_attachments_settlement_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("IX_ledger_attachments_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_ledger_attachments_journal", _TABLE, ["journal_entry_id"])
    op.create_index("IX_ledger_attachments_settlement", _TABLE, ["settlement_id"])


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
