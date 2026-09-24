"""A deleted unit, group or packaging type gives its code back (D-CFG-21).

``UQ_uoms_code``, ``UQ_uom_groups_code`` and ``UQ_packaging_types_code`` were
plain unique keys over ``code``. Every one of these rows is soft-deleted, so a
deleted unit kept its code for ever: re-creating ``STRIP`` after deleting it was
refused as a duplicate of a row no screen showed. Each is replaced by a key
partial on live rows, the shape ``UQ_geo_countries_code_active`` and
``UQ_firms_code_active`` already use.

PostgreSQL only, as with the others: MySQL has no partial index, and there the
service's conflict answer stays the enforcement.

Idempotent and guarded: each table is touched only where it exists, the old key
is dropped only where it is still present (as a constraint or as an index,
because ``create_all`` builds some stores), and the new key is created only
where it is missing. Firm-owned reference data lives in every store, so run it
through ``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0160
Revises: 20260924_0159
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0160"
down_revision: str | Sequence[str] | None = "20260924_0159"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, old plain key, new partial key)
_KEYS = (
    ("uoms", "UQ_uoms_code", "UQ_uoms_code_active"),
    ("uom_groups", "UQ_uom_groups_code", "UQ_uom_groups_code_active"),
    ("packaging_types", "UQ_packaging_types_code", "UQ_packaging_types_code_active"),
)


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Report whether one index is already on the table."""
    return any(index["name"] == name for index in inspector.get_indexes(table))


def _has_constraint(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Report whether one unique constraint is already on the table."""
    return any(
        constraint["name"] == name
        for constraint in inspector.get_unique_constraints(table)
    )


def upgrade() -> None:
    """Swap each plain code key for one over live rows, where the table exists."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table, old, new in _KEYS:
        if not inspector.has_table(table):
            continue
        if _has_constraint(inspector, table, old):
            op.drop_constraint(old, table, type_="unique")
        elif _has_index(inspector, table, old):
            op.drop_index(old, table_name=table)
        if not _has_index(inspector, table, new):
            op.create_index(
                new,
                table,
                ["code"],
                unique=True,
                postgresql_where=sa.text("is_deleted = false"),
            )


def downgrade() -> None:
    """Restore the plain keys, which fails if a retired code has been reused."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table, old, new in _KEYS:
        if not inspector.has_table(table):
            continue
        if _has_index(inspector, table, new):
            op.drop_index(new, table_name=table)
        if not _has_constraint(inspector, table, old):
            op.create_unique_constraint(old, table, ["code"])
