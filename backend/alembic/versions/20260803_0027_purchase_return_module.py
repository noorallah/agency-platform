"""Purchase return module foundation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0027"
down_revision: str | Sequence[str] | None = "20260803_0026"
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
        "purchase_returns",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("return_number", sa.String(length=60), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("supplier_return_number", sa.String(length=120), nullable=True),
        sa.Column("supplier_return_date", sa.Date(), nullable=True),
        sa.Column("reference_grn_number", sa.String(length=80), nullable=True),
        sa.Column("reference_invoice_number", sa.String(length=80), nullable=True),
        sa.Column("return_reason", sa.String(length=80), nullable=True),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("payment_terms", sa.String(length=200), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "allow_direct_purchase_order",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "allow_over_return",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "over_return_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="DRAFT"
        ),
        sa.Column(
            "total_source_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_already_returned_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_current_return_quantity",
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
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "firm_id", "return_number", name="UQ_purchase_returns_firm_return_number"
        ),
    )
    op.create_index("IX_purchase_returns_firm_id", "purchase_returns", ["firm_id"])
    op.create_index(
        "IX_purchase_returns_firm_status", "purchase_returns", ["firm_id", "status"]
    )
    op.create_index(
        "IX_purchase_returns_firm_date", "purchase_returns", ["firm_id", "return_date"]
    )
    op.create_index(
        "IX_purchase_returns_firm_vendor", "purchase_returns", ["firm_id", "vendor_id"]
    )
    op.create_index(
        "IX_purchase_returns_firm_branch", "purchase_returns", ["firm_id", "branch_id"]
    )
    op.create_index(
        "IX_purchase_returns_firm_warehouse",
        "purchase_returns",
        ["firm_id", "warehouse_id"],
    )

    op.create_table(
        "purchase_return_sources",
        *_base_columns(),
        sa.Column("purchase_return_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_type", sa.String(length=30), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_number", sa.String(length=80), nullable=False),
        sa.Column("source_document_date", sa.Date(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"], ["purchase_returns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "purchase_return_id",
            "source_document_type",
            "source_document_id",
            name="UQ_purchase_return_sources_document",
        ),
    )
    op.create_index(
        "IX_purchase_return_sources_purchase_return_id",
        "purchase_return_sources",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_sources_return",
        "purchase_return_sources",
        ["purchase_return_id"],
    )

    op.create_table(
        "purchase_return_lines",
        *_base_columns(),
        sa.Column("purchase_return_id", sa.Uuid(), nullable=False),
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
        sa.Column(
            "already_returned_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_return_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "rejected_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("item_condition", sa.String(length=80), nullable=True),
        sa.Column(
            "replacement_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "refund_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_scrap", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_damaged", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_expired", sa.Boolean(), nullable=False, server_default=sa.text("false")
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
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("packaging_type_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_uom_id", sa.Uuid(), nullable=True),
        sa.Column("return_uom_id", sa.Uuid(), nullable=True),
        sa.Column(
            "conversion_factor", sa.Numeric(24, 10), nullable=False, server_default="1"
        ),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("storage_node_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(length=120), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("accounting_event_reference", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"], ["purchase_returns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
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
            name="FK_purchase_return_lines_purchase_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["return_uom_id"],
            ["uoms.id"],
            name="FK_purchase_return_lines_return_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["storage_node_id"], ["warehouse_storage_nodes.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "purchase_return_id",
            "line_number",
            name="UQ_purchase_return_lines_return_line",
        ),
    )
    op.create_index(
        "IX_purchase_return_lines_purchase_return_id",
        "purchase_return_lines",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_lines_return",
        "purchase_return_lines",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_lines_firm_source",
        "purchase_return_lines",
        ["firm_id", "source_document_line_id"],
    )
    op.create_index(
        "IX_purchase_return_lines_firm_product",
        "purchase_return_lines",
        ["firm_id", "product_id"],
    )

    op.create_table(
        "purchase_return_attachments",
        *_base_columns(),
        sa.Column("purchase_return_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "attachment_kind",
            sa.String(length=40),
            nullable=False,
            server_default="PURCHASE_RETURN_FILE",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"], ["purchase_returns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_return_attachments_purchase_return_id",
        "purchase_return_attachments",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_attachments_return",
        "purchase_return_attachments",
        ["purchase_return_id"],
    )

    op.create_table(
        "purchase_return_notes",
        *_base_columns(),
        sa.Column("purchase_return_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column(
            "note_type", sa.String(length=30), nullable=False, server_default="INTERNAL"
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"], ["purchase_returns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_return_notes_purchase_return_id",
        "purchase_return_notes",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_notes_return",
        "purchase_return_notes",
        ["purchase_return_id"],
    )

    op.create_table(
        "purchase_return_accounting_events",
        *_base_columns(),
        sa.Column("purchase_return_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=False),
        sa.Column("direction", sa.String(length=12), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("source_line_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"], ["purchase_returns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
    )
    op.create_index(
        "IX_purchase_return_accounting_events_purchase_return_id",
        "purchase_return_accounting_events",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_accounting_events_return",
        "purchase_return_accounting_events",
        ["purchase_return_id"],
    )
    op.create_index(
        "IX_purchase_return_accounting_events_type",
        "purchase_return_accounting_events",
        ["firm_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "IX_purchase_return_accounting_events_type",
        table_name="purchase_return_accounting_events",
    )
    op.drop_index(
        "IX_purchase_return_accounting_events_return",
        table_name="purchase_return_accounting_events",
    )
    op.drop_index(
        "IX_purchase_return_accounting_events_purchase_return_id",
        table_name="purchase_return_accounting_events",
    )
    op.drop_table("purchase_return_accounting_events")

    op.drop_index("IX_purchase_return_notes_return", table_name="purchase_return_notes")
    op.drop_index(
        "IX_purchase_return_notes_purchase_return_id",
        table_name="purchase_return_notes",
    )
    op.drop_table("purchase_return_notes")

    op.drop_index(
        "IX_purchase_return_attachments_return",
        table_name="purchase_return_attachments",
    )
    op.drop_index(
        "IX_purchase_return_attachments_purchase_return_id",
        table_name="purchase_return_attachments",
    )
    op.drop_table("purchase_return_attachments")

    op.drop_index(
        "IX_purchase_return_lines_firm_product", table_name="purchase_return_lines"
    )
    op.drop_index(
        "IX_purchase_return_lines_firm_source", table_name="purchase_return_lines"
    )
    op.drop_index("IX_purchase_return_lines_return", table_name="purchase_return_lines")
    op.drop_index(
        "IX_purchase_return_lines_purchase_return_id",
        table_name="purchase_return_lines",
    )
    op.drop_table("purchase_return_lines")

    op.drop_index(
        "IX_purchase_return_sources_return", table_name="purchase_return_sources"
    )
    op.drop_index(
        "IX_purchase_return_sources_purchase_return_id",
        table_name="purchase_return_sources",
    )
    op.drop_table("purchase_return_sources")

    op.drop_index("IX_purchase_returns_firm_warehouse", table_name="purchase_returns")
    op.drop_index("IX_purchase_returns_firm_branch", table_name="purchase_returns")
    op.drop_index("IX_purchase_returns_firm_vendor", table_name="purchase_returns")
    op.drop_index("IX_purchase_returns_firm_date", table_name="purchase_returns")
    op.drop_index("IX_purchase_returns_firm_status", table_name="purchase_returns")
    op.drop_index("IX_purchase_returns_firm_id", table_name="purchase_returns")
    op.drop_table("purchase_returns")
