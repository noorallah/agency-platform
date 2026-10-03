"""The firm's own bank account details (ACC-4, decision A81).

``bank_account_details``: one live row per bank ledger account -- bank, account
name and number, IFSC, branch, kind, SWIFT, UPI -- and at most one per firm
marked to print on documents.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: created only in
a store that holds ledger accounts and lacks it.

Revision ID: 20261003_0254
Revises: 20261003_0253
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0254"
down_revision: str | Sequence[str] | None = "20261003_0253"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "bank_account_details"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("ledger_accounts") or inspector.has_table(_TABLE):
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
        sa.Column("ledger_account_id", UUIDType(), nullable=False),
        sa.Column("bank_name", sa.String(150), nullable=False),
        sa.Column("account_name", sa.String(150), nullable=False),
        sa.Column("account_number", sa.String(64), nullable=False),
        sa.Column("ifsc", sa.String(16), nullable=True),
        sa.Column("branch", sa.String(120), nullable=True),
        sa.Column("account_kind", sa.String(20), nullable=True),
        sa.Column("swift_code", sa.String(16), nullable=True),
        sa.Column("upi_id", sa.String(120), nullable=True),
        sa.Column(
            "print_on_documents",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_bank_account_details"),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            ["ledger_accounts.id"],
            name="FK_bank_account_details_ledger_account_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_bank_account_details_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_bank_account_details_account_active",
        _TABLE,
        ["firm_id", "ledger_account_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )
    op.create_index(
        "UQ_bank_account_details_printed_active",
        _TABLE,
        ["firm_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE AND print_on_documents IS TRUE"),
    )


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
