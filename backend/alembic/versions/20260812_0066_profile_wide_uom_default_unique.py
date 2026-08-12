"""Allow at most one profile-wide UOM default per business profile.

``business_profile_uom_defaults.firm_id`` is nullable on purpose: NULL is the
default every firm on that profile inherits, a value is one firm's override.
``UQ_business_profile_uom_defaults_firm_profile`` covers (firm_id,
business_profile_id), and PostgreSQL treats NULLs as distinct, so it constrains
the override rows and not the profile-wide ones.

That did not matter while only ``seed_uom_reference_data`` could write a NULL
row. It matters now that ``PUT /uom-framework/profiles/{id}/defaults?apply_to=
PROFILE`` can: two administrators saving at once would each find no existing
row and each insert one, and ``get_profile_default`` ranks firm rows above
profile-wide rows without ranking profile-wide rows against each other -- so
which of the duplicates a firm inherited would be arbitrary and could change
between queries.

A partial unique index is the same remedy ``20260809_0056`` applied to the
default-branch and default-warehouse flags. Surplus rows are folded first,
keeping the oldest, because an index cannot be created over existing
duplicates.

The table is firm-owned, so this must run against every store --
``scripts/migrate_all_stores.py``, not a bare ``alembic upgrade head``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0066"
down_revision: str | Sequence[str] | None = "20260811_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "business_profile_uom_defaults"
_INDEX = "UQ_business_profile_uom_defaults_profile_wide"


def upgrade() -> None:
    """Fold surplus profile-wide rows, then constrain them to one."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql":
        return
    # Firm-owned: the platform schema does not have this table.
    if not inspector.has_table(_TABLE):
        return
    folded = bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_deleted = true, deleted_at = now() "  # noqa: S608
            f"WHERE firm_id IS NULL AND NOT is_deleted AND id NOT IN ("
            f"  SELECT DISTINCT ON (business_profile_id) id FROM {_TABLE}"
            f"  WHERE firm_id IS NULL AND NOT is_deleted"
            f"  ORDER BY business_profile_id, created_at, id"
            f")"
        )
    ).rowcount
    if folded:
        print(f"{_TABLE}: retired {folded} duplicate profile-wide row(s)")
    if _INDEX not in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.create_index(
            _INDEX,
            _TABLE,
            ["business_profile_id"],
            unique=True,
            postgresql_where=sa.text("firm_id IS NULL AND NOT is_deleted"),
        )


def downgrade() -> None:
    """Drop the rule; the retired duplicates are not restored."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql":
        return
    if not inspector.has_table(_TABLE):
        return
    if _INDEX in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
