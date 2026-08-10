"""Let a user say light, dark, or follow the operating system.

``user_preferences.preferred_theme`` held one value mixing two ideas: an accent
("blue", "green") and a brightness ("light", "dark"). There was no way to say
"follow Windows", and the desktop client defaulted to light, so anyone running
Windows in dark mode was handed a bright white screen on every launch.

Brightness is added as its own column rather than as another value in
``preferred_theme``. Folding "system" into the existing set would leave "dark"
ambiguous -- accent or brightness? -- and would force a data migration over
values users may have chosen deliberately. A separate column is additive and
readable in both directions: an older client ignores it, and a newer client
treats its absence as "system".

Existing rows default to ``system``. That is not overriding anybody's choice:
until now the field could not express one, so a stored "light" recorded the
absence of a preference rather than a preference for light.

``user_preferences`` is identity data and lives only in the platform schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0062"
down_revision: str | Sequence[str] | None = "20260810_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_preferences"


def upgrade() -> None:
    """Add the brightness and contrast preferences."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables exist only in the platform schema.
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "preferred_theme_mode" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "preferred_theme_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            ),
        )
    if "preferred_high_contrast" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "preferred_high_contrast",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    # Carry across the two legacy values that did express a brightness. A row
    # reading "light" is left on "system", because that value was the old
    # hardcoded default and not a decision.
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET preferred_theme_mode = 'dark' "  # noqa: S608
            "WHERE preferred_theme IN ('dark', 'high_contrast')"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET preferred_high_contrast = true "  # noqa: S608
            "WHERE preferred_theme = 'high_contrast'"
        )
    )


def downgrade() -> None:
    """Drop the brightness preference; the accent column is untouched."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "preferred_high_contrast" in columns:
        op.drop_column(_TABLE, "preferred_high_contrast")
    if "preferred_theme_mode" in columns:
        op.drop_column(_TABLE, "preferred_theme_mode")
