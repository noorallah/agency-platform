"""Create sales territory and beat-planning foundation schema.

Revision ID: 20260801_0013
Revises: 20260801_0012
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0013"
down_revision: str | None = "20260801_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create configurable territory hierarchy, assignments, and beat plans."""
    op.create_table(
        "sales_hierarchy_configs",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("max_levels", sa.Integer(), nullable=False, server_default="6"),
        sa.Column(
            "allow_multi_route_per_salesman",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "allow_multi_salesman_per_route",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "enforce_customer_leaf_assignment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
            ["firm_id"], ["firms.id"], name=op.f("FK_sales_hierarchy_configs_firms")
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_sales_hierarchy_configs_business_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_sales_hierarchy_configs")),
        sa.UniqueConstraint("firm_id", name="UQ_sales_hierarchy_configs_firm"),
    )
    op.create_index(
        op.f("IX_sales_hierarchy_configs_firm_id"),
        "sales_hierarchy_configs",
        ["firm_id"],
    )

    op.create_table(
        "sales_hierarchy_levels",
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("level_order", sa.Integer(), nullable=False),
        sa.Column("level_code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("max_nodes_per_parent", sa.Integer(), nullable=True),
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
            ["config_id"],
            ["sales_hierarchy_configs.id"],
            name=op.f("FK_sales_hierarchy_levels_sales_hierarchy_configs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_sales_hierarchy_levels")),
        sa.UniqueConstraint(
            "config_id",
            "level_order",
            name="UQ_sales_hierarchy_level_order",
        ),
        sa.UniqueConstraint(
            "config_id",
            "level_code",
            name="UQ_sales_hierarchy_level_code",
        ),
    )
    op.create_index(
        "IX_sales_hierarchy_levels_config_enabled",
        "sales_hierarchy_levels",
        ["config_id", "is_enabled"],
    )
    op.create_index(
        op.f("IX_sales_hierarchy_levels_config_id"),
        "sales_hierarchy_levels",
        ["config_id"],
    )

    op.create_table(
        "sales_territories",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("hierarchy_level_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("path", sa.String(length=1200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
            ["firm_id"], ["firms.id"], name=op.f("FK_sales_territories_firms")
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_sales_territories_business_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["hierarchy_level_id"],
            ["sales_hierarchy_levels.id"],
            name=op.f("FK_sales_territories_sales_hierarchy_levels"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["sales_territories.id"],
            name=op.f("FK_sales_territories_sales_territories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_sales_territories")),
        sa.UniqueConstraint("firm_id", "code", name="UQ_sales_territories_firm_code"),
    )
    op.create_index(
        "IX_sales_territories_firm_parent",
        "sales_territories",
        ["firm_id", "parent_id"],
    )
    op.create_index(
        "IX_sales_territories_firm_level",
        "sales_territories",
        ["firm_id", "hierarchy_level_id"],
    )
    op.create_index(
        "IX_sales_territories_firm_path",
        "sales_territories",
        ["firm_id", "path"],
    )
    op.create_index(
        op.f("IX_sales_territories_firm_id"), "sales_territories", ["firm_id"]
    )
    op.create_index(
        op.f("IX_sales_territories_hierarchy_level_id"),
        "sales_territories",
        ["hierarchy_level_id"],
    )

    op.create_table(
        "territory_customer_assignments",
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")
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
            ["territory_id"],
            ["sales_territories.id"],
            name=op.f("FK_territory_customer_assignments_sales_territories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("FK_territory_customer_assignments_customers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_territory_customer_assignments")),
        sa.UniqueConstraint(
            "territory_id",
            "customer_id",
            name="UQ_territory_customer_assignments_territory_customer",
        ),
    )
    op.create_index(
        op.f("IX_territory_customer_assignments_territory_id"),
        "territory_customer_assignments",
        ["territory_id"],
    )
    op.create_index(
        "IX_territory_customer_assignments_customer",
        "territory_customer_assignments",
        ["customer_id"],
    )

    op.create_table(
        "territory_salesman_assignments",
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "include_children",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
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
            ["territory_id"],
            ["sales_territories.id"],
            name=op.f("FK_territory_salesman_assignments_sales_territories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("FK_territory_salesman_assignments_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_territory_salesman_assignments")),
        sa.UniqueConstraint(
            "territory_id",
            "user_id",
            name="UQ_territory_salesman_assignments_territory_user",
        ),
    )
    op.create_index(
        op.f("IX_territory_salesman_assignments_territory_id"),
        "territory_salesman_assignments",
        ["territory_id"],
    )
    op.create_index(
        "IX_territory_salesman_assignments_user",
        "territory_salesman_assignments",
        ["user_id"],
    )

    op.create_table(
        "sales_beat_plans",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan_type", sa.String(length=20), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("week_of_month", sa.Integer(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["firm_id"], ["firms.id"], name=op.f("FK_sales_beat_plans_firms")
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            name=op.f("FK_sales_beat_plans_business_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["sales_territories.id"],
            name=op.f("FK_sales_beat_plans_sales_territories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_sales_beat_plans")),
        sa.UniqueConstraint("firm_id", "code", name="UQ_sales_beat_plans_firm_code"),
    )
    op.create_index(
        "IX_sales_beat_plans_firm_status",
        "sales_beat_plans",
        ["firm_id", "is_active"],
    )
    op.create_index(
        op.f("IX_sales_beat_plans_firm_id"), "sales_beat_plans", ["firm_id"]
    )
    op.create_index(
        op.f("IX_sales_beat_plans_territory_id"),
        "sales_beat_plans",
        ["territory_id"],
    )

    op.create_table(
        "sales_beat_plan_stops",
        sa.Column("beat_plan_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("stop_order", sa.Integer(), nullable=False),
        sa.Column("planned_duration_minutes", sa.Integer(), nullable=True),
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
            ["beat_plan_id"],
            ["sales_beat_plans.id"],
            name=op.f("FK_sales_beat_plan_stops_sales_beat_plans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["sales_territories.id"],
            name=op.f("FK_sales_beat_plan_stops_sales_territories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_sales_beat_plan_stops")),
        sa.UniqueConstraint(
            "beat_plan_id",
            "stop_order",
            name="UQ_sales_beat_plan_stops_plan_order",
        ),
        sa.UniqueConstraint(
            "beat_plan_id",
            "territory_id",
            name="UQ_sales_beat_plan_stops_plan_territory",
        ),
    )
    op.create_index(
        op.f("IX_sales_beat_plan_stops_beat_plan_id"),
        "sales_beat_plan_stops",
        ["beat_plan_id"],
    )
    op.create_index(
        op.f("IX_sales_beat_plan_stops_territory_id"),
        "sales_beat_plan_stops",
        ["territory_id"],
    )


def downgrade() -> None:
    """Drop territory hierarchy and beat-planning foundation schema."""
    op.drop_table("sales_beat_plan_stops")
    op.drop_table("sales_beat_plans")
    op.drop_table("territory_salesman_assignments")
    op.drop_table("territory_customer_assignments")
    op.drop_table("sales_territories")
    op.drop_table("sales_hierarchy_levels")
    op.drop_table("sales_hierarchy_configs")
