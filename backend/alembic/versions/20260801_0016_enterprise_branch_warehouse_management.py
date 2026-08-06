"""Create enterprise branch and warehouse management schema.

Revision ID: 20260801_0016
Revises: 20260801_0015
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0016"
down_revision: str | None = "20260801_0015"
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
        "branch_types",
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
        sa.UniqueConstraint("firm_id", "code", name="UQ_branch_types_firm_code"),
        sa.UniqueConstraint("firm_id", "name", name="UQ_branch_types_firm_name"),
    )
    op.create_index("IX_branch_types_firm_id", "branch_types", ["firm_id"])

    op.create_table(
        "branches",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("branch_type_id", sa.Uuid(), nullable=True),
        sa.Column("branch_manager_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=True),
        sa.Column("country_id", sa.Uuid(), nullable=True),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("district_id", sa.Uuid(), nullable=True),
        sa.Column("city_id", sa.Uuid(), nullable=True),
        sa.Column("postal_code_id", sa.Uuid(), nullable=True),
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        sa.Column("address_line1", sa.String(length=250), nullable=True),
        sa.Column("address_line2", sa.String(length=250), nullable=True),
        sa.Column("timezone", sa.String(length=100), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column(
            "gst_registration",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("pan", sa.String(length=32), nullable=True),
        sa.Column("license_number", sa.String(length=64), nullable=True),
        sa.Column("working_hours", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["business_profile_id"], ["business_profiles.id"]),
        sa.ForeignKeyConstraint(["branch_type_id"], ["branch_types.id"]),
        sa.ForeignKeyConstraint(["branch_manager_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["country_id"], ["geo_countries.id"]),
        sa.ForeignKeyConstraint(["state_id"], ["geo_states.id"]),
        sa.ForeignKeyConstraint(["district_id"], ["geo_districts.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["geo_cities.id"]),
        sa.ForeignKeyConstraint(["postal_code_id"], ["geo_postal_codes.id"]),
        sa.ForeignKeyConstraint(["locality_id"], ["geo_localities.id"]),
        sa.UniqueConstraint("firm_id", "code", name="UQ_branches_firm_code"),
    )
    op.create_index("IX_branches_firm_id", "branches", ["firm_id"])
    op.create_index("IX_branches_firm_name", "branches", ["firm_id", "name"])
    op.create_index("IX_branches_firm_status", "branches", ["firm_id", "status"])

    op.create_table(
        "warehouse_types",
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
        sa.UniqueConstraint("firm_id", "code", name="UQ_warehouse_types_firm_code"),
        sa.UniqueConstraint("firm_id", "name", name="UQ_warehouse_types_firm_name"),
    )
    op.create_index("IX_warehouse_types_firm_id", "warehouse_types", ["firm_id"])

    op.create_table(
        "warehouses",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("warehouse_type_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_manager_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("country_id", sa.Uuid(), nullable=True),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("district_id", sa.Uuid(), nullable=True),
        sa.Column("city_id", sa.Uuid(), nullable=True),
        sa.Column("postal_code_id", sa.Uuid(), nullable=True),
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        sa.Column("address_line1", sa.String(length=250), nullable=True),
        sa.Column("address_line2", sa.String(length=250), nullable=True),
        sa.Column("capacity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("capacity_unit", sa.String(length=20), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "temperature_controlled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("cold_storage", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "hazardous_storage",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_receiving_area",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_dispatch_area",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_returns_area",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_inspection_area",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_packing_area",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_loading_dock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["warehouse_type_id"], ["warehouse_types.id"]),
        sa.ForeignKeyConstraint(["warehouse_manager_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["business_profile_id"], ["business_profiles.id"]),
        sa.ForeignKeyConstraint(["country_id"], ["geo_countries.id"]),
        sa.ForeignKeyConstraint(["state_id"], ["geo_states.id"]),
        sa.ForeignKeyConstraint(["district_id"], ["geo_districts.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["geo_cities.id"]),
        sa.ForeignKeyConstraint(["postal_code_id"], ["geo_postal_codes.id"]),
        sa.ForeignKeyConstraint(["locality_id"], ["geo_localities.id"]),
        sa.UniqueConstraint("firm_id", "code", name="UQ_warehouses_firm_code"),
    )
    op.create_index("IX_warehouses_firm_id", "warehouses", ["firm_id"])
    op.create_index("IX_warehouses_firm_name", "warehouses", ["firm_id", "name"])
    op.create_index("IX_warehouses_branch_status", "warehouses", ["branch_id", "status"])

    op.create_table(
        "warehouse_storage_nodes",
        *_base_columns(),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("node_type", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["warehouse_storage_nodes.id"]),
        sa.UniqueConstraint(
            "warehouse_id",
            "code",
            name="UQ_warehouse_storage_nodes_warehouse_code",
        ),
        sa.UniqueConstraint(
            "warehouse_id",
            "name",
            "parent_id",
            name="UQ_warehouse_storage_nodes_warehouse_name_parent",
        ),
    )
    op.create_index(
        "IX_warehouse_storage_nodes_warehouse_id",
        "warehouse_storage_nodes",
        ["warehouse_id"],
    )
    op.create_index(
        "IX_warehouse_storage_nodes_warehouse_parent",
        "warehouse_storage_nodes",
        ["warehouse_id", "parent_id"],
    )
    op.create_index(
        "IX_warehouse_storage_nodes_warehouse_type",
        "warehouse_storage_nodes",
        ["warehouse_id", "node_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "IX_warehouse_storage_nodes_warehouse_type",
        table_name="warehouse_storage_nodes",
    )
    op.drop_index(
        "IX_warehouse_storage_nodes_warehouse_parent",
        table_name="warehouse_storage_nodes",
    )
    op.drop_index(
        "IX_warehouse_storage_nodes_warehouse_id",
        table_name="warehouse_storage_nodes",
    )
    op.drop_table("warehouse_storage_nodes")
    op.drop_index("IX_warehouses_branch_status", table_name="warehouses")
    op.drop_index("IX_warehouses_firm_name", table_name="warehouses")
    op.drop_index("IX_warehouses_firm_id", table_name="warehouses")
    op.drop_table("warehouses")
    op.drop_index("IX_warehouse_types_firm_id", table_name="warehouse_types")
    op.drop_table("warehouse_types")
    op.drop_index("IX_branches_firm_status", table_name="branches")
    op.drop_index("IX_branches_firm_name", table_name="branches")
    op.drop_index("IX_branches_firm_id", table_name="branches")
    op.drop_table("branches")
    op.drop_index("IX_branch_types_firm_id", table_name="branch_types")
    op.drop_table("branch_types")
