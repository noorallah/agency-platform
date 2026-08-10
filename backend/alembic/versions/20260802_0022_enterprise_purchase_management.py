"""Enterprise purchase management foundation."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_0022"
down_revision: str | Sequence[str] | None = "20260802_0021"
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
        "purchase_orders",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=True),
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("po_number", sa.String(length=60), nullable=False),
        sa.Column("vendor_contact", sa.String(length=200), nullable=True),
        sa.Column("vendor_address", sa.String(length=500), nullable=True),
        sa.Column("department", sa.String(length=120), nullable=True),
        sa.Column(
            "purchase_type",
            sa.String(length=30),
            nullable=False,
            server_default="STANDARD_PURCHASE",
        ),
        sa.Column("purchase_category", sa.String(length=120), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("payment_terms", sa.String(length=200), nullable=True),
        sa.Column("delivery_terms", sa.String(length=200), nullable=True),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("reference_number", sa.String(length=80), nullable=True),
        sa.Column("external_reference", sa.String(length=80), nullable=True),
        sa.Column(
            "priority", sa.String(length=20), nullable=False, server_default="NORMAL"
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="DRAFT"
        ),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "line_discount_total", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "header_discount_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("tax_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "additional_charges", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("round_off", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "firm_id", "po_number", name="UQ_purchase_orders_firm_po_number"
        ),
    )
    op.create_index("IX_purchase_orders_firm_id", "purchase_orders", ["firm_id"])
    op.create_index(
        "IX_purchase_orders_tax_profile_id", "purchase_orders", ["tax_profile_id"]
    )
    op.create_index(
        "IX_purchase_orders_firm_status", "purchase_orders", ["firm_id", "status"]
    )
    op.create_index(
        "IX_purchase_orders_firm_date", "purchase_orders", ["firm_id", "purchase_date"]
    )
    op.create_index(
        "IX_purchase_orders_firm_vendor", "purchase_orders", ["firm_id", "vendor_id"]
    )
    op.create_index(
        "IX_purchase_orders_firm_branch", "purchase_orders", ["firm_id", "branch_id"]
    )
    op.create_index(
        "IX_purchase_orders_firm_warehouse",
        "purchase_orders",
        ["firm_id", "warehouse_id"],
    )

    op.create_table(
        "purchase_order_lines",
        *_base_columns(),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("vendor_product_code", sa.String(length=120), nullable=True),
        sa.Column("purchase_uom_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_uom_id", sa.Uuid(), nullable=True),
        sa.Column(
            "conversion_factor", sa.Numeric(24, 10), nullable=False, server_default="1"
        ),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
        sa.Column("ordered_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "base_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "discount_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "gross_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "batch_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "expiry_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "serial_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ORDERED"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["purchase_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_purchase_order_lines_purchase_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_purchase_order_lines_inventory_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "purchase_order_id",
            "line_number",
            name="UQ_purchase_order_lines_order_line",
        ),
    )
    op.create_index(
        "IX_purchase_order_lines_purchase_order_id",
        "purchase_order_lines",
        ["purchase_order_id"],
    )
    op.create_index(
        "IX_purchase_order_lines_firm_id", "purchase_order_lines", ["firm_id"]
    )
    op.create_index(
        "IX_purchase_order_lines_order", "purchase_order_lines", ["purchase_order_id"]
    )
    op.create_index(
        "IX_purchase_order_lines_firm_product",
        "purchase_order_lines",
        ["firm_id", "product_id"],
    )

    op.create_table(
        "purchase_delivery_schedules",
        *_base_columns(),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="PENDING"
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["purchase_order_line_id"], ["purchase_order_lines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_delivery_schedules_purchase_order_line_id",
        "purchase_delivery_schedules",
        ["purchase_order_line_id"],
    )
    op.create_index(
        "IX_purchase_delivery_schedules_line",
        "purchase_delivery_schedules",
        ["purchase_order_line_id"],
    )
    op.create_index(
        "IX_purchase_delivery_schedules_firm_date",
        "purchase_delivery_schedules",
        ["firm_id", "delivery_date"],
    )

    op.create_table(
        "purchase_attachments",
        *_base_columns(),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "attachment_kind",
            sa.String(length=40),
            nullable=False,
            server_default="PURCHASE_FILE",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_attachments_purchase_order_id",
        "purchase_attachments",
        ["purchase_order_id"],
    )
    op.create_index(
        "IX_purchase_attachments_order", "purchase_attachments", ["purchase_order_id"]
    )

    op.create_table(
        "purchase_notes",
        *_base_columns(),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column(
            "note_type", sa.String(length=30), nullable=False, server_default="INTERNAL"
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_notes_purchase_order_id", "purchase_notes", ["purchase_order_id"]
    )
    op.create_index("IX_purchase_notes_order", "purchase_notes", ["purchase_order_id"])

    op.create_table(
        "purchase_order_history",
        *_base_columns(),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_order_history_purchase_order_id",
        "purchase_order_history",
        ["purchase_order_id"],
    )
    op.create_index(
        "IX_purchase_order_history_order",
        "purchase_order_history",
        ["purchase_order_id"],
    )
    op.create_index(
        "IX_purchase_order_history_firm_action",
        "purchase_order_history",
        ["firm_id", "action"],
    )


def downgrade() -> None:
    op.drop_index(
        "IX_purchase_order_history_firm_action", table_name="purchase_order_history"
    )
    op.drop_index(
        "IX_purchase_order_history_order", table_name="purchase_order_history"
    )
    op.drop_index(
        "IX_purchase_order_history_purchase_order_id",
        table_name="purchase_order_history",
    )
    op.drop_table("purchase_order_history")

    op.drop_index("IX_purchase_notes_order", table_name="purchase_notes")
    op.drop_index("IX_purchase_notes_purchase_order_id", table_name="purchase_notes")
    op.drop_table("purchase_notes")

    op.drop_index("IX_purchase_attachments_order", table_name="purchase_attachments")
    op.drop_index(
        "IX_purchase_attachments_purchase_order_id", table_name="purchase_attachments"
    )
    op.drop_table("purchase_attachments")

    op.drop_index(
        "IX_purchase_delivery_schedules_firm_date",
        table_name="purchase_delivery_schedules",
    )
    op.drop_index(
        "IX_purchase_delivery_schedules_line", table_name="purchase_delivery_schedules"
    )
    op.drop_index(
        "IX_purchase_delivery_schedules_purchase_order_line_id",
        table_name="purchase_delivery_schedules",
    )
    op.drop_table("purchase_delivery_schedules")

    op.drop_index(
        "IX_purchase_order_lines_firm_product", table_name="purchase_order_lines"
    )
    op.drop_index("IX_purchase_order_lines_order", table_name="purchase_order_lines")
    op.drop_index("IX_purchase_order_lines_firm_id", table_name="purchase_order_lines")
    op.drop_index(
        "IX_purchase_order_lines_purchase_order_id", table_name="purchase_order_lines"
    )
    op.drop_table("purchase_order_lines")

    op.drop_index("IX_purchase_orders_firm_warehouse", table_name="purchase_orders")
    op.drop_index("IX_purchase_orders_firm_branch", table_name="purchase_orders")
    op.drop_index("IX_purchase_orders_firm_vendor", table_name="purchase_orders")
    op.drop_index("IX_purchase_orders_firm_date", table_name="purchase_orders")
    op.drop_index("IX_purchase_orders_firm_status", table_name="purchase_orders")
    op.drop_index("IX_purchase_orders_tax_profile_id", table_name="purchase_orders")
    op.drop_index("IX_purchase_orders_firm_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
