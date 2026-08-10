"""Phase 16B enterprise batch, lot, serial number, and expiry management."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260801_0020"
down_revision: str | Sequence[str] | None = "20260801_0019"
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
    # 1. Add tracking flag columns to products
    op.add_column(
        "products",
        sa.Column(
            "track_batch", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "track_lot", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "track_serial",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "track_expiry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "track_manufacturing_date",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "track_warranty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "allow_negative_stock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "require_batch_on_receipt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "require_batch_on_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "require_serial_on_receipt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "require_serial_on_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 2. Create batches table
    op.create_table(
        "batches",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(length=100), nullable=False),
        sa.Column("supplier_batch", sa.String(length=100), nullable=True),
        sa.Column("internal_batch", sa.String(length=100), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("best_before_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="AVAILABLE"
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "available_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "reserved_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "blocked_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "damaged_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "quarantine_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("shelf_life_days", sa.Integer(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "firm_id",
            "batch_number",
            "product_id",
            name="UQ_batches_firm_batch_product",
        ),
    )
    op.create_index("IX_batches_firm_id", "batches", ["firm_id"])
    op.create_index("IX_batches_firm_product", "batches", ["firm_id", "product_id"])
    op.create_index("IX_batches_firm_status", "batches", ["firm_id", "status"])
    op.create_index("IX_batches_expiry_date", "batches", ["firm_id", "expiry_date"])

    # 3. Create lots table
    op.create_table(
        "lots",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("parent_lot_id", sa.Uuid(), nullable=True),
        sa.Column("lot_number", sa.String(length=100), nullable=False),
        sa.Column(
            "lot_type",
            sa.String(length=50),
            nullable=False,
            server_default="PRODUCTION",
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "available_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_lot_id"], ["lots.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "firm_id", "lot_number", "product_id", name="UQ_lots_firm_lot_product"
        ),
    )
    op.create_index("IX_lots_firm_id", "lots", ["firm_id"])
    op.create_index("IX_lots_firm_product", "lots", ["firm_id", "product_id"])
    op.create_index("IX_lots_firm_status", "lots", ["firm_id", "status"])

    # 4. Create serial_numbers table
    op.create_table(
        "serial_numbers",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("serial_number", sa.String(length=200), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="AVAILABLE"
        ),
        sa.Column("manufactured_date", sa.Date(), nullable=True),
        sa.Column("warranty_start", sa.Date(), nullable=True),
        sa.Column("warranty_end", sa.Date(), nullable=True),
        sa.Column("current_owner", sa.String(length=200), nullable=True),
        sa.Column("asset_reference", sa.String(length=200), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inventory_id"], ["inventories.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "firm_id",
            "serial_number",
            "product_id",
            name="UQ_serial_numbers_firm_serial_product",
        ),
    )
    op.create_index("IX_serial_numbers_firm_id", "serial_numbers", ["firm_id"])
    op.create_index(
        "IX_serial_numbers_firm_product", "serial_numbers", ["firm_id", "product_id"]
    )
    op.create_index(
        "IX_serial_numbers_firm_status", "serial_numbers", ["firm_id", "status"]
    )

    # 5. Add FK columns to inventory_transactions
    op.add_column(
        "inventory_transactions", sa.Column("batch_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "inventory_transactions", sa.Column("lot_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "inventory_transactions", sa.Column("serial_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "FK_inventory_transactions_batch_id",
        "inventory_transactions",
        "batches",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "FK_inventory_transactions_lot_id",
        "inventory_transactions",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "FK_inventory_transactions_serial_id",
        "inventory_transactions",
        "serial_numbers",
        ["serial_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "IX_inventory_transactions_batch_id", "inventory_transactions", ["batch_id"]
    )
    op.create_index(
        "IX_inventory_transactions_lot_id", "inventory_transactions", ["lot_id"]
    )
    op.create_index(
        "IX_inventory_transactions_serial_id", "inventory_transactions", ["serial_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "IX_inventory_transactions_serial_id", table_name="inventory_transactions"
    )
    op.drop_index(
        "IX_inventory_transactions_lot_id", table_name="inventory_transactions"
    )
    op.drop_index(
        "IX_inventory_transactions_batch_id", table_name="inventory_transactions"
    )
    op.drop_constraint(
        "FK_inventory_transactions_serial_id",
        "inventory_transactions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "FK_inventory_transactions_lot_id", "inventory_transactions", type_="foreignkey"
    )
    op.drop_constraint(
        "FK_inventory_transactions_batch_id",
        "inventory_transactions",
        type_="foreignkey",
    )
    op.drop_column("inventory_transactions", "serial_id")
    op.drop_column("inventory_transactions", "lot_id")
    op.drop_column("inventory_transactions", "batch_id")

    op.drop_index("IX_serial_numbers_firm_status", table_name="serial_numbers")
    op.drop_index("IX_serial_numbers_firm_product", table_name="serial_numbers")
    op.drop_index("IX_serial_numbers_firm_id", table_name="serial_numbers")
    op.drop_table("serial_numbers")

    op.drop_index("IX_lots_firm_status", table_name="lots")
    op.drop_index("IX_lots_firm_product", table_name="lots")
    op.drop_index("IX_lots_firm_id", table_name="lots")
    op.drop_table("lots")

    op.drop_index("IX_batches_expiry_date", table_name="batches")
    op.drop_index("IX_batches_firm_status", table_name="batches")
    op.drop_index("IX_batches_firm_product", table_name="batches")
    op.drop_index("IX_batches_firm_id", table_name="batches")
    op.drop_table("batches")

    op.drop_column("products", "require_serial_on_issue")
    op.drop_column("products", "require_serial_on_receipt")
    op.drop_column("products", "require_batch_on_issue")
    op.drop_column("products", "require_batch_on_receipt")
    op.drop_column("products", "allow_negative_stock")
    op.drop_column("products", "track_warranty")
    op.drop_column("products", "track_manufacturing_date")
    op.drop_column("products", "track_expiry")
    op.drop_column("products", "track_serial")
    op.drop_column("products", "track_lot")
    op.drop_column("products", "track_batch")
