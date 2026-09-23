"""Rewrite the GST template's profile-id conditions to the group (D-CMP-19).

``20260809_0049`` moved every seeded rule condition off ``tax_profile_id`` --
one version's UUID, which stops matching the moment a rate change mints a
new version -- onto ``tax_profile_group_code``. The GST template kept writing
ids, so every firm set up after that migration has the fragile shape again.
The template now writes the group; this applies 0049's rewrite once more,
for the rules it wrote in between.

Idempotent: only conditions still keyed on ``tax_profile_id`` whose profile
resolves are touched, and re-running finds none. Firm-owned, so run it
through ``scripts/migrate_all_stores.py``.

Revision ID: 20260923_0154
Revises: 20260923_0153
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_0154"
down_revision: str | Sequence[str] | None = "20260923_0153"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rewrite profile-id conditions to their version-stable group code."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("tax_rule_conditions") or not inspector.has_table(
        "tax_profiles"
    ):
        return
    bind.execute(
        sa.text(
            """
            UPDATE tax_rule_conditions AS c
            SET field_key = 'tax_profile_group_code',
                value_text = p.group_code
            FROM tax_profiles AS p
            WHERE c.field_key = 'tax_profile_id'
              AND c.is_deleted = false
              AND p.group_code IS NOT NULL
              AND p.id::text = c.value_text
            """
        )
    )


def downgrade() -> None:
    """Nothing to undo: the rewritten conditions match a superset of what they did."""
