"""A counter bill paid several ways: cash, UPI, card (SEL-12, decision A90).

``sales_invoice_tenders``: each way a bill's counter payment was made, which
becomes its own receipt when the bill is approved.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0261
Revises: 20261003_0260
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0261"
down_revision: str | Sequence[str] | None = "20261003_0260"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_invoice_tenders"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) or not inspector.has_table("sales_invoices"):
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
        sa.Column("sales_invoice_id", UUIDType(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("settlement_id", UUIDType(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_sales_invoice_tenders"),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"],
            ["sales_invoices.id"],
            name="FK_sales_invoice_tenders_sales_invoice_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("IX_sales_invoice_tenders_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_sales_invoice_tenders_invoice", _TABLE, ["sales_invoice_id"])


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
