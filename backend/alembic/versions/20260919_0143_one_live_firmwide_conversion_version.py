"""One live version per firm-wide conversion rule (D-CFG-10).

``UQ_uom_conversion_rules_unique_version`` keys on ``product_id``, which is
NULL for a firm-wide rule, and PostgreSQL treats two NULLs as distinct -- so
two firm-wide rules for one unit pair could both be published as version 1
with different factors, and either converted a document line. Driven on
``fx_t0919duz7_r`` on 2026-09-19: BOX -> PIECE at 10 and at 12, both version 1,
both accepted.

Before the index can be built, live duplicates already in a store are
renumbered rather than retired: in each clashing group the earliest-created
rule keeps its version and each later one takes the next number above every
version the pair has used, in creation order, with a note appended to its
``reason``. Nothing is deleted and no factor changes; a later-published rule
winning as the higher version is what whoever published it meant. One fixture
store on the development server held such a pair when this was written.

Partial on ``product_id IS NULL AND NOT is_deleted``: a product's own rules
stay under the existing constraint, and a retired rule -- which neither
resolver reads -- holds no version. PostgreSQL only, as with every partial
index here; the service check in ``UomService._assert_version_free`` stays
authoritative elsewhere. Idempotent, and firm-owned, so run it through
``scripts/migrate_all_stores.py``.

Revision ID: 20260919_0143
Revises: 20260919_0142
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0143"
down_revision: str | None = "20260919_0142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "UQ_uom_conversion_rules_firmwide_version_active"
_TABLE = "uom_conversion_rules"
_NOTE = (
    " [renumbered from version {old} by migration 20260919_0143: another live"
    " firm-wide rule for this pair was already version {old}]"
)


def _renumber_live_duplicates(bind: sa.engine.Connection) -> None:
    """Give every later firm-wide duplicate the next free version number."""
    groups = bind.execute(
        sa.text(
            "SELECT firm_id, from_uom_id, to_uom_id, version_number "
            "FROM uom_conversion_rules "
            "WHERE product_id IS NULL AND NOT is_deleted "
            "GROUP BY firm_id, from_uom_id, to_uom_id, version_number "
            "HAVING count(*) > 1"
        )
    ).all()
    for firm_id, from_uom_id, to_uom_id, version_number in groups:
        key = {"firm": firm_id, "src": from_uom_id, "dst": to_uom_id}
        highest = bind.execute(
            sa.text(
                "SELECT max(version_number) FROM uom_conversion_rules "
                "WHERE firm_id = :firm AND from_uom_id = :src "
                "AND to_uom_id = :dst AND product_id IS NULL"
            ),
            key,
        ).scalar_one()
        later = bind.execute(
            sa.text(
                "SELECT id FROM uom_conversion_rules "
                "WHERE firm_id = :firm AND from_uom_id = :src "
                "AND to_uom_id = :dst AND product_id IS NULL "
                "AND NOT is_deleted AND version_number = :ver "
                "ORDER BY created_at, id OFFSET 1"
            ),
            {**key, "ver": version_number},
        ).scalars()
        for rule_id in list(later):
            highest += 1
            bind.execute(
                sa.text(
                    "UPDATE uom_conversion_rules "
                    "SET version_number = :new, "
                    "reason = coalesce(reason, '') || :note "
                    "WHERE id = :id"
                ),
                {
                    "new": highest,
                    "note": _NOTE.format(old=version_number),
                    "id": rule_id,
                },
            )


def upgrade() -> None:
    """Renumber any live duplicates, then add the partial unique index."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: absent from the platform schema, and firm stores are partly
    # built by `create_all`, so the index may already be there.
    if not inspector.has_table(_TABLE):
        return
    if any(index["name"] == _INDEX for index in inspector.get_indexes(_TABLE)):
        return
    if bind.dialect.name != "postgresql":
        return
    _renumber_live_duplicates(bind)
    op.create_index(
        _INDEX,
        _TABLE,
        ["firm_id", "from_uom_id", "to_uom_id", "version_number"],
        unique=True,
        postgresql_where=sa.text("product_id IS NULL AND NOT is_deleted"),
    )


def downgrade() -> None:
    """Drop the index; renumbered rules keep their new versions."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    if any(index["name"] == _INDEX for index in inspector.get_indexes(_TABLE)):
        op.drop_index(_INDEX, table_name=_TABLE)
