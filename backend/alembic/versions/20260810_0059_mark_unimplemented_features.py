"""Mark the catalogue entries nothing implements.

Seven of the twenty-one declared features had no backing code in either the
backend or the desktop client: IMEI, PRESCRIPTION_REQUIRED, RECIPE_MANAGEMENT,
KITCHEN_MANAGEMENT, COMMISSION, SERVICE_CONTRACTS and PROJECT_MANAGEMENT. A
firm could switch any of them on and nothing whatsoever would happen, which is
the same defect as the eleven docstring-only packages removed on 2026-08-09 --
worse here, because a feature catalogue is a promise to a customer.

They stay in the catalogue as roadmap rather than being deleted, so the intent
is not lost. ``is_implemented`` records the fact, and the service refuses to
enable one. It is deliberately not ``is_active``: that is a choice an
administrator makes, and an administrator cannot make a subsystem exist.

Any profile that already had one of these enabled is switched off, because the
row asserted a capability the firm never actually had.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0059"
down_revision: str | Sequence[str] | None = "20260810_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "business_features"
_COLUMN = "is_implemented"

UNIMPLEMENTED = (
    "IMEI",
    "PRESCRIPTION_REQUIRED",
    "RECIPE_MANAGEMENT",
    "KITCHEN_MANAGEMENT",
    "COMMISSION",
    "SERVICE_CONTRACTS",
    "PROJECT_MANAGEMENT",
)


def upgrade() -> None:
    """Add the flag and clear it for the seven unbacked features."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The catalogue is firm-owned: every firm store holds its own copy, and
    # the platform schema has none. Run this against each firm target.
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )

    codes = ", ".join(f"'{code}'" for code in UNIMPLEMENTED)
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = false WHERE code IN ({codes})"  # noqa: S608
        )
    )

    # Switch off any profile that had claimed one of them. The row asserted a
    # capability the firm never had, so leaving it enabled would keep the
    # promise visible while the flag says it cannot be kept.
    if inspector.has_table("profile_features"):
        bind.execute(
            sa.text(
                "UPDATE profile_features SET is_enabled = false "
                f"WHERE feature_id IN (SELECT id FROM {_TABLE} "
                f"WHERE {_COLUMN} = false)"  # noqa: S608
            )
        )


def downgrade() -> None:
    """Drop the flag; the catalogue returns to claiming all twenty-one."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
