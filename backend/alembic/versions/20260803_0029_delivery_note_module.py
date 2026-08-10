"""Delivery note module foundation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0029"
down_revision: str | Sequence[str] | None = "20260803_0028"
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
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
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
        "delivery_notes",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("salesman_id", sa.Uuid(), nullable=True),
        sa.Column("route_id", sa.Uuid(), nullable=True),
        sa.Column("territory_id", sa.Uuid(), nullable=True),
        sa.Column("delivery_note_number", sa.String(length=60), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("sales_order_reference", sa.String(length=80), nullable=False),
        sa.Column("vehicle", sa.String(length=120), nullable=True),
        sa.Column("driver", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "allow_over_delivery",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "over_delivery_percent",
            sa.Numeric(9, 4),
            nullable=False,
            server_default="0",
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
            "total_previously_delivered_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_current_delivery_quantity",
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
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["salesman_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["route_id"], ["territory_route_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"], ["sales_territories.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "firm_id", "delivery_note_number", name="UQ_delivery_notes_firm_number"
        ),
    )
    op.create_index("IX_delivery_notes_firm_id", "delivery_notes", ["firm_id"])
    op.create_index(
        "IX_delivery_notes_firm_status", "delivery_notes", ["firm_id", "status"]
    )
    op.create_index(
        "IX_delivery_notes_firm_date", "delivery_notes", ["firm_id", "delivery_date"]
    )
    op.create_index(
        "IX_delivery_notes_firm_sales_order",
        "delivery_notes",
        ["firm_id", "sales_order_id"],
    )
    op.create_index(
        "IX_delivery_notes_firm_customer", "delivery_notes", ["firm_id", "customer_id"]
    )
    op.create_index(
        "IX_delivery_notes_firm_branch", "delivery_notes", ["firm_id", "branch_id"]
    )
    op.create_index(
        "IX_delivery_notes_firm_warehouse",
        "delivery_notes",
        ["firm_id", "warehouse_id"],
    )

    op.create_table(
        "delivery_note_lines",
        *_base_columns(),
        sa.Column("delivery_note_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("ordered_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "reserved_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "previously_delivered_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_delivery_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "delivered_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "remaining_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "damaged_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "short_shipment_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("sales_uom_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_uom_id", sa.Uuid(), nullable=True),
        sa.Column("packaging_type_id", sa.Uuid(), nullable=True),
        sa.Column(
            "conversion_factor", sa.Numeric(24, 10), nullable=False, server_default="1"
        ),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
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
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(length=120), nullable=True),
        sa.Column("serial_numbers", sa.Text(), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("released_reservation_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["delivery_note_id"], ["delivery_notes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["sales_order_line_id"], ["sales_order_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["sales_uom_id"],
            ["uoms.id"],
            name="FK_delivery_note_lines_sales_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_uom_id"],
            ["uoms.id"],
            name="FK_delivery_note_lines_inventory_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["packaging_type_id"], ["packaging_types.id"], ondelete="RESTRICT"
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
            "delivery_note_id", "line_number", name="UQ_delivery_note_lines_note_line"
        ),
    )
    op.create_index(
        "IX_delivery_note_lines_delivery_note_id",
        "delivery_note_lines",
        ["delivery_note_id"],
    )
    op.create_index(
        "IX_delivery_note_lines_note", "delivery_note_lines", ["delivery_note_id"]
    )
    op.create_index(
        "IX_delivery_note_lines_firm_order_line",
        "delivery_note_lines",
        ["firm_id", "sales_order_line_id"],
    )
    op.create_index(
        "IX_delivery_note_lines_firm_product",
        "delivery_note_lines",
        ["firm_id", "product_id"],
    )

    op.create_table(
        "delivery_note_attachments",
        *_base_columns(),
        sa.Column("delivery_note_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "attachment_kind",
            sa.String(length=40),
            nullable=False,
            server_default="DELIVERY_NOTE_FILE",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_note_id"], ["delivery_notes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_delivery_note_attachments_delivery_note_id",
        "delivery_note_attachments",
        ["delivery_note_id"],
    )
    op.create_index(
        "IX_delivery_note_attachments_note",
        "delivery_note_attachments",
        ["delivery_note_id"],
    )

    op.create_table(
        "delivery_note_notes",
        *_base_columns(),
        sa.Column("delivery_note_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column(
            "note_type", sa.String(length=30), nullable=False, server_default="INTERNAL"
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_note_id"], ["delivery_notes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_delivery_note_notes_delivery_note_id",
        "delivery_note_notes",
        ["delivery_note_id"],
    )
    op.create_index(
        "IX_delivery_note_notes_note", "delivery_note_notes", ["delivery_note_id"]
    )


def downgrade() -> None:
    op.drop_index("IX_delivery_note_notes_note", table_name="delivery_note_notes")
    op.drop_index(
        "IX_delivery_note_notes_delivery_note_id", table_name="delivery_note_notes"
    )
    op.drop_table("delivery_note_notes")

    op.drop_index(
        "IX_delivery_note_attachments_note", table_name="delivery_note_attachments"
    )
    op.drop_index(
        "IX_delivery_note_attachments_delivery_note_id",
        table_name="delivery_note_attachments",
    )
    op.drop_table("delivery_note_attachments")

    op.drop_index(
        "IX_delivery_note_lines_firm_product", table_name="delivery_note_lines"
    )
    op.drop_index(
        "IX_delivery_note_lines_firm_order_line", table_name="delivery_note_lines"
    )
    op.drop_index("IX_delivery_note_lines_note", table_name="delivery_note_lines")
    op.drop_index(
        "IX_delivery_note_lines_delivery_note_id", table_name="delivery_note_lines"
    )
    op.drop_table("delivery_note_lines")

    op.drop_index("IX_delivery_notes_firm_warehouse", table_name="delivery_notes")
    op.drop_index("IX_delivery_notes_firm_branch", table_name="delivery_notes")
    op.drop_index("IX_delivery_notes_firm_customer", table_name="delivery_notes")
    op.drop_index("IX_delivery_notes_firm_sales_order", table_name="delivery_notes")
    op.drop_index("IX_delivery_notes_firm_date", table_name="delivery_notes")
    op.drop_index("IX_delivery_notes_firm_status", table_name="delivery_notes")
    op.drop_index("IX_delivery_notes_firm_id", table_name="delivery_notes")
    op.drop_table("delivery_notes")
