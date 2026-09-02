"""Commission is implemented, so stop refusing to switch it on.

`20260810_0059` cleared `is_implemented` for seven catalogue entries that had
no backing code in either application. That was true of `COMMISSION` when it
was written and stopped being true on 2026-08-23, when `app/commission` shipped
with effective-dated rates, a collection-based report, seeded permissions and a
desktop screen. The flag outlived the fact, so an administrator was refused a
feature the platform had.

`is_implemented` is a statement about the codebase, which is why this is a
migration and not a decision: nothing here says a firm *should* have commission,
only that it may now be switched on.

**No profile claim is restored.** `20260810_0059` withdrew the ones that
advertised the seven, and which profiles ought to sell on commission is a
product decision an administrator makes on the business-profile screen, not one
a migration should make on their behalf.

The catalogue is firm-owned, so this runs against every firm store and the
platform schema returns early.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0107"
down_revision: str | Sequence[str] | None = "20260902_0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "business_features"
_CODE = "COMMISSION"


def upgrade() -> None:
    """Record that commission now has code behind it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: every firm store holds its own catalogue and the platform
    # schema holds none.
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "is_implemented" not in columns:
        return
    # Only the rows still asserting the old fact, so a replay cannot overwrite
    # a later decision about this row.
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_implemented = true "  # noqa: S608
            "WHERE code = :code AND is_implemented = false"
        ),
        {"code": _CODE},
    )


def downgrade() -> None:
    """Mark it unimplemented again.

    Reversible, unlike the permission seeds: this flag grants nothing on its
    own, so restoring it strips no administrator's work.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "is_implemented" not in columns:
        return
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_implemented = false "  # noqa: S608
            "WHERE code = :code"
        ),
        {"code": _CODE},
    )
