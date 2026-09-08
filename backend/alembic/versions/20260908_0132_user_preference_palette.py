"""Store the accent the desktop has been choosing since 2026-08-10.

``20260810_0062`` split appearance into a brightness (``preferred_theme_mode``)
and a contrast flag, and the desktop was changed the same day to send three
fields: those two and ``preferred_palette``. The third was never added here.
``ApiSchema`` forbids an unknown field, so every appearance save answered 422
and stored **nothing** -- not the palette, and not the two fields that were
declared, because they rode in the same refused request. The next sign-in
handed the client this row's untouched defaults, which the client wrote over
its own correct local copy. A theme chosen on Monday was gone on Tuesday, and
the only trace was an unhandled exception in the crash log.

The column is additive. Existing rows default to ``neutral``, then the two
legacy accent values in ``preferred_theme`` are carried across -- "blue" and
"green" were palettes there and stay palettes here -- only where the new
column is still at its default, so a replay cannot overwrite a live choice.

``user_preferences`` is identity data and lives only in the platform schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_0132"
down_revision: str | Sequence[str] | None = "20260906_0131"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_preferences"
_COLUMN = "preferred_palette"


def upgrade() -> None:
    """Add the accent column and carry the legacy accents across."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables exist only in the platform schema.
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(length=16),
                nullable=False,
                server_default="neutral",
            ),
        )
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = preferred_theme "  # noqa: S608
            f"WHERE preferred_theme IN ('blue', 'green') AND {_COLUMN} = 'neutral'"
        )
    )


def downgrade() -> None:
    """Drop the accent column; the legacy value in ``preferred_theme`` remains."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
