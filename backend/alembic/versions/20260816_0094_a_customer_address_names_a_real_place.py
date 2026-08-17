"""Give a customer address the geography keys, and fill them where the text says.

``customer_addresses`` held ``city``, ``area``, ``district``, ``state``,
``country`` and ``postal_code`` as plain strings with no link to the geography
masters. So "Parrys" and "Parry's Corner" never grouped, a pin-code search was
a string match, and there was nowhere to hang a coordinate -- adding a latitude
to a free-text address gives a map full of points nobody can group by locality.

Vendors, branches and warehouses already carried these keys and simply had no
form. Customers are the opposite and the reason this is a migration: they have
the text and no keys.

**The text stays.** It is NOT NULL, every report reads it, and a firm whose
masters are empty still has to be able to record an address. From here
``CustomerService`` derives it from the keys wherever they are set, so the two
cannot drift apart; rows with no keys keep the text they always had.

The backfill matches only what it is sure of: one live master row, compared
case-insensitively, at each rung in turn, and never below a rung that did not
match. Anything ambiguous is left NULL for someone to choose on screen -- a
guess here would be indistinguishable from a fact afterwards.

Firm-owned table, and the masters live in the same store, so run
``scripts/migrate_all_stores.py``. Idempotent: the sample-data and tenancy-reset
scripts build firm stores with ``Base.metadata.create_all``, so the columns can
already exist at an older ``alembic_version``.

Revision ID: 20260816_0094
Revises: 20260816_0093
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0094"
down_revision: str | Sequence[str] | None = "20260816_0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customer_addresses"

#: column, referred table, and the text column the backfill matches on.
_KEYS: tuple[tuple[str, str], ...] = (
    ("country_id", "geo_countries"),
    ("state_id", "geo_states"),
    ("district_id", "geo_districts"),
    ("city_id", "geo_cities"),
    ("postal_code_id", "geo_postal_codes"),
    ("locality_id", "geo_localities"),
)


def _existing_columns(inspector: sa.Inspector) -> set[str]:
    """Names already on the address table."""
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the six keys and backfill what the text unambiguously names."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        # The platform schema holds no customers.
        return

    present = _existing_columns(inspector)
    for column, referred in _KEYS:
        if column in present:
            continue
        op.add_column(_TABLE, sa.Column(column, sa.Uuid(), nullable=True))
        # Guarded the way `20260809_0042` guards cross-schema references: a
        # store that has not built its geography masters yet gets the column
        # without the constraint rather than a failed migration.
        if inspector.has_table(referred):
            op.create_foreign_key(
                f"FK_{_TABLE}_{column}",
                _TABLE,
                referred,
                [column],
                ["id"],
                ondelete="RESTRICT",
            )

    _backfill(bind, inspector)


def _backfill(bind: sa.engine.Connection, inspector: sa.Inspector) -> None:
    """Match each rung to a master row, but only where exactly one matches.

    Three passes, because real addresses are ragged:

    1. **Anchored**, top down -- a city is matched inside the district already
       found, which is what makes "Chennai" mean one place.
    2. **By unique name**, for a rung whose parent is blank. Half the seeded
       addresses have no district at all, and refusing them would leave a city
       unmatched that exactly one master row names. A name unique across the
       whole store is not a guess.
    3. **Upwards**, from whatever was matched. A city knows its district, which
       knows its state; filling ancestors this way cannot contradict itself,
       and the service refuses an address whose rungs disagree.

    Every statement is scoped to rows still NULL, so a replay cannot overwrite
    a place somebody has since chosen by hand.
    """
    if not all(inspector.has_table(referred) for _, referred in _KEYS):
        return

    statements = (
        # Country: the text column holds an ISO2 code.
        """
        UPDATE customer_addresses AS a
           SET country_id = m.id
          FROM geo_countries AS m
         WHERE a.country_id IS NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND upper(m.iso2) = upper(a.country)
           AND (SELECT count(*) FROM geo_countries AS d
                 WHERE d.is_deleted = false
                   AND upper(d.iso2) = upper(a.country)) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET state_id = m.id
          FROM geo_states AS m
         WHERE a.state_id IS NULL
           AND a.country_id IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND m.country_id = a.country_id
           AND lower(trim(m.name)) = lower(trim(a.state))
           AND (SELECT count(*) FROM geo_states AS d
                 WHERE d.is_deleted = false
                   AND d.country_id = a.country_id
                   AND lower(trim(d.name)) = lower(trim(a.state))) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET district_id = m.id
          FROM geo_districts AS m
         WHERE a.district_id IS NULL
           AND a.state_id IS NOT NULL
           AND a.district IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND m.state_id = a.state_id
           AND lower(trim(m.name)) = lower(trim(a.district))
           AND (SELECT count(*) FROM geo_districts AS d
                 WHERE d.is_deleted = false
                   AND d.state_id = a.state_id
                   AND lower(trim(d.name)) = lower(trim(a.district))) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET city_id = m.id
          FROM geo_cities AS m
         WHERE a.city_id IS NULL
           AND a.district_id IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND m.district_id = a.district_id
           AND lower(trim(m.name)) = lower(trim(a.city))
           AND (SELECT count(*) FROM geo_cities AS d
                 WHERE d.is_deleted = false
                   AND d.district_id = a.district_id
                   AND lower(trim(d.name)) = lower(trim(a.city))) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET postal_code_id = m.id
          FROM geo_postal_codes AS m
         WHERE a.postal_code_id IS NULL
           AND a.city_id IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND m.city_id = a.city_id
           AND trim(m.postal_code) = trim(a.postal_code)
           AND (SELECT count(*) FROM geo_postal_codes AS d
                 WHERE d.is_deleted = false
                   AND d.city_id = a.city_id
                   AND trim(d.postal_code) = trim(a.postal_code)) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET locality_id = m.id
          FROM geo_localities AS m
         WHERE a.locality_id IS NULL
           AND a.postal_code_id IS NOT NULL
           AND a.area IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND m.postal_code_id = a.postal_code_id
           AND lower(trim(m.name)) = lower(trim(a.area))
           AND (SELECT count(*) FROM geo_localities AS d
                 WHERE d.is_deleted = false
                   AND d.postal_code_id = a.postal_code_id
                   AND lower(trim(d.name)) = lower(trim(a.area))) = 1
        """,
    )

    # Pass 2: a rung whose parent is blank, matched on a name that exactly one
    # live master row in this store bears. Each still refuses to contradict an
    # ancestor pass 1 already settled -- written out per level rather than
    # generated, because that condition is the whole safety of the pass.
    by_unique_name = (
        """
        UPDATE customer_addresses AS a
           SET state_id = m.id
          FROM geo_states AS m
         WHERE a.state_id IS NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND lower(trim(m.name)) = lower(trim(a.state))
           AND (a.country_id IS NULL OR a.country_id = m.country_id)
           AND (SELECT count(*) FROM geo_states AS d
                 WHERE d.is_deleted = false
                   AND lower(trim(d.name)) = lower(trim(a.state))) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET district_id = m.id
          FROM geo_districts AS m
          JOIN geo_states AS ms ON ms.id = m.state_id
         WHERE a.district_id IS NULL
           AND a.district IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND lower(trim(m.name)) = lower(trim(a.district))
           AND (a.state_id IS NULL OR a.state_id = m.state_id)
           AND (a.country_id IS NULL OR a.country_id = ms.country_id)
           AND (SELECT count(*) FROM geo_districts AS d
                 WHERE d.is_deleted = false
                   AND lower(trim(d.name)) = lower(trim(a.district))) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET city_id = m.id
          FROM geo_cities AS m
          JOIN geo_districts AS md ON md.id = m.district_id
         WHERE a.city_id IS NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND lower(trim(m.name)) = lower(trim(a.city))
           AND (a.district_id IS NULL OR a.district_id = m.district_id)
           AND (a.state_id IS NULL OR a.state_id = md.state_id)
           AND (SELECT count(*) FROM geo_cities AS d
                 WHERE d.is_deleted = false
                   AND lower(trim(d.name)) = lower(trim(a.city))) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET postal_code_id = m.id
          FROM geo_postal_codes AS m
          JOIN geo_cities AS mc ON mc.id = m.city_id
         WHERE a.postal_code_id IS NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND trim(m.postal_code) = trim(a.postal_code)
           AND (a.city_id IS NULL OR a.city_id = m.city_id)
           AND (a.district_id IS NULL OR a.district_id = mc.district_id)
           AND (SELECT count(*) FROM geo_postal_codes AS d
                 WHERE d.is_deleted = false
                   AND trim(d.postal_code) = trim(a.postal_code)) = 1
        """,
        """
        UPDATE customer_addresses AS a
           SET locality_id = m.id
          FROM geo_localities AS m
          JOIN geo_postal_codes AS mp ON mp.id = m.postal_code_id
         WHERE a.locality_id IS NULL
           AND a.area IS NOT NULL
           AND a.is_deleted = false
           AND m.is_deleted = false
           AND lower(trim(m.name)) = lower(trim(a.area))
           AND (a.postal_code_id IS NULL OR a.postal_code_id = m.postal_code_id)
           AND (a.city_id IS NULL OR a.city_id = mp.city_id)
           AND (SELECT count(*) FROM geo_localities AS d
                 WHERE d.is_deleted = false
                   AND lower(trim(d.name)) = lower(trim(a.area))) = 1
        """,
    )

    # Pass 3: fill the ancestors of whatever was matched. These cannot be
    # wrong -- the master row itself says which parent it belongs to.
    upwards = (
        """
        UPDATE customer_addresses AS a SET city_id = m.city_id
          FROM geo_postal_codes AS m
         WHERE a.city_id IS NULL AND a.postal_code_id = m.id AND a.is_deleted = false
        """,
        """
        UPDATE customer_addresses AS a SET district_id = m.district_id
          FROM geo_cities AS m
         WHERE a.district_id IS NULL AND a.city_id = m.id AND a.is_deleted = false
        """,
        """
        UPDATE customer_addresses AS a SET state_id = m.state_id
          FROM geo_districts AS m
         WHERE a.state_id IS NULL AND a.district_id = m.id AND a.is_deleted = false
        """,
        """
        UPDATE customer_addresses AS a SET country_id = m.country_id
          FROM geo_states AS m
         WHERE a.country_id IS NULL AND a.state_id = m.id AND a.is_deleted = false
        """,
    )

    if bind.dialect.name != "postgresql":
        # `UPDATE ... FROM` is PostgreSQL syntax. Everywhere else the columns
        # are added and left for the screen to fill, which is the same place
        # an ambiguous match ends up anyway.
        return
    for statement in (*statements, *by_unique_name, *upwards):
        bind.execute(sa.text(statement))


def downgrade() -> None:
    """Drop the six keys, leaving the free text exactly as it was."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    present = _existing_columns(inspector)
    for column, _ in reversed(_KEYS):
        if column in present:
            op.drop_column(_TABLE, column)
