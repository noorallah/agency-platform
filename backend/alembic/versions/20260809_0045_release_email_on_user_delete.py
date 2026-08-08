"""Scope user email uniqueness to live accounts.

``users.email`` carried a table-wide UNIQUE constraint, but ``delete_user`` only
soft deletes. The address therefore stayed reserved forever: re-onboarding a
leaver failed with "A user with this email already exists" for an account no
listing would show.

Uniqueness now applies only where ``is_deleted`` is false, matching the partial
index already used for ``UQ_user_firms_active_primary``. MySQL ignores the
predicate, so ``IdentityService.create_user`` remains the authoritative check.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0045"
down_revision: str | Sequence[str] | None = "20260809_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONSTRAINT = "UQ_users_email"
_NEW_INDEX = "UQ_users_email_active"


def upgrade() -> None:
    """Replace the table-wide email constraint with a live-account one."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # users exists only in the platform schema.
    if not inspector.has_table("users"):
        return
    if bind.dialect.name != "postgresql":
        return

    duplicates = bind.execute(
        sa.text(
            "SELECT count(*) FROM ("
            "  SELECT email FROM users WHERE is_deleted = false"
            "  GROUP BY email HAVING count(*) > 1"
            ") AS d"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"Cannot scope email uniqueness: {duplicates} duplicate live "
            "address(es) exist. Resolve them before upgrading."
        )

    existing = {c["name"] for c in inspector.get_unique_constraints("users")}
    if _OLD_CONSTRAINT in existing:
        op.drop_constraint(_OLD_CONSTRAINT, "users", type_="unique")
    indexes = {i["name"] for i in inspector.get_indexes("users")}
    if _NEW_INDEX not in indexes:
        op.create_index(
            _NEW_INDEX,
            "users",
            ["email"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )


def downgrade() -> None:
    """Restore the table-wide email constraint."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users") or bind.dialect.name != "postgresql":
        return
    indexes = {i["name"] for i in inspector.get_indexes("users")}
    if _NEW_INDEX in indexes:
        op.drop_index(_NEW_INDEX, table_name="users")
    existing = {c["name"] for c in inspector.get_unique_constraints("users")}
    if _OLD_CONSTRAINT not in existing:
        op.create_unique_constraint(_OLD_CONSTRAINT, "users", ["email"])
