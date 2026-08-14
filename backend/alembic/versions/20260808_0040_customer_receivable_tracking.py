"""Add customer receivable tracking balances and transaction ledger.

Revision ID: 20260808_0040
Revises: 20260807_0039
Create Date: 2026-08-08 01:35:00.000000
"""

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision = "20260808_0040"
down_revision = "20260807_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the customer receivable tracking balances and transaction ledger."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("customers"):
        return
    # Firm schemas may already carry these objects: they are created directly by
    # Base.metadata.create_all in the sample-data and tenancy-reset scripts. Guard
    # each step so replaying this revision against such a schema is a no-op
    # instead of a DuplicateColumn / DuplicateTable failure.
    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "current_outstanding" not in columns:
        op.add_column(
            "customers",
            sa.Column(
                "current_outstanding",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
            ),
        )
    if "unapplied_advance_balance" not in columns:
        op.add_column(
            "customers",
            sa.Column(
                "unapplied_advance_balance",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
            ),
        )
    # Seed only rows that are still at their defaults. On a fresh column that is
    # every row; on a schema where the columns already existed it leaves any
    # balance the application has since computed untouched.
    op.execute(
        sa.text(
            """
            UPDATE customers
            SET current_outstanding =
                    CASE WHEN opening_balance > 0
                         THEN opening_balance ELSE 0 END,
                unapplied_advance_balance =
                    CASE WHEN opening_balance < 0
                         THEN ABS(opening_balance) ELSE 0 END
            WHERE current_outstanding = 0
              AND unapplied_advance_balance = 0
              AND opening_balance <> 0
            """
        )
    )
    if inspector.has_table("customer_receivable_transactions"):
        return
    op.create_table(
        "customer_receivable_transactions",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("transaction_type", sa.String(40), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("outstanding_delta", sa.Numeric(18, 2), nullable=False),
        sa.Column("advance_delta", sa.Numeric(18, 2), nullable=False),
        sa.Column("outstanding_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("advance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference_type", sa.String(40), nullable=True),
        sa.Column("reference_id", UUIDType(), nullable=True),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_customer_receivable_transactions_firm_id",
        "customer_receivable_transactions",
        ["firm_id"],
    )
    op.create_index(
        "IX_customer_receivable_transactions_customer_id",
        "customer_receivable_transactions",
        ["customer_id"],
    )
    op.create_index(
        "IX_customer_ar_tx_customer_date",
        "customer_receivable_transactions",
        ["customer_id", "transaction_date"],
    )
    op.create_index(
        "IX_customer_ar_tx_firm_type",
        "customer_receivable_transactions",
        ["firm_id", "transaction_type"],
    )


def downgrade() -> None:
    """Reverse the customer receivable tracking balances and transaction ledger."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("customers"):
        return
    if inspector.has_table("customer_receivable_transactions"):
        op.drop_index(
            "IX_customer_ar_tx_firm_type", table_name="customer_receivable_transactions"
        )
        op.drop_index(
            "IX_customer_ar_tx_customer_date",
            table_name="customer_receivable_transactions",
        )
        op.drop_index(
            "IX_customer_receivable_transactions_customer_id",
            table_name="customer_receivable_transactions",
        )
        op.drop_index(
            "IX_customer_receivable_transactions_firm_id",
            table_name="customer_receivable_transactions",
        )
        op.drop_table("customer_receivable_transactions")
    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "unapplied_advance_balance" in columns:
        op.drop_column("customers", "unapplied_advance_balance")
    if "current_outstanding" in columns:
        op.drop_column("customers", "current_outstanding")
