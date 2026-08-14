"""Create sales_invoice module tables.

Revision ID: 20260803_0030
Revises: 20260803_0029
Create Date: 2026-08-03 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision = "20260803_0030"
down_revision = "20260803_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the sales_invoice module tables."""
    # sales_invoices table
    op.create_table(
        "sales_invoices",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("salesman_id", UUIDType(), nullable=True),
        sa.Column("territory_id", UUIDType(), nullable=True),
        sa.Column("route_id", UUIDType(), nullable=True),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("business_profile_id", UUIDType(), nullable=True),
        sa.Column("invoice_number", sa.String(60), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("customer_invoice_number", sa.String(120), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("payment_terms", sa.String(200), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "allow_direct_sales_order",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "allow_over_invoice", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "over_invoice_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column(
            "total_source_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_already_invoiced_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_current_invoice_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
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
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType(), nullable=False),
        sa.Column("updated_by", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["route_id"], ["territory_route_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["salesman_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["territory_id"], ["sales_territories.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "firm_id", "invoice_number", name="UQ_sales_invoices_firm_invoice_number"
        ),
    )
    op.create_index(
        "IX_sales_invoices_firm_status", "sales_invoices", ["firm_id", "status"]
    )
    op.create_index(
        "IX_sales_invoices_firm_date", "sales_invoices", ["firm_id", "invoice_date"]
    )
    op.create_index(
        "IX_sales_invoices_firm_customer", "sales_invoices", ["firm_id", "customer_id"]
    )
    op.create_index(
        "IX_sales_invoices_firm_branch", "sales_invoices", ["firm_id", "branch_id"]
    )
    op.create_index(
        "IX_sales_invoices_firm_due_date", "sales_invoices", ["firm_id", "due_date"]
    )

    # sales_invoice_sources table
    op.create_table(
        "sales_invoice_sources",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False, index=True),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("source_document_type", sa.String(30), nullable=False),
        sa.Column("source_document_id", UUIDType(), nullable=False),
        sa.Column("source_document_number", sa.String(80), nullable=False),
        sa.Column("source_document_date", sa.Date(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType(), nullable=False),
        sa.Column("updated_by", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"], ["sales_invoices.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sales_invoice_id",
            "source_document_type",
            "source_document_id",
            name="UQ_sales_invoice_sources_document",
        ),
    )
    op.create_index(
        "IX_sales_invoice_sources_invoice",
        "sales_invoice_sources",
        ["sales_invoice_id"],
    )

    # sales_invoice_lines table
    op.create_table(
        "sales_invoice_lines",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False, index=True),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("source_document_type", sa.String(30), nullable=False),
        sa.Column("source_document_id", UUIDType(), nullable=False),
        sa.Column("source_document_number", sa.String(80), nullable=False),
        sa.Column("source_document_line_id", UUIDType(), nullable=False),
        sa.Column("source_document_line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("delivered_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "already_invoiced_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_invoice_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "discount_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "charges_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "gross_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_profile_id", UUIDType(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("packaging_type_id", UUIDType(), nullable=True),
        sa.Column("order_uom_id", UUIDType(), nullable=True),
        sa.Column("invoice_uom_id", UUIDType(), nullable=True),
        sa.Column(
            "conversion_factor", sa.Numeric(24, 10), nullable=False, server_default="1"
        ),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", UUIDType(), nullable=True),
        sa.Column("storage_node_id", UUIDType(), nullable=True),
        sa.Column("batch_number", sa.String(120), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("accounting_event_reference", sa.String(120), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType(), nullable=False),
        sa.Column("updated_by", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_uom_id"],
            ["uoms.id"],
            name="FK_sales_invoice_lines_invoice_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_uom_id"],
            ["uoms.id"],
            name="FK_sales_invoice_lines_order_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["packaging_type_id"], ["packaging_types.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"], ["sales_invoices.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sales_invoice_id",
            "line_number",
            name="UQ_sales_invoice_lines_invoice_line",
        ),
    )
    op.create_index(
        "IX_sales_invoice_lines_invoice", "sales_invoice_lines", ["sales_invoice_id"]
    )
    op.create_index(
        "IX_sales_invoice_lines_firm_source",
        "sales_invoice_lines",
        ["firm_id", "source_document_line_id"],
    )
    op.create_index(
        "IX_sales_invoice_lines_firm_product",
        "sales_invoice_lines",
        ["firm_id", "product_id"],
    )

    # sales_invoice_attachments table
    op.create_table(
        "sales_invoice_attachments",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False, index=True),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType(), nullable=False),
        sa.Column("updated_by", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"], ["sales_invoices.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_sales_invoice_attachments_invoice",
        "sales_invoice_attachments",
        ["sales_invoice_id"],
    )

    # sales_invoice_notes table
    op.create_table(
        "sales_invoice_notes",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False, index=True),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", UUIDType(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType(), nullable=False),
        sa.Column("updated_by", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"], ["sales_invoices.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_sales_invoice_notes_invoice", "sales_invoice_notes", ["sales_invoice_id"]
    )

    # sales_invoice_accounting_events table
    op.create_table(
        "sales_invoice_accounting_events",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False, index=True),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("reference_entity", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType(), nullable=False),
        sa.Column("updated_by", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"], ["sales_invoices.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_sales_invoice_accounting_events_invoice",
        "sales_invoice_accounting_events",
        ["sales_invoice_id"],
    )
    op.create_index(
        "IX_sales_invoice_accounting_events_type",
        "sales_invoice_accounting_events",
        ["event_type"],
    )


def downgrade() -> None:
    """Reverse the sales_invoice module tables."""
    op.drop_index(
        "IX_sales_invoice_accounting_events_type",
        table_name="sales_invoice_accounting_events",
    )
    op.drop_index(
        "IX_sales_invoice_accounting_events_invoice",
        table_name="sales_invoice_accounting_events",
    )
    op.drop_table("sales_invoice_accounting_events")

    op.drop_index("IX_sales_invoice_notes_invoice", table_name="sales_invoice_notes")
    op.drop_table("sales_invoice_notes")

    op.drop_index(
        "IX_sales_invoice_attachments_invoice", table_name="sales_invoice_attachments"
    )
    op.drop_table("sales_invoice_attachments")

    op.drop_index(
        "IX_sales_invoice_lines_firm_product", table_name="sales_invoice_lines"
    )
    op.drop_index(
        "IX_sales_invoice_lines_firm_source", table_name="sales_invoice_lines"
    )
    op.drop_index("IX_sales_invoice_lines_invoice", table_name="sales_invoice_lines")
    op.drop_table("sales_invoice_lines")

    op.drop_index(
        "IX_sales_invoice_sources_invoice", table_name="sales_invoice_sources"
    )
    op.drop_table("sales_invoice_sources")

    op.drop_index("IX_sales_invoices_firm_due_date", table_name="sales_invoices")
    op.drop_index("IX_sales_invoices_firm_branch", table_name="sales_invoices")
    op.drop_index("IX_sales_invoices_firm_customer", table_name="sales_invoices")
    op.drop_index("IX_sales_invoices_firm_date", table_name="sales_invoices")
    op.drop_index("IX_sales_invoices_firm_status", table_name="sales_invoices")
    op.drop_table("sales_invoices")
