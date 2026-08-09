"""Allow only one default branch per firm and one default warehouse per branch.

``is_default`` was accepted on create and update and maintained by nothing, so
every branch in a firm could carry the flag at once and anything resolving "the
default" got an arbitrary row.

The service now demotes the previous holder; these partial indexes make the rule
hold at the database as well, the way ``UQ_user_firms_active_primary`` does.
MySQL ignores the predicate, so the service check stays authoritative there.

Existing data can already hold several defaults. The state is ambiguous by
construction and there is no correct winner, so the oldest row keeps the flag and
the rest are demoted -- reported in the migration output rather than done
silently.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0056"
down_revision: str | Sequence[str] | None = "20260809_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    ("branches", "firm_id", "UQ_branches_default_active"),
    ("warehouses", "branch_id", "UQ_warehouses_default_active"),
)


def upgrade() -> None:
    """Demote surplus defaults, then constrain the flag."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql":
        return
    for table, owner_column, index_name in _INDEXES:
        # branches and warehouses are firm-owned; platform has neither.
        if not inspector.has_table(table):
            continue
        demoted = bind.execute(
            sa.text(
                f"UPDATE {table} SET is_default = false "  # noqa: S608
                f"WHERE is_default AND NOT is_deleted AND id NOT IN ("
                f"  SELECT DISTINCT ON ({owner_column}) id FROM {table}"
                f"  WHERE is_default AND NOT is_deleted"
                f"  ORDER BY {owner_column}, created_at, id"
                f")"
            )
        ).rowcount
        if demoted:
            print(f"{table}: demoted {demoted} surplus default row(s)")
        if index_name not in {i["name"] for i in inspector.get_indexes(table)}:
            op.create_index(
                index_name,
                table,
                [owner_column],
                unique=True,
                postgresql_where=sa.text("is_default AND NOT is_deleted"),
            )


def downgrade() -> None:
    """Drop the single-default rule; the demotions are not reversible."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "postgresql":
        return
    for table, _owner_column, index_name in _INDEXES:
        if not inspector.has_table(table):
            continue
        if index_name in {i["name"] for i in inspector.get_indexes(table)}:
            op.drop_index(index_name, table_name=table)
