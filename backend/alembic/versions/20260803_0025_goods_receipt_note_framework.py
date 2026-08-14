"""Goods receipt note foundation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0025"
down_revision: str | Sequence[str] | None = "20260803_0024"
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
    """Apply goods receipt note foundation."""
    op.create_table(
        "goods_receipts",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_number", sa.String(length=60), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("received_by_id", sa.Uuid(), nullable=True),
        sa.Column("grn_number", sa.String(length=60), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("transport_details", sa.String(length=250), nullable=True),
        sa.Column("vehicle_number", sa.String(length=80), nullable=True),
        sa.Column("invoice_reference", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "allow_over_receipt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "over_receipt_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="DRAFT"
        ),
        sa.Column(
            "total_ordered_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_previous_received_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_current_receipt_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_accepted_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_rejected_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_damaged_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "line_discount_total", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "additional_charges", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("round_off", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["received_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "firm_id", "grn_number", name="UQ_goods_receipts_firm_grn_number"
        ),
    )
    op.create_index("IX_goods_receipts_firm_id", "goods_receipts", ["firm_id"])
    op.create_index(
        "IX_goods_receipts_firm_status", "goods_receipts", ["firm_id", "status"]
    )
    op.create_index(
        "IX_goods_receipts_firm_date", "goods_receipts", ["firm_id", "receipt_date"]
    )
    op.create_index(
        "IX_goods_receipts_firm_po", "goods_receipts", ["firm_id", "purchase_order_id"]
    )
    op.create_index(
        "IX_goods_receipts_firm_vendor", "goods_receipts", ["firm_id", "vendor_id"]
    )

    op.create_table(
        "goods_receipt_lines",
        *_base_columns(),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("ordered_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "previously_received_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_receipt_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "accepted_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
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
            "rejected_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "damaged_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("packaging_type_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_uom_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_uom_id", sa.Uuid(), nullable=True),
        sa.Column(
            "conversion_factor", sa.Numeric(24, 10), nullable=False, server_default="1"
        ),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(length=120), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("inventory_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["purchase_order_line_id"], ["purchase_order_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["packaging_type_id"], ["packaging_types.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_uom_id"],
            ["uoms.id"],
            name="FK_goods_receipt_lines_purchase_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_uom_id"],
            ["uoms.id"],
            name="FK_goods_receipt_lines_inventory_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_transaction_id"],
            ["inventory_transactions.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "goods_receipt_id",
            "line_number",
            name="UQ_goods_receipt_lines_receipt_line",
        ),
    )
    op.create_index(
        "IX_goods_receipt_lines_goods_receipt_id",
        "goods_receipt_lines",
        ["goods_receipt_id"],
    )
    op.create_index(
        "IX_goods_receipt_lines_receipt", "goods_receipt_lines", ["goods_receipt_id"]
    )
    op.create_index(
        "IX_goods_receipt_lines_firm_po_line",
        "goods_receipt_lines",
        ["firm_id", "purchase_order_line_id"],
    )
    op.create_index(
        "IX_goods_receipt_lines_firm_product",
        "goods_receipt_lines",
        ["firm_id", "product_id"],
    )

    op.create_table(
        "goods_receipt_attachments",
        *_base_columns(),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "attachment_kind",
            sa.String(length=40),
            nullable=False,
            server_default="GRN_FILE",
        ),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_goods_receipt_attachments_goods_receipt_id",
        "goods_receipt_attachments",
        ["goods_receipt_id"],
    )
    op.create_index(
        "IX_goods_receipt_attachments_receipt",
        "goods_receipt_attachments",
        ["goods_receipt_id"],
    )

    op.create_table(
        "goods_receipt_notes",
        *_base_columns(),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("note_type", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_goods_receipt_notes_goods_receipt_id",
        "goods_receipt_notes",
        ["goods_receipt_id"],
    )
    op.create_index(
        "IX_goods_receipt_notes_receipt", "goods_receipt_notes", ["goods_receipt_id"]
    )


def downgrade() -> None:
    """Reverse goods receipt note foundation."""
    op.drop_index("IX_goods_receipt_notes_receipt", table_name="goods_receipt_notes")
    op.drop_index(
        "IX_goods_receipt_notes_goods_receipt_id", table_name="goods_receipt_notes"
    )
    op.drop_table("goods_receipt_notes")

    op.drop_index(
        "IX_goods_receipt_attachments_receipt", table_name="goods_receipt_attachments"
    )
    op.drop_index(
        "IX_goods_receipt_attachments_goods_receipt_id",
        table_name="goods_receipt_attachments",
    )
    op.drop_table("goods_receipt_attachments")

    op.drop_index(
        "IX_goods_receipt_lines_firm_product", table_name="goods_receipt_lines"
    )
    op.drop_index(
        "IX_goods_receipt_lines_firm_po_line", table_name="goods_receipt_lines"
    )
    op.drop_index("IX_goods_receipt_lines_receipt", table_name="goods_receipt_lines")
    op.drop_index(
        "IX_goods_receipt_lines_goods_receipt_id", table_name="goods_receipt_lines"
    )
    op.drop_table("goods_receipt_lines")

    op.drop_index("IX_goods_receipts_firm_vendor", table_name="goods_receipts")
    op.drop_index("IX_goods_receipts_firm_po", table_name="goods_receipts")
    op.drop_index("IX_goods_receipts_firm_date", table_name="goods_receipts")
    op.drop_index("IX_goods_receipts_firm_status", table_name="goods_receipts")
    op.drop_index("IX_goods_receipts_firm_id", table_name="goods_receipts")
    op.drop_table("goods_receipts")
