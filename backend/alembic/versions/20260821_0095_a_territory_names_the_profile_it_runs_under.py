"""Fill the business profile a territory, its hierarchy and its beat plans run under.

``SalesTerritoryService`` resolved the firm's assignment with a query of its
own and answered NULL for a firm nobody had assigned -- where
``resolve_capabilities`` had already decided that firm operates under the
platform default profile. So an unassigned firm's hierarchy config, every
territory beneath it and every beat plan copied from those territories recorded
no industry at all, and none of them answered a ``business_profile_id`` filter.
The service now shares ``app.business.gating.resolve_profile_id``; this fills
what it wrote before that.

The backfill reproduces that resolver per row rather than stamping the default
everywhere: the firm's own active assignment first, the store's default profile
second. A firm assigned after it built its territories therefore gets its real
profile, not GENERIC. Beat plans take their territory's value, which is what
``create_beat_plan`` copies -- one plan cannot belong to a different industry
from the route it calls.

Only rows still NULL are touched, so a replay cannot overwrite a profile
somebody has since set, and a store with neither an assignment nor a default
profile is left exactly as it is -- a configuration gap is not a decision.

Firm-owned tables, and ``business_profiles`` lives in the same store, so run
``scripts/migrate_all_stores.py``; a bare ``alembic upgrade head`` advances only
the platform schema, which holds no territories. Idempotent, and guarded by
``has_table`` because a store built by ``Base.metadata.create_all`` can hold
these tables at an older ``alembic_version`` -- and the platform schema holds
none of them.

Revision ID: 20260821_0095
Revises: 20260816_0094
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0095"
down_revision: str | Sequence[str] | None = "20260816_0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables carrying the column, filled from the firm's own resolution.
_FIRM_SCOPED = ("sales_hierarchy_configs", "sales_territories")

#: What ``resolve_profile_id`` answers, as a correlated subquery: the firm's
#: active assignment, else the store's default profile.
_RESOLVED = """
        COALESCE(
            (SELECT a.business_profile_id
               FROM firm_business_profiles AS a
               JOIN business_profiles AS p
                 ON p.id = a.business_profile_id
              WHERE a.firm_id = {table}.firm_id
                AND a.is_active = true
                AND a.is_deleted = false
                AND p.is_deleted = false
              LIMIT 1),
            (SELECT d.id
               FROM business_profiles AS d
              WHERE d.is_default = true
                AND d.status = 'ACTIVE'
                AND d.is_deleted = false
              LIMIT 1)
        )
"""


def upgrade() -> None:
    """Fill the profile on rows an unassigned firm left NULL."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_profiles") or not inspector.has_table(
        "firm_business_profiles"
    ):
        return

    for table in _FIRM_SCOPED:
        if not inspector.has_table(table):
            continue
        resolved = _RESOLVED.format(table=table)
        bind.execute(
            sa.text(
                f"""
                UPDATE {table}
                   SET business_profile_id = {resolved}
                 WHERE business_profile_id IS NULL
                   AND is_deleted = false
                   AND {resolved} IS NOT NULL
                """
            )
        )

    if not inspector.has_table("sales_beat_plans") or not inspector.has_table(
        "sales_territories"
    ):
        return
    # A beat plan inherits from the route it calls, the way create_beat_plan
    # copies it. Territories are filled above, so this reads the resolved value.
    inherited = """
        (SELECT t.business_profile_id
           FROM sales_territories AS t
          WHERE t.id = sales_beat_plans.territory_id)
    """
    bind.execute(
        sa.text(
            f"""
            UPDATE sales_beat_plans
               SET business_profile_id = {inherited}
             WHERE business_profile_id IS NULL
               AND is_deleted = false
               AND {inherited} IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    """Leave the filled profiles alone.

    Nothing records which rows were NULL before, and clearing every profile
    would take the assignment away from firms that always had one. The column
    stays nullable, so a downgraded schema holds these values harmlessly.
    """
