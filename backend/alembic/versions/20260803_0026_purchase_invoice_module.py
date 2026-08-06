"""Purchase invoice module foundation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0026"
down_revision: str | Sequence[str] | None = "20260803_0025"
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    op.create_table(
        "purchase_invoices",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_number", sa.String(length=60), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("supplier_invoice_number", sa.String(length=120), nullable=False),
        sa.Column("supplier_invoice_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("payment_terms", sa.String(length=200), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("allow_direct_purchase_order", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_over_invoice", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("over_invoice_percent", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("total_source_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_already_invoiced_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_current_invoice_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("line_discount_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("additional_charges", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("round_off", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("firm_id", "invoice_number", name="UQ_purchase_invoices_firm_invoice_number"),
    )
    op.create_index("IX_purchase_invoices_firm_id", "purchase_invoices", ["firm_id"])
    op.create_index("IX_purchase_invoices_firm_status", "purchase_invoices", ["firm_id", "status"])
    op.create_index("IX_purchase_invoices_firm_date", "purchase_invoices", ["firm_id", "invoice_date"])
    op.create_index("IX_purchase_invoices_firm_vendor", "purchase_invoices", ["firm_id", "vendor_id"])
    op.create_index("IX_purchase_invoices_firm_branch", "purchase_invoices", ["firm_id", "branch_id"])
    op.create_index("IX_purchase_invoices_firm_due_date", "purchase_invoices", ["firm_id", "due_date"])

    op.create_table(
        "purchase_invoice_sources",
        *_base_columns(),
        sa.Column("purchase_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_type", sa.String(length=30), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_number", sa.String(length=80), nullable=False),
        sa.Column("source_document_date", sa.Date(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "purchase_invoice_id",
            "source_document_type",
            "source_document_id",
            name="UQ_purchase_invoice_sources_document",
        ),
    )
    op.create_index("IX_purchase_invoice_sources_purchase_invoice_id", "purchase_invoice_sources", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_sources_invoice", "purchase_invoice_sources", ["purchase_invoice_id"])

    op.create_table(
        "purchase_invoice_lines",
        *_base_columns(),
        sa.Column("purchase_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("source_document_type", sa.String(length=30), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_number", sa.String(length=80), nullable=False),
        sa.Column("source_document_line_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("received_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("already_invoiced_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("current_invoice_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("discount_percent", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("charges_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("gross_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("packaging_type_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_uom_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_uom_id", sa.Uuid(), nullable=True),
        sa.Column("conversion_factor", sa.Numeric(24, 10), nullable=False, server_default="1"),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(length=120), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("accounting_event_reference", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["packaging_type_id"], ["packaging_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["purchase_uom_id"],
            ["uoms.id"],
            name="FK_purchase_invoice_lines_purchase_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_uom_id"],
            ["uoms.id"],
            name="FK_purchase_invoice_lines_invoice_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("purchase_invoice_id", "line_number", name="UQ_purchase_invoice_lines_invoice_line"),
    )
    op.create_index("IX_purchase_invoice_lines_purchase_invoice_id", "purchase_invoice_lines", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_lines_invoice", "purchase_invoice_lines", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_lines_firm_source", "purchase_invoice_lines", ["firm_id", "source_document_line_id"])
    op.create_index("IX_purchase_invoice_lines_firm_product", "purchase_invoice_lines", ["firm_id", "product_id"])

    op.create_table(
        "purchase_invoice_attachments",
        *_base_columns(),
        sa.Column("purchase_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("attachment_kind", sa.String(length=40), nullable=False, server_default="PURCHASE_INVOICE_FILE"),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index("IX_purchase_invoice_attachments_purchase_invoice_id", "purchase_invoice_attachments", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_attachments_invoice", "purchase_invoice_attachments", ["purchase_invoice_id"])

    op.create_table(
        "purchase_invoice_notes",
        *_base_columns(),
        sa.Column("purchase_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("note_type", sa.String(length=30), nullable=False, server_default="INTERNAL"),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index("IX_purchase_invoice_notes_purchase_invoice_id", "purchase_invoice_notes", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_notes_invoice", "purchase_invoice_notes", ["purchase_invoice_id"])

    op.create_table(
        "purchase_invoice_accounting_events",
        *_base_columns(),
        sa.Column("purchase_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=False),
        sa.Column("direction", sa.String(length=12), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("source_line_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index("IX_purchase_invoice_accounting_events_purchase_invoice_id", "purchase_invoice_accounting_events", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_accounting_events_invoice", "purchase_invoice_accounting_events", ["purchase_invoice_id"])
    op.create_index("IX_purchase_invoice_accounting_events_type", "purchase_invoice_accounting_events", ["firm_id", "event_type"])


def downgrade() -> None:
    op.drop_index("IX_purchase_invoice_accounting_events_type", table_name="purchase_invoice_accounting_events")
    op.drop_index("IX_purchase_invoice_accounting_events_invoice", table_name="purchase_invoice_accounting_events")
    op.drop_index("IX_purchase_invoice_accounting_events_purchase_invoice_id", table_name="purchase_invoice_accounting_events")
    op.drop_table("purchase_invoice_accounting_events")

    op.drop_index("IX_purchase_invoice_notes_invoice", table_name="purchase_invoice_notes")
    op.drop_index("IX_purchase_invoice_notes_purchase_invoice_id", table_name="purchase_invoice_notes")
    op.drop_table("purchase_invoice_notes")

    op.drop_index("IX_purchase_invoice_attachments_invoice", table_name="purchase_invoice_attachments")
    op.drop_index("IX_purchase_invoice_attachments_purchase_invoice_id", table_name="purchase_invoice_attachments")
    op.drop_table("purchase_invoice_attachments")

    op.drop_index("IX_purchase_invoice_lines_firm_product", table_name="purchase_invoice_lines")
    op.drop_index("IX_purchase_invoice_lines_firm_source", table_name="purchase_invoice_lines")
    op.drop_index("IX_purchase_invoice_lines_invoice", table_name="purchase_invoice_lines")
    op.drop_index("IX_purchase_invoice_lines_purchase_invoice_id", table_name="purchase_invoice_lines")
    op.drop_table("purchase_invoice_lines")

    op.drop_index("IX_purchase_invoice_sources_invoice", table_name="purchase_invoice_sources")
    op.drop_index("IX_purchase_invoice_sources_purchase_invoice_id", table_name="purchase_invoice_sources")
    op.drop_table("purchase_invoice_sources")

    op.drop_index("IX_purchase_invoices_firm_due_date", table_name="purchase_invoices")
    op.drop_index("IX_purchase_invoices_firm_branch", table_name="purchase_invoices")
    op.drop_index("IX_purchase_invoices_firm_vendor", table_name="purchase_invoices")
    op.drop_index("IX_purchase_invoices_firm_date", table_name="purchase_invoices")
    op.drop_index("IX_purchase_invoices_firm_status", table_name="purchase_invoices")
    op.drop_index("IX_purchase_invoices_firm_id", table_name="purchase_invoices")
    op.drop_table("purchase_invoices")
