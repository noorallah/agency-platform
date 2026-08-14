"""Stop demanding an IMEI from every product in every firm.

`20260801_0011` seeded four product attributes with ``mandatory = True`` and no
category or profile scope: EXPIRY_DATE, BATCH_NUMBER, MANUFACTURER and IMEI.
An unscoped mandatory attribute applies to **every product of every firm**, so
a pharmacy could not save a product without an IMEI and an electronics
distributor could not save one without an expiry date. `AttributeService`
refuses the write, so this blocks product creation outright wherever that seed
is present -- which is every database built from migrations. It surfaced when
the sample-data reset started working and the demo seeder met the catalogue as
migrated rather than as some older database had left it.

IMEI is one of the seven features `20260810_0059` marks ``is_implemented =
false``: making a roadmap attribute compulsory for every product is the clearest
case, but none of the four is right. An expiry date belongs to pharmacy and
food, a batch number to whatever is traced, a manufacturer to whoever records
one -- all of which the platform already expresses properly through
``category_attribute_rules``, scoped to a business profile and a category. That
mechanism stays; only the blanket flag goes.

This clears the flag rather than deleting the definitions: a firm that has been
filling one of them in keeps its values, and the scoped rules keep working.

``attribute_definitions`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_0087"
down_revision: str | Sequence[str] | None = "20260814_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "attribute_definitions"

#: The four `20260801_0011` marked mandatory with no scope at all.
_UNSCOPED = ("EXPIRY_DATE", "BATCH_NUMBER", "MANUFACTURER", "IMEI")


def _has_table() -> bool:
    """Return whether this store has the table, asked for now."""
    return sa.inspect(op.get_bind()).has_table(_TABLE)


def upgrade() -> None:
    """Clear the blanket mandatory flag on the four unscoped attributes."""
    if not _has_table():
        return
    op.get_bind().execute(
        sa.text(
            "UPDATE attribute_definitions SET mandatory = false "
            "WHERE code IN :codes "
            # Only the ones still unscoped: a firm that has since narrowed one
            # to a category or a profile meant it, and that is not this bug.
            "AND applicable_category IS NULL "
            "AND applicable_business_profile_id IS NULL"
        ).bindparams(sa.bindparam("codes", value=_UNSCOPED, expanding=True))
    )


def downgrade() -> None:
    """Put the blanket flag back, which is what the old seed did."""
    if not _has_table():
        return
    op.get_bind().execute(
        sa.text(
            "UPDATE attribute_definitions SET mandatory = true "
            "WHERE code IN :codes "
            "AND applicable_category IS NULL "
            "AND applicable_business_profile_id IS NULL"
        ).bindparams(sa.bindparam("codes", value=_UNSCOPED, expanding=True))
    )
