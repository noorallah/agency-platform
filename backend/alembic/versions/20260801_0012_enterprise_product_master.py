"""Create enterprise product master schema and module seed.

Revision ID: 20260801_0012
Revises: 20260801_0011
Create Date: 2026-08-01
"""

# ruff: noqa: E501

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0012"
down_revision: str | None = "20260801_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create product core, category, attribute-value, and media tables."""
    op.create_table(
        "product_categories",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
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
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name=op.f("FK_product_categories_firms")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["product_categories.id"],
            name=op.f("FK_product_categories_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_product_categories")),
        sa.UniqueConstraint("firm_id", "code", name="UQ_product_categories_firm_code"),
        sa.UniqueConstraint(
            "firm_id",
            "name",
            "parent_id",
            name="UQ_product_categories_firm_name_parent",
        ),
    )
    op.create_index(
        "IX_product_categories_firm_parent",
        "product_categories",
        ["firm_id", "parent_id"],
    )
    op.create_index(
        "IX_product_categories_firm_path", "product_categories", ["firm_id", "path"]
    )
    op.create_index(
        op.f("IX_product_categories_firm_id"), "product_categories", ["firm_id"]
    )

    op.create_table(
        "products",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("barcode", sa.String(length=120), nullable=True),
        sa.Column("qr_code", sa.String(length=300), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_type", sa.String(length=30), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("sub_category_id", sa.Uuid(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("hsn_sac", sa.String(length=20), nullable=True),
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("purchase_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("selling_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("mrp", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
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
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name=op.f("FK_products_firms")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("FK_products_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sub_category_id"],
            ["product_categories.id"],
            name=op.f("FK_products_product_categories_2"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_products")),
        sa.UniqueConstraint("firm_id", "code", name="UQ_products_firm_code"),
    )
    op.create_index("IX_products_firm_name", "products", ["firm_id", "name"])
    op.create_index("IX_products_firm_status", "products", ["firm_id", "status"])
    op.create_index("IX_products_firm_barcode", "products", ["firm_id", "barcode"])
    op.create_index("IX_products_firm_qr_code", "products", ["firm_id", "qr_code"])
    op.create_index(op.f("IX_products_firm_id"), "products", ["firm_id"])

    op.create_table(
        "product_attribute_values",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_definition_id", sa.Uuid(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(20, 6), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
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
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name=op.f("FK_product_attribute_values_firms")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("FK_product_attribute_values_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_definition_id"],
            ["attribute_definitions.id"],
            name=op.f("FK_product_attribute_values_attribute_definitions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_product_attribute_values")),
        sa.UniqueConstraint(
            "product_id",
            "attribute_definition_id",
            name="UQ_product_attribute_values_product_attribute",
        ),
    )
    op.create_index(
        "IX_product_attribute_values_firm_text",
        "product_attribute_values",
        ["firm_id", "value_text"],
    )
    op.create_index(
        "IX_product_attribute_values_firm_number",
        "product_attribute_values",
        ["firm_id", "value_number"],
    )
    op.create_index(
        "IX_product_attribute_values_firm_date",
        "product_attribute_values",
        ["firm_id", "value_date"],
    )
    op.create_index(
        op.f("IX_product_attribute_values_firm_id"),
        "product_attribute_values",
        ["firm_id"],
    )
    op.create_index(
        op.f("IX_product_attribute_values_product_id"),
        "product_attribute_values",
        ["product_id"],
    )
    op.create_index(
        op.f("IX_product_attribute_values_attribute_definition_id"),
        "product_attribute_values",
        ["attribute_definition_id"],
    )

    op.create_table(
        "product_media",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("media_kind", sa.String(length=30), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
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
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name=op.f("FK_product_media_firms")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("FK_product_media_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_product_media")),
    )
    op.create_index(
        "IX_product_media_firm_kind", "product_media", ["firm_id", "media_kind"]
    )
    op.create_index(
        "IX_product_media_product_primary",
        "product_media",
        ["product_id", "is_primary"],
    )
    op.create_index(op.f("IX_product_media_firm_id"), "product_media", ["firm_id"])
    op.create_index(
        op.f("IX_product_media_product_id"), "product_media", ["product_id"]
    )

    _seed_product_business_module()


def downgrade() -> None:
    """Drop product schema tables and seeded module mappings."""
    _remove_product_business_module()
    op.drop_table("product_media")
    op.drop_table("product_attribute_values")
    op.drop_table("products")
    op.drop_table("product_categories")


def _seed_product_business_module() -> None:
    connection = op.get_bind()
    module_id = UUID("30000000-0000-0000-0000-00000000000E")
    generic_profile_id = UUID("10000000-0000-0000-0000-000000000001")
    mapping_id = UUID("60000000-0000-0000-0000-0000000000EE")
    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                "INSERT INTO business_modules "
                "(id, code, name, description, ui_route, default_enabled, is_active, version, is_deleted) "
                "VALUES (:id, 'PRODUCTS', 'Products', 'Product master module.', 'products', true, true, 1, false) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": module_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO profile_modules "
                "(id, business_profile_id, module_id, is_enabled, is_visible, display_order, configuration, version, is_deleted) "
                "VALUES (:id, :profile_id, :module_id, true, true, 4, NULL, 1, false) "
                "ON CONFLICT (business_profile_id, module_id) DO NOTHING"
            ),
            {
                "id": mapping_id,
                "profile_id": generic_profile_id,
                "module_id": module_id,
            },
        )
        return
    if connection.dialect.name == "sqlite":
        connection.execute(
            sa.text(
                "INSERT OR IGNORE INTO business_modules "
                "(id, code, name, description, ui_route, default_enabled, is_active, version, is_deleted) "
                "VALUES (:id, 'PRODUCTS', 'Products', 'Product master module.', 'products', 1, 1, 1, 0)"
            ),
            {"id": module_id},
        )
        connection.execute(
            sa.text(
                "INSERT OR IGNORE INTO profile_modules "
                "(id, business_profile_id, module_id, is_enabled, is_visible, display_order, configuration, version, is_deleted) "
                "VALUES (:id, :profile_id, :module_id, 1, 1, 4, NULL, 1, 0)"
            ),
            {
                "id": mapping_id,
                "profile_id": generic_profile_id,
                "module_id": module_id,
            },
        )
        return
    existing = connection.execute(
        sa.text("SELECT id FROM business_modules WHERE code = 'PRODUCTS'")
    ).first()
    if existing is None:
        connection.execute(
            sa.text(
                "INSERT INTO business_modules "
                "(id, code, name, description, ui_route, default_enabled, is_active, version, is_deleted) "
                "VALUES (:id, 'PRODUCTS', 'Products', 'Product master module.', 'products', 1, 1, 1, 0)"
            ),
            {"id": module_id},
        )
    existing_mapping = connection.execute(
        sa.text(
            "SELECT id FROM profile_modules WHERE business_profile_id = :profile_id AND module_id = :module_id"
        ),
        {"profile_id": generic_profile_id, "module_id": module_id},
    ).first()
    if existing_mapping is None:
        connection.execute(
            sa.text(
                "INSERT INTO profile_modules "
                "(id, business_profile_id, module_id, is_enabled, is_visible, display_order, configuration, version, is_deleted) "
                "VALUES (:id, :profile_id, :module_id, 1, 1, 4, NULL, 1, 0)"
            ),
            {
                "id": mapping_id,
                "profile_id": generic_profile_id,
                "module_id": module_id,
            },
        )


def _remove_product_business_module() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM profile_modules WHERE module_id = :module_id"),
        {"module_id": UUID("30000000-0000-0000-0000-00000000000E")},
    )
    connection.execute(sa.text("DELETE FROM business_modules WHERE code = 'PRODUCTS'"))
