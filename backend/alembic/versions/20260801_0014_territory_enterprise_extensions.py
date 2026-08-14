"""Add enterprise territory extensions for geo masters and route metadata.

Revision ID: 20260801_0014
Revises: 20260801_0013
Create Date: 2026-08-01
"""

# ruff: noqa: D103

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0014"
down_revision: str | None = "20260801_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
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
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    """Apply the territory extensions for geo masters and route metadata."""
    op.add_column(
        "territory_customer_assignments",
        sa.Column("visit_sequence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "territory_customer_assignments",
        sa.Column(
            "is_potential",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "geo_countries",
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("iso2", sa.String(length=2), nullable=True),
        sa.Column("iso3", sa.String(length=3), nullable=True),
        sa.Column("phone_code", sa.String(length=10), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_geo_countries")),
        sa.UniqueConstraint("code", name="UQ_geo_countries_code"),
        sa.UniqueConstraint("name", name="UQ_geo_countries_name"),
    )
    op.create_table(
        "geo_states",
        sa.Column("country_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["country_id"], ["geo_countries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_geo_states")),
        sa.UniqueConstraint("country_id", "code", name="UQ_geo_states_country_code"),
        sa.UniqueConstraint("country_id", "name", name="UQ_geo_states_country_name"),
    )
    op.create_index(
        "IX_geo_states_country_active", "geo_states", ["country_id", "is_active"]
    )

    op.create_table(
        "geo_districts",
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(["state_id"], ["geo_states.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_geo_districts")),
        sa.UniqueConstraint("state_id", "code", name="UQ_geo_districts_state_code"),
        sa.UniqueConstraint("state_id", "name", name="UQ_geo_districts_state_name"),
    )
    op.create_index(
        "IX_geo_districts_state_active", "geo_districts", ["state_id", "is_active"]
    )

    op.create_table(
        "geo_cities",
        sa.Column("district_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["district_id"], ["geo_districts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_geo_cities")),
        sa.UniqueConstraint("district_id", "code", name="UQ_geo_cities_district_code"),
        sa.UniqueConstraint("district_id", "name", name="UQ_geo_cities_district_name"),
    )
    op.create_index(
        "IX_geo_cities_district_active", "geo_cities", ["district_id", "is_active"]
    )

    op.create_table(
        "geo_postal_codes",
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(["city_id"], ["geo_cities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_geo_postal_codes")),
        sa.UniqueConstraint(
            "city_id", "postal_code", name="UQ_geo_postal_codes_city_postal_code"
        ),
    )
    op.create_index(
        "IX_geo_postal_codes_city_active", "geo_postal_codes", ["city_id", "is_active"]
    )

    op.create_table(
        "geo_localities",
        sa.Column("postal_code_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["postal_code_id"], ["geo_postal_codes.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_geo_localities")),
        sa.UniqueConstraint(
            "postal_code_id", "name", name="UQ_geo_localities_postal_code_name"
        ),
    )
    op.create_index(
        "IX_geo_localities_postal_active",
        "geo_localities",
        ["postal_code_id", "is_active"],
    )

    op.create_table(
        "address_masters",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("owner_type", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("address_type", sa.String(length=40), nullable=False),
        sa.Column("line1", sa.String(length=300), nullable=False),
        sa.Column("line2", sa.String(length=300), nullable=True),
        sa.Column("landmark", sa.String(length=200), nullable=True),
        sa.Column("country_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("district_id", sa.Uuid(), nullable=True),
        sa.Column("city_id", sa.Uuid(), nullable=True),
        sa.Column("postal_code_id", sa.Uuid(), nullable=True),
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["country_id"], ["geo_countries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["state_id"], ["geo_states.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["district_id"], ["geo_districts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["city_id"], ["geo_cities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["postal_code_id"], ["geo_postal_codes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["locality_id"], ["geo_localities.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_address_masters")),
    )
    op.create_index(
        "IX_address_masters_owner",
        "address_masters",
        ["firm_id", "owner_type", "owner_id"],
    )
    op.create_index(
        "IX_address_masters_geo",
        "address_masters",
        ["country_id", "state_id", "city_id"],
    )

    op.create_table(
        "sales_route_types",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_sales_route_types")),
        sa.UniqueConstraint("firm_id", "code", name="UQ_sales_route_types_firm_code"),
        sa.UniqueConstraint("firm_id", "name", name="UQ_sales_route_types_firm_name"),
    )
    op.create_index(
        "IX_sales_route_types_firm_active",
        "sales_route_types",
        ["firm_id", "is_active"],
    )

    op.create_table(
        "territory_route_profiles",
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("route_type_id", sa.Uuid(), nullable=True),
        sa.Column(
            "visit_frequency",
            sa.String(length=20),
            nullable=False,
            server_default="ON_DEMAND",
        ),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("city_id", sa.Uuid(), nullable=True),
        sa.Column("postal_code_id", sa.Uuid(), nullable=True),
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["territory_id"], ["sales_territories.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["route_type_id"], ["sales_route_types.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["city_id"], ["geo_cities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["postal_code_id"], ["geo_postal_codes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["locality_id"], ["geo_localities.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_territory_route_profiles")),
        sa.UniqueConstraint(
            "territory_id", name="UQ_territory_route_profiles_territory"
        ),
    )
    op.create_index(
        "IX_territory_route_profiles_route_type",
        "territory_route_profiles",
        ["route_type_id"],
    )

    op.create_table(
        "territory_working_days",
        sa.Column("route_profile_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["route_profile_id"], ["territory_route_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("PK_territory_working_days")),
        sa.UniqueConstraint(
            "route_profile_id", "weekday", name="UQ_territory_working_days_profile_day"
        ),
    )
    op.create_index(
        "IX_territory_working_days_profile",
        "territory_working_days",
        ["route_profile_id"],
    )


def downgrade() -> None:
    """Reverse the territory extensions for geo masters and route metadata."""
    op.drop_table("territory_working_days")
    op.drop_table("territory_route_profiles")
    op.drop_table("sales_route_types")
    op.drop_index("IX_address_masters_geo", table_name="address_masters")
    op.drop_index("IX_address_masters_owner", table_name="address_masters")
    op.drop_table("address_masters")
    op.drop_table("geo_localities")
    op.drop_table("geo_postal_codes")
    op.drop_table("geo_cities")
    op.drop_table("geo_districts")
    op.drop_table("geo_states")
    op.drop_table("geo_countries")
    op.drop_column("territory_customer_assignments", "is_potential")
    op.drop_column("territory_customer_assignments", "visit_sequence")
