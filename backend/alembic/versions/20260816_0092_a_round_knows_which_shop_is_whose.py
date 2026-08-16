"""Constrain the customer assignments a round is built from.

``territory_customer_assignments`` carried one table-wide key and nothing else,
which left three things the code assumes unenforced:

1. **One primary round per shop.** ``resolve_sales_scope`` decides which round a
   sale counts against by finding exactly one primary assignment. Two of them
   resolve to nothing, so the document is saved with no territory and no
   salesman and lands in none of the by-territory, by-route or by-salesman
   reports -- silently, because nothing refuses it.
2. **One shop per stop number.** ``visit_sequence`` had no key, so two outlets
   could both be stop 1 and the call list fell back to a ``created_at``
   tiebreak: the round was walked in an order nobody chose.
3. **The pair key spanned soft-deleted rows**, so a retired assignment reserved
   that shop for that round forever. ``set_customers`` works around it by
   un-retiring the row it finds, but any other insert path -- the bulk
   endpoint, a seeder, a future import -- would meet a 409 with no visible
   cause. Same trap as ``20260816_0091`` and ``UQ_firms_code_active``.

The primary backfill demotes duplicates rather than failing: the oldest
assignment keeps the flag, which is the one that has been answering for that
shop all along. Sequences are only ever duplicated within one round, so those
are cleared rather than guessed at -- an unplaced shop sorts last and can be
dragged back into position, where a wrong number is invisible.

PostgreSQL only, like the partial keys it mirrors. Firm-owned table, so run
``scripts/migrate_all_stores.py``.

Revision ID: 20260816_0092
Revises: 20260816_0091
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0092"
down_revision: str | Sequence[str] | None = "20260816_0091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "territory_customer_assignments"
_OLD_KEY = "UQ_territory_customer_assignments_territory_customer"
_PAIR = "UQ_territory_customer_assignments_pair_active"
_PRIMARY = "UQ_territory_customer_assignments_primary_active"
_SEQUENCE = "UQ_territory_customer_assignments_sequence_active"


def upgrade() -> None:
    """Backfill the conflicts, then add the three live-row keys."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql" or not inspector.has_table(_TABLE):
        return

    # Demote every primary but the oldest, per shop. Done before the key is
    # created so the migration cannot fail on data it is able to repair.
    op.execute(
        sa.text(
            f"""
            UPDATE {_TABLE} AS later
               SET is_primary = false
              FROM (
                    SELECT customer_id, MIN(created_at) AS kept
                      FROM {_TABLE}
                     WHERE is_primary AND is_deleted = false
                  GROUP BY customer_id
                    HAVING COUNT(*) > 1
                   ) AS dupes
             WHERE later.customer_id = dupes.customer_id
               AND later.is_primary
               AND later.is_deleted = false
               AND later.created_at > dupes.kept
            """
        )
    )
    # Clear duplicate stop numbers, keeping the oldest row at each number.
    op.execute(
        sa.text(
            f"""
            UPDATE {_TABLE} AS later
               SET visit_sequence = NULL
              FROM (
                    SELECT territory_id, visit_sequence, MIN(created_at) AS kept
                      FROM {_TABLE}
                     WHERE visit_sequence IS NOT NULL AND is_deleted = false
                  GROUP BY territory_id, visit_sequence
                    HAVING COUNT(*) > 1
                   ) AS dupes
             WHERE later.territory_id = dupes.territory_id
               AND later.visit_sequence = dupes.visit_sequence
               AND later.is_deleted = false
               AND later.created_at > dupes.kept
            """
        )
    )

    if _OLD_KEY in {item["name"] for item in inspector.get_unique_constraints(_TABLE)}:
        op.drop_constraint(_OLD_KEY, _TABLE, type_="unique")

    existing = {item["name"] for item in inspector.get_indexes(_TABLE)}
    if _PAIR not in existing:
        op.create_index(
            _PAIR,
            _TABLE,
            ["territory_id", "customer_id"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if _PRIMARY not in existing:
        op.create_index(
            _PRIMARY,
            _TABLE,
            ["customer_id"],
            unique=True,
            postgresql_where=sa.text("is_primary AND is_deleted = false"),
        )
    if _SEQUENCE not in existing:
        op.create_index(
            _SEQUENCE,
            _TABLE,
            ["territory_id", "visit_sequence"],
            unique=True,
            postgresql_where=sa.text(
                "visit_sequence IS NOT NULL AND is_deleted = false"
            ),
        )


def downgrade() -> None:
    """Restore the single table-wide pair key."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql" or not inspector.has_table(_TABLE):
        return
    existing = {item["name"] for item in inspector.get_indexes(_TABLE)}
    for name in (_SEQUENCE, _PRIMARY, _PAIR):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    if _OLD_KEY not in {
        item["name"] for item in inspector.get_unique_constraints(_TABLE)
    }:
        op.create_unique_constraint(_OLD_KEY, _TABLE, ["territory_id", "customer_id"])
