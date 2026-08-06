"""Phase 16A enterprise inventory foundation."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260801_0019"
down_revision: str | Sequence[str] | None = "20260801_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    op.create_table(
        "inventories",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("storage_locator", sa.String(length=80), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("current_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("reserved_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("available_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("blocked_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("damaged_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quarantine_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("in_transit_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("minimum_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("maximum_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("reorder_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("safety_stock", sa.Numeric(18, 4), nullable=True),
        sa.Column("last_transaction_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "firm_id",
            "branch_id",
            "warehouse_id",
            "storage_locator",
            "product_id",
            name="UQ_inventories_location_product",
        ),
    )
    op.create_index("IX_inventories_firm_id", "inventories", ["firm_id"])
    op.create_index("IX_inventories_firm_product", "inventories", ["firm_id", "product_id"])
    op.create_index("IX_inventories_firm_status", "inventories", ["firm_id", "status"])
    op.create_index("IX_inventories_firm_warehouse", "inventories", ["firm_id", "warehouse_id"])
    op.create_index("IX_inventories_firm_branch", "inventories", ["firm_id", "branch_id"])

    op.create_table(
        "inventory_transactions",
        *_base_columns(),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("reference_number", sa.String(length=80), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("reserved_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("blocked_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("damaged_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quarantine_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("in_transit_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("previous_current_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_current_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_available_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_available_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_blocked_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_blocked_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_damaged_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_damaged_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_quarantine_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_quarantine_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_in_transit_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_in_transit_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "IX_inventory_transactions_firm_id", "inventory_transactions", ["firm_id"]
    )
    op.create_index(
        "IX_inventory_transactions_firm_date",
        "inventory_transactions",
        ["firm_id", "transaction_date"],
    )
    op.create_index(
        "IX_inventory_transactions_firm_type",
        "inventory_transactions",
        ["firm_id", "transaction_type"],
    )
    op.create_index(
        "IX_inventory_transactions_firm_product",
        "inventory_transactions",
        ["firm_id", "product_id"],
    )
    op.create_index(
        "IX_inventory_transactions_firm_reference",
        "inventory_transactions",
        ["firm_id", "reference_type"],
    )

    op.create_table(
        "stock_ledger_entries",
        *_base_columns(),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("reference_number", sa.String(length=80), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("reserved_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("blocked_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("damaged_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quarantine_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("in_transit_quantity_delta", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("previous_current_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_current_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_available_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_available_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_blocked_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_blocked_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_damaged_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_damaged_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_quarantine_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_quarantine_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("previous_in_transit_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("new_in_transit_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["inventory_transactions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("transaction_id", name="UQ_stock_ledger_entries_transaction_id"),
    )
    op.create_index("IX_stock_ledger_entries_firm_id", "stock_ledger_entries", ["firm_id"])
    op.create_index(
        "IX_stock_ledger_entries_firm_date",
        "stock_ledger_entries",
        ["firm_id", "transaction_date"],
    )
    op.create_index(
        "IX_stock_ledger_entries_firm_product",
        "stock_ledger_entries",
        ["firm_id", "product_id"],
    )
    op.create_index(
        "IX_stock_ledger_entries_firm_warehouse",
        "stock_ledger_entries",
        ["firm_id", "warehouse_id"],
    )
    op.create_index(
        "IX_stock_ledger_entries_firm_type",
        "stock_ledger_entries",
        ["firm_id", "transaction_type"],
    )

    op.create_table(
        "opening_stock_batches",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("reference_number", sa.String(length=80), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("source_format", sa.String(length=20), nullable=False, server_default="MANUAL"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "firm_id", "reference_number", name="UQ_opening_stock_batches_reference"
        ),
    )
    op.create_index("IX_opening_stock_batches_firm_id", "opening_stock_batches", ["firm_id"])
    op.create_index(
        "IX_opening_stock_batches_firm_date",
        "opening_stock_batches",
        ["firm_id", "posting_date"],
    )
    op.create_index(
        "IX_opening_stock_batches_firm_status",
        "opening_stock_batches",
        ["firm_id", "status"],
    )

    op.create_table(
        "opening_stock_lines",
        *_base_columns(),
        sa.Column("opening_stock_batch_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("storage_locator", sa.String(length=80), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("minimum_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("maximum_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("reorder_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("safety_stock", sa.Numeric(18, 4), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["opening_stock_batch_id"], ["opening_stock_batches.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["inventory_transactions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "opening_stock_batch_id",
            "line_number",
            name="UQ_opening_stock_lines_batch_line",
        ),
        sa.UniqueConstraint(
            "opening_stock_batch_id",
            "product_id",
            "storage_locator",
            name="UQ_opening_stock_lines_batch_product_location",
        ),
    )
    op.create_index(
        "IX_opening_stock_lines_batch_id", "opening_stock_lines", ["opening_stock_batch_id"]
    )


def downgrade() -> None:
    op.drop_index("IX_opening_stock_lines_batch_id", table_name="opening_stock_lines")
    op.drop_table("opening_stock_lines")

    op.drop_index("IX_opening_stock_batches_firm_status", table_name="opening_stock_batches")
    op.drop_index("IX_opening_stock_batches_firm_date", table_name="opening_stock_batches")
    op.drop_index("IX_opening_stock_batches_firm_id", table_name="opening_stock_batches")
    op.drop_table("opening_stock_batches")

    op.drop_index("IX_stock_ledger_entries_firm_type", table_name="stock_ledger_entries")
    op.drop_index("IX_stock_ledger_entries_firm_warehouse", table_name="stock_ledger_entries")
    op.drop_index("IX_stock_ledger_entries_firm_product", table_name="stock_ledger_entries")
    op.drop_index("IX_stock_ledger_entries_firm_date", table_name="stock_ledger_entries")
    op.drop_index("IX_stock_ledger_entries_firm_id", table_name="stock_ledger_entries")
    op.drop_table("stock_ledger_entries")

    op.drop_index(
        "IX_inventory_transactions_firm_reference", table_name="inventory_transactions"
    )
    op.drop_index(
        "IX_inventory_transactions_firm_product", table_name="inventory_transactions"
    )
    op.drop_index("IX_inventory_transactions_firm_type", table_name="inventory_transactions")
    op.drop_index("IX_inventory_transactions_firm_date", table_name="inventory_transactions")
    op.drop_index("IX_inventory_transactions_firm_id", table_name="inventory_transactions")
    op.drop_table("inventory_transactions")

    op.drop_index("IX_inventories_firm_branch", table_name="inventories")
    op.drop_index("IX_inventories_firm_warehouse", table_name="inventories")
    op.drop_index("IX_inventories_firm_status", table_name="inventories")
    op.drop_index("IX_inventories_firm_product", table_name="inventories")
    op.drop_index("IX_inventories_firm_id", table_name="inventories")
    op.drop_table("inventories")
