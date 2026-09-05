"""How far a platform administrator's designation reaches.

The platform has had exactly one kind of administrator, who passes every
permission check by short-circuit and every firm-membership check by exemption.
That conflates two jobs a real deployment separates: running the platform --
creating firms, creating their people, provisioning storage, setting a firm up
until it works -- and acting inside a firm's books.

`platform_admins.scope` separates them. Every existing row is backfilled to
`ALL_FIRMS`, which is exactly what it has today: this migration changes nobody's
access. Demoting a live administrator without being asked would lock whoever
runs the platform out of it, and the person who would have to fix that is the
one who was demoted.

The column carries **no server default**, the shape `einvoice.mode` uses and for
the same reason: a default is one migration away from silently handing somebody
every firm's books. New rows take the narrow value from the ORM.

`platform_admins` is platform-owned -- `_PLATFORM_TABLES` in
`app/core/tenancy/lifecycle.py` lists it, so provisioning drops it from a firm
store -- and this migration is a no-op wherever it is absent.

Revision ID: 20260905_0128
Revises: 20260903_0127
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260905_0128"
down_revision: str | None = "20260903_0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "platform_admins"
_COLUMN = "scope"


def upgrade() -> None:
    """Add the reach column and grant every existing designation every firm."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    # Firm stores are partly built by `create_all`, so the column can exist
    # even where `alembic_version` reads older.
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=20), nullable=True))
    # Only rows still at their default, so a replay cannot overwrite a
    # deliberate narrowing made after the first run.
    op.execute(
        sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = 'ALL_FIRMS' WHERE {_COLUMN} IS NULL")
    )
    op.alter_column(_TABLE, _COLUMN, existing_type=sa.String(length=20), nullable=False)


def downgrade() -> None:
    """Drop the reach column, returning every designation to one kind."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.drop_column(_TABLE, _COLUMN)
