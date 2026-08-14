"""Phase 15 enterprise tax framework and product tax profile linkage."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260801_0017"
down_revision: str | Sequence[str] | None = "20260801_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply phase 15 enterprise tax framework and product tax profile linkage."""
    op.create_table(
        "tax_systems",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("country_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["country_id"], ["geo_countries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firm_id", "code", name="UQ_tax_systems_firm_code"),
    )
    op.create_index(
        "IX_tax_systems_firm_country",
        "tax_systems",
        ["firm_id", "country_id"],
        unique=False,
    )
    op.create_index(
        "IX_tax_systems_firm_status", "tax_systems", ["firm_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_tax_systems_firm_id"), "tax_systems", ["firm_id"], unique=False
    )
    op.create_index(
        op.f("ix_tax_systems_country_id"), "tax_systems", ["country_id"], unique=False
    )

    op.create_table(
        "tax_components",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("tax_system_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("short_label", sa.String(length=40), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "calculation_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("percentage", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column(
            "included_in_price", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "recoverable", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["tax_system_id"], ["tax_systems.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tax_system_id", "code", name="UQ_tax_components_system_code"
        ),
    )
    op.create_index(
        "IX_tax_components_firm_system",
        "tax_components",
        ["firm_id", "tax_system_id"],
        unique=False,
    )
    op.create_index(
        "IX_tax_components_firm_status",
        "tax_components",
        ["firm_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_components_firm_id"), "tax_components", ["firm_id"], unique=False
    )
    op.create_index(
        op.f("ix_tax_components_tax_system_id"),
        "tax_components",
        ["tax_system_id"],
        unique=False,
    )

    op.create_table(
        "tax_profiles",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("tax_system_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_historical", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["tax_system_id"], ["tax_systems.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firm_id", "code", name="UQ_tax_profiles_firm_code"),
    )
    op.create_index(
        "IX_tax_profiles_firm_system",
        "tax_profiles",
        ["firm_id", "tax_system_id"],
        unique=False,
    )
    op.create_index(
        "IX_tax_profiles_firm_status",
        "tax_profiles",
        ["firm_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_profiles_firm_id"), "tax_profiles", ["firm_id"], unique=False
    )
    op.create_index(
        op.f("ix_tax_profiles_tax_system_id"),
        "tax_profiles",
        ["tax_system_id"],
        unique=False,
    )

    op.create_table(
        "tax_profile_components",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("tax_profile_id", sa.Uuid(), nullable=False),
        sa.Column("tax_component_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("short_label", sa.String(length=40), nullable=True),
        sa.Column(
            "calculation_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("percentage", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column(
            "included_in_price", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "recoverable", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["tax_component_id"], ["tax_components.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tax_profile_id",
            "tax_component_id",
            name="UQ_tax_profile_components_profile_component",
        ),
    )
    op.create_index(
        "IX_tax_profile_components_firm_profile",
        "tax_profile_components",
        ["firm_id", "tax_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_profile_components_firm_id"),
        "tax_profile_components",
        ["firm_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_profile_components_tax_profile_id"),
        "tax_profile_components",
        ["tax_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_profile_components_tax_component_id"),
        "tax_profile_components",
        ["tax_component_id"],
        unique=False,
    )

    op.create_table(
        "tax_country_mappings",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("country_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("tax_system_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["country_id"], ["geo_countries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["tax_system_id"], ["tax_systems.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "firm_id",
            "country_id",
            "business_profile_id",
            "tax_system_id",
            name="UQ_tax_country_mappings_unique",
        ),
    )
    op.create_index(
        "IX_tax_country_mappings_firm_country",
        "tax_country_mappings",
        ["firm_id", "country_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_country_mappings_firm_id"),
        "tax_country_mappings",
        ["firm_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_country_mappings_country_id"),
        "tax_country_mappings",
        ["country_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_country_mappings_tax_system_id"),
        "tax_country_mappings",
        ["tax_system_id"],
        unique=False,
    )

    op.create_table(
        "tax_migration_mappings",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("legacy_tax_code", sa.String(length=50), nullable=False),
        sa.Column("legacy_tax_name", sa.String(length=120), nullable=False),
        sa.Column("source_system", sa.String(length=120), nullable=True),
        sa.Column("legacy_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("target_tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column(
            "keep_historical", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["target_tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "firm_id",
            "legacy_tax_code",
            "legacy_tax_name",
            name="UQ_tax_migration_mappings_legacy",
        ),
    )
    op.create_index(
        "IX_tax_migration_mappings_firm_historical",
        "tax_migration_mappings",
        ["firm_id", "keep_historical"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_migration_mappings_firm_id"),
        "tax_migration_mappings",
        ["firm_id"],
        unique=False,
    )

    op.create_table(
        "tax_settings",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column(
            "primary_label", sa.String(length=50), nullable=False, server_default="Tax"
        ),
        sa.Column(
            "component_label",
            sa.String(length=50),
            nullable=False,
            server_default="Component",
        ),
        sa.Column(
            "profile_label",
            sa.String(length=50),
            nullable=False,
            server_default="Profile",
        ),
        sa.Column(
            "report_label", sa.String(length=80), nullable=False, server_default="Tax"
        ),
        sa.Column(
            "allow_mixed_historical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "additional_settings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firm_id", name="UQ_tax_settings_firm"),
    )
    op.create_index(
        op.f("ix_tax_settings_firm_id"), "tax_settings", ["firm_id"], unique=False
    )

    op.add_column("products", sa.Column("tax_profile_id", sa.Uuid(), nullable=True))
    op.create_index(
        "IX_products_firm_tax_profile",
        "products",
        ["firm_id", "tax_profile_id"],
        unique=False,
    )
    op.create_foreign_key(
        "FK_products_tax_profile",
        "products",
        "tax_profiles",
        ["tax_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_column("products", "gst_rate")


def downgrade() -> None:
    """Reverse phase 15 enterprise tax framework and product tax profile linkage."""
    op.add_column("products", sa.Column("gst_rate", sa.Numeric(5, 2), nullable=True))
    op.drop_constraint("FK_products_tax_profile", "products", type_="foreignkey")
    op.drop_index("IX_products_firm_tax_profile", table_name="products")
    op.drop_column("products", "tax_profile_id")

    op.drop_index(op.f("ix_tax_settings_firm_id"), table_name="tax_settings")
    op.drop_table("tax_settings")

    op.drop_index(
        op.f("ix_tax_migration_mappings_firm_id"), table_name="tax_migration_mappings"
    )
    op.drop_index(
        "IX_tax_migration_mappings_firm_historical", table_name="tax_migration_mappings"
    )
    op.drop_table("tax_migration_mappings")

    op.drop_index(
        op.f("ix_tax_country_mappings_tax_system_id"), table_name="tax_country_mappings"
    )
    op.drop_index(
        op.f("ix_tax_country_mappings_country_id"), table_name="tax_country_mappings"
    )
    op.drop_index(
        op.f("ix_tax_country_mappings_firm_id"), table_name="tax_country_mappings"
    )
    op.drop_index(
        "IX_tax_country_mappings_firm_country", table_name="tax_country_mappings"
    )
    op.drop_table("tax_country_mappings")

    op.drop_index(
        op.f("ix_tax_profile_components_tax_component_id"),
        table_name="tax_profile_components",
    )
    op.drop_index(
        op.f("ix_tax_profile_components_tax_profile_id"),
        table_name="tax_profile_components",
    )
    op.drop_index(
        op.f("ix_tax_profile_components_firm_id"), table_name="tax_profile_components"
    )
    op.drop_index(
        "IX_tax_profile_components_firm_profile", table_name="tax_profile_components"
    )
    op.drop_table("tax_profile_components")

    op.drop_index(op.f("ix_tax_profiles_tax_system_id"), table_name="tax_profiles")
    op.drop_index(op.f("ix_tax_profiles_firm_id"), table_name="tax_profiles")
    op.drop_index("IX_tax_profiles_firm_status", table_name="tax_profiles")
    op.drop_index("IX_tax_profiles_firm_system", table_name="tax_profiles")
    op.drop_table("tax_profiles")

    op.drop_index(op.f("ix_tax_components_tax_system_id"), table_name="tax_components")
    op.drop_index(op.f("ix_tax_components_firm_id"), table_name="tax_components")
    op.drop_index("IX_tax_components_firm_status", table_name="tax_components")
    op.drop_index("IX_tax_components_firm_system", table_name="tax_components")
    op.drop_table("tax_components")

    op.drop_index(op.f("ix_tax_systems_country_id"), table_name="tax_systems")
    op.drop_index(op.f("ix_tax_systems_firm_id"), table_name="tax_systems")
    op.drop_index("IX_tax_systems_firm_status", table_name="tax_systems")
    op.drop_index("IX_tax_systems_firm_country", table_name="tax_systems")
    op.drop_table("tax_systems")
