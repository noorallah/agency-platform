"""Create business profile framework entities and baseline seeds.

Revision ID: 20260801_0011
Revises: 20260801_0010
Create Date: 2026-08-01
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0011"
down_revision: str | None = "20260801_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create business profile framework tables and seed baseline records."""
    op.create_table(
        "business_profiles",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("default_settings", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_business_profiles")),
        sa.UniqueConstraint("code", name=op.f("UQ_business_profiles_code")),
    )
    op.create_table(
        "business_features",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column(
            "default_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_business_features")),
        sa.UniqueConstraint("code", name=op.f("UQ_business_features_code")),
    )
    op.create_table(
        "business_modules",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ui_route", sa.String(length=100), nullable=True),
        sa.Column(
            "default_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_business_modules")),
        sa.UniqueConstraint("code", name=op.f("UQ_business_modules_code")),
    )
    op.create_table(
        "profile_features",
        sa.Column("business_profile_id", sa.Uuid(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_profile_features_business_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["business_features.id"],
            name=op.f("FK_profile_features_business_features"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_profile_features")),
        sa.UniqueConstraint(
            "business_profile_id",
            "feature_id",
            name=op.f("UQ_profile_features_business_profile_id"),
        ),
    )
    op.create_table(
        "profile_modules",
        sa.Column("business_profile_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_profile_modules_business_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["business_modules.id"],
            name=op.f("FK_profile_modules_business_modules"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_profile_modules")),
        sa.UniqueConstraint(
            "business_profile_id",
            "module_id",
            name=op.f("UQ_profile_modules_business_profile_id"),
        ),
    )
    op.create_table(
        "attribute_definitions",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=50), nullable=False),
        sa.Column(
            "mandatory", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("validation_rule", sa.JSON(), nullable=True),
        sa.Column("applicable_category", sa.String(length=100), nullable=True),
        sa.Column("applicable_business_profile_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
            ["applicable_business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_attribute_definitions_business_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_attribute_definitions")),
        sa.UniqueConstraint("code", name=op.f("UQ_attribute_definitions_code")),
    )
    op.create_table(
        "category_attribute_rules",
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("category_code", sa.String(length=100), nullable=False),
        sa.Column("attribute_definition_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("validation_override", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_category_attribute_rules_business_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["attribute_definition_id"],
            ["attribute_definitions.id"],
            name=op.f("FK_category_attribute_rules_attribute_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_category_attribute_rules")),
        sa.UniqueConstraint(
            "business_profile_id",
            "category_code",
            "attribute_definition_id",
            name=op.f("UQ_category_attribute_rules_business_profile_id"),
        ),
    )
    op.create_table(
        "firm_business_profiles",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
            ["firm_id"], ["firms.id"], name=op.f("FK_firm_business_profiles_firms")
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_firm_business_profiles_business_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_firm_business_profiles")),
        sa.UniqueConstraint("firm_id", name=op.f("UQ_firm_business_profiles_firm_id")),
    )

    _seed_baseline_data()


def downgrade() -> None:
    """Drop business profile framework tables."""
    op.drop_table("firm_business_profiles")
    op.drop_table("category_attribute_rules")
    op.drop_table("attribute_definitions")
    op.drop_table("profile_modules")
    op.drop_table("profile_features")
    op.drop_table("business_modules")
    op.drop_table("business_features")
    op.drop_table("business_profiles")


def _seed_baseline_data() -> None:
    connection = op.get_bind()
    profiles = sa.table(
        "business_profiles",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("industry_type", sa.String()),
        sa.column("status", sa.String()),
        sa.column("is_default", sa.Boolean()),
        sa.column("default_settings", sa.JSON()),
        sa.column("version", sa.Integer()),
    )
    features = sa.table(
        "business_features",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("default_enabled", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("version", sa.Integer()),
    )
    modules = sa.table(
        "business_modules",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("ui_route", sa.String()),
        sa.column("default_enabled", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("version", sa.Integer()),
    )
    profile_features = sa.table(
        "profile_features",
        sa.column("id", sa.Uuid()),
        sa.column("business_profile_id", sa.Uuid()),
        sa.column("feature_id", sa.Uuid()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("configuration", sa.JSON()),
        sa.column("version", sa.Integer()),
    )
    profile_modules = sa.table(
        "profile_modules",
        sa.column("id", sa.Uuid()),
        sa.column("business_profile_id", sa.Uuid()),
        sa.column("module_id", sa.Uuid()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("is_visible", sa.Boolean()),
        sa.column("display_order", sa.Integer()),
        sa.column("configuration", sa.JSON()),
        sa.column("version", sa.Integer()),
    )
    attribute_definitions = sa.table(
        "attribute_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("data_type", sa.String()),
        sa.column("mandatory", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("validation_rule", sa.JSON()),
        sa.column("version", sa.Integer()),
    )
    category_rules = sa.table(
        "category_attribute_rules",
        sa.column("id", sa.Uuid()),
        sa.column("business_profile_id", sa.Uuid()),
        sa.column("category_code", sa.String()),
        sa.column("attribute_definition_id", sa.Uuid()),
        sa.column("is_mandatory", sa.Boolean()),
        sa.column("version", sa.Integer()),
    )

    profile_ids = {
        "GENERIC": UUID("10000000-0000-0000-0000-000000000001"),
        "AGENCY": UUID("10000000-0000-0000-0000-000000000002"),
        "PHARMACY": UUID("10000000-0000-0000-0000-000000000003"),
        "FOOD": UUID("10000000-0000-0000-0000-000000000004"),
        "RESTAURANT": UUID("10000000-0000-0000-0000-000000000005"),
        "GARMENTS": UUID("10000000-0000-0000-0000-000000000006"),
        "ELECTRONICS": UUID("10000000-0000-0000-0000-000000000007"),
        "SERVICE": UUID("10000000-0000-0000-0000-000000000008"),
        "MANUFACTURING": UUID("10000000-0000-0000-0000-000000000009"),
        "WHOLESALE": UUID("10000000-0000-0000-0000-00000000000A"),
        "RETAIL": UUID("10000000-0000-0000-0000-00000000000B"),
        "CUSTOM": UUID("10000000-0000-0000-0000-00000000000C"),
    }
    feature_ids = {
        "BATCH_TRACKING": UUID("20000000-0000-0000-0000-000000000001"),
        "EXPIRY_TRACKING": UUID("20000000-0000-0000-0000-000000000002"),
        "MANUFACTURING_DATE": UUID("20000000-0000-0000-0000-000000000003"),
        "WARRANTY": UUID("20000000-0000-0000-0000-000000000004"),
        "SERIAL_NUMBER": UUID("20000000-0000-0000-0000-000000000005"),
        "IMEI": UUID("20000000-0000-0000-0000-000000000006"),
        "DRUG_LICENSE": UUID("20000000-0000-0000-0000-000000000007"),
        "PRESCRIPTION_REQUIRED": UUID("20000000-0000-0000-0000-000000000008"),
        "SHELF_LIFE": UUID("20000000-0000-0000-0000-000000000009"),
        "RECIPE_MANAGEMENT": UUID("20000000-0000-0000-0000-00000000000A"),
        "KITCHEN_MANAGEMENT": UUID("20000000-0000-0000-0000-00000000000B"),
        "VEHICLE_TRACKING": UUID("20000000-0000-0000-0000-00000000000C"),
        "PROJECT_MANAGEMENT": UUID("20000000-0000-0000-0000-00000000000D"),
        "COMMISSION": UUID("20000000-0000-0000-0000-00000000000E"),
        "TERRITORY": UUID("20000000-0000-0000-0000-00000000000F"),
        "SERVICE_CONTRACTS": UUID("20000000-0000-0000-0000-000000000010"),
        "BARCODE": UUID("20000000-0000-0000-0000-000000000011"),
        "QR_CODE": UUID("20000000-0000-0000-0000-000000000012"),
        "ATTACHMENTS": UUID("20000000-0000-0000-0000-000000000013"),
        "APPROVAL_WORKFLOW": UUID("20000000-0000-0000-0000-000000000014"),
        "MULTIPLE_WAREHOUSES": UUID("20000000-0000-0000-0000-000000000015"),
    }
    module_ids = {
        "DASHBOARD": UUID("30000000-0000-0000-0000-000000000001"),
        "ADMINISTRATION": UUID("30000000-0000-0000-0000-000000000002"),
        "MASTERS": UUID("30000000-0000-0000-0000-000000000003"),
        "SALES": UUID("30000000-0000-0000-0000-000000000004"),
        "PURCHASES": UUID("30000000-0000-0000-0000-000000000005"),
        "INVENTORY": UUID("30000000-0000-0000-0000-000000000006"),
        "ACCOUNTING": UUID("30000000-0000-0000-0000-000000000007"),
        "REPORTS": UUID("30000000-0000-0000-0000-000000000008"),
        "SETTINGS": UUID("30000000-0000-0000-0000-000000000009"),
        "RECIPES": UUID("30000000-0000-0000-0000-00000000000A"),
        "KITCHEN": UUID("30000000-0000-0000-0000-00000000000B"),
        "PROJECTS": UUID("30000000-0000-0000-0000-00000000000C"),
        "CONTRACTS": UUID("30000000-0000-0000-0000-00000000000D"),
    }
    attribute_ids = {
        "EXPIRY_DATE": UUID("40000000-0000-0000-0000-000000000001"),
        "BATCH_NUMBER": UUID("40000000-0000-0000-0000-000000000002"),
        "MANUFACTURER": UUID("40000000-0000-0000-0000-000000000003"),
        "WARRANTY_MONTHS": UUID("40000000-0000-0000-0000-000000000004"),
        "IMEI": UUID("40000000-0000-0000-0000-000000000005"),
        "COLOR": UUID("40000000-0000-0000-0000-000000000006"),
        "SIZE": UUID("40000000-0000-0000-0000-000000000007"),
        "WEIGHT": UUID("40000000-0000-0000-0000-000000000008"),
        "SHELF_LIFE_DAYS": UUID("40000000-0000-0000-0000-000000000009"),
        "FSSAI_NUMBER": UUID("40000000-0000-0000-0000-00000000000A"),
        "DRUG_LICENSE_NUMBER": UUID("40000000-0000-0000-0000-00000000000B"),
        "ENGINE_NUMBER": UUID("40000000-0000-0000-0000-00000000000C"),
        "CHASSIS_NUMBER": UUID("40000000-0000-0000-0000-00000000000D"),
    }

    op.bulk_insert(
        profiles,
        [
            {
                "id": profile_id,
                "code": code,
                "name": code.title(),
                "description": f"{code.title()} business operating profile.",
                "industry_type": code,
                "status": "ACTIVE",
                "is_default": code == "GENERIC",
                "default_settings": {},
                "version": 1,
            }
            for code, profile_id in profile_ids.items()
        ],
    )
    op.bulk_insert(
        features,
        [
            {
                "id": feature_id,
                "code": code,
                "name": code.replace("_", " ").title(),
                "description": f"{code.replace('_', ' ').title()} control.",
                "category": "OPERATIONS",
                "default_enabled": code in {"BARCODE", "ATTACHMENTS"},
                "is_active": True,
                "version": 1,
            }
            for code, feature_id in feature_ids.items()
        ],
    )
    op.bulk_insert(
        modules,
        [
            {
                "id": module_id,
                "code": code,
                "name": code.replace("_", " ").title(),
                "description": f"{code.replace('_', ' ').title()} module.",
                "ui_route": code.lower(),
                "default_enabled": code
                in {
                    "DASHBOARD",
                    "ADMINISTRATION",
                    "MASTERS",
                    "REPORTS",
                    "SETTINGS",
                },
                "is_active": True,
                "version": 1,
            }
            for code, module_id in module_ids.items()
        ],
    )

    generic_profile_id = profile_ids["GENERIC"]
    op.bulk_insert(
        profile_features,
        [
            {
                "id": UUID(f"50000000-0000-0000-0000-0000000000{index:02X}"),
                "business_profile_id": generic_profile_id,
                "feature_id": feature_id,
                "is_enabled": code in {"BARCODE", "ATTACHMENTS"},
                "configuration": {},
                "version": 1,
            }
            for index, (code, feature_id) in enumerate(feature_ids.items(), start=1)
        ],
    )
    op.bulk_insert(
        profile_modules,
        [
            {
                "id": UUID(f"60000000-0000-0000-0000-0000000000{index:02X}"),
                "business_profile_id": generic_profile_id,
                "module_id": module_id,
                "is_enabled": code
                in {
                    "DASHBOARD",
                    "ADMINISTRATION",
                    "MASTERS",
                    "REPORTS",
                    "SETTINGS",
                },
                "is_visible": True,
                "display_order": index,
                "configuration": {},
                "version": 1,
            }
            for index, (code, module_id) in enumerate(module_ids.items(), start=1)
        ],
    )
    op.bulk_insert(
        attribute_definitions,
        [
            {
                "id": attribute_id,
                "code": code,
                "name": code.replace("_", " ").title(),
                "description": f"{code.replace('_', ' ').title()} attribute.",
                "data_type": "TEXT",
                # No attribute is mandatory for every firm. An unscoped
                # mandatory flag applies to every product everywhere, which
                # asked a pharmacy for an IMEI and an electronics distributor
                # for an expiry date -- and `AttributeService` refuses the
                # write, so it blocked product creation outright. Where an
                # attribute really is required, `category_attribute_rules`
                # says so per business profile and category, which is what the
                # rows below do. `20260815_0087` clears the flag on databases
                # that already ran this.
                "mandatory": False,
                "is_active": True,
                "validation_rule": {},
                "version": 1,
            }
            for code, attribute_id in attribute_ids.items()
        ],
    )
    op.bulk_insert(
        category_rules,
        [
            {
                "id": UUID("70000000-0000-0000-0000-000000000001"),
                "business_profile_id": profile_ids["PHARMACY"],
                "category_code": "MEDICINE",
                "attribute_definition_id": attribute_ids["BATCH_NUMBER"],
                "is_mandatory": True,
                "version": 1,
            },
            {
                "id": UUID("70000000-0000-0000-0000-000000000002"),
                "business_profile_id": profile_ids["PHARMACY"],
                "category_code": "MEDICINE",
                "attribute_definition_id": attribute_ids["EXPIRY_DATE"],
                "is_mandatory": True,
                "version": 1,
            },
            {
                "id": UUID("70000000-0000-0000-0000-000000000003"),
                "business_profile_id": profile_ids["PHARMACY"],
                "category_code": "MEDICINE",
                "attribute_definition_id": attribute_ids["MANUFACTURER"],
                "is_mandatory": True,
                "version": 1,
            },
            {
                "id": UUID("70000000-0000-0000-0000-000000000004"),
                "business_profile_id": profile_ids["FOOD"],
                "category_code": "FOOD",
                "attribute_definition_id": attribute_ids["EXPIRY_DATE"],
                "is_mandatory": True,
                "version": 1,
            },
            {
                "id": UUID("70000000-0000-0000-0000-000000000005"),
                "business_profile_id": profile_ids["FOOD"],
                "category_code": "FOOD",
                "attribute_definition_id": attribute_ids["SHELF_LIFE_DAYS"],
                "is_mandatory": True,
                "version": 1,
            },
            {
                "id": UUID("70000000-0000-0000-0000-000000000006"),
                "business_profile_id": profile_ids["ELECTRONICS"],
                "category_code": "ELECTRONICS",
                "attribute_definition_id": attribute_ids["WARRANTY_MONTHS"],
                "is_mandatory": True,
                "version": 1,
            },
            {
                "id": UUID("70000000-0000-0000-0000-000000000007"),
                "business_profile_id": profile_ids["ELECTRONICS"],
                "category_code": "ELECTRONICS",
                "attribute_definition_id": attribute_ids["IMEI"],
                "is_mandatory": True,
                "version": 1,
            },
        ],
    )

    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                "UPDATE business_profiles "
                "SET default_settings = '{}'::jsonb "
                "WHERE default_settings IS NULL"
            )
        )
