"""Record what customers owed at cutover, bill by bill (backlog 36).

* ``customer_opening_bills`` in every firm store -- the receivable twin of
  ``vendor_opening_bills`` (``20260930_0169``).
* ``settlement_allocations.customer_opening_bill_id``, so a receipt can clear
  one, with its own unique key and index beside the sales-invoice ones.

Nothing is backfilled: a customer's single-figure opening balance stays what it
is, and the two are never held together. Idempotent throughout; run per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260930_0172"
down_revision: str | Sequence[str] | None = "20260930_0170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column[object]]:
    """Return the ``BaseEntity`` columns, timestamps defaulted by the server."""
    return [
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
    ]


def upgrade() -> None:
    """Create the table and the allocation column in a firm store."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: customers exist in firm stores only.
    if not inspector.has_table("customers"):
        return
    if not inspector.has_table("customer_opening_bills"):
        op.create_table(
            "customer_opening_bills",
            *_audit_columns(),
            sa.Column("customer_id", UUIDType(), nullable=False),
            sa.Column("bill_number", sa.String(30), nullable=False),
            sa.Column("reference_number", sa.String(60), nullable=True),
            sa.Column("bill_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("posting_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("narration", sa.Text(), nullable=True),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'POSTED'"),
                nullable=False,
            ),
            sa.Column("journal_entry_id", UUIDType(), nullable=False),
            sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_by", UUIDType(), nullable=True),
            sa.Column("cancellation_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_customer_opening_bills"),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_customer_opening_bills_customer_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["journal_entry_id"],
                ["journal_entries.id"],
                name="FK_customer_opening_bills_journal_entry_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["reversal_journal_entry_id"],
                ["journal_entries.id"],
                name="FK_customer_opening_bills_reversal_journal_entry_id",
                ondelete="RESTRICT",
            ),
            sa.CheckConstraint(
                "amount > 0", name="CK_customer_opening_bills_amount_positive"
            ),
            sa.UniqueConstraint(
                "firm_id", "bill_number", name="UQ_customer_opening_bills_firm_number"
            ),
        )
        op.create_index(
            "IX_customer_opening_bills_firm_id", "customer_opening_bills", ["firm_id"]
        )
        op.create_index(
            "IX_customer_opening_bills_firm_customer",
            "customer_opening_bills",
            ["firm_id", "customer_id"],
        )

    columns = {
        column["name"] for column in inspector.get_columns("settlement_allocations")
    }
    if "customer_opening_bill_id" not in columns:
        op.add_column(
            "settlement_allocations",
            sa.Column("customer_opening_bill_id", UUIDType(), nullable=True),
        )
        op.create_foreign_key(
            "FK_settlement_allocations_customer_opening_bill_id",
            "settlement_allocations",
            "customer_opening_bills",
            ["customer_opening_bill_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_unique_constraint(
            "UQ_settlement_allocations_customer_opening_bill",
            "settlement_allocations",
            ["settlement_id", "customer_opening_bill_id"],
        )
        op.create_index(
            "IX_settlement_allocations_customer_opening_bill",
            "settlement_allocations",
            ["firm_id", "customer_opening_bill_id"],
        )


def downgrade() -> None:
    """Drop the column and the table."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("settlement_allocations"):
        return
    columns = {
        column["name"] for column in inspector.get_columns("settlement_allocations")
    }
    if "customer_opening_bill_id" in columns:
        op.drop_index(
            "IX_settlement_allocations_customer_opening_bill",
            table_name="settlement_allocations",
        )
        op.drop_constraint(
            "UQ_settlement_allocations_customer_opening_bill",
            "settlement_allocations",
            type_="unique",
        )
        op.drop_constraint(
            "FK_settlement_allocations_customer_opening_bill_id",
            "settlement_allocations",
            type_="foreignkey",
        )
        op.drop_column("settlement_allocations", "customer_opening_bill_id")
    if inspector.has_table("customer_opening_bills"):
        op.drop_table("customer_opening_bills")
