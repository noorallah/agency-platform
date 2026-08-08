"""Match tax rules on the tax group rather than one profile version.

Seeded rule conditions compared ``tax_profile_id`` against a specific profile's
UUID. Profiles are versioned: a rate change creates a new row with a new id and
the same ``group_code``. Every rule written against the old id therefore stopped
matching the moment a rate changed — silently, because a rule that does not
match simply does not fire.

INTERSTATE_GST_18 is the clearest case: it swaps local GST for interstate IGST,
so losing it means an interstate sale is taxed as a local one with no error
raised anywhere.

Products were moved off profile ids onto ``group_code`` by fe17621 for exactly
this reason. This applies the same correction to rule conditions.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0049"
down_revision: str | Sequence[str] | None = "20260809_0048"
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

    # Only rewrite where the referenced profile still resolves; anything else is
    # left alone rather than guessed at, and stays visible as a broken condition.
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
    """Return group-code conditions to the currently active profile version.

    The original id cannot be recovered once a rate change has superseded it, so
    this maps back to whichever version is active now. That is lossy, which is
    itself a reason not to store version ids in rules.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("tax_rule_conditions"):
        return
    bind.execute(
        sa.text(
            """
            UPDATE tax_rule_conditions AS c
            SET field_key = 'tax_profile_id',
                value_text = p.id::text
            FROM tax_profiles AS p
            WHERE c.field_key = 'tax_profile_group_code'
              AND c.is_deleted = false
              AND p.group_code = c.value_text
              AND p.firm_id = c.firm_id
              AND p.is_deleted = false
              AND p.status = 'ACTIVE'
            """
        )
    )
