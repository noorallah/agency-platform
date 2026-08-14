"""Generic enterprise document lifecycle framework."""

# ruff: noqa: D103

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0024"
down_revision: str | Sequence[str] | None = "20260803_0023"
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
    """Apply generic enterprise document lifecycle framework."""
    op.create_table(
        "document_type_definitions",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.UniqueConstraint(
            "firm_id", "code", name="UQ_document_type_definitions_firm_code"
        ),
    )
    op.create_index(
        "IX_document_type_definitions_firm_id", "document_type_definitions", ["firm_id"]
    )

    op.create_table(
        "document_state_definitions",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_type_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_terminal", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "allows_edit", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "allows_print", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "allows_email", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "allows_export_pdf",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("transition_rules", sa.JSON(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_type_definitions.id"]),
        sa.UniqueConstraint(
            "firm_id",
            "document_type_id",
            "code",
            name="UQ_document_state_definitions_firm_type_code",
        ),
    )
    op.create_index(
        "IX_document_state_definitions_firm_id",
        "document_state_definitions",
        ["firm_id"],
    )
    op.create_index(
        "IX_document_state_definitions_document_type_id",
        "document_state_definitions",
        ["document_type_id"],
    )

    op.create_table(
        "document_numbering_rules",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_type_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("prefix", sa.String(length=40), nullable=True),
        sa.Column("suffix", sa.String(length=40), nullable=True),
        sa.Column(
            "separator", sa.String(length=10), nullable=False, server_default="-"
        ),
        sa.Column(
            "include_financial_year",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "include_branch_code",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "include_company_code",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "auto_reset", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "manual_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sequence_padding", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("next_sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_scope_signature", sa.String(length=200), nullable=True),
        sa.Column("format_pattern", sa.String(length=200), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_type_definitions.id"]),
        sa.UniqueConstraint(
            "firm_id",
            "document_type_id",
            "code",
            name="UQ_document_numbering_rules_firm_type_code",
        ),
    )
    op.create_index(
        "IX_document_numbering_rules_firm_id", "document_numbering_rules", ["firm_id"]
    )
    op.create_index(
        "IX_document_numbering_rules_document_type_id",
        "document_numbering_rules",
        ["document_type_id"],
    )

    op.create_table(
        "document_lifecycle_events",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_module_code", sa.String(length=80), nullable=True),
        sa.Column("document_number", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("from_state", sa.String(length=80), nullable=True),
        sa.Column("to_state", sa.String(length=80), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("printed_by", sa.Uuid(), nullable=True),
        sa.Column("exported_by", sa.Uuid(), nullable=True),
        sa.Column("email_recipient", sa.String(length=255), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_type_definitions.id"]),
    )
    op.create_index(
        "IX_document_lifecycle_events_firm_id", "document_lifecycle_events", ["firm_id"]
    )
    op.create_index(
        "IX_document_lifecycle_events_source_document_id",
        "document_lifecycle_events",
        ["source_document_id"],
    )
    op.create_index(
        "IX_document_lifecycle_events_firm_document",
        "document_lifecycle_events",
        ["firm_id", "source_document_id"],
    )

    op.create_table(
        "document_headers",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("document_number", sa.String(length=80), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("firm_name", sa.String(length=200), nullable=True),
        sa.Column("business_profile_name", sa.String(length=200), nullable=True),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "status", sa.String(length=80), nullable=False, server_default="DRAFT"
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_type_definitions.id"]),
        sa.UniqueConstraint(
            "firm_id",
            "document_number",
            name="UQ_document_headers_firm_document_number",
        ),
    )
    op.create_index("IX_document_headers_firm_id", "document_headers", ["firm_id"])
    op.create_index(
        "IX_document_headers_source_document_id",
        "document_headers",
        ["source_document_id"],
    )

    op.create_table(
        "document_lines",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_header_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("uom_id", sa.Uuid(), nullable=True),
        sa.Column("packaging", sa.String(length=120), nullable=True),
        sa.Column("quantity", sa.String(length=40), nullable=True),
        sa.Column("free_quantity", sa.String(length=40), nullable=True),
        sa.Column("unit_price", sa.String(length=40), nullable=True),
        sa.Column("discount", sa.String(length=40), nullable=True),
        sa.Column("tax_profile", sa.String(length=120), nullable=True),
        sa.Column("amount", sa.String(length=40), nullable=True),
        sa.Column("net_amount", sa.String(length=40), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["document_header_id"], ["document_headers.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "firm_id",
            "document_header_id",
            "line_number",
            name="UQ_document_lines_header_line",
        ),
    )
    op.create_index("IX_document_lines_firm_id", "document_lines", ["firm_id"])
    op.create_index(
        "IX_document_lines_document_header_id", "document_lines", ["document_header_id"]
    )

    op.create_table(
        "document_totals",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_header_id", sa.Uuid(), nullable=False),
        sa.Column("subtotal", sa.String(length=40), nullable=True),
        sa.Column("discount", sa.String(length=40), nullable=True),
        sa.Column("tax", sa.String(length=40), nullable=True),
        sa.Column("charges", sa.String(length=40), nullable=True),
        sa.Column("round_off", sa.String(length=40), nullable=True),
        sa.Column("grand_total", sa.String(length=40), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["document_header_id"], ["document_headers.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "firm_id", "document_header_id", name="UQ_document_totals_firm_header"
        ),
    )
    op.create_index("IX_document_totals_firm_id", "document_totals", ["firm_id"])
    op.create_index(
        "IX_document_totals_document_header_id",
        "document_totals",
        ["document_header_id"],
    )


def downgrade() -> None:
    """Reverse generic enterprise document lifecycle framework."""
    op.drop_index("IX_document_totals_document_header_id", table_name="document_totals")
    op.drop_index("IX_document_totals_firm_id", table_name="document_totals")
    op.drop_table("document_totals")

    op.drop_index("IX_document_lines_document_header_id", table_name="document_lines")
    op.drop_index("IX_document_lines_firm_id", table_name="document_lines")
    op.drop_table("document_lines")

    op.drop_index(
        "IX_document_headers_source_document_id", table_name="document_headers"
    )
    op.drop_index("IX_document_headers_firm_id", table_name="document_headers")
    op.drop_table("document_headers")

    op.drop_index(
        "IX_document_lifecycle_events_firm_document",
        table_name="document_lifecycle_events",
    )
    op.drop_index(
        "IX_document_lifecycle_events_source_document_id",
        table_name="document_lifecycle_events",
    )
    op.drop_index(
        "IX_document_lifecycle_events_firm_id", table_name="document_lifecycle_events"
    )
    op.drop_table("document_lifecycle_events")

    op.drop_index(
        "IX_document_numbering_rules_document_type_id",
        table_name="document_numbering_rules",
    )
    op.drop_index(
        "IX_document_numbering_rules_firm_id", table_name="document_numbering_rules"
    )
    op.drop_table("document_numbering_rules")

    op.drop_index(
        "IX_document_state_definitions_document_type_id",
        table_name="document_state_definitions",
    )
    op.drop_index(
        "IX_document_state_definitions_firm_id", table_name="document_state_definitions"
    )
    op.drop_table("document_state_definitions")

    op.drop_index(
        "IX_document_type_definitions_firm_id", table_name="document_type_definitions"
    )
    op.drop_table("document_type_definitions")
