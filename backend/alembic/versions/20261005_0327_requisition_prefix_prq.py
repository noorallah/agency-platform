"""Purchase requisitions are numbered ``PRQ``, not ``PR`` (D-BUY-46).

A requisition's default numbering rule carried the purchase return's prefix,
so the two documents were numbered alike: on TEST01 four numbers belonged to
one of each, and a journal or an order's reference quoting
``PR-2026-2027-000017`` could mean either.

``PurchaseRequisitionService`` now creates the rule with ``PRQ``. A rule is
created on a firm's first requisition, so every store that has raised one
already holds a rule saying ``PR``; this moves those. **Only a rule still at
the default**: its own code, and a prefix of exactly ``PR``. A firm that chose
another prefix keeps it. Numbers already issued stay as issued -- nothing
rewrites a requisition -- and the sequence carries on under the new prefix.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a second run
finds no rule at ``PR``.

Revision ID: 20261005_0327
Revises: 20261005_0332
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0327"
down_revision: str | Sequence[str] | None = "20261005_0332"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_numbering_rules"
_RULE = "PURCHASE_REQUISITION_DEFAULT"


def _move(old: str, new: str) -> None:
    """Move the requisition rule's prefix where the store keeps such rules."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET prefix = :new "  # noqa: S608
            "WHERE code = :rule AND prefix = :old"
        ),
        {"new": new, "old": old, "rule": _RULE},
    )


def upgrade() -> None:
    """Give the requisition's default rule a prefix of its own."""
    _move("PR", "PRQ")


def downgrade() -> None:
    """Put the shared prefix back on a rule still at the new default."""
    _move("PRQ", "PR")
