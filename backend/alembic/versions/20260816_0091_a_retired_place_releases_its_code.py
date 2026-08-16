"""Scope the geography master keys to live rows.

The six geography tables carried table-wide ``UNIQUE`` constraints on their code
and name. Every query in ``app/sales`` filters ``is_deleted``, so a retired
country is invisible while still holding both -- and re-creating it fails on a
constraint with nothing on screen to explain why. That is the same trap
``UQ_firms_code_active``, ``UQ_users_email_active`` and ``20260815_0089``
already closed elsewhere.

It was unreachable until now: nothing could soft-delete a geography row,
because no update or delete existed. Adding them is what makes it reachable, so
it is closed in the same change rather than discovered later by whoever first
retires a city and cannot make it again.

PostgreSQL only, like the three above: MySQL ignores an index predicate, so the
service-level checks (``_assert_geo_code_free`` and ``_assert_geo_unused``)
stay authoritative there.

Firm stores hold these tables too, so run
``scripts/migrate_all_stores.py``, not a bare ``alembic upgrade head``.

Revision ID: 20260816_0091
Revises: 20260816_0090
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0091"
down_revision: str | Sequence[str] | None = "20260816_0090"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, old constraint, new index, the columns it keys on)
_KEYS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "geo_countries",
        "UQ_geo_countries_code",
        "UQ_geo_countries_code_active",
        ("code",),
    ),
    (
        "geo_countries",
        "UQ_geo_countries_name",
        "UQ_geo_countries_name_active",
        ("name",),
    ),
    (
        "geo_states",
        "UQ_geo_states_country_code",
        "UQ_geo_states_country_code_active",
        ("country_id", "code"),
    ),
    (
        "geo_states",
        "UQ_geo_states_country_name",
        "UQ_geo_states_country_name_active",
        ("country_id", "name"),
    ),
    (
        "geo_districts",
        "UQ_geo_districts_state_code",
        "UQ_geo_districts_state_code_active",
        ("state_id", "code"),
    ),
    (
        "geo_districts",
        "UQ_geo_districts_state_name",
        "UQ_geo_districts_state_name_active",
        ("state_id", "name"),
    ),
    (
        "geo_cities",
        "UQ_geo_cities_district_code",
        "UQ_geo_cities_district_code_active",
        ("district_id", "code"),
    ),
    (
        "geo_cities",
        "UQ_geo_cities_district_name",
        "UQ_geo_cities_district_name_active",
        ("district_id", "name"),
    ),
    (
        "geo_postal_codes",
        "UQ_geo_postal_codes_city_postal_code",
        "UQ_geo_postal_codes_city_code_active",
        ("city_id", "postal_code"),
    ),
    (
        "geo_localities",
        "UQ_geo_localities_postal_code_name",
        "UQ_geo_localities_postal_name_active",
        ("postal_code_id", "name"),
    ),
)


def upgrade() -> None:
    """Replace the table-wide geography keys with ones scoped to live rows."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql":
        return
    for table, old_name, new_name, columns in _KEYS:
        # Guarded per table: firm stores are partly built by
        # `Base.metadata.create_all`, so a table can be absent or already
        # carry the new index at an older `alembic_version`.
        if not inspector.has_table(table):
            continue
        existing = {item["name"] for item in inspector.get_unique_constraints(table)}
        if old_name in existing:
            op.drop_constraint(old_name, table, type_="unique")
        if new_name in {item["name"] for item in inspector.get_indexes(table)}:
            continue
        op.create_index(
            new_name,
            table,
            list(columns),
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )


def downgrade() -> None:
    """Restore the table-wide geography keys."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql":
        return
    for table, old_name, new_name, columns in _KEYS:
        if not inspector.has_table(table):
            continue
        if new_name in {item["name"] for item in inspector.get_indexes(table)}:
            op.drop_index(new_name, table_name=table)
        if old_name not in {
            item["name"] for item in inspector.get_unique_constraints(table)
        }:
            op.create_unique_constraint(old_name, table, list(columns))
