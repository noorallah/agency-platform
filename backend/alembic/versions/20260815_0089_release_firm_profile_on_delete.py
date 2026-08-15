"""Scope the firm business-profile assignment key to live rows.

``firm_business_profiles`` carried a table-wide ``UNIQUE (firm_id)``, so a
soft-deleted assignment would reserve its firm forever: every query in
``app/business`` filters ``is_deleted``, so the row is invisible while still
holding the key, and re-assigning that firm would fail on the constraint with
no visible cause.

Nothing sets ``is_deleted`` on this table today -- all four references only
filter on it -- so the trap is currently unreachable. This closes it before the
first "unassign" action opens it rather than after, and brings the table into
line with ``UQ_firms_code_active`` and ``UQ_users_email_active``.

PostgreSQL only, like those two: MySQL ignores a partial index predicate, so
there the service check stays authoritative -- ``assign_profile_to_firm``
updates the firm's existing row in place and never inserts a second.

Revision ID: 20260815_0089
Revises: 20260815_0088
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_0089"
down_revision: str | Sequence[str] | None = "20260815_0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "firm_business_profiles"
_OLD_CONSTRAINT = "UQ_firm_business_profiles_firm_id"
_NEW_INDEX = "UQ_firm_business_profiles_firm_active"


def upgrade() -> None:
    """Replace the table-wide firm key with one scoped to live rows."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned table: absent from the platform schema, present in every firm
    # store. Guarded so one migration can run against all of them.
    if not inspector.has_table(_TABLE) or bind.dialect.name != "postgresql":
        return

    # A duplicate live assignment would make the new index impossible to build,
    # and failing here with the count is far kinder than a bare index error.
    duplicates = bind.execute(
        sa.text(
            f"SELECT count(*) FROM (SELECT firm_id FROM {_TABLE} "
            "WHERE is_deleted = false GROUP BY firm_id HAVING count(*) > 1) d"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"Cannot scope {_TABLE} uniqueness: {duplicates} firm(s) hold more "
            "than one live assignment. Resolve them before upgrading."
        )

    existing = {c["name"] for c in inspector.get_unique_constraints(_TABLE)}
    indexes = {i["name"] for i in inspector.get_indexes(_TABLE)}
    if _OLD_CONSTRAINT in existing:
        op.drop_constraint(_OLD_CONSTRAINT, _TABLE, type_="unique")
    if _NEW_INDEX not in indexes:
        op.create_index(
            _NEW_INDEX,
            _TABLE,
            ["firm_id"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )


def downgrade() -> None:
    """Restore the table-wide assignment constraint."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE) or bind.dialect.name != "postgresql":
        return
    indexes = {i["name"] for i in inspector.get_indexes(_TABLE)}
    existing = {c["name"] for c in inspector.get_unique_constraints(_TABLE)}
    if _NEW_INDEX in indexes:
        op.drop_index(_NEW_INDEX, table_name=_TABLE)
    if _OLD_CONSTRAINT not in existing:
        # Only possible if no firm holds a soft-deleted assignment alongside a
        # live one -- which is exactly the state the upgrade exists to allow.
        op.create_unique_constraint(_OLD_CONSTRAINT, _TABLE, ["firm_id"])
