"""Create enterprise vendor management schema.

Revision ID: 20260801_0015
Revises: 20260801_0014
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0015"
down_revision: str | None = "20260801_0014"
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
        "vendor_categories",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.UniqueConstraint("firm_id", "code", name="UQ_vendor_categories_firm_code"),
        sa.UniqueConstraint("firm_id", "name", name="UQ_vendor_categories_firm_name"),
    )
    op.create_index("IX_vendor_categories_firm_id", "vendor_categories", ["firm_id"])

    op.create_table(
        "vendor_types",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.UniqueConstraint("firm_id", "code", name="UQ_vendor_types_firm_code"),
        sa.UniqueConstraint("firm_id", "name", name="UQ_vendor_types_firm_name"),
    )
    op.create_index("IX_vendor_types_firm_id", "vendor_types", ["firm_id"])

    op.create_table(
        "vendors",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("type_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "gst_registration",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("gstin", sa.String(length=32), nullable=True),
        sa.Column("pan", sa.String(length=32), nullable=True),
        sa.Column("license_number", sa.String(length=64), nullable=True),
        sa.Column("registration_number", sa.String(length=64), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "business_attributes", sa.JSON(), nullable=False, server_default="{}"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["vendor_categories.id"]),
        sa.ForeignKeyConstraint(["type_id"], ["vendor_types.id"]),
        sa.ForeignKeyConstraint(["business_profile_id"], ["business_profiles.id"]),
        sa.UniqueConstraint("firm_id", "code", name="UQ_vendors_firm_code"),
        sa.UniqueConstraint("firm_id", "gstin", name="UQ_vendors_firm_gstin"),
    )
    op.create_index("IX_vendors_firm_id", "vendors", ["firm_id"])
    op.create_index("IX_vendors_firm_name", "vendors", ["firm_id", "name"])
    op.create_index("IX_vendors_firm_status", "vendors", ["firm_id", "status"])

    op.create_table(
        "vendor_contacts",
        *_base_columns(),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("designation", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
    )
    op.create_index("IX_vendor_contacts_vendor_id", "vendor_contacts", ["vendor_id"])

    op.create_table(
        "vendor_addresses",
        *_base_columns(),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("address_type", sa.String(length=20), nullable=False),
        sa.Column("address_line1", sa.String(length=250), nullable=False),
        sa.Column("address_line2", sa.String(length=250), nullable=True),
        sa.Column("country_id", sa.Uuid(), nullable=True),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("district_id", sa.Uuid(), nullable=True),
        sa.Column("city_id", sa.Uuid(), nullable=True),
        sa.Column("postal_code_id", sa.Uuid(), nullable=True),
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["country_id"], ["geo_countries.id"]),
        sa.ForeignKeyConstraint(["state_id"], ["geo_states.id"]),
        sa.ForeignKeyConstraint(["district_id"], ["geo_districts.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["geo_cities.id"]),
        sa.ForeignKeyConstraint(["postal_code_id"], ["geo_postal_codes.id"]),
        sa.ForeignKeyConstraint(["locality_id"], ["geo_localities.id"]),
    )
    op.create_index("IX_vendor_addresses_vendor_id", "vendor_addresses", ["vendor_id"])
    op.create_index(
        "IX_vendor_addresses_vendor_city",
        "vendor_addresses",
        ["vendor_id", "city_id"],
    )

    op.create_table(
        "vendor_bank_accounts",
        *_base_columns(),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("bank_name", sa.String(length=150), nullable=False),
        sa.Column("account_name", sa.String(length=150), nullable=False),
        sa.Column("account_number", sa.String(length=64), nullable=False),
        sa.Column("ifsc", sa.String(length=16), nullable=True),
        sa.Column("branch", sa.String(length=120), nullable=True),
        sa.Column("upi_id", sa.String(length=120), nullable=True),
        sa.Column("swift_code", sa.String(length=16), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "IX_vendor_bank_accounts_vendor_id",
        "vendor_bank_accounts",
        ["vendor_id"],
    )
    op.create_index(
        "IX_vendor_bank_accounts_vendor_primary",
        "vendor_bank_accounts",
        ["vendor_id", "is_primary"],
    )

    op.create_table(
        "vendor_tax_details",
        *_base_columns(),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("gstin", sa.String(length=32), nullable=True),
        sa.Column("pan", sa.String(length=32), nullable=True),
        sa.Column("tan", sa.String(length=32), nullable=True),
        sa.Column("fssai", sa.String(length=32), nullable=True),
        sa.Column("drug_license", sa.String(length=64), nullable=True),
        sa.Column("import_export_code", sa.String(length=32), nullable=True),
        sa.Column("extra_fields", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "IX_vendor_tax_details_vendor_id",
        "vendor_tax_details",
        ["vendor_id"],
    )
    op.create_index(
        "IX_vendor_tax_details_vendor_primary",
        "vendor_tax_details",
        ["vendor_id", "is_primary"],
    )

    op.create_table(
        "vendor_attachments",
        *_base_columns(),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "IX_vendor_attachments_vendor_id",
        "vendor_attachments",
        ["vendor_id"],
    )

    op.create_table(
        "vendor_notes",
        *_base_columns(),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "note_type", sa.String(length=30), nullable=False, server_default="GENERAL"
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
    )
    op.create_index("IX_vendor_notes_vendor_id", "vendor_notes", ["vendor_id"])


def downgrade() -> None:
    op.drop_index("IX_vendor_notes_vendor_id", table_name="vendor_notes")
    op.drop_table("vendor_notes")
    op.drop_index("IX_vendor_attachments_vendor_id", table_name="vendor_attachments")
    op.drop_table("vendor_attachments")
    op.drop_index(
        "IX_vendor_tax_details_vendor_primary",
        table_name="vendor_tax_details",
    )
    op.drop_index("IX_vendor_tax_details_vendor_id", table_name="vendor_tax_details")
    op.drop_table("vendor_tax_details")
    op.drop_index(
        "IX_vendor_bank_accounts_vendor_primary",
        table_name="vendor_bank_accounts",
    )
    op.drop_index(
        "IX_vendor_bank_accounts_vendor_id", table_name="vendor_bank_accounts"
    )
    op.drop_table("vendor_bank_accounts")
    op.drop_index(
        "IX_vendor_addresses_vendor_city",
        table_name="vendor_addresses",
    )
    op.drop_index("IX_vendor_addresses_vendor_id", table_name="vendor_addresses")
    op.drop_table("vendor_addresses")
    op.drop_index("IX_vendor_contacts_vendor_id", table_name="vendor_contacts")
    op.drop_table("vendor_contacts")
    op.drop_index("IX_vendors_firm_status", table_name="vendors")
    op.drop_index("IX_vendors_firm_name", table_name="vendors")
    op.drop_index("IX_vendors_firm_id", table_name="vendors")
    op.drop_table("vendors")
    op.drop_index("IX_vendor_types_firm_id", table_name="vendor_types")
    op.drop_table("vendor_types")
    op.drop_index("IX_vendor_categories_firm_id", table_name="vendor_categories")
    op.drop_table("vendor_categories")
