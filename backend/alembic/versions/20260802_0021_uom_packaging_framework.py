"""Enterprise UOM and packaging framework."""

from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_0021"
down_revision: str | Sequence[str] | None = "20260801_0020"
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
        "uoms",
        *_base_columns(),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=True),
        sa.Column("dimension", sa.String(length=30), nullable=False, server_default="COUNT"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("is_decimal_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("code", name="UQ_uoms_code"),
    )
    op.create_index("IX_uoms_status", "uoms", ["status"])

    op.create_table(
        "uom_groups",
        *_base_columns(),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.UniqueConstraint("code", name="UQ_uom_groups_code"),
    )
    op.create_index("IX_uom_groups_status", "uom_groups", ["status"])

    op.create_table(
        "uom_group_units",
        *_base_columns(),
        sa.Column("uom_group_id", sa.Uuid(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["uom_group_id"], ["uom_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uom_id"], ["uoms.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("uom_group_id", "uom_id", name="UQ_uom_group_units_group_uom"),
    )
    op.create_index("IX_uom_group_units_group", "uom_group_units", ["uom_group_id"])

    op.create_table(
        "packaging_types",
        *_base_columns(),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.UniqueConstraint("code", name="UQ_packaging_types_code"),
    )
    op.create_index("IX_packaging_types_status", "packaging_types", ["status"])

    op.create_table(
        "uom_conversion_rules",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("from_uom_id", sa.Uuid(), nullable=False),
        sa.Column("to_uom_id", sa.Uuid(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(24, 10), nullable=False),
        sa.Column("rounding_mode", sa.String(length=20), nullable=False, server_default="HALF_UP"),
        sa.Column("precision_scale", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["from_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_uom_conversion_rules_from_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["to_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_uom_conversion_rules_to_uoms",
        ),
        sa.UniqueConstraint(
            "firm_id",
            "product_id",
            "from_uom_id",
            "to_uom_id",
            "version",
            name="UQ_uom_conversion_rules_unique_version",
        ),
    )
    op.create_index("IX_uom_conversion_rules_firm", "uom_conversion_rules", ["firm_id"])
    op.create_index("IX_uom_conversion_rules_product", "uom_conversion_rules", ["product_id"])
    op.create_index(
        "IX_uom_conversion_rules_effective",
        "uom_conversion_rules",
        ["effective_from", "effective_to"],
    )

    op.create_table(
        "business_profile_uom_defaults",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=False),
        sa.Column("base_uom_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_uom_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_uom_id", sa.Uuid(), nullable=True),
        sa.Column("sales_uom_id", sa.Uuid(), nullable=True),
        sa.Column("allow_fraction", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_decimal", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["base_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_business_profile_uom_defaults_base_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_business_profile_uom_defaults_inventory_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_business_profile_uom_defaults_purchase_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["sales_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_business_profile_uom_defaults_sales_uoms",
        ),
        sa.UniqueConstraint("firm_id", "business_profile_id", name="UQ_business_profile_uom_defaults_firm_profile"),
    )
    op.create_index(
        "IX_business_profile_uom_defaults_profile",
        "business_profile_uom_defaults",
        ["business_profile_id"],
    )

    op.create_table(
        "uom_industry_templates",
        *_base_columns(),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("industry_type", sa.String(length=60), nullable=False),
        sa.Column("template_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("code", name="UQ_uom_industry_templates_code"),
    )
    op.create_index("IX_uom_industry_templates_industry", "uom_industry_templates", ["industry_type"])
    op.create_index("IX_uom_industry_templates_status", "uom_industry_templates", ["status"])

    op.create_table(
        "product_uom_configs",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("base_uom_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_uom_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_uom_id", sa.Uuid(), nullable=True),
        sa.Column("sales_uom_id", sa.Uuid(), nullable=True),
        sa.Column("default_receiving_uom_id", sa.Uuid(), nullable=True),
        sa.Column("default_dispatch_uom_id", sa.Uuid(), nullable=True),
        sa.Column("minimum_sales_uom_id", sa.Uuid(), nullable=True),
        sa.Column("allow_fraction", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_decimal", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("weight", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Numeric(18, 6), nullable=True),
        sa.Column("length", sa.Numeric(18, 6), nullable=True),
        sa.Column("width", sa.Numeric(18, 6), nullable=True),
        sa.Column("height", sa.Numeric(18, 6), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["base_uom_id"], ["uoms.id"], ondelete="RESTRICT", name="FK_product_uom_configs_base_uoms"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_product_uom_configs_inventory_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_product_uom_configs_purchase_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["sales_uom_id"], ["uoms.id"], ondelete="RESTRICT", name="FK_product_uom_configs_sales_uoms"
        ),
        sa.ForeignKeyConstraint(
            ["default_receiving_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_product_uom_configs_default_receiving_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["default_dispatch_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_product_uom_configs_default_dispatch_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["minimum_sales_uom_id"],
            ["uoms.id"],
            ondelete="RESTRICT",
            name="FK_product_uom_configs_minimum_sales_uoms",
        ),
        sa.UniqueConstraint("firm_id", "product_id", name="UQ_product_uom_configs_firm_product"),
    )
    op.create_index("IX_product_uom_configs_firm_product", "product_uom_configs", ["firm_id", "product_id"])

    op.create_table(
        "product_packaging_levels",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("parent_level_id", sa.Uuid(), nullable=True),
        sa.Column("packaging_type_id", sa.Uuid(), nullable=True),
        sa.Column("uom_id", sa.Uuid(), nullable=True),
        sa.Column("level_name", sa.String(length=120), nullable=False),
        sa.Column("conversion_to_base_factor", sa.Numeric(24, 10), nullable=False, server_default="1"),
        sa.Column("barcode", sa.String(length=120), nullable=True),
        sa.Column("qr_code", sa.String(length=300), nullable=True),
        sa.Column("gtin", sa.String(length=30), nullable=True),
        sa.Column("ean", sa.String(length=30), nullable=True),
        sa.Column("upc", sa.String(length=30), nullable=True),
        sa.Column("weight", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Numeric(18, 6), nullable=True),
        sa.Column("length", sa.Numeric(18, 6), nullable=True),
        sa.Column("width", sa.Numeric(18, 6), nullable=True),
        sa.Column("height", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_level_id"], ["product_packaging_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["packaging_type_id"], ["packaging_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uom_id"], ["uoms.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("firm_id", "product_id", "level_name", name="UQ_product_packaging_levels_product_level_name"),
    )
    op.create_index("IX_product_packaging_levels_product", "product_packaging_levels", ["firm_id", "product_id"])
    op.create_index("IX_product_packaging_levels_parent", "product_packaging_levels", ["parent_level_id"])
    op.create_index("IX_product_packaging_levels_barcode", "product_packaging_levels", ["barcode"])

    op.add_column("products", sa.Column("base_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("inventory_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("purchase_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("sales_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("default_receiving_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("default_dispatch_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("minimum_sales_uom_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("weight", sa.Numeric(18, 6), nullable=True))
    op.add_column("products", sa.Column("volume", sa.Numeric(18, 6), nullable=True))
    op.add_column("products", sa.Column("length", sa.Numeric(18, 6), nullable=True))
    op.add_column("products", sa.Column("width", sa.Numeric(18, 6), nullable=True))
    op.add_column("products", sa.Column("height", sa.Numeric(18, 6), nullable=True))
    op.add_column("products", sa.Column("allow_fraction", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("products", sa.Column("allow_decimal", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.create_foreign_key("FK_products_base_uom_id", "products", "uoms", ["base_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("FK_products_inventory_uom_id", "products", "uoms", ["inventory_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("FK_products_purchase_uom_id", "products", "uoms", ["purchase_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("FK_products_sales_uom_id", "products", "uoms", ["sales_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("FK_products_default_receiving_uom_id", "products", "uoms", ["default_receiving_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("FK_products_default_dispatch_uom_id", "products", "uoms", ["default_dispatch_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("FK_products_minimum_sales_uom_id", "products", "uoms", ["minimum_sales_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_index("IX_products_base_uom_id", "products", ["base_uom_id"])

    op.add_column("inventories", sa.Column("display_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"))
    op.add_column("inventories", sa.Column("display_uom_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("FK_inventories_display_uom_id", "inventories", "uoms", ["display_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_index("IX_inventories_display_uom_id", "inventories", ["display_uom_id"])

    op.add_column("inventory_transactions", sa.Column("entered_quantity", sa.Numeric(18, 4), nullable=True))
    op.add_column("inventory_transactions", sa.Column("entered_uom_id", sa.Uuid(), nullable=True))
    op.add_column("inventory_transactions", sa.Column("conversion_version", sa.Integer(), nullable=True))
    op.create_foreign_key("FK_inventory_transactions_entered_uom_id", "inventory_transactions", "uoms", ["entered_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_index("IX_inventory_transactions_entered_uom_id", "inventory_transactions", ["entered_uom_id"])

    op.add_column("stock_ledger_entries", sa.Column("original_quantity", sa.Numeric(18, 4), nullable=True))
    op.add_column("stock_ledger_entries", sa.Column("original_uom_id", sa.Uuid(), nullable=True))
    op.add_column("stock_ledger_entries", sa.Column("base_quantity", sa.Numeric(18, 4), nullable=True))
    op.create_foreign_key("FK_stock_ledger_entries_original_uom_id", "stock_ledger_entries", "uoms", ["original_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_index("IX_stock_ledger_entries_original_uom_id", "stock_ledger_entries", ["original_uom_id"])

    op.add_column("opening_stock_lines", sa.Column("entered_quantity", sa.Numeric(18, 4), nullable=True))
    op.add_column("opening_stock_lines", sa.Column("entered_uom_id", sa.Uuid(), nullable=True))
    op.add_column("opening_stock_lines", sa.Column("conversion_version", sa.Integer(), nullable=True))
    op.create_foreign_key("FK_opening_stock_lines_entered_uom_id", "opening_stock_lines", "uoms", ["entered_uom_id"], ["id"], ondelete="RESTRICT")
    op.create_index("IX_opening_stock_lines_entered_uom_id", "opening_stock_lines", ["entered_uom_id"])

    uoms = sa.table(
        "uoms",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("symbol", sa.String()),
        sa.column("dimension", sa.String()),
        sa.column("status", sa.String()),
        sa.column("is_decimal_allowed", sa.Boolean()),
    )
    op.bulk_insert(
        uoms,
        [
            {"id": uuid4(), "code": "PIECE", "name": "Piece", "symbol": "pc", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "EACH", "name": "Each", "symbol": "ea", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "TABLET", "name": "Tablet", "symbol": "tab", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "CAPSULE", "name": "Capsule", "symbol": "cap", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "STRIP", "name": "Strip", "symbol": "strip", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "PACK", "name": "Pack", "symbol": "pack", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "BOX", "name": "Box", "symbol": "box", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "CARTON", "name": "Carton", "symbol": "ctn", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "CASE", "name": "Case", "symbol": "case", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "BOTTLE", "name": "Bottle", "symbol": "btl", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "TUBE", "name": "Tube", "symbol": "tube", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "JAR", "name": "Jar", "symbol": "jar", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "BAG", "name": "Bag", "symbol": "bag", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "SACK", "name": "Sack", "symbol": "sack", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "BUNDLE", "name": "Bundle", "symbol": "bundle", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "ROLL", "name": "Roll", "symbol": "roll", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "COIL", "name": "Coil", "symbol": "coil", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "SHEET", "name": "Sheet", "symbol": "sheet", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "METER", "name": "Meter", "symbol": "m", "dimension": "LENGTH", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "FEET", "name": "Feet", "symbol": "ft", "dimension": "LENGTH", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "INCH", "name": "Inch", "symbol": "in", "dimension": "LENGTH", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "SQUARE_METER", "name": "Square Meter", "symbol": "m2", "dimension": "AREA", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "CUBIC_METER", "name": "Cubic Meter", "symbol": "m3", "dimension": "VOLUME", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "GRAM", "name": "Gram", "symbol": "g", "dimension": "WEIGHT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "KILOGRAM", "name": "Kilogram", "symbol": "kg", "dimension": "WEIGHT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "TON", "name": "Ton", "symbol": "t", "dimension": "WEIGHT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "MILLILITRE", "name": "Millilitre", "symbol": "ml", "dimension": "VOLUME", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "LITRE", "name": "Litre", "symbol": "l", "dimension": "VOLUME", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "PALLET", "name": "Pallet", "symbol": "plt", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
            {"id": uuid4(), "code": "CRATE", "name": "Crate", "symbol": "crate", "dimension": "COUNT", "status": "ACTIVE", "is_decimal_allowed": True},
        ],
    )


def downgrade() -> None:
    op.drop_index("IX_opening_stock_lines_entered_uom_id", table_name="opening_stock_lines")
    op.drop_constraint("FK_opening_stock_lines_entered_uom_id", "opening_stock_lines", type_="foreignkey")
    op.drop_column("opening_stock_lines", "conversion_version")
    op.drop_column("opening_stock_lines", "entered_uom_id")
    op.drop_column("opening_stock_lines", "entered_quantity")

    op.drop_index("IX_stock_ledger_entries_original_uom_id", table_name="stock_ledger_entries")
    op.drop_constraint("FK_stock_ledger_entries_original_uom_id", "stock_ledger_entries", type_="foreignkey")
    op.drop_column("stock_ledger_entries", "base_quantity")
    op.drop_column("stock_ledger_entries", "original_uom_id")
    op.drop_column("stock_ledger_entries", "original_quantity")

    op.drop_index("IX_inventory_transactions_entered_uom_id", table_name="inventory_transactions")
    op.drop_constraint("FK_inventory_transactions_entered_uom_id", "inventory_transactions", type_="foreignkey")
    op.drop_column("inventory_transactions", "conversion_version")
    op.drop_column("inventory_transactions", "entered_uom_id")
    op.drop_column("inventory_transactions", "entered_quantity")

    op.drop_index("IX_inventories_display_uom_id", table_name="inventories")
    op.drop_constraint("FK_inventories_display_uom_id", "inventories", type_="foreignkey")
    op.drop_column("inventories", "display_uom_id")
    op.drop_column("inventories", "display_quantity")

    op.drop_index("IX_products_base_uom_id", table_name="products")
    op.drop_constraint("FK_products_minimum_sales_uom_id", "products", type_="foreignkey")
    op.drop_constraint("FK_products_default_dispatch_uom_id", "products", type_="foreignkey")
    op.drop_constraint("FK_products_default_receiving_uom_id", "products", type_="foreignkey")
    op.drop_constraint("FK_products_sales_uom_id", "products", type_="foreignkey")
    op.drop_constraint("FK_products_purchase_uom_id", "products", type_="foreignkey")
    op.drop_constraint("FK_products_inventory_uom_id", "products", type_="foreignkey")
    op.drop_constraint("FK_products_base_uom_id", "products", type_="foreignkey")
    op.drop_column("products", "allow_decimal")
    op.drop_column("products", "allow_fraction")
    op.drop_column("products", "height")
    op.drop_column("products", "width")
    op.drop_column("products", "length")
    op.drop_column("products", "volume")
    op.drop_column("products", "weight")
    op.drop_column("products", "minimum_sales_uom_id")
    op.drop_column("products", "default_dispatch_uom_id")
    op.drop_column("products", "default_receiving_uom_id")
    op.drop_column("products", "sales_uom_id")
    op.drop_column("products", "purchase_uom_id")
    op.drop_column("products", "inventory_uom_id")
    op.drop_column("products", "base_uom_id")

    op.drop_index("IX_product_packaging_levels_barcode", table_name="product_packaging_levels")
    op.drop_index("IX_product_packaging_levels_parent", table_name="product_packaging_levels")
    op.drop_index("IX_product_packaging_levels_product", table_name="product_packaging_levels")
    op.drop_table("product_packaging_levels")

    op.drop_index("IX_product_uom_configs_firm_product", table_name="product_uom_configs")
    op.drop_table("product_uom_configs")

    op.drop_index("IX_uom_industry_templates_status", table_name="uom_industry_templates")
    op.drop_index("IX_uom_industry_templates_industry", table_name="uom_industry_templates")
    op.drop_table("uom_industry_templates")

    op.drop_index("IX_business_profile_uom_defaults_profile", table_name="business_profile_uom_defaults")
    op.drop_table("business_profile_uom_defaults")

    op.drop_index("IX_uom_conversion_rules_effective", table_name="uom_conversion_rules")
    op.drop_index("IX_uom_conversion_rules_product", table_name="uom_conversion_rules")
    op.drop_index("IX_uom_conversion_rules_firm", table_name="uom_conversion_rules")
    op.drop_table("uom_conversion_rules")

    op.drop_index("IX_packaging_types_status", table_name="packaging_types")
    op.drop_table("packaging_types")

    op.drop_index("IX_uom_group_units_group", table_name="uom_group_units")
    op.drop_table("uom_group_units")

    op.drop_index("IX_uom_groups_status", table_name="uom_groups")
    op.drop_table("uom_groups")

    op.drop_index("IX_uoms_status", table_name="uoms")
    op.drop_table("uoms")
