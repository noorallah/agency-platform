"""Stock transfer as a document (STK-1, decision A126).

* ``stock_transfers``: a numbered transfer from one warehouse to another,
  Draft, Dispatched, Received or Cancelled.
* ``stock_transfer_lines``: what was sent, and what arrived, arrived damaged
  or never arrived.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0288
Revises: 20261003_0287
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0288"
down_revision: str | Sequence[str] | None = "20261003_0287"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
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
    ]


def _money(name: str) -> sa.Column:  # type: ignore[type-arg]
    """Return a value column defaulting to zero."""
    return sa.Column(
        name, sa.Numeric(18, 4), server_default=sa.text("0"), nullable=False
    )


def upgrade() -> None:
    """Create both tables where a firm store lacks them."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no stock.
    if not inspector.has_table("inventory_transactions"):
        return
    if not inspector.has_table("stock_transfers"):
        op.create_table(
            "stock_transfers",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("transfer_number", sa.String(60), nullable=False),
            sa.Column("transfer_date", sa.Date(), nullable=False),
            sa.Column("from_branch_id", UUIDType(), nullable=False),
            sa.Column("from_warehouse_id", UUIDType(), nullable=False),
            sa.Column("to_branch_id", UUIDType(), nullable=False),
            sa.Column("to_warehouse_id", UUIDType(), nullable=False),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'DRAFT'"),
                nullable=False,
            ),
            sa.Column("dispatched_on", sa.Date(), nullable=True),
            sa.Column("received_on", sa.Date(), nullable=True),
            sa.Column("vehicle_number", sa.String(30), nullable=True),
            sa.Column("transporter_name", sa.String(200), nullable=True),
            _money("dispatched_value"),
            _money("shortage_value"),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("receipt_remarks", sa.Text(), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_stock_transfers"),
            sa.ForeignKeyConstraint(
                ["from_branch_id"],
                ["branches.id"],
                name="FK_stock_transfers_from_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["from_warehouse_id"],
                ["warehouses.id"],
                name="FK_stock_transfers_from_warehouse_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["to_branch_id"],
                ["branches.id"],
                name="FK_stock_transfers_to_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["to_warehouse_id"],
                ["warehouses.id"],
                name="FK_stock_transfers_to_warehouse_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_stock_transfers_firm_id", "stock_transfers", ["firm_id"])
        op.create_index(
            "IX_stock_transfers_firm_date",
            "stock_transfers",
            ["firm_id", "transfer_date"],
        )
    if not inspector.has_table("stock_transfer_lines"):
        op.create_table(
            "stock_transfer_lines",
            *_base_columns(),
            sa.Column("transfer_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=False),
            sa.Column("batch_id", UUIDType(), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column("received_quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("damaged_quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("short_quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("remarks", sa.String(500), nullable=True),
            sa.Column("dispatch_transaction_id", UUIDType(), nullable=True),
            sa.Column("transit_transaction_id", UUIDType(), nullable=True),
            sa.Column("receive_transaction_id", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_stock_transfer_lines"),
            sa.ForeignKeyConstraint(
                ["transfer_id"],
                ["stock_transfers.id"],
                name="FK_stock_transfer_lines_transfer_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="FK_stock_transfer_lines_product_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["batch_id"],
                ["batches.id"],
                name="FK_stock_transfer_lines_batch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["dispatch_transaction_id"],
                ["inventory_transactions.id"],
                name="FK_stock_transfer_lines_dispatch_transaction_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["transit_transaction_id"],
                ["inventory_transactions.id"],
                name="FK_stock_transfer_lines_transit_transaction_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["receive_transaction_id"],
                ["inventory_transactions.id"],
                name="FK_stock_transfer_lines_receive_transaction_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "IX_stock_transfer_lines_firm_id", "stock_transfer_lines", ["firm_id"]
        )
        op.create_index(
            "IX_stock_transfer_lines_transfer", "stock_transfer_lines", ["transfer_id"]
        )


def downgrade() -> None:
    """Drop both tables."""
    inspector = sa.inspect(op.get_bind())
    for table in ("stock_transfer_lines", "stock_transfers"):
        if inspector.has_table(table):
            op.drop_table(table)
