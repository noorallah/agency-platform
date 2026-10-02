"""Cheque printing offsets per bank account (ACC-12).

``cheque_layouts``: one live row per bank ledger account, holding how far the
firm's printer is off the CTS-2010 positions and whether to cross the cheque.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: created only in
a store that holds ledger accounts and lacks it.

Revision ID: 20261003_0247
Revises: 20261003_0246
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0247"
down_revision: str | Sequence[str] | None = "20261003_0246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "cheque_layouts"


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
        sa.Column(
            "offset_x_mm", sa.Numeric(5, 1), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "offset_y_mm", sa.Numeric(5, 1), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "print_ac_payee",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_cheque_layouts"),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            ["ledger_accounts.id"],
            name="FK_cheque_layouts_ledger_account_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_cheque_layouts_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_cheque_layouts_account_active",
        _TABLE,
        ["firm_id", "ledger_account_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
