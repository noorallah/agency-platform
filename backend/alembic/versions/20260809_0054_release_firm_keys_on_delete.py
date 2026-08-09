"""Scope firm natural-key uniqueness to live firms.

``firms.code``, ``gst_number`` and ``pan_number`` carried table-wide UNIQUE
constraints, but ``FirmService.delete`` only soft deletes and
``_assert_unique`` ignores deleted rows. A deleted firm therefore kept its code,
GST and PAN reserved forever: re-creating it passed the service check and then
failed on the constraint with a 500 instead of a business error.

Uniqueness now applies only where ``is_deleted`` is false, matching
``UQ_users_email_active`` from ``20260809_0045``. MySQL ignores the predicate, so
``FirmService._assert_unique`` remains the authoritative check there.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0054"
down_revision: str | Sequence[str] | None = "20260809_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("code", "gst_number", "pan_number")


def upgrade() -> None:
    """Replace the table-wide firm key constraints with live-firm ones."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # firms exists only in the platform schema.
    if not inspector.has_table("firms"):
        return
    if bind.dialect.name != "postgresql":
        return

    for column in _COLUMNS:
        duplicates = bind.execute(
            sa.text(
                f"SELECT count(*) FROM ("
                f"  SELECT {column} FROM firms"
                f"  WHERE is_deleted = false AND {column} IS NOT NULL"
                f"  GROUP BY {column} HAVING count(*) > 1"
                f") AS d"
            )
        ).scalar()
        if duplicates:
            raise RuntimeError(
                f"Cannot scope firm {column} uniqueness: {duplicates} duplicate "
                "live value(s) exist. Resolve them before upgrading."
            )

    existing = {c["name"] for c in inspector.get_unique_constraints("firms")}
    indexes = {i["name"] for i in inspector.get_indexes("firms")}
    for column in _COLUMNS:
        old_constraint = f"UQ_firms_{column}"
        new_index = f"UQ_firms_{column}_active"
        if old_constraint in existing:
            op.drop_constraint(old_constraint, "firms", type_="unique")
        if new_index not in indexes:
            op.create_index(
                new_index,
                "firms",
                [column],
                unique=True,
                postgresql_where=sa.text("is_deleted = false"),
            )


def downgrade() -> None:
    """Restore the table-wide firm key constraints."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("firms") or bind.dialect.name != "postgresql":
        return
    indexes = {i["name"] for i in inspector.get_indexes("firms")}
    existing = {c["name"] for c in inspector.get_unique_constraints("firms")}
    for column in _COLUMNS:
        new_index = f"UQ_firms_{column}_active"
        old_constraint = f"UQ_firms_{column}"
        if new_index in indexes:
            op.drop_index(new_index, table_name="firms")
        if old_constraint not in existing:
            op.create_unique_constraint(old_constraint, "firms", [column])
